"""Tests for the $disconnect WebSocket handler."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import boto3
from shared.connections import (
    put_connection_meta,
    subscribe_connection,
)
from ws_disconnect.handler import lambda_handler


def _disconnect_event(connection_id: str = "abc123=") -> dict[str, Any]:
    return {"requestContext": {"connectionId": connection_id}}


def _seed_connection(connection_id: str, table_name: str, *, game_pks: list[int]) -> None:
    put_connection_meta(
        connection_id=connection_id,
        domain_name="d.example.com",
        stage="production",
        connected_at_utc="2026-04-27T00:00:00+00:00",
        table_name=table_name,
    )
    for pk in game_pks:
        subscribe_connection(connection_id=connection_id, game_pk=pk, table_name=table_name)


def _row_count(connection_id: str, table_name: str) -> int:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": connection_id},
    )
    return len(resp.get("Items", []))


def test_deletes_all_rows_for_connection(connections_table: str) -> None:
    _seed_connection("conn-A", connections_table, game_pks=[1001, 1002, 1003])
    assert _row_count("conn-A", connections_table) == 4  # META + 3 GAME#

    response = lambda_handler(_disconnect_event("conn-A"), None, table_name=connections_table)

    assert response["statusCode"] == 200
    assert _row_count("conn-A", connections_table) == 0


def test_no_op_when_connection_has_no_rows(connections_table: str) -> None:
    """A $disconnect for a connection that never $connected must succeed silently."""
    response = lambda_handler(_disconnect_event("ghost"), None, table_name=connections_table)
    assert response["statusCode"] == 200
    assert _row_count("ghost", connections_table) == 0


def test_returns_200_even_when_dynamodb_query_explodes(connections_table: str) -> None:
    """$disconnect must NEVER fail — the TTL is the safety net for any leak."""
    _seed_connection("conn-B", connections_table, game_pks=[1])

    with patch(
        "ws_disconnect.handler.delete_connection_all_rows",
        side_effect=RuntimeError("simulated DynamoDB outage"),
    ):
        response = lambda_handler(_disconnect_event("conn-B"), None, table_name=connections_table)

    assert response["statusCode"] == 200
