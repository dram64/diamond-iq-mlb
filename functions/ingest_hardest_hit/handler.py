from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
from shared.keys import hit_sk, hits_pk
from shared.log import get_logger
from shared.mlb_client import MLBAPIError, fetch_game_feed_live, fetch_schedule_finals

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
HARDEST_HIT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
INTER_CALL_SLEEP_SECONDS = 0.1
TOP_N = 25
EXCLUDED_TRAJECTORIES = frozenset({"bunt_groundball", "bunt_popup"})

CLOUDWATCH_NAMESPACE = "DiamondIQ/HardestHit"
DEFAULT_FUNCTION_NAME = "diamond-iq-ingest-hardest-hit"


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _yesterday_utc(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=1)


def _ttl_now() -> int:
    return int(time.time()) + HARDEST_HIT_TTL_SECONDS


def _safe_get(d: dict[str, Any] | None, *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _to_decimal(value: Any) -> Decimal | None:
    """Parse launch_speed / launch_angle into Decimal; None on missing."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except (ArithmeticError, ValueError):
            return None
    return None


def _extract_hits_from_game(feed_payload: dict[str, Any], game_pk: int) -> list[dict[str, Any]]:
    """Walk allPlays[].playEvents[] and yield one record per batted-ball event."""
    out: list[dict[str, Any]] = []
    plays = _safe_get(feed_payload, "liveData", "plays", "allPlays") or []
    for play in plays:
        play_events = play.get("playEvents") or []
        for event_idx, pe in enumerate(play_events):
            hd = pe.get("hitData") or {}
            speed = _to_decimal(hd.get("launchSpeed"))
            if speed is None or speed <= 0:
                continue
            trajectory = hd.get("trajectory")
            if trajectory in EXCLUDED_TRAJECTORIES:
                continue
            batter = _safe_get(play, "matchup", "batter") or {}
            about = play.get("about") or {}
            result = play.get("result") or {}
            out.append(
                {
                    "_speed_float": float(speed),
                    "_event_idx": event_idx,
                    "game_pk": game_pk,
                    "batter_id": batter.get("id"),
                    "batter_name": batter.get("fullName"),
                    "inning": about.get("inning"),
                    "half_inning": about.get("halfInning"),
                    "result_event": result.get("event"),
                    "result_event_type": result.get("eventType"),
                    "launch_speed": speed,
                    "launch_angle": _to_decimal(hd.get("launchAngle")),
                    "total_distance": _to_decimal(hd.get("totalDistance")),
                    "trajectory": trajectory,
                }
            )
    return out


def _build_item(date_iso: str, hit: dict[str, Any]) -> dict[str, Any]:
    speed_float = float(hit["_speed_float"])
    return {
        "PK": hits_pk(date_iso),
        "SK": hit_sk(speed_float, int(hit["game_pk"]), int(hit["_event_idx"])),
        "game_pk": hit["game_pk"],
        "batter_id": hit.get("batter_id"),
        "batter_name": hit.get("batter_name"),
        "inning": hit.get("inning"),
        "half_inning": hit.get("half_inning"),
        "result_event": hit.get("result_event"),
        "result_event_type": hit.get("result_event_type"),
        "launch_speed": hit["launch_speed"],
        "launch_angle": hit.get("launch_angle"),
        "total_distance": hit.get("total_distance"),
        "trajectory": hit.get("trajectory"),
        "ttl": _ttl_now(),
    }


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    games_processed: int,
    events_parsed: int,
    hits_ingested: int,
    games_failed: int,
    max_launch_speed: float,
) -> None:
    dims = [{"Name": "LambdaFunction", "Value": function_name}]
    md: list[dict[str, Any]] = [
        {
            "MetricName": "GamesProcessed",
            "Value": games_processed,
            "Unit": "Count",
            "Dimensions": dims,
        },
        {"MetricName": "EventsParsed", "Value": events_parsed, "Unit": "Count", "Dimensions": dims},
        {"MetricName": "HitsIngested", "Value": hits_ingested, "Unit": "Count", "Dimensions": dims},
        {"MetricName": "GamesFailed", "Value": games_failed, "Unit": "Count", "Dimensions": dims},
    ]
    if max_launch_speed > 0:
        md.append(
            {
                "MetricName": "MaxLaunchSpeed",
                "Value": max_launch_speed,
                "Unit": "None",
                "Dimensions": dims,
            }
        )
    cw_client.put_metric_data(Namespace=CLOUDWATCH_NAMESPACE, MetricData=md)


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
            games_processed=int(summary.get("games_processed", 0)),
            events_parsed=int(summary.get("events_parsed", 0)),
            hits_ingested=int(summary.get("hits_ingested", 0)),
            games_failed=int(summary.get("games_failed", 0)),
            max_launch_speed=float(summary.get("max_launch_speed", 0) or 0),
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

    yesterday_dt = _yesterday_utc(now)
    date_iso = yesterday_dt.date().isoformat()
    log_ctx: dict[str, Any] = {"request_id": request_id, "date": date_iso}

    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    try:
        finals = fetch_schedule_finals(yesterday_dt.date())
    except MLBAPIError as err:
        logger.error(
            "Failed to fetch schedule; aborting",
            extra={**log_ctx, "error": str(err)},
        )
        summary = {
            "ok": False,
            "reason": "schedule_fetch_failed",
            "date": date_iso,
            "games_total": 0,
            "games_processed": 0,
            "games_failed": 0,
            "events_parsed": 0,
            "hits_ingested": 0,
            "max_launch_speed": 0,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    games_total = len(finals)
    games_processed = 0
    games_failed = 0
    all_hits: list[dict[str, Any]] = []

    for game in finals:
        game_pk = game.get("gamePk")
        if not isinstance(game_pk, int):
            continue
        try:
            feed = fetch_game_feed_live(game_pk)
            hits = _extract_hits_from_game(feed, game_pk)
            all_hits.extend(hits)
            games_processed += 1
        except Exception as err:  # noqa: BLE001 - per-game isolation
            games_failed += 1
            logger.warning(
                "feed/live fetch or parse failed; continuing",
                extra={**log_ctx, "game_pk": game_pk, "error": str(err)},
            )
        time.sleep(INTER_CALL_SLEEP_SECONDS)

    events_parsed = len(all_hits)
    # Sort by launch_speed descending; tiebreak by gamePk + event index for
    # deterministic ordering when two events share an exit velocity.
    all_hits.sort(
        key=lambda h: (-float(h["_speed_float"]), int(h["game_pk"]), int(h["_event_idx"]))
    )
    top_hits = all_hits[:TOP_N]
    max_launch_speed = float(top_hits[0]["_speed_float"]) if top_hits else 0.0

    hits_ingested = 0
    for hit in top_hits:
        try:
            table.put_item(Item=_build_item(date_iso, hit))
            hits_ingested += 1
        except Exception as err:  # noqa: BLE001 - per-row isolation
            logger.warning(
                "Hit put_item failed; continuing",
                extra={
                    **log_ctx,
                    "game_pk": hit.get("game_pk"),
                    "batter_id": hit.get("batter_id"),
                    "error": str(err),
                },
            )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary: dict[str, Any] = {
        "ok": hits_ingested > 0,
        "date": date_iso,
        "games_total": games_total,
        "games_processed": games_processed,
        "games_failed": games_failed,
        "events_parsed": events_parsed,
        "hits_ingested": hits_ingested,
        "max_launch_speed": max_launch_speed,
        "elapsed_ms": elapsed_ms,
    }
    if not top_hits:
        summary["reason"] = "no_qualifying_hits"
    logger.info("Hardest-hit ingest complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
