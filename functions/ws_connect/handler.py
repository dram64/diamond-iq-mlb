"""$connect handler — registers a new WebSocket connection.

API Gateway routes $connect to this Lambda when a client opens a
WebSocket. The connection ID is already minted by API Gateway by the
time we run; our job is to record the META row in the connections table
so the stream processor (commit 3) can locate the connection's
PostToConnection endpoint later.

Returning 200 authorizes the connection. Any 4xx/5xx rejects the
handshake and the client gets a 4xx-style WebSocket close.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shared.connections import put_connection_meta
from shared.log import get_logger

logger = get_logger(__name__)


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    table_name: str | None = None,
) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", None) if context else None
    request_context = (event or {}).get("requestContext") or {}
    connection_id = request_context.get("connectionId")
    domain_name = request_context.get("domainName")
    stage = request_context.get("stage")

    log_ctx: dict[str, Any] = {
        "request_id": request_id,
        "connection_id": connection_id,
        "domain_name": domain_name,
        "stage": stage,
    }

    if not connection_id or not domain_name or not stage:
        logger.error(
            "Missing requestContext fields on $connect; rejecting handshake",
            extra=log_ctx,
        )
        return {"statusCode": 400, "body": "missing requestContext"}

    try:
        put_connection_meta(
            connection_id=connection_id,
            domain_name=domain_name,
            stage=stage,
            connected_at_utc=datetime.now(UTC).isoformat(),
            table_name=table_name,
        )
    except Exception as err:  # noqa: BLE001 - log and reject so client sees a clean failure
        logger.error(
            "Failed to register connection in DynamoDB; rejecting handshake",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )
        return {"statusCode": 500, "body": "registration failed"}

    logger.info("WebSocket connection registered", extra=log_ctx)
    return {"statusCode": 200}
