from __future__ import annotations

import os
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from shared.keys import awards_pk, awards_sk, player_global_pk
from shared.log import get_logger
from shared.mlb_client import MLBAPIError, MLBNotFoundError, fetch_player_awards

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
INTER_CALL_SLEEP_SECONDS = 0.05
CLOUDWATCH_NAMESPACE = "DiamondIQ/PlayerAwards"
DEFAULT_FUNCTION_NAME = "diamond-iq-ingest-player-awards"


# Award id-code allowlist. Each entry maps an MLB upstream `id` value (or
# stable substring) to the canonical category we expose in the API. The
# upstream enumeration is open-ended (their database has hundreds of
# minor-league + amateur honors); we hardcode to the MLB-tier subset that
# carries career-narrative weight on the comparison page.
_ALLOWLIST: dict[str, str] = {
    # MVP
    "ALMVP": "mvp",
    "NLMVP": "mvp",
    "MLBMVP": "mvp",
    "ALCSMVP": "lcs_mvp",
    "NLCSMVP": "lcs_mvp",
    "WSMVP": "world_series_mvp",
    # Cy Young
    "ALCY": "cy_young",
    "NLCY": "cy_young",
    "MLBCY": "cy_young",
    # Rookie of the Year
    "ALROY": "rookie_of_the_year",
    "NLROY": "rookie_of_the_year",
    # All-Star (MLBASG = MLB All-Star Game; ALAS / NLAS league-side codes)
    "MLBASG": "all_star",
    "ALAS": "all_star",
    "NLAS": "all_star",
    "ASGMVP": "all_star_mvp",
    # Gold Glove
    "ALGG": "gold_glove",
    "NLGG": "gold_glove",
    "MLBGG": "gold_glove",
    # Silver Slugger
    "ALSS": "silver_slugger",
    "NLSS": "silver_slugger",
    "MLBSS": "silver_slugger",
    # World Series ring (championship roster)
    "WSC": "world_series",
}


# Aggregator key → DynamoDB column-name pair (count + years).
_CATEGORIES = (
    ("all_star", "all_star_count", "all_star_years"),
    ("mvp", "mvp_count", "mvp_years"),
    ("cy_young", "cy_young_count", "cy_young_years"),
    ("rookie_of_the_year", "rookie_of_the_year_count", "rookie_of_the_year_years"),
    ("gold_glove", "gold_glove_count", "gold_glove_years"),
    ("silver_slugger", "silver_slugger_count", "silver_slugger_years"),
    ("world_series", "world_series_count", "world_series_years"),
)


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _classify(award: dict[str, Any]) -> str | None:
    """Return our canonical category for an MLB award, or None to skip."""
    raw_id = award.get("id")
    if not isinstance(raw_id, str):
        return None
    return _ALLOWLIST.get(raw_id)


def _aggregate(awards: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Reduce a player's raw awards list to the per-category summary."""
    buckets: dict[str, list[int]] = {key: [] for key, _, _ in _CATEGORIES}
    total = 0
    for award in awards:
        category = _classify(award)
        if category is None:
            continue
        # Only roll up the categories we surface; the world_series_mvp /
        # lcs_mvp / all_star_mvp categories are recognized but counted only
        # toward total_awards (the prominent display surface uses the seven
        # count fields).
        total += 1
        if category not in buckets:
            continue
        season_raw = award.get("season")
        try:
            season = int(season_raw) if season_raw is not None else None
        except (TypeError, ValueError):
            season = None
        if season is not None:
            buckets[category].append(season)

    out: dict[str, Any] = {"total_awards": total}
    for key, count_field, years_field in _CATEGORIES:
        years = sorted(set(buckets[key]))
        out[count_field] = len(years)
        out[years_field] = years
    return out


def _award_item(person_id: int, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "PK": awards_pk(),
        "SK": awards_sk(person_id),
        "person_id": person_id,
        **summary,
    }


def _iter_player_ids(table: Any) -> list[int]:
    """Page through PLAYER#GLOBAL and yield every person_id."""
    person_ids: list[int] = []
    last_key: dict[str, Any] | None = None
    while True:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(player_global_pk()),
            "ProjectionExpression": "person_id",
        }
        if last_key is not None:
            kwargs["ExclusiveStartKey"] = last_key
        resp = table.query(**kwargs)
        for item in resp.get("Items", []):
            pid = item.get("person_id")
            # DynamoDB returns Decimal for Number attributes; normalize to int.
            if pid is None:
                continue
            try:
                person_ids.append(int(pid))
            except (TypeError, ValueError):
                continue
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return person_ids


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    players_total: int,
    players_ingested: int,
    players_failed: int,
    elapsed_ms: int,
) -> None:
    dims = [{"Name": "LambdaFunction", "Value": function_name}]
    cw_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                "MetricName": "PlayersTotal",
                "Value": players_total,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "PlayersIngested",
                "Value": players_ingested,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "PlayersFailed",
                "Value": players_failed,
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
            players_total=int(summary.get("players_total", 0)),
            players_ingested=int(summary.get("players_ingested", 0)),
            players_failed=int(summary.get("players_failed", 0)),
            elapsed_ms=int(summary.get("elapsed_ms", 0)),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],  # noqa: ARG001 - reserved
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
    when = now or datetime.now(UTC)
    log_ctx: dict[str, Any] = {"request_id": request_id, "ingest_at": when.isoformat()}

    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    try:
        person_ids = _iter_player_ids(table)
    except Exception as err:  # noqa: BLE001 - if we can't list players, abort
        logger.error("Failed to enumerate players", extra={**log_ctx, "error": str(err)})
        summary = {
            "ok": False,
            "reason": "player_list_failed",
            "players_total": 0,
            "players_ingested": 0,
            "players_failed": 0,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    players_ingested = 0
    players_failed = 0
    for person_id in person_ids:
        try:
            awards_raw = fetch_player_awards(person_id)
        except MLBNotFoundError:
            # Player has no awards record on MLB's side — write an empty
            # summary so the API layer can serve a deterministic shape
            # rather than 503.
            awards_raw = []
        except MLBAPIError as err:
            players_failed += 1
            logger.warning(
                "Awards fetch failed; continuing",
                extra={**log_ctx, "person_id": person_id, "error": str(err)},
            )
            time.sleep(INTER_CALL_SLEEP_SECONDS)
            continue

        try:
            summary = _aggregate(awards_raw)
            table.put_item(Item=_award_item(person_id, summary))
            players_ingested += 1
        except Exception as err:  # noqa: BLE001 - per-player isolation
            players_failed += 1
            logger.warning(
                "Awards write failed; continuing",
                extra={**log_ctx, "person_id": person_id, "error": str(err)},
            )
        time.sleep(INTER_CALL_SLEEP_SECONDS)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary_out: dict[str, Any] = {
        "ok": players_failed == 0 and players_ingested > 0,
        "players_total": len(person_ids),
        "players_ingested": players_ingested,
        "players_failed": players_failed,
        "elapsed_ms": elapsed_ms,
    }
    logger.info("Player-awards ingest complete", extra={**log_ctx, **summary_out})
    _safe_emit_metrics(cw_client, function_name, summary_out, log_ctx)
    return summary_out
