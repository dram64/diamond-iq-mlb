"""Tests for the ingest_live_games Lambda handler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from ingest_live_games.handler import lambda_handler
from shared.dynamodb import list_todays_games
from shared.mlb_client import MLBAPIError

# All tests in this module need the moto-mocked table.
pytestmark = pytest.mark.usefixtures("dynamodb_table")


# ── Helpers ──────────────────────────────────────────────────────────


def _live_raw(game_pk: int, date_iso: str = "2026-04-24") -> dict[str, Any]:
    return {
        "gamePk": game_pk,
        "gameDate": f"{date_iso}T19:00:00Z",
        "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
        "teams": {
            "away": {"team": {"id": 1, "name": "Away", "abbreviation": "AWY"}, "score": 0},
            "home": {"team": {"id": 2, "name": "Home", "abbreviation": "HOM"}, "score": 0},
        },
        "linescore": {
            "currentInning": 1,
            "inningHalf": "Top",
            "balls": 0,
            "strikes": 0,
            "outs": 0,
            "teams": {"away": {"runs": 0}, "home": {"runs": 0}},
        },
    }


def _final_raw(game_pk: int, date_iso: str = "2026-04-24") -> dict[str, Any]:
    return {
        "gamePk": game_pk,
        "gameDate": f"{date_iso}T19:00:00Z",
        "status": {"abstractGameState": "Final", "detailedState": "Final"},
        "teams": {
            "away": {"team": {"id": 1, "name": "Away", "abbreviation": "AWY"}, "score": 5},
            "home": {"team": {"id": 2, "name": "Home", "abbreviation": "HOM"}, "score": 3},
        },
    }


def _preview_raw(game_pk: int, date_iso: str = "2026-04-24") -> dict[str, Any]:
    return {
        "gamePk": game_pk,
        "gameDate": f"{date_iso}T22:00:00Z",
        "status": {"abstractGameState": "Preview", "detailedState": "Scheduled"},
        "teams": {
            "away": {"team": {"id": 1, "name": "Away", "abbreviation": "AWY"}},
            "home": {"team": {"id": 2, "name": "Home", "abbreviation": "HOM"}},
        },
    }


def _payload(games: list[dict[str, Any]], date_iso: str = "2026-04-24") -> dict[str, Any]:
    return {"dates": [{"date": date_iso, "games": games}]}


def _empty_payload() -> dict[str, Any]:
    return {"dates": []}


def _by_date_response(per_date: dict[str, dict[str, Any]]):
    """side_effect that returns different payloads per `today=` kwarg."""

    def side_effect(*_args, today=None, **_kwargs):
        if today is None:
            return _empty_payload()
        return per_date.get(today.isoformat(), _empty_payload())

    return side_effect


def _expected_dates() -> tuple[str, str]:
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    return yesterday.isoformat(), today.isoformat()


# ── Mixed-slate writing ──────────────────────────────────────────────


def _postponed_raw(game_pk: int, date_iso: str = "2026-04-24") -> dict[str, Any]:
    return {
        "gamePk": game_pk,
        "gameDate": f"{date_iso}T22:00:00Z",
        "status": {"abstractGameState": "Preview", "detailedState": "Postponed: Rain"},
        "teams": {
            "away": {"team": {"id": 1, "name": "Away", "abbreviation": "AWY"}},
            "home": {"team": {"id": 2, "name": "Home", "abbreviation": "HOM"}},
        },
    }


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_writes_all_three_statuses_from_mixed_slate(mock_fetch, games_table_name: str) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: _payload(
                [
                    _live_raw(101, today),
                    _live_raw(102, today),
                    _final_raw(103, today),
                    _final_raw(104, today),
                    _preview_raw(105, today),
                    _preview_raw(106, today),
                ],
                date_iso=today,
            ),
        }
    )

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["dates_queried"] == [yesterday, today]
    assert result["total_games_in_schedule"] == 6
    assert result["live_games_processed"] == 2
    assert result["final_games_processed"] == 2
    assert result["preview_games_processed"] == 2
    assert result["games_written"] == 6
    assert result["games_failed"] == 0

    written = list_todays_games(today, table_name=games_table_name)
    assert {g.game_pk for g in written} == {101, 102, 103, 104, 105, 106}
    by_pk = {g.game_pk: g for g in written}
    assert by_pk[101].status == "live"
    assert by_pk[103].status == "final"
    assert by_pk[105].status == "preview"


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_combines_live_games_across_two_dates(mock_fetch, games_table_name: str) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _payload([_live_raw(1, yesterday)], date_iso=yesterday),
            today: _payload(
                [_live_raw(2, today), _live_raw(3, today)],
                date_iso=today,
            ),
        }
    )

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["total_games_in_schedule"] == 3
    assert result["live_games_processed"] == 3
    assert result["games_written"] == 3

    yesterday_games = list_todays_games(yesterday, table_name=games_table_name)
    today_games = list_todays_games(today, table_name=games_table_name)
    all_pks = {g.game_pk for g in yesterday_games} | {g.game_pk for g in today_games}
    assert all_pks == {1, 2, 3}


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_writes_all_qualifying_games_from_real_fixture(
    mock_fetch,
    mlb_schedule_fixture: dict[str, Any],
    games_table_name: str,
) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: mlb_schedule_fixture,
        }
    )
    fixture_date = mlb_schedule_fixture["dates"][0]["date"]

    def _count(state: str) -> int:
        return sum(
            1
            for g in mlb_schedule_fixture["dates"][0]["games"]
            if g["status"]["abstractGameState"] == state
        )

    expected_live = _count("Live")
    expected_final = _count("Final")
    expected_preview = _count("Preview")
    expected_total = expected_live + expected_final + expected_preview

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["live_games_processed"] == expected_live
    assert result["final_games_processed"] == expected_final
    assert result["preview_games_processed"] == expected_preview
    assert result["games_written"] == expected_total
    assert result["games_failed"] == 0

    # MLB schedule entries can roll into the next UTC day; check the fixture's
    # nominal date plus the day after to capture late-night starts.
    from datetime import date as _date

    base = _date.fromisoformat(fixture_date)
    written = list_todays_games(fixture_date, table_name=games_table_name) + list_todays_games(
        (base + timedelta(days=1)).isoformat(), table_name=games_table_name
    )
    assert len(written) == expected_total


# ── Self-throttle paths ──────────────────────────────────────────────


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_empty_schedule_returns_zero_writes(mock_fetch) -> None:
    mock_fetch.return_value = _empty_payload()

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["total_games_in_schedule"] == 0
    assert result["live_games_processed"] == 0
    assert result["final_games_processed"] == 0
    assert result["preview_games_processed"] == 0
    assert result["games_written"] == 0
    assert result["games_failed"] == 0


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_writes_final_and_preview_when_no_live(mock_fetch, games_table_name: str) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _payload([_final_raw(1, yesterday)], date_iso=yesterday),
            today: _payload([_preview_raw(2, today)], date_iso=today),
        }
    )

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["total_games_in_schedule"] == 2
    assert result["live_games_processed"] == 0
    assert result["final_games_processed"] == 1
    assert result["preview_games_processed"] == 1
    assert result["games_written"] == 2
    assert result["games_failed"] == 0


# ── Partial / total failure ──────────────────────────────────────────


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_partial_failure_one_date_succeeds(mock_fetch, games_table_name: str) -> None:
    """If one date errors, the other date's games are still written."""
    yesterday, today = _expected_dates()

    def side_effect(*_args, today=None, **_kwargs):
        if today is None:
            return _empty_payload()
        if today.isoformat() == yesterday:
            raise MLBAPIError("upstream 503 for yesterday", status=503)
        return _payload([_live_raw(42, today.isoformat())], date_iso=today.isoformat())

    mock_fetch.side_effect = side_effect

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["live_games_processed"] == 1
    assert result["games_written"] == 1
    assert result["games_failed"] == 0

    written = list_todays_games(today, table_name=games_table_name)
    assert {g.game_pk for g in written} == {42}


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_both_dates_fail_returns_failure_summary(mock_fetch) -> None:
    mock_fetch.side_effect = MLBAPIError("upstream 503", status=503)

    result = lambda_handler({}, None)

    assert result["ok"] is False
    assert result["reason"] == "mlb_api_error"
    assert result["games_written"] == 0
    assert result["games_failed"] == 0
    assert result["live_games_processed"] == 0
    assert result["final_games_processed"] == 0
    assert result["preview_games_processed"] == 0


