from __future__ import annotations

import json
from typing import Any

import boto3
from api_players.handler import lambda_handler


def _seed_players(table: Any, players: list[tuple[int, str, str]]) -> None:
    for pid, name, pos in players:
        table.put_item(
            Item={
                "PK": "PLAYER#GLOBAL",
                "SK": f"PLAYER#{pid}",
                "person_id": pid,
                "full_name": name,
                "primary_position_abbr": pos,
                "primary_number": "00",
            }
        )


def _invoke(games_table_name: str, q: str | None, limit: str | None = None) -> dict[str, Any]:
    qs: dict[str, Any] = {}
    if q is not None:
        qs["q"] = q
    if limit is not None:
        qs["limit"] = limit
    event = {
        "routeKey": "GET /api/players/search",
        "pathParameters": {},
        "queryStringParameters": qs,
    }
    return lambda_handler(event, None, table_name=games_table_name)


def test_search_happy_path_returns_matches(seeded_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_players(
        table,
        [
            (592450, "Aaron Judge", "RF"),
            (1234, "Mike Judge", "OF"),
            (519242, "Chris Sale", "SP"),
        ],
    )
    response = _invoke(games_table_name, "judge")
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    names = [r["full_name"] for r in body["data"]["results"]]
    assert "Aaron Judge" in names
    assert "Mike Judge" in names
    assert body["data"]["count"] == 2


def test_search_prefix_match_outranks_substring(seeded_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_players(
        table,
        [
            (1, "Tony Gwynn", "OF"),
            (2, "Tony La Russa", "MGR"),
            (3, "Marco Tonyo", "1B"),  # contains 'tony' but doesn't start with it
        ],
    )
    response = _invoke(games_table_name, "tony")
    body = json.loads(response["body"])
    names = [r["full_name"] for r in body["data"]["results"]]
    # Prefix matches first, alphabetized; substring match last.
    assert names[0] == "Tony Gwynn"
    assert names[1] == "Tony La Russa"
    assert names[2] == "Marco Tonyo"


def test_search_400_on_short_query(seeded_table, games_table_name):  # noqa: ARG001
    response = _invoke(games_table_name, "a")
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_query"


def test_search_400_on_missing_query(seeded_table, games_table_name):  # noqa: ARG001
    response = _invoke(games_table_name, None)
    assert response["statusCode"] == 400


def test_search_respects_custom_limit(seeded_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_players(table, [(i, f"Sample Player {i:03d}", "RF") for i in range(20)])
    response = _invoke(games_table_name, "sample", limit="5")
    body = json.loads(response["body"])
    assert len(body["data"]["results"]) == 5


def test_search_default_limit_caps_at_10(seeded_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_players(table, [(i, f"Match Player {i:03d}", "RF") for i in range(20)])
    response = _invoke(games_table_name, "match")
    body = json.loads(response["body"])
    assert len(body["data"]["results"]) == 10


def test_search_400_on_oversized_limit(seeded_table, games_table_name):  # noqa: ARG001
    response = _invoke(games_table_name, "judge", limit="100")
    assert response["statusCode"] == 400


def test_search_case_insensitive(seeded_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_players(table, [(1, "Aaron Judge", "RF")])
    response = _invoke(games_table_name, "JUDGE")
    body = json.loads(response["body"])
    assert body["data"]["count"] == 1


def test_search_empty_results_is_200(seeded_table, games_table_name):  # noqa: ARG001
    response = _invoke(games_table_name, "zzz_no_match")
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["count"] == 0
    assert body["data"]["results"] == []


def test_search_projects_only_typeahead_fields(seeded_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_players(table, [(1, "Aaron Judge", "RF")])
    response = _invoke(games_table_name, "judge")
    body = json.loads(response["body"])
    row = body["data"]["results"][0]
    # Lean payload — typeahead row needs id, name, pos, number; nothing else.
    assert set(row.keys()) == {
        "person_id",
        "full_name",
        "primary_position_abbr",
        "primary_number",
    }
