"""Tests for the data models and normalization."""

from __future__ import annotations

from typing import Any

import pytest
from shared.models import (
    Game,
    Linescore,
    Team,
    game_to_api_response,
    game_to_dynamodb_item,
    normalize_game,
)

VALID_STATUSES = {"live", "final", "scheduled", "preview", "postponed"}


def _minimal_raw(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "gamePk": 1,
        "gameDate": "2026-04-24T19:00:00Z",
        "status": {"abstractGameState": "Preview", "detailedState": "Scheduled"},
        "teams": {
            "away": {"team": {"id": 100, "name": "Away", "abbreviation": "AWY"}},
            "home": {"team": {"id": 200, "name": "Home", "abbreviation": "HOM"}},
        },
    }
    base.update(overrides)
    return base


def test_normalize_each_fixture_game_yields_valid_status(
    mlb_schedule_fixture: dict[str, Any],
) -> None:
    games_raw = mlb_schedule_fixture["dates"][0]["games"]
    assert games_raw, "fixture should contain games"

    games = [normalize_game(g) for g in games_raw]
    assert len(games) == len(games_raw)
    for g in games:
        assert isinstance(g, Game)
        assert g.game_pk > 0
        assert len(g.date) == 10  # yyyy-mm-dd
        assert g.status in VALID_STATUSES


def test_normalize_pulls_runs_from_linescore_teams(
    mlb_schedule_fixture: dict[str, Any],
) -> None:
    games_raw = mlb_schedule_fixture["dates"][0]["games"]
    live = next(g for g in games_raw if g["status"]["abstractGameState"] == "Live")

    game = normalize_game(live)

    assert game.linescore is not None
    assert game.linescore.away_runs == live["linescore"]["teams"]["away"]["runs"]
    assert game.linescore.home_runs == live["linescore"]["teams"]["home"]["runs"]


def test_status_live() -> None:
    raw = _minimal_raw(
        status={"abstractGameState": "Live", "detailedState": "In Progress"},
    )
    assert normalize_game(raw).status == "live"


def test_status_final() -> None:
    raw = _minimal_raw(
        status={"abstractGameState": "Final", "detailedState": "Final"},
    )
    assert normalize_game(raw).status == "final"


def test_status_preview() -> None:
    raw = _minimal_raw(
        status={"abstractGameState": "Preview", "detailedState": "Scheduled"},
    )
    assert normalize_game(raw).status == "preview"


def test_status_postponed_overrides_abstract_state() -> None:
    raw = _minimal_raw(
        status={"abstractGameState": "Final", "detailedState": "Postponed: Rain"},
    )
    assert normalize_game(raw).status == "postponed"


def test_status_unknown_falls_back_to_scheduled() -> None:
    raw = _minimal_raw(
        status={"abstractGameState": "Other", "detailedState": "Some new state"},
    )
    assert normalize_game(raw).status == "scheduled"


def test_normalize_handles_missing_optional_fields() -> None:
    raw = _minimal_raw()  # no linescore, no venue, no scores
    g = normalize_game(raw)
    assert g.linescore is None
    assert g.venue is None
    assert g.away_score == 0
    assert g.home_score == 0


def test_normalize_handles_completely_empty_dict() -> None:
    g = normalize_game({})
    assert g.game_pk == 0
    assert g.date == ""
    assert g.status == "scheduled"
    assert g.away_team == Team(id=0, name="", abbreviation="")


def test_game_to_dynamodb_item_keys_and_attributes() -> None:
    g = Game(
        game_pk=12345,
        date="2026-04-24",
        status="live",
        detailed_state="In Progress",
        away_team=Team(1, "A", "A"),
        home_team=Team(2, "H", "H"),
        away_score=3,
        home_score=2,
        venue="Park",
        start_time_utc="2026-04-24T19:00:00Z",
        linescore=Linescore(inning=5, inning_half="Top", balls=2, strikes=1, outs=1),
    )

    item = game_to_dynamodb_item(g)

    assert item["PK"] == "GAME#2026-04-24"
    assert item["SK"] == "GAME#12345"
    assert item["away_team"] == {"id": 1, "name": "A", "abbreviation": "A"}
    assert item["home_team"] == {"id": 2, "name": "H", "abbreviation": "H"}
    assert item["away_score"] == 3
    assert item["home_score"] == 2
    assert item["linescore"]["inning"] == 5
    assert "ttl" in item
    assert item["ttl"] > 0


def test_game_to_dynamodb_item_strips_none_values() -> None:
    g = Game(
        game_pk=1,
        date="2026-04-24",
        status="preview",
        detailed_state="Scheduled",
        away_team=Team(1, "A", "A"),
        home_team=Team(2, "H", "H"),
        away_score=0,
        home_score=0,
        venue=None,
        start_time_utc="2026-04-24T19:00:00Z",
        linescore=None,
    )

    item = game_to_dynamodb_item(g)

    assert "venue" not in item
    assert "linescore" not in item


def test_game_to_dynamodb_item_strips_none_inside_linescore() -> None:
    g = Game(
        game_pk=1,
        date="2026-04-24",
        status="live",
        detailed_state="In Progress",
        away_team=Team(1, "A", "A"),
        home_team=Team(2, "H", "H"),
        away_score=0,
        home_score=0,
        venue="Park",
        start_time_utc="2026-04-24T19:00:00Z",
        linescore=Linescore(inning=3, balls=2),
    )

    item = game_to_dynamodb_item(g)

    assert item["linescore"] == {"inning": 3, "balls": 2}


@pytest.mark.parametrize("missing_field", ["status", "teams", "linescore"])
def test_normalize_tolerates_missing_top_level_fields(missing_field: str) -> None:
    raw = _minimal_raw()
    raw.pop(missing_field, None)
    # Should not raise
    g = normalize_game(raw)
    assert isinstance(g, Game)


def test_game_to_api_response_shape_with_linescore() -> None:
    g = Game(
        game_pk=12345,
        date="2026-04-24",
        status="live",
        detailed_state="In Progress",
        away_team=Team(1, "Away", "AWY"),
        home_team=Team(2, "Home", "HOM"),
        away_score=3,
        home_score=2,
        venue="Park",
        start_time_utc="2026-04-24T19:00:00Z",
        linescore=Linescore(inning=5, inning_half="Top", balls=2, strikes=1, outs=1),
    )

    body = game_to_api_response(g)

    assert body["game_pk"] == 12345
    assert body["date"] == "2026-04-24"
    assert body["status"] == "live"
    assert body["away"] == {"id": 1, "name": "Away", "abbreviation": "AWY"}
    assert body["home"] == {"id": 2, "name": "Home", "abbreviation": "HOM"}
    assert body["away_score"] == 3
    assert body["home_score"] == 2
    assert body["linescore"]["inning"] == 5
    assert body["linescore"]["inning_half"] == "Top"
    # PK/SK and ttl belong to DynamoDB only — never leak via the API.
    assert "PK" not in body
    assert "SK" not in body
    assert "ttl" not in body


def test_game_to_api_response_strips_none_fields() -> None:
    g = Game(
        game_pk=1,
        date="2026-04-24",
        status="preview",
        detailed_state="Scheduled",
        away_team=Team(1, "A", "A"),
        home_team=Team(2, "H", "H"),
        away_score=0,
        home_score=0,
        venue=None,
        start_time_utc="2026-04-24T19:00:00Z",
        linescore=None,
    )

    body = game_to_api_response(g)

    assert "venue" not in body
    assert "linescore" not in body
