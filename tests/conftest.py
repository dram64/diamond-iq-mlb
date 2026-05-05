"""Shared pytest fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mlb_schedule_fixture() -> dict[str, Any]:
    """Load the captured MLB Stats API schedule response."""
    with (FIXTURES_DIR / "mlb_schedule.json").open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def games_table_name() -> str:
    return "diamond-iq-games-test"


@pytest.fixture
def dynamodb_table(monkeypatch: pytest.MonkeyPatch, games_table_name: str) -> Iterator[None]:
    """Spin up a moto-mocked DynamoDB table mirroring the production schema."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("GAMES_TABLE_NAME", games_table_name)

    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=games_table_name,
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.update_time_to_live(
            TableName=games_table_name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
        )
        yield


@pytest.fixture
def connections_table_name() -> str:
    return "diamond-iq-connections-test"


@pytest.fixture
def connections_table(
    monkeypatch: pytest.MonkeyPatch, connections_table_name: str
) -> Iterator[str]:
    """Spin up a moto-mocked connections table with the production schema."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("CONNECTIONS_TABLE_NAME", connections_table_name)

    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=connections_table_name,
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "game_pk_str", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "by-game",
                    "KeySchema": [
                        {"AttributeName": "game_pk_str", "KeyType": "HASH"},
                        {"AttributeName": "PK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        client.update_time_to_live(
            TableName=connections_table_name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
        )
        yield connections_table_name
