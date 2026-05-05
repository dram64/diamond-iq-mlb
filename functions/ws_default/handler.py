"""$default handler — handles client-sent WebSocket messages.

The client sends a JSON message of one of two shapes:

    {"action": "subscribe",   "game_pk": 12345}
    {"action": "unsubscribe", "game_pk": 12345}

subscribe writes a GAME#<pk> row linking connection_id to game_pk.
unsubscribe deletes that row. Both are idempotent — duplicate
subscribes overwrite (PutItem), unknown unsubscribes are no-ops
(DeleteItem against a missing key is silent).

Validation responses use 400 with a brief error body so the client
can tell the difference between malformed input and server error.
"""

from __future__ import annotations

import json
from typing import Any

from shared.connections import subscribe_connection, unsubscribe_connection
from shared.log import get_logger

logger = get_logger(__name__)

ALLOWED_ACTIONS = frozenset({"subscribe", "unsubscribe"})


def _bad_request(message: str) -> dict[str, Any]:
    return {"statusCode": 400, "body": message}


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    table_name: str | None = None,
) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", None) if context else None
    request_context = (event or {}).get("requestContext") or {}
    connection_id = request_context.get("connectionId")

    log_ctx: dict[str, Any] = {
        "request_id": request_id,
        "connection_id": connection_id,
    }

    if not connection_id:
        logger.error("Missing connection_id on $default", extra=log_ctx)
        return _bad_request("missing connection_id")

    raw_body = (event or {}).get("body")
    if not raw_body:
        return _bad_request("empty body")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Malformed JSON on $default", extra=log_ctx)
        return _bad_request("malformed json")

    action = body.get("action")
    if action not in ALLOWED_ACTIONS:
        logger.warning("Unknown action on $default", extra={**log_ctx, "action": action})
        return _bad_request(f"unknown action {action!r}; expected one of {sorted(ALLOWED_ACTIONS)}")

    raw_game_pk = body.get("game_pk")
    if not isinstance(raw_game_pk, int) or isinstance(raw_game_pk, bool):
        logger.warning(
            "Missing or invalid game_pk on $default",
            extra={**log_ctx, "raw_game_pk": raw_game_pk},
        )
        return _bad_request("game_pk must be an integer")

    try:
        if action == "subscribe":
            subscribe_connection(
                connection_id=connection_id,
                game_pk=raw_game_pk,
                table_name=table_name,
            )
        else:
            unsubscribe_connection(
                connection_id=connection_id,
                game_pk=raw_game_pk,
                table_name=table_name,
            )
    except Exception as err:  # noqa: BLE001
        logger.error(
            "DynamoDB write failed on $default",
            extra={
                **log_ctx,
                "action": action,
                "game_pk": raw_game_pk,
                "error_class": type(err).__name__,
                "error_message": str(err),
            },
        )
        return {"statusCode": 500, "body": "subscription update failed"}

    logger.info(
        "Subscription updated",
        extra={**log_ctx, "action": action, "game_pk": raw_game_pk},
    )
    return {"statusCode": 200}
