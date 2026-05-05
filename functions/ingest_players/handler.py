from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from shared.keys import player_global_pk, player_sk, roster_pk, roster_sk
from shared.log import get_logger
from shared.mlb_client import (
    MLBAPIError,
    fetch_people_bulk,
    fetch_roster,
    fetch_teams,
)

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
ROSTER_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
PEOPLE_BULK_BATCH_SIZE = 50
INTER_CALL_SLEEP_SECONDS = 0.1
ALLOWED_MODES = frozenset({"full", "roster_only"})

CLOUDWATCH_NAMESPACE = "DiamondIQ/Players"
DEFAULT_FUNCTION_NAME = "diamond-iq-ingest-players"


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _resolve_season() -> int:
    return datetime.now(UTC).year


def _ttl_now() -> int:
    return int(time.time()) + ROSTER_TTL_SECONDS


def _safe_get(d: dict[str, Any] | None, *keys: str) -> Any:
    """Defensive nested .get — returns None for any missing/non-dict step."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _player_metadata_item(person: dict[str, Any]) -> dict[str, Any]:
    """Project a /people response entry into the PLAYER#GLOBAL row shape."""
    person_id = person.get("id")
    return {
        "PK": player_global_pk(),
        "SK": player_sk(int(person_id)) if person_id is not None else "",
        "person_id": person_id,
        "full_name": person.get("fullName"),
        "primary_number": person.get("primaryNumber"),  # may be absent on some players
        "current_age": person.get("currentAge"),
        "height": person.get("height"),
        "weight": person.get("weight"),
        "bat_side": _safe_get(person, "batSide", "code"),
        "pitch_hand": _safe_get(person, "pitchHand", "code"),
        "primary_position_abbr": _safe_get(person, "primaryPosition", "abbreviation"),
    }


def _roster_item(season: int, team_id: int, roster_entry: dict[str, Any]) -> dict[str, Any]:
    """Project a /teams/{id}/roster entry into a ROSTER row.

    The roster row carries the team-specific data (jerseyNumber, position
    on this club). Player metadata that's stable across teams lives in
    the PLAYER#GLOBAL row.
    """
    person_id = _safe_get(roster_entry, "person", "id")
    return {
        "PK": roster_pk(season, team_id),
        "SK": roster_sk(int(person_id)) if person_id is not None else "",
        "season": season,
        "team_id": team_id,
        "person_id": person_id,
        "full_name": _safe_get(roster_entry, "person", "fullName"),
        "jersey_number": roster_entry.get("jerseyNumber"),
        "position_abbr": _safe_get(roster_entry, "position", "abbreviation"),
        "status_code": _safe_get(roster_entry, "status", "code"),
        "ttl": _ttl_now(),
    }


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    players_ingested: int,
    rosters_ingested: int,
    teams_failed: int,
    players_failed: int,
) -> None:
    dimensions = [{"Name": "LambdaFunction", "Value": function_name}]
    cw_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                "MetricName": "PlayersIngestedCount",
                "Value": players_ingested,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "RostersIngestedCount",
                "Value": rosters_ingested,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "TeamsFailedCount",
                "Value": teams_failed,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "PlayersFailedCount",
                "Value": players_failed,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
        ],
    )


