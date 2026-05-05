"""API Gateway HTTP API Lambda — serves /scoreboard/today and /games/{gameId}.

Reads from DynamoDB only; never calls the MLB API. Returns structured JSON
with permissive-for-dev CORS headers. Unexpected exceptions are logged with
full traceback to CloudWatch but never leaked in the response body.
"""

from __future__ import annotations

import json
import re
import traceback
from datetime import UTC, datetime
from typing import Any

from shared.dynamodb import get_game, get_todays_content, list_todays_games
from shared.log import get_logger
from shared.models import Game, content_item_to_api_response, game_to_api_response

logger = get_logger(__name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": "http://localhost:5173",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}


def build_response(
    status_code: int,
    body: dict[str, Any],
    additional_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", **CORS_HEADERS}
    if additional_headers:
        headers.update(additional_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }


def error_response(status_code: int, error_code: str, message: str) -> dict[str, Any]:
    return build_response(status_code, {"error": {"code": error_code, "message": message}})


def _today_utc_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def _valid_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _query_params(event: dict[str, Any]) -> dict[str, str]:
    return event.get("queryStringParameters") or {}


def _path_params(event: dict[str, Any]) -> dict[str, str]:
    return event.get("pathParameters") or {}


def handle_root() -> dict[str, Any]:
    return build_response(
        200,
        {
            "service": "Diamond IQ API",
            "version": "1.0",
            "endpoints": {
                "scoreboard": "/scoreboard/today",
                "scoreboard_by_date": "/scoreboard/today?date=YYYY-MM-DD",
                "game_detail": "/games/{gameId}?date=YYYY-MM-DD",
                "content_today": "/content/today",
                "content_by_date": "/content/today?date=YYYY-MM-DD",
            },
            "documentation": "https://github.com/dram64/diamond-iq",
            "live_demo": True,
        },
    )


def handle_content_today(event: dict[str, Any]) -> dict[str, Any]:
    qs = _query_params(event)
    date_str = qs.get("date") or _today_utc_iso()

    if not _valid_date(date_str):
        return error_response(
            400,
            "invalid_date",
            f"date query parameter must be YYYY-MM-DD, got {date_str!r}",
        )

    content = get_todays_content(date_str)
    return build_response(
        200,
        {
            "date": date_str,
            "recap": [content_item_to_api_response(it) for it in content["recap"]],
            "previews": [content_item_to_api_response(it) for it in content["previews"]],
            "featured": [content_item_to_api_response(it) for it in content["featured"]],
        },
        additional_headers={"Cache-Control": "max-age=300"},
    )


def handle_scoreboard_today(event: dict[str, Any]) -> dict[str, Any]:
    qs = _query_params(event)
    date_str = qs.get("date") or _today_utc_iso()

    if not _valid_date(date_str):
        return error_response(
            400,
            "invalid_date",
            f"date query parameter must be YYYY-MM-DD, got {date_str!r}",
        )

    games: list[Game] = list_todays_games(date_str)
    return build_response(
        200,
        {
            "date": date_str,
            "count": len(games),
            "games": [game_to_api_response(g) for g in games],
        },
    )


def handle_get_game(event: dict[str, Any]) -> dict[str, Any]:
    path = _path_params(event)
    raw_game_id = path.get("gameId")
    if not raw_game_id:
        return error_response(400, "missing_game_id", "gameId path parameter is required")

    try:
        game_pk = int(raw_game_id)
    except (TypeError, ValueError):
        return error_response(
            400, "invalid_game_id", f"gameId must be an integer, got {raw_game_id!r}"
        )

    qs = _query_params(event)
    date_str = qs.get("date")
    if not date_str:
        return error_response(
            400,
            "missing_date",
            "date query parameter is required (YYYY-MM-DD) until the game-pk GSI ships",
        )
    if not _valid_date(date_str):
        return error_response(
            400, "invalid_date", f"date query parameter must be YYYY-MM-DD, got {date_str!r}"
        )

    game = get_game(game_pk, date_str)
    if game is None:
        return error_response(
            404,
            "game_not_found",
            f"no game with game_pk={game_pk} on date {date_str}",
        )
    return build_response(200, {"game": game_to_api_response(game)})


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", None) if context else None
    route_key = event.get("routeKey", "")
    log_ctx = {"request_id": request_id, "route_key": route_key}

    try:
        if route_key == "GET /":
            response = handle_root()
        elif route_key == "GET /scoreboard/today":
            response = handle_scoreboard_today(event)
        elif route_key == "GET /games/{gameId}":
            response = handle_get_game(event)
        elif route_key == "GET /content/today":
            response = handle_content_today(event)
        else:
            response = error_response(404, "unknown_route", f"no handler for {route_key!r}")

        logger.info(
            "api request handled",
            extra={**log_ctx, "status_code": response["statusCode"]},
        )
        return response
    except Exception as e:  # noqa: BLE001 - last-resort safety net
        logger.error(
            "unhandled exception in api_scoreboard",
            extra={
                **log_ctx,
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )
        return error_response(500, "internal_error", "internal server error")