# ── Per-game failure isolation ───────────────────────────────────────


@patch("ingest_live_games.handler.put_game")
@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_per_game_write_failure_does_not_crash_batch(mock_fetch, mock_put) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: _payload(
                [_live_raw(1, today), _live_raw(2, today), _live_raw(3, today)],
                date_iso=today,
            ),
        }
    )

    def selective_put(game, table_name=None):  # noqa: ARG001
        if game.game_pk == 2:
            raise RuntimeError("simulated write failure")

    mock_put.side_effect = selective_put

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["live_games_processed"] == 3
    assert result["games_written"] == 2
    assert result["games_failed"] == 1


# ── Idempotency / dedup ──────────────────────────────────────────────


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_idempotent_writes(mock_fetch, games_table_name: str) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: _payload([_live_raw(1, today), _live_raw(2, today)], date_iso=today),
        }
    )

    lambda_handler({}, None)
    after_first = list_todays_games(today, table_name=games_table_name)

    lambda_handler({}, None)
    after_second = list_todays_games(today, table_name=games_table_name)

    assert {g.game_pk for g in after_first} == {g.game_pk for g in after_second}
    assert len(after_first) == len(after_second) == 2


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_dedupes_same_game_pk_across_two_date_responses(mock_fetch, games_table_name: str) -> None:
    """Defensive: if MLB returns the same game under both date queries, write it once."""
    yesterday, today = _expected_dates()
    duplicate = _live_raw(777, today)
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _payload([duplicate], date_iso=yesterday),
            today: _payload([duplicate], date_iso=today),
        }
    )

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["total_games_in_schedule"] == 2
    assert result["live_games_processed"] == 1
    assert result["games_written"] == 1

    written = list_todays_games(today, table_name=games_table_name)
    assert len(written) == 1
    assert written[0].game_pk == 777


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_writes_preview_games(mock_fetch, games_table_name: str) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: _payload([_preview_raw(201, today), _preview_raw(202, today)], date_iso=today),
        }
    )

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["preview_games_processed"] == 2
    assert result["live_games_processed"] == 0
    assert result["final_games_processed"] == 0
    assert result["games_written"] == 2

    written = list_todays_games(today, table_name=games_table_name)
    assert {g.game_pk for g in written} == {201, 202}
    assert all(g.status == "preview" for g in written)


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_writes_final_games(mock_fetch, games_table_name: str) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: _payload([_final_raw(301, today), _final_raw(302, today)], date_iso=today),
        }
    )

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["final_games_processed"] == 2
    assert result["live_games_processed"] == 0
    assert result["preview_games_processed"] == 0
    assert result["games_written"] == 2

    written = list_todays_games(today, table_name=games_table_name)
    assert {g.game_pk for g in written} == {301, 302}
    assert all(g.status == "final" for g in written)
    # Final games should carry final scores through normalization.
    by_pk = {g.game_pk: g for g in written}
    assert by_pk[301].away_score == 5
    assert by_pk[301].home_score == 3


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_postponed_games_excluded(mock_fetch, games_table_name: str) -> None:
    """Postponed games carry abstractGameState=Preview but should be ingested
    along with regular Previews — the filter is by abstract state only."""
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: _payload(
                [_postponed_raw(401, today), _live_raw(402, today)],
                date_iso=today,
            ),
        }
    )

    result = lambda_handler({}, None)

    # Postponed shows up under abstract=Preview, so it's written as preview.
    assert result["ok"] is True
    assert result["live_games_processed"] == 1
    assert result["preview_games_processed"] == 1
    assert result["games_written"] == 2

    written = list_todays_games(today, table_name=games_table_name)
    by_pk = {g.game_pk: g for g in written}
    assert by_pk[401].status == "postponed"  # _map_status detects detailedState
    assert by_pk[402].status == "live"


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_live_to_final_transition_overwrites_in_place(mock_fetch, games_table_name: str) -> None:
    yesterday, today = _expected_dates()

    # First run: game is Live with score 3-2.
    live_record = _live_raw(555, today)
    live_record["teams"]["away"]["score"] = 3
    live_record["teams"]["home"]["score"] = 2
    mock_fetch.side_effect = _by_date_response(
        {yesterday: _empty_payload(), today: _payload([live_record], date_iso=today)}
    )
    lambda_handler({}, None)

    after_live = list_todays_games(today, table_name=games_table_name)
    assert len(after_live) == 1
    assert after_live[0].status == "live"
    assert after_live[0].away_score == 3
    assert after_live[0].home_score == 2

    # Second run: same gamePk, now Final with final score 5-3.
    final_record = _final_raw(555, today)
    mock_fetch.side_effect = _by_date_response(
        {yesterday: _empty_payload(), today: _payload([final_record], date_iso=today)}
    )
    lambda_handler({}, None)

    after_final = list_todays_games(today, table_name=games_table_name)
    assert len(after_final) == 1, "PK/SK is stable; same row overwritten in place"
    assert after_final[0].game_pk == 555
    assert after_final[0].status == "final"
    assert after_final[0].away_score == 5
    assert after_final[0].home_score == 3


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_summary_log_has_five_field_shape_on_writes(mock_fetch) -> None:
    yesterday, today = _expected_dates()
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _empty_payload(),
            today: _payload([_live_raw(1, today)], date_iso=today),
        }
    )

    result = lambda_handler({}, None)

    for key in (
        "live_games_processed",
        "final_games_processed",
        "preview_games_processed",
        "games_written",
        "games_failed",
    ):
        assert key in result, f"missing summary field: {key}"


@patch("ingest_live_games.handler.fetch_todays_schedule")
def test_dedup_prefers_today_over_yesterdays_stale_record(
    mock_fetch, games_table_name: str
) -> None:
    """Cross-date dedup: when the same gamePk appears under both queries,
    today's fresher record (Final) wins over yesterday's stale (Live)."""
    yesterday, today = _expected_dates()
    stale_live = _live_raw(888, yesterday)
    fresh_final = _final_raw(888, today)
    mock_fetch.side_effect = _by_date_response(
        {
            yesterday: _payload([stale_live], date_iso=yesterday),
            today: _payload([fresh_final], date_iso=today),
        }
    )

    result = lambda_handler({}, None)

    assert result["ok"] is True
    assert result["games_written"] == 1
    # The dedup keeps today's record, which is Final.
    assert result["final_games_processed"] == 1
    assert result["live_games_processed"] == 0

    # Game is keyed by its own gameDate's UTC date, so it lands under today.
    written = list_todays_games(today, table_name=games_table_name)
    assert len(written) == 1
    assert written[0].game_pk == 888
    assert written[0].status == "final"
