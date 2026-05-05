"""Tests for the api_scoreboard Lambda handler."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any
from unittest.mock import patch

import pytest
from api_scoreboard.handler import lambda_handler
from shared.dynamodb import put_game
from shared.models import Game, Linescore, Team

pytestmark = pytest.mark.usefixtures("dynamodb_table")


def _sample_game(game_pk: int, date: str = "2026-04-24") -> Game:
    return Game(
        game_pk=game_pk,
        date=date,
        status="live",
        detailed_state="In Progress",
        away_team=Team(id=1, name="Away", abbreviation="AWY"),
        home_team=Team(id=2, name="Home", abbreviation="HOM"),
        away_score=3,
        home_score=2,
        venue="Park",
        start_time_utc=f"{date}T19:00:00Z",
        linescore=Linescore(inning=5, inning_half="Top", balls=2, strikes=1, outs=1),
    )


def _scoreboard_event(date: str | None = None) -> dict[str, Any]:
    return {
        "routeKey": "GET /scoreboard/today",
        "rawPath": "/scoreboard/today",
        "queryStringParameters": {"date": date} if date else None,
    }


def _game_event(game_id: str, date: str | None = None) -> dict[str, Any]:
    return {
        "routeKey": "GET /games/{gameId}",
        "rawPath": f"/games/{game_id}",
        "pathParameters": {"gameId": game_id},
        "queryStringParameters": {"date": date} if date else None,
    }


def _body(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["body"])


def _assert_cors_and_json(response: dict[str, Any]) -> None:
    headers = response["headers"]
    assert headers["Content-Type"] == "application/json"
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert headers["Access-Control-Allow-Methods"] == "GET, OPTIONS"
    assert headers["Access-Control-Allow-Headers"] == "Content-Type"
    assert headers["Access-Control-Max-Age"] == "86400"


# ── GET /scoreboard/today ─────────────────────────────────────────────


def test_scoreboard_today_returns_games_for_explicit_date(games_table_name: str) -> None:
    put_game(_sample_game(1), table_name=games_table_name)
    put_game(_sample_game(2), table_name=games_table_name)

    response = lambda_handler(_scoreboard_event("2026-04-24"), None)

    assert response["statusCode"] == 200
    _assert_cors_and_json(response)
    body = _body(response)
    assert body["date"] == "2026-04-24"
    assert body["count"] == 2
    assert {g["game_pk"] for g in body["games"]} == {1, 2}


def test_scoreboard_today_defaults_to_utc_today_when_no_date(games_table_name: str) -> None:
    from datetime import datetime

    today = datetime.now(UTC).date().isoformat()
    put_game(_sample_game(99, date=today), table_name=games_table_name)

    response = lambda_handler(_scoreboard_event(None), None)

    assert response["statusCode"] == 200
    body = _body(response)
    assert body["date"] == today
    assert body["count"] == 1
    assert body["games"][0]["game_pk"] == 99


def test_scoreboard_today_empty_when_no_games() -> None:
    response = lambda_handler(_scoreboard_event("2030-01-01"), None)

    assert response["statusCode"] == 200
    body = _body(response)
    assert body["count"] == 0
    assert body["games"] == []


def test_scoreboard_today_400_on_malformed_date() -> None:
    response = lambda_handler(_scoreboard_event("not-a-date"), None)

    assert response["statusCode"] == 400
    body = _body(response)
    assert body["error"]["code"] == "invalid_date"
    _assert_cors_and_json(response)


def test_scoreboard_today_400_on_impossible_date() -> None:
    # parses regex but fails datetime.strptime
    response = lambda_handler(_scoreboard_event("2026-13-40"), None)

    assert response["statusCode"] == 400
    assert _body(response)["error"]["code"] == "invalid_date"


# ── GET /games/{gameId} ───────────────────────────────────────────────


def test_get_game_happy_path(games_table_name: str) -> None:
    put_game(_sample_game(12345), table_name=games_table_name)

    response = lambda_handler(_game_event("12345", date="2026-04-24"), None)

    assert response["statusCode"] == 200
    _assert_cors_and_json(response)
    body = _body(response)
    assert body["game"]["game_pk"] == 12345
    assert body["game"]["away"]["abbreviation"] == "AWY"
    assert body["game"]["linescore"]["inning"] == 5


def test_get_game_404_when_not_found() -> None:
    response = lambda_handler(_game_event("99999", date="2026-04-24"), None)

    assert response["statusCode"] == 404
    body = _body(response)
    assert body["error"]["code"] == "game_not_found"
    _assert_cors_and_json(response)


def test_get_game_400_when_date_missing() -> None:
    response = lambda_handler(_game_event("12345"), None)

    assert response["statusCode"] == 400
    assert _body(response)["error"]["code"] == "missing_date"


def test_get_game_400_when_game_id_not_integer() -> None:
    response = lambda_handler(_game_event("not-a-number", date="2026-04-24"), None)

    assert response["statusCode"] == 400
    assert _body(response)["error"]["code"] == "invalid_game_id"


def test_get_game_400_when_date_malformed() -> None:
    response = lambda_handler(_game_event("12345", date="bad"), None)

    assert response["statusCode"] == 400
    assert _body(response)["error"]["code"] == "invalid_date"


# ── GET / ─────────────────────────────────────────────────────────────


def test_root_returns_welcome_payload() -> None:
    response = lambda_handler({"routeKey": "GET /", "rawPath": "/"}, None)

    assert response["statusCode"] == 200
    _assert_cors_and_json(response)
    body = _body(response)
    assert body["service"] == "Diamond IQ API"
    assert body["version"] == "1.0"
    assert body["endpoints"]["scoreboard"] == "/scoreboard/today"
    assert body["endpoints"]["scoreboard_by_date"] == "/scoreboard/today?date=YYYY-MM-DD"
    assert body["endpoints"]["game_detail"] == "/games/{gameId}?date=YYYY-MM-DD"
    assert body["documentation"] == "https://github.com/dram64/diamond-iq"
    assert body["live_demo"] is True


# ── routing / errors ──────────────────────────────────────────────────


def test_unknown_route_returns_404() -> None:
    response = lambda_handler({"routeKey": "GET /nope"}, None)

    assert response["statusCode"] == 404
    body = _body(response)
    assert body["error"]["code"] == "unknown_route"
    _assert_cors_and_json(response)


@patch("api_scoreboard.handler.list_todays_games")
def test_unhandled_exception_returns_500_without_internals(mock_list) -> None:
    mock_list.side_effect = RuntimeError("boom: secret credential 12345")

    response = lambda_handler(_scoreboard_event("2026-04-24"), None)

    assert response["statusCode"] == 500
    body = _body(response)
    assert body["error"]["code"] == "internal_error"
    # The internal error message should NOT be in the response body
    assert "boom" not in response["body"]
    assert "secret" not in response["body"]
    _assert_cors_and_json(response)


def test_all_responses_are_json_parseable() -> None:
    """Smoke check that every error path produces parseable JSON."""
    cases = [
        _scoreboard_event("2026-04-24"),
        _scoreboard_event("bad-date"),
        _game_event("1"),
        _game_event("abc", date="2026-04-24"),
        _game_event("1", date="2026-04-24"),
        {"routeKey": "GET /nope"},
    ]
    for event in cases:
        resp = lambda_handler(event, None)
        # must always return JSON-parseable body and a numeric status
        assert isinstance(resp["statusCode"], int)
        json.loads(resp["body"])
        _assert_cors_and_json(resp)
