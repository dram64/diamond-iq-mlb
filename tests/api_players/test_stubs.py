from __future__ import annotations

import json
from decimal import Decimal

import boto3
from api_players.handler import lambda_handler


def test_standings_503_when_partition_empty(seeded_table, games_table_name) -> None:
    event = {
        "routeKey": "GET /api/standings/{season}",
        "pathParameters": {"season": "2026"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"]["code"] == "data_not_yet_available"
    assert body["error"]["details"]["season"] == 2026


def test_hardest_hit_503_when_partition_empty(seeded_table, games_table_name) -> None:
    event = {
        "routeKey": "GET /api/hardest-hit/{date}",
        "pathParameters": {"date": "2026-04-26"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"]["code"] == "data_not_yet_available"


def test_hardest_hit_400_for_bad_date(seeded_table, games_table_name) -> None:
    event = {
        "routeKey": "GET /api/hardest-hit/{date}",
        "pathParameters": {"date": "2026-13-99"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    # The regex catches "2026-13-99" as well-formed; explicit non-YYYY-MM-DD:
    event["pathParameters"]["date"] = "not-a-date"
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_date"


def test_standings_returns_200_when_partition_populated(seeded_table, games_table_name) -> None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    table.put_item(
        Item={
            "PK": "STANDINGS#2026",
            "SK": "STANDINGS#147",
            "season": 2026,
            "team_id": 147,
            "team_name": "Yankees",
            "wins": 18,
            "losses": 10,
            "pct": ".643",
            "games_back": "-",
            "streak_code": "L1",
            "last_ten_record": "8-2",
            "run_differential": 47,
            "division_rank": 1,
        }
    )
    event = {
        "routeKey": "GET /api/standings/{season}",
        "pathParameters": {"season": "2026"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["season"] == 2026
    assert len(body["data"]["teams"]) == 1
    assert body["data"]["teams"][0]["team_name"] == "Yankees"


def test_hardest_hit_returns_200_when_partition_populated(seeded_table, games_table_name) -> None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    # Seed 3 hits with descending velocities; SK encoding inverts so 118mph → 8819
    rows = [
        {"velocity": Decimal("118.0"), "sk": "HIT#8820#1234#5", "batter": "Judge"},
        {"velocity": Decimal("110.0"), "sk": "HIT#8900#1235#3", "batter": "Trout"},
        {"velocity": Decimal("100.0"), "sk": "HIT#9000#1236#1", "batter": "Olson"},
    ]
    for r in rows:
        table.put_item(
            Item={
                "PK": "HITS#2026-04-26",
                "SK": r["sk"],
                "launch_speed": r["velocity"],
                "batter_name": r["batter"],
                "result_event": "Single",
            }
        )
    event = {
        "routeKey": "GET /api/hardest-hit/{date}",
        "pathParameters": {"date": "2026-04-26"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    hits = body["data"]["hits"]
    assert len(hits) == 3
    # Top of list = highest velocity (Judge at 118)
    assert hits[0]["batter_name"] == "Judge"
    assert hits[2]["batter_name"] == "Olson"
