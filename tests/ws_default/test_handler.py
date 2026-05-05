"""Tests for the $default WebSocket handler."""

from __future__ import annotations

import json
from typing import Any

import boto3
from ws_default.handler import lambda_handler


def _default_event(
    body: str | None,
    connection_id: str = "abc123=",
) -> dict[str, Any]:
    return {
        "requestContext": {"connectionId": connection_id},
        "body": body,
    }


def _read_subscription(connection_id: str, game_pk: int, table_name: str) -> dict[str, Any] | None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)
    return table.get_item(Key={"PK": connection_id, "SK": f"GAME#{game_pk}"}).get("Item")


# ── subscribe ─────────────────────────────────────────────────────────


def test_subscribe_writes_game_row(connections_table: str) -> None:
    body = json.dumps({"action": "subscribe", "game_pk": 12345})
    response = lambda_handler(_default_event(body, "conn-A"), None, table_name=connections_table)

    assert response["statusCode"] == 200
    row = _read_subscription("conn-A", 12345, connections_table)
    assert row is not None
    assert row["PK"] == "conn-A"
    assert row["SK"] == "GAME#12345"
    assert int(row["game_pk"]) == 12345
    assert row["game_pk_str"] == "12345"  # GSI key — must be present and string-typed


def test_duplicate_subscribe_is_idempotent(connections_table: str) -> None:
    body = json.dumps({"action": "subscribe", "game_pk": 7777})
    lambda_handler(_default_event(body, "conn-A"), None, table_name=connections_table)
    response2 = lambda_handler(_default_event(body, "conn-A"), None, table_name=connections_table)

    assert response2["statusCode"] == 200
    assert _read_subscription("conn-A", 7777, connections_table) is not None


# ── unsubscribe ───────────────────────────────────────────────────────


def test_unsubscribe_deletes_game_row(connections_table: str) -> None:
    sub_body = json.dumps({"action": "subscribe", "game_pk": 4242})
    unsub_body = json.dumps({"action": "unsubscribe", "game_pk": 4242})

    lambda_handler(_default_event(sub_body, "conn-B"), None, table_name=connections_table)
    assert _read_subscription("conn-B", 4242, connections_table) is not None

    response = lambda_handler(
        _default_event(unsub_body, "conn-B"), None, table_name=connections_table
    )

    assert response["statusCode"] == 200
    assert _read_subscription("conn-B", 4242, connections_table) is None


# ── validation ────────────────────────────────────────────────────────


def test_malformed_json_returns_400(connections_table: str) -> None:
    response = lambda_handler(
        _default_event("{not-json}", "conn-X"), None, table_name=connections_table
    )
    assert response["statusCode"] == 400


def test_unknown_action_returns_400(connections_table: str) -> None:
    body = json.dumps({"action": "delete-the-database", "game_pk": 1})
    response = lambda_handler(_default_event(body, "conn-X"), None, table_name=connections_table)
    assert response["statusCode"] == 400


def test_missing_or_invalid_game_pk_returns_400(connections_table: str) -> None:
    cases = [
        json.dumps({"action": "subscribe"}),
        json.dumps({"action": "subscribe", "game_pk": "not-an-int"}),
        json.dumps(
            {"action": "subscribe", "game_pk": True}
        ),  # bool is technically int but rejected
        json.dumps({"action": "subscribe", "game_pk": None}),
    ]
    for body in cases:
        response = lambda_handler(
            _default_event(body, "conn-X"), None, table_name=connections_table
        )
        assert response["statusCode"] == 400, f"expected 400 for body={body!r}"
