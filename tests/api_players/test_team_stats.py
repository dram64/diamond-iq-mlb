from __future__ import annotations

import json
from typing import Any

import boto3
from api_players.handler import lambda_handler


def _seed_team(table: Any, team_id: int, name: str = "Yankees") -> None:
    table.put_item(
        Item={
            "PK": "TEAMSTATS#2026",
            "SK": f"TEAMSTATS#{team_id}",
            "season": 2026,
            "team_id": team_id,
            "team_name": name,
            "hitting": {
                "games_played": 31,
                "at_bats": 1013,
                "runs": 153,
                "hits": 232,
                "home_runs": 48,
                "rbi": 145,
                "walks": 138,
                "strikeouts": 279,
                "stolen_bases": 32,
                "avg": ".229",
                "obp": ".324",
                "slg": ".424",
                "ops": ".748",
            },
            "pitching": {
                "games_played": 31,
                "wins": 20,
                "losses": 11,
                "saves": 9,
                "innings_pitched": "274.2",
                "earned_runs": 95,
                "strikeouts": 270,
                "walks_allowed": 85,
                "era": "3.11",
                "whip": "1.14",
                "opp_avg": ".222",
            },
        }
    )


def test_team_stats_happy_path(seeded_table, games_table_name) -> None:  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_team(table, 147, "Yankees")
    event = {
        "routeKey": "GET /api/teams/{teamId}/stats",
        "pathParameters": {"teamId": "147"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["team_name"] == "Yankees"
    assert body["data"]["hitting"]["avg"] == ".229"
    assert body["data"]["pitching"]["era"] == "3.11"
    # PK / SK stripped from the projected payload.
    assert "PK" not in body["data"]
    assert "SK" not in body["data"]


def test_team_stats_503_when_partition_empty(seeded_table, games_table_name) -> None:  # noqa: ARG001
    event = {
        "routeKey": "GET /api/teams/{teamId}/stats",
        "pathParameters": {"teamId": "999"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"]["code"] == "data_not_yet_available"


def test_team_stats_400_for_invalid_team_id(seeded_table, games_table_name) -> None:  # noqa: ARG001
    event = {
        "routeKey": "GET /api/teams/{teamId}/stats",
        "pathParameters": {"teamId": "not-a-number"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_team_id"


def test_team_compare_two_teams(seeded_table, games_table_name) -> None:  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_team(table, 147, "Yankees")
    _seed_team(table, 117, "Astros")
    event = {
        "routeKey": "GET /api/teams/compare",
        "pathParameters": {},
        "queryStringParameters": {"ids": "147,117"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    teams = body["data"]["teams"]
    assert len(teams) == 2
    assert {t["team_id"] for t in teams} == {147, 117}


def test_team_compare_404_if_any_id_missing(seeded_table, games_table_name) -> None:  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_team(table, 147, "Yankees")
    event = {
        "routeKey": "GET /api/teams/compare",
        "pathParameters": {},
        "queryStringParameters": {"ids": "147,99999"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "team_not_found"


def test_team_compare_too_few_ids(seeded_table, games_table_name) -> None:  # noqa: ARG001
    event = {
        "routeKey": "GET /api/teams/compare",
        "pathParameters": {},
        "queryStringParameters": {"ids": "147"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_ids_count"


def test_team_compare_too_many_ids(seeded_table, games_table_name) -> None:  # noqa: ARG001
    event = {
        "routeKey": "GET /api/teams/compare",
        "pathParameters": {},
        "queryStringParameters": {"ids": "1,2,3,4,5"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 400
