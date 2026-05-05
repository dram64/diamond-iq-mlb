"""Tests for DynamoDB read/write helpers, against a moto-mocked table."""

from __future__ import annotations

import pytest
from shared.dynamodb import get_game, list_todays_games, put_game
from shared.models import Game, Linescore, Team


def _sample(game_pk: int, date: str = "2026-04-24") -> Game:
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


def test_put_then_get_roundtrip(dynamodb_table: None, games_table_name: str) -> None:
    g = _sample(12345)
    put_game(g, table_name=games_table_name)

    found = get_game(12345, "2026-04-24", table_name=games_table_name)

    assert found is not None
    assert found.game_pk == 12345
    assert found.date == "2026-04-24"
    assert found.status == "live"
    assert found.away_team == Team(id=1, name="Away", abbreviation="AWY")
    assert found.home_team == Team(id=2, name="Home", abbreviation="HOM")
    assert found.linescore is not None
    assert found.linescore.inning == 5
    assert found.linescore.outs == 1


def test_get_returns_none_when_missing(dynamodb_table: None, games_table_name: str) -> None:
    assert get_game(99999, "2026-04-24", table_name=games_table_name) is None


def test_list_todays_games_filters_by_date(dynamodb_table: None, games_table_name: str) -> None:
    put_game(_sample(1, "2026-04-24"), table_name=games_table_name)
    put_game(_sample(2, "2026-04-24"), table_name=games_table_name)
    put_game(_sample(3, "2026-04-23"), table_name=games_table_name)

    today_games = list_todays_games("2026-04-24", table_name=games_table_name)

    assert {g.game_pk for g in today_games} == {1, 2}


def test_list_todays_games_empty_when_no_matches(
    dynamodb_table: None, games_table_name: str
) -> None:
    assert list_todays_games("2030-01-01", table_name=games_table_name) == []


def test_table_name_falls_back_to_env_var(
    dynamodb_table: None, games_table_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GAMES_TABLE_NAME is already set by the dynamodb_table fixture; calling
    # without an override should pick it up.
    put_game(_sample(7777), table_name=games_table_name)
    found = get_game(7777, "2026-04-24")  # no table_name arg
    assert found is not None
    assert found.game_pk == 7777


def test_missing_env_var_raises_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GAMES_TABLE_NAME", raising=False)
    with pytest.raises(RuntimeError, match="GAMES_TABLE_NAME"):
        get_game(1, "2026-04-24")
