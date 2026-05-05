"""DynamoDB helpers for the WebSocket connections table.

Schema (see infrastructure/main.tf for the full Terraform definition):
    PK  = connection_id
    SK  = "META"                  one per connection (the connection record)
        | "GAME#<game_pk>"        one per per-game subscription
    GSI "by-game":
        PK = game_pk_str (string-typed game_pk for GSI key)
        SK = connection_id

The META row holds the API Gateway Management API endpoint metadata
(domain_name + stage) the stream processor needs to construct
PostToConnection calls. Subscription rows project sparsely to the GSI —
META rows have no game_pk_str attribute and stay out of the index.

TTL is 4 hours from connect time on every row, so a client that drops
without sending $disconnect is cleaned up automatically.
"""

from __future__ import annotations

import os
import time
from typing import Any

import boto3

CONNECTIONS_TABLE_ENV = "CONNECTIONS_TABLE_NAME"
META_SK = "META"
TTL_SECONDS = 4 * 60 * 60  # 4 hours


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(CONNECTIONS_TABLE_ENV)
    if not name:
        raise RuntimeError(
            f"{CONNECTIONS_TABLE_ENV} environment variable not set and no override provided"
        )
    return name


def _table(table_name: str | None):
    name = _resolve_table_name(table_name)
    return boto3.resource("dynamodb").Table(name)


def _ttl_now() -> int:
    return int(time.time()) + TTL_SECONDS


def game_sk(game_pk: int) -> str:
    """SK builder for a per-game subscription row."""
    return f"GAME#{game_pk}"


def put_connection_meta(
    *,
    connection_id: str,
    domain_name: str,
    stage: str,
    connected_at_utc: str,
    table_name: str | None = None,
) -> None:
    """Write the META row for a new connection.

    Idempotent — re-writing the same connection_id replaces the row, which
    is what we want if API Gateway re-issues a $connect for the same id.
    """
    table = _table(table_name)
    table.put_item(
        Item={
            "PK": connection_id,
            "SK": META_SK,
            "connection_id": connection_id,
            "domain_name": domain_name,
            "stage": stage,
            "connected_at_utc": connected_at_utc,
            "ttl": _ttl_now(),
        }
    )


def subscribe_connection(
    *,
    connection_id: str,
    game_pk: int,
    table_name: str | None = None,
) -> None:
    """Add a subscription row linking connection_id to game_pk.

    Idempotent — duplicate subscribes overwrite, no error.
    """
    table = _table(table_name)
    table.put_item(
        Item={
            "PK": connection_id,
            "SK": game_sk(game_pk),
            "connection_id": connection_id,
            "game_pk": game_pk,
            "game_pk_str": str(game_pk),  # GSI hash key
            "ttl": _ttl_now(),
        }
    )


def unsubscribe_connection(
    *,
    connection_id: str,
    game_pk: int,
    table_name: str | None = None,
) -> None:
    """Remove a subscription row. No-op if it doesn't exist."""
    table = _table(table_name)
    table.delete_item(
        Key={"PK": connection_id, "SK": game_sk(game_pk)},
    )


def list_connection_rows(connection_id: str, table_name: str | None = None) -> list[dict[str, Any]]:
    """Query every row (META + all GAME# subscriptions) for a connection."""
    table = _table(table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": connection_id},
        ProjectionExpression="PK,SK",
    )
    return list(resp.get("Items", []))


def delete_connection_all_rows(connection_id: str, table_name: str | None = None) -> int:
    """Delete every row for a connection. Returns the number of rows deleted.

    Used by $disconnect to clean up the META row plus any subscriptions.
    Per-row deletes (not BatchWriteItem) so partial failures surface
    individually — the alternative requires hand-rolling unprocessed-item
    retries which isn't worth it at this scale.
    """
    table = _table(table_name)
    rows = list_connection_rows(connection_id, table_name=table_name)
    deleted = 0
    for row in rows:
        try:
            table.delete_item(Key={"PK": row["PK"], "SK": row["SK"]})
            deleted += 1
        except Exception:  # noqa: BLE001 - keep deleting even if one fails
            continue
    return deleted


def list_connections_for_game(game_pk: int, table_name: str | None = None) -> list[dict[str, Any]]:
    """Query the by-game GSI for every connection subscribed to a game.

    Used by the stream processor (commit 3) to fan out updates.
    """
    table = _table(table_name)
    resp = table.query(
        IndexName="by-game",
        KeyConditionExpression="game_pk_str = :g",
        ExpressionAttributeValues={":g": str(game_pk)},
    )
    return list(resp.get("Items", []))


def get_connection_meta(connection_id: str, table_name: str | None = None) -> dict[str, Any] | None:
    """Read a connection's META row. Returns None if not found.

    Used by the stream processor to look up domain_name + stage when
    posting to a specific connection.
    """
    table = _table(table_name)
    resp = table.get_item(Key={"PK": connection_id, "SK": META_SK})
    return resp.get("Item")
