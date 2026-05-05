"""Tests for GET /api/players/{personId}."""

from __future__ import annotations

import json

from api_players.handler import lambda_handler


def _event(person_id: str) -> dict:
    return {
        "routeKey": "GET /api/players/{personId}",
        "pathParameters": {"personId": person_id},
    }


def test_player_happy_path_with_hitting_and_pitching(seeded_table, games_table_name) -> None:
    """Bravo (id=2) is a pitcher. Alpha (id=1) is a hitter. Test a player with
    both stats by using id=1 with hitting only — and id=2 with pitching only —
    each separately verifies the response shape."""
    response = lambda_handler(_event("1"), None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["metadata"]["full_name"] == "Alpha"
    assert body["data"]["hitting"]["avg"] == ".320"
    assert body["data"]["pitching"] is None
    assert body["meta"]["season"] == 2026


def test_player_pitcher_has_pitching_stats(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("2"), None, table_name=games_table_name)
    body = json.loads(response["body"])
    assert body["data"]["metadata"]["full_name"] == "Bravo"
    assert body["data"]["pitching"]["era"] == "2.50"
    assert body["data"]["hitting"] is None


def test_player_404_for_unknown(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("999999"), None, table_name=games_table_name)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "player_not_found"


def test_player_400_for_non_integer_id(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("abc"), None, table_name=games_table_name)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_person_id"


def test_player_includes_5d_computed_stats(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1"), None, table_name=games_table_name)
    body = json.loads(response["body"])
    hitting = body["data"]["hitting"]
    assert "woba" in hitting
    assert "ops_plus" in hitting
    assert abs(hitting["woba"] - 0.420) < 1e-6
    assert abs(hitting["ops_plus"] - 160.5) < 1e-6


def test_player_cache_header_set(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1"), None, table_name=games_table_name)
    assert "max-age=300" in response["headers"]["Cache-Control"]


def test_player_response_strips_pk_sk(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("1"), None, table_name=games_table_name)
    body = json.loads(response["body"])
    assert "PK" not in body["data"]["metadata"]
    assert "SK" not in body["data"]["metadata"]
