"""Stream processor — consumes DynamoDB Streams from the games table and
fans out score updates to subscribed WebSocket clients.

For each Streams record:
  1. Skip non-MODIFY events (INSERT/REMOVE) — INSERTs are start-of-day
     creations before any client could subscribe, REMOVEs are TTL cleanups.
  2. Diff old vs new image via shared.websocket_helpers.meaningful_change.
     Most ingest writes are TTL-only refreshes; meaningful_change returns
     None for those and we skip.
  3. Resolve the game_pk from the new image, build the payload.
  4. Query the connections table by-game GSI for subscribers.
  5. Fan out via PostToConnection, parallelized across connections.
  6. Handle 410 Gone responses by deleting the stale connection's rows.

Per-record errors do NOT raise — DynamoDB Streams retries the whole batch
on Lambda failure, which would re-deliver records that already succeeded.
We log and continue. The bisect_batch_on_function_error stream-trigger
setting catches genuinely poison records by halving the batch on retry.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError
from shared.connections import (
    delete_connection_all_rows,
    list_connections_for_game,
)
from shared.log import get_logger
from shared.websocket_helpers import build_payload, image_to_python, meaningful_change

logger = get_logger(__name__)

WEBSOCKET_API_ENDPOINT_ENV = "WEBSOCKET_API_ENDPOINT"
DEFAULT_FANOUT_WORKERS = 10


def _management_client(endpoint_url: str) -> Any:
    """Build a boto3 apigatewaymanagementapi client pointed at our WS endpoint."""
    return boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=endpoint_url,
        region_name="us-east-1",
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _post_to_connection(
    *,
    client: Any,
    connection_id: str,
    payload: dict[str, Any],
    table_name: str | None,
    log_ctx: dict[str, Any],
) -> str:
    """Post one payload to one connection. Returns the outcome string.

    Outcomes: "sent", "stale", "error". Never raises — every failure is
    logged and reduced to a counter.
    """
    try:
        client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(payload).encode("utf-8"),
        )
        return "sent"
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        # The management API exposes 410 Gone as either GoneException
        # (older botocore) or by HTTP status in the response metadata.
        status = err.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code == "GoneException" or status == 410:
            try:
                delete_connection_all_rows(connection_id, table_name=table_name)
            except Exception as delete_err:  # noqa: BLE001
                logger.warning(
                    "Stale-connection cleanup failed; TTL is the safety net",
                    extra={
                        **log_ctx,
                        "connection_id": connection_id,
                        "error_class": type(delete_err).__name__,
                        "error_message": str(delete_err),
                    },
                )
            return "stale"
        logger.warning(
            "PostToConnection failed (non-stale)",
            extra={
                **log_ctx,
                "connection_id": connection_id,
                "error_code": code,
                "error_message": str(err),
            },
        )
        return "error"
    except Exception as err:  # noqa: BLE001
        logger.warning(
            "PostToConnection raised unexpected exception",
            extra={
                **log_ctx,
                "connection_id": connection_id,
                "error_class": type(err).__name__,
                "error_message": str(err),
            },
        )
        return "error"


def _process_record(
    *,
    record: dict[str, Any],
    management_client: Any,
    connections_table_name: str | None,
    log_ctx: dict[str, Any],
) -> dict[str, int]:
    """Handle one Streams record. Returns counters for the summary."""
    counters = {"skipped": 0, "sent": 0, "stale": 0, "error": 0}
    event_name = record.get("eventName")
    if event_name != "MODIFY":
        counters["skipped"] += 1
        return counters

    dynamodb = record.get("dynamodb") or {}
    old_image = dynamodb.get("OldImage")
    new_image = dynamodb.get("NewImage")

    changes = meaningful_change(old_image, new_image)
    if changes is None:
        counters["skipped"] += 1
        return counters

    new = image_to_python(new_image)
    raw_pk = new.get("game_pk")
    if raw_pk is None:
        counters["skipped"] += 1
        return counters
    try:
        game_pk = int(raw_pk)
    except (TypeError, ValueError):
        counters["skipped"] += 1
        return counters

    payload = build_payload(game_pk=game_pk, timestamp=_now_iso(), changes=changes)

    subscribers = list_connections_for_game(game_pk, table_name=connections_table_name)
    if not subscribers:
        counters["skipped"] += 1  # no one to push to; not a failure
        return counters

    record_log_ctx = {**log_ctx, "game_pk": game_pk, "subscribers": len(subscribers)}

    with ThreadPoolExecutor(max_workers=DEFAULT_FANOUT_WORKERS) as pool:
        outcomes = list(
            pool.map(
                lambda sub: _post_to_connection(
                    client=management_client,
                    connection_id=sub["connection_id"],
                    payload=payload,
                    table_name=connections_table_name,
                    log_ctx=record_log_ctx,
                ),
                subscribers,
            )
        )

    for o in outcomes:
        counters[o] = counters.get(o, 0) + 1
    logger.info(
        "Score update fanned out",
        extra={**record_log_ctx, "outcomes": counters},
    )
    return counters


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    management_client: Any | None = None,
    connections_table_name: str | None = None,
) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", None) if context else None
    endpoint = os.environ.get(WEBSOCKET_API_ENDPOINT_ENV, "")
    log_ctx: dict[str, Any] = {"request_id": request_id, "endpoint": endpoint}

    records = (event or {}).get("Records") or []
    if not records:
        logger.info("Empty batch; nothing to process", extra=log_ctx)
        return {"records_processed": 0, "skipped": 0, "sent": 0, "stale": 0, "error": 0}

    client = management_client
    if client is None and endpoint:
        client = _management_client(endpoint)

    summary = {"records_processed": 0, "skipped": 0, "sent": 0, "stale": 0, "error": 0}
    for record in records:
        summary["records_processed"] += 1
        counters = _process_record(
            record=record,
            management_client=client,
            connections_table_name=connections_table_name,
            log_ctx=log_ctx,
        )
        for k in ("skipped", "sent", "stale", "error"):
            summary[k] += counters.get(k, 0)

    logger.info("Stream batch complete", extra={**log_ctx, **summary})
    return summary
