from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3
from shared.keys import statcast_pk, statcast_sk
from shared.log import get_logger
from shared.savant_client import (
    SavantAPIError,
    _normalize_player_id,
    fetch_bat_tracking,
    fetch_batted_ball,
    fetch_custom_batter,
    fetch_custom_pitcher,
    fetch_statcast_batter,
)

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
CLOUDWATCH_NAMESPACE = "DiamondIQ/Statcast"
DEFAULT_FUNCTION_NAME = "diamond-iq-ingest-statcast"


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


# ── Field projection helpers ───────────────────────────────────────────


def _str_or_none(row: dict[str, str], key: str) -> str | None:
    """Return the string value if present and non-empty, else None.

    Statcast CSVs store rate stats as strings (.290) and numeric stats as
    plain digits. We preserve the upstream formatting verbatim so the
    frontend can render it without re-parsing."""
    val = row.get(key)
    if val is None or val == "":
        return None
    return val


def _num_or_none(row: dict[str, str], key: str) -> Decimal | None:
    """Parse a numeric column to Decimal; return None on missing/empty/non-numeric.

    DynamoDB rejects native Python floats — Decimal is the supported numeric
    type. We funnel every Statcast numeric through Decimal at the parse
    boundary so the put_item call has nothing to convert."""
    val = row.get(key)
    if val is None or val == "":
        return None
    try:
        # Decimal(str) avoids float-binary representation noise
        # (94.7 → Decimal('94.7') rather than 94.7000000000000028...)
        return Decimal(val.strip())
    except (TypeError, ValueError, ArithmeticError):
        return None


def _hitter_block_from_custom(row: dict[str, str]) -> dict[str, Any]:
    return {
        "xba": _str_or_none(row, "xba"),
        "xslg": _str_or_none(row, "xslg"),
        "xwoba": _str_or_none(row, "xwoba"),
        "sweet_spot_percent": _num_or_none(row, "sweet_spot_percent"),
        "sprint_speed": _num_or_none(row, "sprint_speed"),
    }


def _hitter_block_from_statcast(row: dict[str, str]) -> dict[str, Any]:
    return {
        "avg_hit_speed": _num_or_none(row, "avg_hit_speed"),
        "max_hit_speed": _num_or_none(row, "max_hit_speed"),
        "ev95_percent": _num_or_none(row, "ev95percent"),  # hard-hit %
        "barrel_percent": _num_or_none(row, "brl_percent"),
        "barrel_per_pa_percent": _num_or_none(row, "brl_pa"),
        "max_distance": _num_or_none(row, "max_distance"),
        "avg_distance": _num_or_none(row, "avg_distance"),
        "avg_hr_distance": _num_or_none(row, "avg_hr_distance"),
    }


def _pitcher_block_from_custom(row: dict[str, str]) -> dict[str, Any]:
    return {
        "xera": _num_or_none(row, "xera"),
        "xba_against": _str_or_none(row, "xba"),
        "whiff_percent": _num_or_none(row, "whiff_percent"),
        "chase_whiff_percent": _num_or_none(row, "oz_swing_miss_percent"),
        "fastball_avg_speed": _num_or_none(row, "fastball_avg_speed"),
        "fastball_avg_spin": _num_or_none(row, "fastball_avg_spin"),
    }


def _bat_tracking_block(row: dict[str, str]) -> dict[str, Any]:
    return {
        "avg_bat_speed": _num_or_none(row, "avg_bat_speed"),
        "swing_length": _num_or_none(row, "swing_length"),
        "hard_swing_rate": _num_or_none(row, "hard_swing_rate"),
        "squared_up_per_swing": _num_or_none(row, "squared_up_per_swing"),
        "blast_per_swing": _num_or_none(row, "blast_per_swing"),
    }


def _batted_ball_block(row: dict[str, str]) -> dict[str, Any]:
    return {
        "pull_rate": _num_or_none(row, "pull_rate"),
        "straight_rate": _num_or_none(row, "straight_rate"),
        "oppo_rate": _num_or_none(row, "oppo_rate"),
        "gb_rate": _num_or_none(row, "gb_rate"),
        "fb_rate": _num_or_none(row, "fb_rate"),
        "ld_rate": _num_or_none(row, "ld_rate"),
    }


def _safe_fetch(label: str, fn: Any, log_ctx: dict[str, Any]) -> tuple[list[dict[str, str]], bool]:
    """Run a fetch. Returns (rows, errored). `errored` distinguishes a real
    SavantAPIError after retries from a successful empty response — the
    pitcher-only CSV legitimately returns no rows when our test fixture
    only covers hitters; that shouldn't flip ok=False."""
    try:
        rows = fn()
        logger.info(
            "Statcast CSV fetched",
            extra={**log_ctx, "endpoint": label, "rows": len(rows)},
        )
        return rows, False
    except SavantAPIError as err:
        logger.warning(
            "Statcast CSV fetch failed; continuing without this dataset",
            extra={**log_ctx, "endpoint": label, "error": str(err)},
        )
        return [], True


