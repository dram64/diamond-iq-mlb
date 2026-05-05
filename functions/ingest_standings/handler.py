from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from shared.keys import standings_pk, standings_sk
from shared.log import get_logger
from shared.mlb_client import MLBAPIError, fetch_standings

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
CLOUDWATCH_NAMESPACE = "DiamondIQ/Standings"
DEFAULT_FUNCTION_NAME = "diamond-iq-ingest-standings"


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _safe_get(d: dict[str, Any] | None, *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _split_record(team_record: dict[str, Any], split_type: str) -> str | None:
    """Find a split record (home/away/lastTen) and return "W-L"."""
    splits = _safe_get(team_record, "records", "splitRecords") or []
    for s in splits:
        if s.get("type") == split_type:
            wins = s.get("wins", 0)
            losses = s.get("losses", 0)
            return f"{wins}-{losses}"
    return None


def _team_item(
    season: int, division: dict[str, Any], league: dict[str, Any], team_record: dict[str, Any]
) -> dict[str, Any] | None:
    """Project one team_record into a STANDINGS row."""
    team_id = _safe_get(team_record, "team", "id")
    if not isinstance(team_id, int):
        return None
    return {
        "PK": standings_pk(season),
        "SK": standings_sk(team_id),
        "season": season,
        "team_id": team_id,
        "team_name": _safe_get(team_record, "team", "name"),
        "division_id": division.get("id"),
        "division_name": division.get("name"),
        "league_id": league.get("id"),
        "league_name": league.get("name"),
        "wins": team_record.get("wins"),
        "losses": team_record.get("losses"),
        "pct": team_record.get("winningPercentage"),
        "games_back": team_record.get("gamesBack"),
        "wild_card_games_back": team_record.get("wildCardGamesBack"),
        "streak_code": _safe_get(team_record, "streak", "streakCode"),
        "last_ten_record": _split_record(team_record, "lastTen"),
        "home_record": _split_record(team_record, "home"),
        "away_record": _split_record(team_record, "away"),
        "run_differential": team_record.get("runDifferential"),
        "runs_scored": team_record.get("runsScored"),
        "runs_allowed": team_record.get("runsAllowed"),
        "division_rank": team_record.get("divisionRank"),
        "league_rank": team_record.get("leagueRank"),
        "games_played": team_record.get("gamesPlayed"),
        # No TTL — standings overwrites in place every day.
    }


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    teams_ingested: int,
    teams_failed: int,
    elapsed_ms: int,
) -> None:
    dims = [{"Name": "LambdaFunction", "Value": function_name}]
    cw_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                "MetricName": "TeamsIngested",
                "Value": teams_ingested,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "TeamsFailed",
                "Value": teams_failed,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "IngestionElapsedMs",
                "Value": elapsed_ms,
                "Unit": "Milliseconds",
                "Dimensions": dims,
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
            teams_ingested=int(summary.get("teams_ingested", 0)),
            teams_failed=int(summary.get("teams_failed", 0)),
            elapsed_ms=int(summary.get("elapsed_ms", 0)),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],  # noqa: ARG001 - reserved for future invocation overrides
    context: Any,
    *,
    table_name: str | None = None,
    cloudwatch_client: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    request_id = getattr(context, "aws_request_id", None) if context else None
    function_name = (
        getattr(context, "function_name", None) if context else None
    ) or DEFAULT_FUNCTION_NAME

    season = _resolve_season(now)
    log_ctx: dict[str, Any] = {"request_id": request_id, "season": season}

    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    try:
        records = fetch_standings(season)
    except MLBAPIError as err:
        logger.error(
            "Failed to fetch standings; aborting",
            extra={**log_ctx, "error": str(err)},
        )
        summary = {
            "ok": False,
            "reason": "standings_fetch_failed",
            "season": season,
            "divisions_seen": 0,
            "teams_ingested": 0,
            "teams_failed": 0,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    if not records:
        logger.error("Standings response empty; aborting", extra=log_ctx)
        summary = {
            "ok": False,
            "reason": "empty_standings",
            "season": season,
            "divisions_seen": 0,
            "teams_ingested": 0,
            "teams_failed": 0,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    teams_ingested = 0
    teams_failed = 0
    for record in records:
        division = record.get("division") or {}
        league = record.get("league") or {}
        for team_record in record.get("teamRecords") or []:
            try:
                item = _team_item(season, division, league, team_record)
                if item is None:
                    teams_failed += 1
                    continue
                table.put_item(Item=item)
                teams_ingested += 1
            except Exception as err:  # noqa: BLE001 - per-team isolation
                teams_failed += 1
                logger.warning(
                    "Team standings put_item failed; continuing",
                    extra={
                        **log_ctx,
                        "team_id": _safe_get(team_record, "team", "id"),
                        "error": str(err),
                    },
                )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary: dict[str, Any] = {
        "ok": teams_failed == 0 and teams_ingested > 0,
        "season": season,
        "divisions_seen": len(records),
        "teams_ingested": teams_ingested,
        "teams_failed": teams_failed,
        "elapsed_ms": elapsed_ms,
    }
    logger.info("Standings ingest complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
