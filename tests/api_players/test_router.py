"""Routing dispatch tests."""

from __future__ import annotations

import json

from api_players.handler import ROUTES, lambda_handler


def test_routes_table_contains_all_endpoints() -> None:
    assert "GET /api/players/{personId}" in ROUTES
    assert "GET /api/players/compare" in ROUTES
    assert "GET /api/players/search" in ROUTES
    assert "GET /api/featured-matchup" in ROUTES
    assert "GET /api/games/featured" in ROUTES
    assert "GET /api/leaders/{group}/{stat}" in ROUTES
    assert "GET /api/teams/{teamId}/roster" in ROUTES
    assert "GET /api/teams/{teamId}/stats" in ROUTES
    assert "GET /api/teams/compare" in ROUTES
    assert "GET /api/standings/{season}" in ROUTES
    assert "GET /api/hardest-hit/{date}" in ROUTES
    assert len(ROUTES) == 11


def test_compare_and_player_routes_both_present() -> None:
    """Q3 verification: both literal /compare and parameterized /{personId}
    are registered as distinct dispatch keys. API Gateway HTTP API v2 routes
    literal-before-path-parameter at the gateway level; we mirror both keys
    so a misordered routeKey from a future config drift fails loudly."""
    assert "GET /api/players/compare" in ROUTES
    assert "GET /api/players/{personId}" in ROUTES
    assert ROUTES["GET /api/players/compare"] is not ROUTES["GET /api/players/{personId}"]


def test_unknown_routekey_returns_404(seeded_table, games_table_name) -> None:
    event = {"routeKey": "GET /api/nonexistent", "pathParameters": {}}
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "route_not_found"