def _safe_emit_metrics(
    cw_client: Any | None,
    function_name: str,
    summary: dict[str, Any],
    log_ctx: dict[str, Any],
) -> None:
    if cw_client is None:
        return
    try:
        _emit_metrics(
            cw_client,
            function_name,
            players_ingested=int(summary.get("player_metadata_written", 0)),
            rosters_ingested=int(summary.get("roster_entries_written", 0)),
            teams_failed=int(summary.get("teams_failed", 0)),
            players_failed=int(summary.get("players_failed", 0)),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    table_name: str | None = None,
    cloudwatch_client: Any | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    request_id = getattr(context, "aws_request_id", None) if context else None
    function_name = (
        getattr(context, "function_name", None) if context else None
    ) or DEFAULT_FUNCTION_NAME

    mode = (event or {}).get("mode") or "full"
    if mode not in ALLOWED_MODES:
        logger.error(
            "Unknown mode; rejecting",
            extra={"request_id": request_id, "mode": mode},
        )
        return {"ok": False, "reason": "unknown_mode", "mode": mode}

    season = _resolve_season()
    log_ctx: dict[str, Any] = {
        "request_id": request_id,
        "season": season,
        "mode": mode,
    }

    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    api_calls = 0
    teams_failed = 0
    players_failed = 0
    roster_entries_written = 0
    player_metadata_written = 0
    person_ids_seen: set[int] = set()

    # ── Step 1: teams ──────────────────────────────────────────────
    try:
        teams = fetch_teams(season)
        api_calls += 1
    except MLBAPIError as err:
        logger.error(
            "Failed to fetch teams; aborting run",
            extra={**log_ctx, "error": str(err)},
        )
        summary = {
            "ok": False,
            "reason": "teams_fetch_failed",
            "season": season,
            "mode": mode,
            "teams_fetched": 0,
            "roster_entries_written": 0,
            "player_metadata_written": 0,
            "teams_failed": 0,
            "players_failed": 0,
            "api_calls_made": api_calls,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    # ── Step 2: per-team roster fetch (with per-team isolation) ────
    for team in teams:
        team_id = team.get("id")
        if not isinstance(team_id, int):
            continue
        try:
            roster = fetch_roster(team_id, season)
            api_calls += 1
        except Exception as err:  # noqa: BLE001 - per-team isolation
            teams_failed += 1
            logger.warning(
                "Roster fetch failed; continuing",
                extra={**log_ctx, "team_id": team_id, "error": str(err)},
            )
            time.sleep(INTER_CALL_SLEEP_SECONDS)
            continue
        # Write each roster row.
        for entry in roster:
            item = _roster_item(season, team_id, entry)
            if not item["SK"]:
                continue  # missing person.id; skip
            try:
                table.put_item(Item=item)
                roster_entries_written += 1
                pid = item["person_id"]
                if isinstance(pid, int):
                    person_ids_seen.add(pid)
            except Exception as err:  # noqa: BLE001 - per-row isolation
                logger.warning(
                    "Roster put_item failed; continuing",
                    extra={
                        **log_ctx,
                        "team_id": team_id,
                        "person_id": item.get("person_id"),
                        "error": str(err),
                    },
                )
        time.sleep(INTER_CALL_SLEEP_SECONDS)

    # ── Step 3: bulk player metadata (skipped in roster_only mode) ──
    if mode == "full" and person_ids_seen:
        person_ids_list = sorted(person_ids_seen)
        for chunk_start in range(0, len(person_ids_list), PEOPLE_BULK_BATCH_SIZE):
            chunk = person_ids_list[chunk_start : chunk_start + PEOPLE_BULK_BATCH_SIZE]
            try:
                people = fetch_people_bulk(chunk)
                api_calls += 1
            except Exception as err:  # noqa: BLE001 - per-batch isolation
                players_failed += len(chunk)
                logger.warning(
                    "Bulk metadata fetch failed; counting batch as players_failed",
                    extra={**log_ctx, "batch_size": len(chunk), "error": str(err)},
                )
                time.sleep(INTER_CALL_SLEEP_SECONDS)
                continue
            returned_ids = {p.get("id") for p in people if p.get("id") is not None}
            requested_ids = set(chunk)
            missing = requested_ids - returned_ids
            if missing:
                logger.info(
                    "Bulk metadata batch silently dropped some IDs",
                    extra={
                        **log_ctx,
                        "missing_count": len(missing),
                        "missing_sample": sorted(missing)[:5],
                    },
                )
            for person in people:
                item = _player_metadata_item(person)
                if not item["SK"]:
                    continue
                try:
                    table.put_item(Item=item)
                    player_metadata_written += 1
                except Exception as err:  # noqa: BLE001
                    players_failed += 1
                    logger.warning(
                        "Player metadata put_item failed; continuing",
                        extra={**log_ctx, "person_id": item.get("person_id"), "error": str(err)},
                    )
            time.sleep(INTER_CALL_SLEEP_SECONDS)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary: dict[str, Any] = {
        "ok": teams_failed == 0,
        "season": season,
        "mode": mode,
        "teams_fetched": len(teams),
        "roster_entries_written": roster_entries_written,
        "player_metadata_written": player_metadata_written,
        "teams_failed": teams_failed,
        "players_failed": players_failed,
        "api_calls_made": api_calls,
        "elapsed_ms": elapsed_ms,
    }
    logger.info("Player ingest complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
