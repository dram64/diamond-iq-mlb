"""Tests for the $connect WebSocket handler."""

from __future__ import annotations

import time
from typing import Any

import boto3
import pytest
from ws_connect.handler import lambda_handler


def _connect_event(
    connection_id: str = "abc123=",
    domain_name: str = "abcd1234.execute-api.us-east-1.amazonaws.com",
    stage: str = "production",
) -> dict[str, Any]:
    rc: dict[str, Any] = {}
    if connection_id is not None:
        rc["connectionId"] = connection_id
    if domain_name is not None:
        rc["domainName"] = domain_name
    if stage is not None:
        rc["stage"] = stage
    return {"requestContext": rc}


def _read_meta(connection_id: str, table_name: str) -> dict[str, Any] | None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)
    return table.get_item(Key={"PK": connection_id, "SK": "META"}).get("Item")


def test_writes_meta_row_with_correct_shape(connections_table: str) -> None:
    response = lambda_handler(_connect_event("conn-A"), None, table_name=connections_table)

    assert response["statusCode"] == 200
    item = _read_meta("conn-A", connections_table)
    assert item is not None
    assert item["PK"] == "conn-A"
    assert item["SK"] == "META"
    assert item["connection_id"] == "conn-A"
    assert item["domain_name"] == "abcd1234.execute-api.us-east-1.amazonaws.com"
    assert item["stage"] == "production"
    assert "connected_at_utc" in item


def test_idempotent_on_duplicate_connect(connections_table: str) -> None:
    """API Gateway can theoretically retry a $connect; the second call must
    not error and must leave the META row in place."""
    lambda_handler(_connect_event("conn-B"), None, table_name=connections_table)
    response2 = lambda_handler(_connect_event("conn-B"), None, table_name=connections_table)

    assert response2["statusCode"] == 200
    assert _read_meta("conn-B", connections_table) is not None


def test_ttl_is_set_to_roughly_four_hours_ahead(connections_table: str) -> None:
    before = int(time.time())
    lambda_handler(_connect_event("conn-C"), None, table_name=connections_table)
    after = int(time.time())

    item = _read_meta("conn-C", connections_table)
    assert item is not None
    ttl = int(item["ttl"])
    four_hours = 4 * 60 * 60
    # Window is whatever happened between before/after, plus the four-hour
    # offset, plus a 60s tolerance for clock variance in CI.
    assert before + four_hours <= ttl <= after + four_hours + 60


@pytest.mark.parametrize(
    "missing",
    ["connection_id", "domain_name", "stage"],
)
def test_rejects_when_request_context_missing_field(missing: str, connections_table: str) -> None:
    """Any missing requestContext field must reject the handshake with 400."""
    event = _connect_event()
    if missing == "connection_id":
        event["requestContext"].pop("connectionId")
    elif missing == "domain_name":
        event["requestContext"].pop("domainName")
    else:
        event["requestContext"].pop("stage")

    response = lambda_handler(event, None, table_name=connections_table)
    assert response["statusCode"] == 400
