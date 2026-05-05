"""$disconnect handler — cleans up all DynamoDB rows for a connection.

API Gateway routes $disconnect when a client cleanly closes the
WebSocket OR when AWS reaps an idle connection (~10 minutes of
inactivity). Either way, we remove the META row and any subscription
rows that were left behind.

Stale connections (client crashed without close) eventually fall off
via the table's TTL, but $disconnect cleans them up faster.
"""

from __future__ import annotations

from typing import Any

from shared.connections import delete_connection_all_rows
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

    log_ctx: dict[str, Any] = {
        "request_id": request_id,
        "connection_id": connection_id,
    }

    if not connection_id:
        logger.warning("Missing connection_id on $disconnect; nothing to clean up", extra=log_ctx)
        return {"statusCode": 200}

    try:
        deleted = delete_connection_all_rows(connection_id, table_name=table_name)
    except Exception as err:  # noqa: BLE001 - $disconnect must always 200
        logger.error(
            "Cleanup failed; TTL will catch the rows in <=4h",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )
        return {"statusCode": 200}

    logger.info("WebSocket disconnect cleaned up", extra={**log_ctx, "rows_deleted": deleted})
    return {"statusCode": 200}
