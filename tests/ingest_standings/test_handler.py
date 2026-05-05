"""Tests for the diamond-iq-ingest-standings Lambda."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from ingest_standings.handler import lambda_handler

pytestmark = pytest.mark.usefixtures("dynamodb_table")


def _team_record(
    team_id: int, name: str, wins: int, losses: int, **overrides: Any
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "team": {"id": team_id, "name": name},
        "wins": wins,
        "losses": losses,
        "winningPercentage": f".{int(1000 * wins / max(1, wins + losses)):03d}",
        "gamesBack": "-",
        "wildCardGamesBack": "-",
        "streak": {"streakCode": "W1", "streakType": "wins", "streakNumber": 1},
        "runDifferential": 10,
        "runsScored": 100,
        "runsAllowed": 90,
        "divisionRank": 1,
        "leagueRank": 1,
        "gamesPlayed": wins + losses,
        "records": {
            "splitRecords": [
                {"type": "home", "wins": wins // 2, "losses": losses // 2},
                {"type": "away", "wins": wins - wins // 2, "losses": losses - losses // 2},
                {"type": "lastTen", "wins": 7, "losses": 3},
            ],
        },
    }
    base.update(overrides)
    return base


def _division(
    div_id: int, div_name: str, league_id: int, league_name: str, teams: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "division": {"id": div_id, "name": div_name},
        "league": {"id": league_id, "name": league_name},
        "teamRecords": teams,
    }


def _full_records() -> list[dict[str, Any]]:
    """6 divisions × 5 teams = 30 teams."""
    out = []
    team_id = 100
    for div_id in range(201, 207):
        teams = []
        for i in range(5):
            teams.append(_team_record(team_id, f"Team {team_id}", 18 - i, 10 + i))
            team_id += 1
        out.append(
            _division(
                div_id,
                f"Div {div_id}",
                103 if div_id < 204 else 104,
                "AL" if div_id < 204 else "NL",
                teams,
            )
        )
    return out


def _read_all_standings(games_table_name: str, season: int) -> list[dict[str, Any]]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"STANDINGS#{season}"},
    )
    return resp.get("Items") or []


class _CWCapture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@pytest.fixture
def patched_now():
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_a, **_kw: None)


def test_happy_path_30_teams(games_table_name, patched_now):
    cw = _CWCapture()
    with patch("ingest_standings.handler.fetch_standings", return_value=_full_records()):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is True
    assert result["divisions_seen"] == 6
    assert result["teams_ingested"] == 30
    assert result["teams_failed"] == 0
    items = _read_all_standings(games_table_name, 2026)
    assert len(items) == 30


def test_pk_sk_shape(games_table_name, patched_now):
    with patch("ingest_standings.handler.fetch_standings", return_value=_full_records()):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_all_standings(games_table_name, 2026)
    item = items[0]
    assert item["PK"] == "STANDINGS#2026"
    assert item["SK"].startswith("STANDINGS#")
    assert int(item["SK"].split("#")[1]) == int(item["team_id"])


def test_empty_response_returns_ok_false(games_table_name, patched_now):
    cw = _CWCapture()
    with patch("ingest_standings.handler.fetch_standings", return_value=[]):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is False
    assert result["reason"] == "empty_standings"


def test_fetch_failure_returns_ok_false(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    cw = _CWCapture()
    with patch(
        "ingest_standings.handler.fetch_standings", side_effect=MLBAPIError("503", status=503)
    ):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is False
    assert result["reason"] == "standings_fetch_failed"


def test_partial_team_failure_increments_counter(games_table_name, patched_now):
    """Team without a numeric id is skipped; rest of league still ingests."""
    bad_team = {"team": {"id": "not_an_int", "name": "Borked"}}
    records = [
        _division(
            201, "AL East", 103, "American League", [bad_team] + [_team_record(101, "OK", 18, 10)]
        ),
    ]
    with patch("ingest_standings.handler.fetch_standings", return_value=records):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["teams_failed"] == 1
    assert result["teams_ingested"] == 1
    # ok is False because teams_failed > 0
    assert result["ok"] is False


def test_streak_code_extracted(games_table_name, patched_now):
    records = [
        _division(
            201,
            "AL East",
            103,
            "American League",
            [
                _team_record(
                    147,
                    "Yankees",
                    18,
                    10,
                    streak={"streakCode": "L3", "streakType": "losses", "streakNumber": 3},
                )
            ],
        ),
    ]
    with patch("ingest_standings.handler.fetch_standings", return_value=records):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_all_standings(games_table_name, 2026)
    assert items[0]["streak_code"] == "L3"


def test_last_ten_record_extracted(games_table_name, patched_now):
    records = [
        _division(
            201,
            "AL East",
            103,
            "American League",
            [
                _team_record(
                    147,
                    "Yankees",
                    18,
                    10,
                    records={
                        "splitRecords": [
                            {"type": "home", "wins": 9, "losses": 5},
                            {"type": "away", "wins": 9, "losses": 5},
                            {"type": "lastTen", "wins": 8, "losses": 2},
                        ],
                    },
                )
            ],
        ),
    ]
    with patch("ingest_standings.handler.fetch_standings", return_value=records):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_all_standings(games_table_name, 2026)
    assert items[0]["last_ten_record"] == "8-2"
    assert items[0]["home_record"] == "9-5"
    assert items[0]["away_record"] == "9-5"


def test_metrics_namespace_and_values(games_table_name, patched_now):
    cw = _CWCapture()
    with patch("ingest_standings.handler.fetch_standings", return_value=_full_records()):
        lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now)
    assert len(cw.calls) == 1
    assert cw.calls[0]["Namespace"] == "DiamondIQ/Standings"
    names = {m["MetricName"] for m in cw.calls[0]["MetricData"]}
    assert names == {"TeamsIngested", "TeamsFailed", "IngestionElapsedMs"}
    metric_map = {m["MetricName"]: m["Value"] for m in cw.calls[0]["MetricData"]}
    assert metric_map["TeamsIngested"] == 30
    assert metric_map["TeamsFailed"] == 0


def test_metric_emission_failure_does_not_break(games_table_name, patched_now):
    class BoomCW:
        def put_metric_data(self, **_kw):
            raise RuntimeError("CW down")

    with patch("ingest_standings.handler.fetch_standings", return_value=_full_records()):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=BoomCW(), now=patched_now
        )
    assert result["ok"] is True


def test_idempotent_rerun(games_table_name, patched_now):
    with patch("ingest_standings.handler.fetch_standings", return_value=_full_records()):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
        first = _read_all_standings(games_table_name, 2026)
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
        second = _read_all_standings(games_table_name, 2026)
    assert len(first) == 30
    assert len(second) == 30


def test_stores_division_and_league_metadata(games_table_name, patched_now):
    records = [
        _division(
            201,
            "American League East",
            103,
            "American League",
            [_team_record(147, "Yankees", 18, 10)],
        ),
    ]
    with patch("ingest_standings.handler.fetch_standings", return_value=records):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_all_standings(games_table_name, 2026)
    assert items[0]["division_id"] == 201
    assert items[0]["division_name"] == "American League East"
    assert items[0]["league_id"] == 103


def test_summary_includes_required_fields(games_table_name, patched_now):
    with patch("ingest_standings.handler.fetch_standings", return_value=_full_records()):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    for f in ("ok", "season", "divisions_seen", "teams_ingested", "teams_failed", "elapsed_ms"):
        assert f in result, f"missing {f}"
