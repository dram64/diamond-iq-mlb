from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

# Make the function directory importable as a flat package both inside the
# Lambda zip (where everything lives at the zip root) and in pytest (where
# this file is at functions/api_players/handler.py and the api_players/
# package is on pythonpath but its siblings are not). The bootstrap turns
# `from api_responses import X` and `from routes import X` into one resolution
# path that works in both environments.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import boto3  # noqa: E402
from api_responses import build_error_response  # noqa: E402
from routes import (  # noqa: E402
    compare,
    featured_game,
    featured_matchup,
    hardest_hit,
    leaders,
    player,
    roster,
    search,
    standings,
    team_compare,
    team_stats,
)
from shared.log import get_logger  # noqa: E402

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
CLOUDWATCH_NAMESPACE = "DiamondIQ/PlayerAPI"
DEFAULT_FUNCTION_NAME = "diamond-iq-api-players"


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _route_player(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return player.handle(event, table=table)


def _route_compare(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return compare.handle(event, table=table)


def _route_leaders(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return leaders.handle(event, table=table)


def _route_roster(
    event: dict[str, Any],
    *,
    table: Any,
    table_name: str,
    dynamodb_resource: Any | None = None,
    **_: Any,
) -> dict[str, Any]:
    return roster.handle(
        event, table=table, table_name=table_name, dynamodb_resource=dynamodb_resource
    )


def _route_standings(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return standings.handle(event, table=table)


def _route_hardest_hit(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return hardest_hit.handle(event, table=table)


def _route_team_stats(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return team_stats.handle(event, table=table)


def _route_team_compare(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return team_compare.handle(event, table=table)


def _route_search(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return search.handle(event, table=table)


def _route_featured_matchup(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return featured_matchup.handle(event, table=table)


def _route_featured_game(event: dict[str, Any], *, table: Any, **_: Any) -> dict[str, Any]:
    return featured_game.handle(event, table=table)


# Single source of truth for endpoint dispatch. Order matters only for human
# review; API Gateway has already matched the routeKey to a static string.
# the {personId}-parameterized route. API Gateway HTTP API v2 routes
# literal-segment-priority at runtime, so registration order doesn't change
# matching; we keep them next to /compare for human review symmetry.
ROUTES: dict[str, Callable[..., dict[str, Any]]] = {
    "GET /api/players/compare": _route_compare,
    "GET /api/players/search": _route_search,
    "GET /api/players/{personId}": _route_player,
    "GET /api/featured-matchup": _route_featured_matchup,
    "GET /api/games/featured": _route_featured_game,
    "GET /api/leaders/{group}/{stat}": _route_leaders,
    "GET /api/teams/compare": _route_team_compare,
    "GET /api/teams/{teamId}/roster": _route_roster,
    "GET /api/teams/{teamId}/stats": _route_team_stats,
    "GET /api/standings/{season}": _route_standings,
    "GET /api/hardest-hit/{date}": _route_hardest_hit,
}


def _emit_route_metric(
    cw_client: Any | None,
    function_name: str,
    *,
    route_key: str,
    elapsed_ms: int,
    status_code: int,
) -> None:
    if cw_client is None:
        return
    try:
        dims = [
            {"Name": "LambdaFunction", "Value": function_name},
            {"Name": "RouteKey", "Value": route_key},
        ]
        cw_client.put_metric_data(
            Namespace=CLOUDWATCH_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "RequestCount",
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": dims,
                },
                {
                    "MetricName": "ResponseTimeMs",
                    "Value": elapsed_ms,
                    "Unit": "Milliseconds",
                    "Dimensions": dims,
                },
                {
                    "MetricName": "StatusCode",
                    "Value": status_code,
                    "Unit": "None",
                    "Dimensions": dims,
                },
            ],
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={"error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    table_name: str | None = None,
    dynamodb_resource: Any | None = None,
    cloudwatch_client: Any | None = None,
    now: datetime | None = None,  # noqa: ARG001 - reserved for handlers that need it
) -> dict[str, Any]:
    started = time.monotonic()
    request_id = getattr(context, "aws_request_id", None) if context else None
    function_name = (
        getattr(context, "function_name", None) if context else None
    ) or DEFAULT_FUNCTION_NAME

    route_key = (event or {}).get("routeKey") or ""
    handler = ROUTES.get(route_key)
    if handler is None:
        logger.warning(
            "Unmatched routeKey",
            extra={"request_id": request_id, "route_key": route_key},
        )
        return build_error_response(404, "route_not_found", f"No handler for {route_key!r}")

    resolved_table_name = _resolve_table_name(table_name)
    resource = dynamodb_resource or boto3.resource("dynamodb")
    table = resource.Table(resolved_table_name)
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    try:
        response = handler(
            event,
            table=table,
            table_name=resolved_table_name,
            dynamodb_resource=resource,
        )
    except Exception as err:  # noqa: BLE001 - last-resort guard for unexpected errors
        logger.exception(
            "Unhandled exception in route handler",
            extra={"request_id": request_id, "route_key": route_key, "error": str(err)},
        )
        response = build_error_response(500, "internal_error", "Unexpected error")

    elapsed_ms = int((time.monotonic() - started) * 1000)
    status_code = int(response.get("statusCode", 500))
    logger.info(
        "Player API request",
        extra={
            "request_id": request_id,
            "route_key": route_key,
            "status_code": status_code,
            "elapsed_ms": elapsed_ms,
        },
    )
    _emit_route_metric(
        cw_client,
        function_name,
        route_key=route_key,
        elapsed_ms=elapsed_ms,
        status_code=status_code,
    )
    return response