def _index_by_player_id(rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    for row in rows:
        pid = _normalize_player_id(row)
        if pid is None:
            continue
        out[pid] = row
    return out


def _merge_player_rows(
    season: int,
    custom_batter_rows: list[dict[str, str]],
    statcast_batter_rows: list[dict[str, str]],
    custom_pitcher_rows: list[dict[str, str]],
    bat_tracking_rows: list[dict[str, str]],
    batted_ball_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Merge five CSV result-sets into one item per distinct player_id.

    Hitters typically appear in 4 of the 5 CSVs (custom_batter,
    statcast_batter, bat_tracking, batted_ball). Pitchers appear only in
    custom_pitcher. A two-way player would appear in all five.
    """
    custom_batter = _index_by_player_id(custom_batter_rows)
    statcast_batter = _index_by_player_id(statcast_batter_rows)
    custom_pitcher = _index_by_player_id(custom_pitcher_rows)
    bat_tracking = _index_by_player_id(bat_tracking_rows)
    batted_ball = _index_by_player_id(batted_ball_rows)

    all_ids = (
        set(custom_batter)
        | set(statcast_batter)
        | set(custom_pitcher)
        | set(bat_tracking)
        | set(batted_ball)
    )

    items: list[dict[str, Any]] = []
    for pid in all_ids:
        cb = custom_batter.get(pid)
        sb = statcast_batter.get(pid)
        cp = custom_pitcher.get(pid)
        bt = bat_tracking.get(pid)
        bb = batted_ball.get(pid)

        # Display name: prefer the custom-batter row's "last_name, first_name",
        # fall back to whichever CSV has it. bat-tracking and batted-ball use
        # a "name" column; custom uses "last_name, first_name".
        display_name = (
            (cb or {}).get("last_name, first_name")
            or (sb or {}).get("last_name, first_name")
            or (cp or {}).get("last_name, first_name")
            or (bt or {}).get("name")
            or (bb or {}).get("name")
        )

        item: dict[str, Any] = {
            "PK": statcast_pk(season),
            "SK": statcast_sk(pid),
            "person_id": pid,
            "season": season,
            "display_name": display_name,
            "hitting": None,
            "pitching": None,
            "bat_tracking": None,
            "batted_ball": None,
        }

        # Hitter side: combine custom_batter + statcast_batter projections.
        if cb is not None or sb is not None:
            hitting = {}
            if cb is not None:
                hitting.update(_hitter_block_from_custom(cb))
            if sb is not None:
                hitting.update(_hitter_block_from_statcast(sb))
            item["hitting"] = hitting

        if cp is not None:
            item["pitching"] = _pitcher_block_from_custom(cp)
        if bt is not None:
            item["bat_tracking"] = _bat_tracking_block(bt)
        if bb is not None:
            item["batted_ball"] = _batted_ball_block(bb)

        items.append(item)

    return items


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    players_written: int,
    csvs_succeeded: int,
    csvs_failed: int,
    elapsed_ms: int,
) -> None:
    dims = [{"Name": "LambdaFunction", "Value": function_name}]
    cw_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                "MetricName": "PlayersWritten",
                "Value": players_written,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "CSVsSucceeded",
                "Value": csvs_succeeded,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {"MetricName": "CSVsFailed", "Value": csvs_failed, "Unit": "Count", "Dimensions": dims},
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
            players_written=int(summary.get("players_written", 0)),
            csvs_succeeded=int(summary.get("csvs_succeeded", 0)),
            csvs_failed=int(summary.get("csvs_failed", 0)),
            elapsed_ms=int(summary.get("elapsed_ms", 0)),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],  # noqa: ARG001 - reserved for cron payloads
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

    fetches = [
        ("custom_batter", lambda: fetch_custom_batter(season)),
        ("statcast_batter", lambda: fetch_statcast_batter(season)),
        ("custom_pitcher", lambda: fetch_custom_pitcher(season)),
        ("bat_tracking", lambda: fetch_bat_tracking(season)),
        ("batted_ball", lambda: fetch_batted_ball(season)),
    ]
    results: dict[str, list[dict[str, str]]] = {}
    csvs_succeeded = 0
    csvs_failed = 0
    for label, fn in fetches:
        rows, errored = _safe_fetch(label, fn, log_ctx)
        results[label] = rows
        if errored:
            csvs_failed += 1
        else:
            csvs_succeeded += 1

    items = _merge_player_rows(
        season,
        results["custom_batter"],
        results["statcast_batter"],
        results["custom_pitcher"],
        results["bat_tracking"],
        results["batted_ball"],
    )

    players_written = 0
    for item in items:
        try:
            table.put_item(Item=item)
            players_written += 1
        except Exception as err:  # noqa: BLE001 - per-player isolation
            logger.warning(
                "Statcast row write failed; continuing",
                extra={**log_ctx, "person_id": item.get("person_id"), "error": str(err)},
            )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary: dict[str, Any] = {
        "ok": csvs_failed == 0 and players_written > 0,
        "season": season,
        "csvs_succeeded": csvs_succeeded,
        "csvs_failed": csvs_failed,
        "players_written": players_written,
        "elapsed_ms": elapsed_ms,
    }
    logger.info("Statcast ingest complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
