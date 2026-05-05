"""EventBridge-triggered Lambda that ingests qualifying MLB games into DynamoDB.

Writes Live, Final, and Preview games (Postponed and other states excluded).
Designed to be self-throttling and idempotent:
  - If neither today's nor yesterday's UTC slate has any qualifying games,
    exit immediately with no DynamoDB writes.
  - Per-game write failures are caught and counted, not raised.
  - If one MLB API date query fails, the other date's results are still
    processed (partial success). Only when BOTH fail do we return ok=False
    so EventBridge / Lambda's retry doesn't hammer a transient outage.

Two-date query rationale: MLB groups games by *local* date but our handler
runs in Lambda which is UTC. A late-Pacific start at 22:30 PT lives under
local date X but its `gameDate` is X+1 in UTC, and right after UTC midnight
the API's "today" is the next day's slate. Querying both today and yesterday
UTC covers the full window of in-progress games at any wall-clock time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from shared.dynamodb import put_game
from shared.log import get_logger
from shared.mlb_client import MLBAPIError, fetch_todays_schedule
from shared.models import normalize_game

logger = get_logger(__name__)


_QUALIFYING_STATUSES: frozenset[str] = frozenset({"Live", "Final", "Preview"})


def _failure_summary(dates_queried: list[str], reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "dates_queried": dates_queried,
        "total_games_in_schedule": 0,
        "live_games_processed": 0,
        "final_games_processed": 0,
        "preview_games_processed": 0,
        "games_written": 0,
        "games_failed": 0,
    }


def _extract_games(payload: dict[str, Any]) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for d in payload.get("dates") or []:
        games.extend(d.get("games") or [])
    return games


def _fetch_for_date(
    target: date, log_ctx: dict[str, Any]
) -> tuple[list[dict[str, Any]], MLBAPIError | None]:
    """Fetch one date's schedule. Returns (games, None) on success, ([], error) on failure."""
    try:
        payload = fetch_todays_schedule(today=target)
        return _extract_games(payload), None
    except MLBAPIError as e:
        logger.error(
            "MLB API call failed for one date; continuing with other dates",
            extra={
                **log_ctx,
                "failed_date": target.isoformat(),
                "error": str(e),
                "status": getattr(e, "status", None),
            },
        )
        return [], e


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", None) if context else None
    today_utc = datetime.now(UTC).date()
    yesterday_utc = today_utc - timedelta(days=1)
    dates_queried = [yesterday_utc.isoformat(), today_utc.isoformat()]
    log_ctx = {"request_id": request_id, "dates_queried": dates_queried}

    yesterday_games, yesterday_err = _fetch_for_date(yesterday_utc, log_ctx)
    today_games, today_err = _fetch_for_date(today_utc, log_ctx)

    if yesterday_err and today_err:
        return _failure_summary(dates_queried, "mlb_api_error")

    games_raw = yesterday_games + today_games
    total_games = len(games_raw)

    qualifying_raw = [
        g
        for g in games_raw
        if (g.get("status") or {}).get("abstractGameState") in _QUALIFYING_STATUSES
    ]

    # Dedup by gamePk keeping the LAST occurrence — yesterday's results come
    # first, today's second, so today's fresher record wins over a stale
    # cross-date duplicate (e.g., a game whose Live record from yesterday's
    # query is now Final under today's query).
    by_pk: dict[int, dict[str, Any]] = {}
    for raw in qualifying_raw:
        pk = raw.get("gamePk")
        if isinstance(pk, int):
            by_pk[pk] = raw
    deduped = list(by_pk.values())

    live_count = sum(
        1 for g in deduped if (g.get("status") or {}).get("abstractGameState") == "Live"
    )
    final_count = sum(
        1 for g in deduped if (g.get("status") or {}).get("abstractGameState") == "Final"
    )
    preview_count = sum(
        1 for g in deduped if (g.get("status") or {}).get("abstractGameState") == "Preview"
    )

    # Self-throttle: nothing qualifying across either date, no DynamoDB writes.
    if not deduped:
        logger.info(
            "No qualifying games across queried dates; skipping write",
            extra={**log_ctx, "total_games_in_schedule": total_games},
        )
        return {
            "ok": True,
            "dates_queried": dates_queried,
            "total_games_in_schedule": total_games,
            "live_games_processed": 0,
            "final_games_processed": 0,
            "preview_games_processed": 0,
            "games_written": 0,
            "games_failed": 0,
        }

    written = 0
    failed = 0
    for raw in deduped:
        game_pk = raw.get("gamePk")
        try:
            game = normalize_game(raw)
            put_game(game)
            written += 1
        except Exception as e:  # noqa: BLE001 - per-game isolation on purpose
            failed += 1
            logger.error(
                "Failed to write game",
                extra={**log_ctx, "game_pk": game_pk, "error": str(e)},
            )

    summary = {
        "ok": True,
        "dates_queried": dates_queried,
        "total_games_in_schedule": total_games,
        "live_games_processed": live_count,
        "final_games_processed": final_count,
        "preview_games_processed": preview_count,
        "games_written": written,
        "games_failed": failed,
    }
    logger.info("Ingest run complete", extra={**log_ctx, **summary})
    return summary
