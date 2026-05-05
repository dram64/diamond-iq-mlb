"""Tests for GET /api/teams/{teamId}/roster."""

from __future__ import annotations

import json

from api_players.handler import lambda_handler


def _event(team_id: str) -> dict:
    return {
        "routeKey": "GET /api/teams/{teamId}/roster",
        "pathParameters": {"teamId": team_id},
    }


def test_roster_happy_path(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("147"), None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["team_id"] == 147
    roster = body["data"]["roster"]
    assert len(roster) == 3
    names = {entry["full_name"] for entry in roster}
    assert names == {"Alpha", "Bravo", "Charlie"}


def test_roster_includes_metadata_enrichment(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("147"), None, table_name=games_table_name)
    body = json.loads(response["body"])
    roster = body["data"]["roster"]
    for entry in roster:
        assert "metadata" in entry
        assert entry["metadata"]["primary_number"] is not None


def test_roster_404_for_unknown_team(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("999"), None, table_name=games_table_name)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "team_not_found"


def test_roster_cache_header_one_hour(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("147"), None, table_name=games_table_name)
    assert "max-age=3600" in response["headers"]["Cache-Control"]


def test_roster_400_for_invalid_team_id(seeded_table, games_table_name) -> None:
    response = lambda_handler(_event("not-a-number"), None, table_name=games_table_name)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"]["code"] == "invalid_team_id"
