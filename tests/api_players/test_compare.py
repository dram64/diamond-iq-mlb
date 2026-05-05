"""Tests for GET /api/players/compare."""

from __future__ import annotations

import json

from api_players.handler import lambda_handler


def _event(ids: str) -> dict:
    return {
        "routeKey": "GET /api/players/compare",
        "pathParameters": {},
        "queryStringParameters": {"ids": ids},
    }


def test_compare_two_players(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1,2"), None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    players = body["data"]["players"]
    assert len(players) == 2
    assert players[0]["person_id"] == 1
    assert players[1]["person_id"] == 2


def test_compare_three_players(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1,2,3"), None, table_name=games_table_name)
    body = json.loads(response["body"])
    assert len(body["data"]["players"]) == 3


def test_compare_too_few_400(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1"), None, table_name=games_table_name)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_ids_count"


def test_compare_too_many_400(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1,2,3,4,5"), None, table_name=games_table_name)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_ids_count"


def test_compare_404_if_any_id_missing(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1,99999"), None, table_name=games_table_name)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "player_not_found"
