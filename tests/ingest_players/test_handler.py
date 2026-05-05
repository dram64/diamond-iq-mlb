"""Tests for the diamond-iq-ingest-players Lambda."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from ingest_players.handler import lambda_handler

pytestmark = pytest.mark.usefixtures("dynamodb_table")


# ── Helpers ─────────────────────────────────────────────────────────


def _team(team_id: int, name: str = "Team") -> dict[str, Any]:
    return {"id": team_id, "name": name, "abbreviation": name[:3].upper()}


def _roster_entry(person_id: int, *, jersey: str = "99", pos: str = "RF") -> dict[str, Any]:
    return {
        "person": {"id": person_id, "fullName": f"Player {person_id}"},
        "jerseyNumber": jersey,
        "position": {"abbreviation": pos, "name": "Outfielder"},
        "status": {"code": "A"},
    }


def _person(person_id: int, *, with_age: bool = True) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": person_id,
        "fullName": f"Player {person_id}",
        "primaryNumber": "99",
        "height": "6' 4\"",
        "weight": 220,
        "batSide": {"code": "R"},
        "pitchHand": {"code": "R"},
        "primaryPosition": {"abbreviation": "RF"},
    }
    if with_age:
        base["currentAge"] = 30
    return base


def _read_player(person_id: int, table_name: str) -> dict[str, Any] | None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)
    return table.get_item(Key={"PK": "PLAYER#GLOBAL", "SK": f"PLAYER#{person_id}"}).get("Item")


def _read_roster(
    season: int, team_id: int, person_id: int, table_name: str
) -> dict[str, Any] | None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)
    return table.get_item(
        Key={"PK": f"ROSTER#{season}#{team_id}", "SK": f"ROSTER#{person_id}"}
    ).get("Item")


def _capture_cw_client():
    """A capture-only fake of the boto3 cloudwatch client."""
    calls: list[dict[str, Any]] = []

    class _CW:
        def put_metric_data(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {}

    return _CW(), calls


# ── Happy paths and flow ────────────────────────────────────────────


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_full_mode_end_to_end_writes_rosters_and_metadata(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147), _team(133)]
    mock_roster.side_effect = [
        [_roster_entry(101), _roster_entry(102)],
        [_roster_entry(201)],
    ]
    mock_people.return_value = [_person(101), _person(102), _person(201)]

    result = lambda_handler({}, None, table_name=games_table_name)

    assert result["ok"] is True
    assert result["mode"] == "full"
    assert result["teams_fetched"] == 2
    assert result["roster_entries_written"] == 3
    assert result["player_metadata_written"] == 3
    assert result["teams_failed"] == 0
    assert result["players_failed"] == 0


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_roster_only_mode_skips_metadata(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101)]

    result = lambda_handler({"mode": "roster_only"}, None, table_name=games_table_name)

    assert result["ok"] is True
    assert result["mode"] == "roster_only"
    assert result["roster_entries_written"] == 1
    assert result["player_metadata_written"] == 0
    mock_people.assert_not_called()


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_empty_roster_team_writes_nothing(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = []
    mock_people.return_value = []

    result = lambda_handler({}, None, table_name=games_table_name)
    assert result["roster_entries_written"] == 0
    assert result["player_metadata_written"] == 0


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_player_global_pk_and_sk_shape(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(592450)]
    mock_people.return_value = [_person(592450)]

    lambda_handler({}, None, table_name=games_table_name)
    item = _read_player(592450, games_table_name)
    assert item is not None
    assert item["PK"] == "PLAYER#GLOBAL"
    assert item["SK"] == "PLAYER#592450"
    assert int(item["person_id"]) == 592450
    assert item["full_name"] == "Player 592450"
    assert item["bat_side"] == "R"
    assert item["pitch_hand"] == "R"
    assert item["primary_position_abbr"] == "RF"
    assert "war" not in item  # WAR intentionally omitted; ADR 012 amendment


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_roster_pk_and_sk_with_ttl(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101, jersey="42", pos="SS")]
    mock_people.return_value = [_person(101)]

    before = int(time.time())
    lambda_handler({}, None, table_name=games_table_name)
    after = int(time.time())

    item = _read_roster(2026, 147, 101, games_table_name)
    assert item is not None
    assert item["PK"] == "ROSTER#2026#147"
    assert item["SK"] == "ROSTER#101"
    assert item["jersey_number"] == "42"
    assert item["position_abbr"] == "SS"
    assert int(item["team_id"]) == 147
    seven_days = 7 * 24 * 60 * 60
    ttl = int(item["ttl"])
    assert before + seven_days <= ttl <= after + seven_days + 60


# ── Error isolation ─────────────────────────────────────────────────


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_one_team_roster_fails_others_succeed(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147), _team(133), _team(111)]
    from shared.mlb_client import MLBAPIError

    def roster_side(team_id, season, **_kw):
        if team_id == 133:
            raise MLBAPIError("upstream 503", status=503)
        return [_roster_entry(team_id * 10 + 1)]

    mock_roster.side_effect = roster_side
    mock_people.return_value = [_person(1471), _person(1111)]

    result = lambda_handler({}, None, table_name=games_table_name)
    assert result["teams_fetched"] == 3
    assert result["teams_failed"] == 1
    assert result["roster_entries_written"] == 2  # only 147 and 111 succeeded
    assert result["ok"] is False  # any team failure flips ok


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_silent_id_drop_in_bulk_response_does_not_count_as_failure(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    """Bulk endpoint silently drops unknown IDs. Must NOT count as players_failed."""
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101), _roster_entry(102), _roster_entry(103)]
    # API returns only 2 of 3 requested IDs (silent drop).
    mock_people.return_value = [_person(101), _person(102)]

    result = lambda_handler({}, None, table_name=games_table_name)
    assert result["ok"] is True
    assert result["players_failed"] == 0  # silent drops don't count
    assert result["player_metadata_written"] == 2


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_metadata_batch_failure_counts_batch_as_failed(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    from shared.mlb_client import MLBAPIError

    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(i) for i in range(101, 104)]
    mock_people.side_effect = MLBAPIError("upstream 503", status=503)

    result = lambda_handler({}, None, table_name=games_table_name)
    assert result["players_failed"] == 3  # whole batch counted
    assert result["player_metadata_written"] == 0


@patch("ingest_players.handler.fetch_teams")
def test_teams_fetch_failure_aborts_run(mock_teams, games_table_name: str) -> None:
    from shared.mlb_client import MLBAPIError

    mock_teams.side_effect = MLBAPIError("upstream 503", status=503)
    result = lambda_handler({}, None, table_name=games_table_name)
    assert result["ok"] is False
    assert result["reason"] == "teams_fetch_failed"
    assert result["teams_fetched"] == 0


# ── Mode validation ─────────────────────────────────────────────────


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_default_mode_is_full(mock_teams, mock_roster, mock_people, games_table_name: str) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101)]
    mock_people.return_value = [_person(101)]

    result = lambda_handler({}, None, table_name=games_table_name)
    assert result["mode"] == "full"
    mock_people.assert_called_once()


def test_unknown_mode_rejects(games_table_name: str) -> None:
    result = lambda_handler({"mode": "wat"}, None, table_name=games_table_name)
    assert result["ok"] is False
    assert result["reason"] == "unknown_mode"


# ── Custom metrics ──────────────────────────────────────────────────


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_metric_emission_writes_to_correct_namespace(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101)]
    mock_people.return_value = [_person(101)]
    cw, calls = _capture_cw_client()

    lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=cw)
    assert len(calls) == 1
    assert calls[0]["Namespace"] == "DiamondIQ/Players"
    metric_names = {m["MetricName"] for m in calls[0]["MetricData"]}
    assert metric_names == {
        "PlayersIngestedCount",
        "RostersIngestedCount",
        "TeamsFailedCount",
        "PlayersFailedCount",
    }


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_metric_values_match_summary(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101), _roster_entry(102)]
    mock_people.return_value = [_person(101), _person(102)]
    cw, calls = _capture_cw_client()

    result = lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=cw)
    by_name = {m["MetricName"]: m["Value"] for m in calls[0]["MetricData"]}
    assert by_name["RostersIngestedCount"] == result["roster_entries_written"]
    assert by_name["PlayersIngestedCount"] == result["player_metadata_written"]


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_metric_emission_failure_does_not_break_lambda(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101)]
    mock_people.return_value = [_person(101)]

    class _ExplodingCW:
        def put_metric_data(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("CloudWatch unavailable")

    result = lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=_ExplodingCW())
    assert result["ok"] is True
    assert result["roster_entries_written"] == 1


# ── Bulk batching ───────────────────────────────────────────────────


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_metadata_batches_are_50_at_a_time(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    """75 players → 2 calls to fetch_people_bulk (50 + 25)."""
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(i) for i in range(1000, 1075)]

    def people_side(person_ids, **_kw):
        return [_person(pid) for pid in person_ids]

    mock_people.side_effect = people_side

    lambda_handler({}, None, table_name=games_table_name)
    assert mock_people.call_count == 2
    first_chunk = mock_people.call_args_list[0].args[0]
    second_chunk = mock_people.call_args_list[1].args[0]
    assert len(first_chunk) == 50
    assert len(second_chunk) == 25


# ── Summary log shape ───────────────────────────────────────────────


@patch("ingest_players.handler.fetch_people_bulk")
@patch("ingest_players.handler.fetch_roster")
@patch("ingest_players.handler.fetch_teams")
def test_summary_includes_all_required_fields(
    mock_teams, mock_roster, mock_people, games_table_name: str
) -> None:
    mock_teams.return_value = [_team(147)]
    mock_roster.return_value = [_roster_entry(101)]
    mock_people.return_value = [_person(101)]

    result = lambda_handler({}, None, table_name=games_table_name)
    for key in (
        "ok",
        "season",
        "mode",
        "teams_fetched",
        "roster_entries_written",
        "player_metadata_written",
        "teams_failed",
        "players_failed",
        "api_calls_made",
        "elapsed_ms",
    ):
        assert key in result, f"missing summary field: {key}"
    assert result["api_calls_made"] >= 1 + 1 + 1  # teams + roster + bulk metadata
