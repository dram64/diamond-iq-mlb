"""Tests for the diamond-iq-ingest-team-stats Lambda."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from ingest_team_stats.handler import lambda_handler

pytestmark = pytest.mark.usefixtures("dynamodb_table")


def _team(team_id: int, name: str = "Sample") -> dict[str, Any]:
    return {"id": team_id, "name": name}


def _hitting_stat() -> dict[str, Any]:
    return {
        "gamesPlayed": 31,
        "atBats": 1013,
        "plateAppearances": 1170,
        "runs": 153,
        "hits": 232,
        "doubles": 46,
        "triples": 4,
        "homeRuns": 48,
        "rbi": 145,
        "baseOnBalls": 138,
        "strikeOuts": 279,
        "stolenBases": 32,
        "caughtStealing": 9,
        "hitByPitch": 9,
        "sacFlies": 9,
        "totalBases": 430,
        "avg": ".229",
        "obp": ".324",
        "slg": ".424",
        "ops": ".748",
        "babip": ".265",
    }


def _pitching_stat() -> dict[str, Any]:
    return {
        "gamesPlayed": 31,
        "gamesStarted": 31,
        "completeGames": 0,
        "shutouts": 5,
        "wins": 20,
        "losses": 11,
        "saves": 9,
        "saveOpportunities": 14,
        "blownSaves": 5,
        "holds": 14,
        "inningsPitched": "274.2",
        "hits": 227,
        "runs": 106,
        "earnedRuns": 95,
        "homeRuns": 26,
        "baseOnBalls": 85,
        "strikeOuts": 270,
        "battersFaced": 1129,
        "era": "3.11",
        "whip": "1.14",
        "avg": ".222",
        "obp": ".289",
        "slg": ".344",
        "ops": ".633",
        "hitsPer9Inn": "7.44",
        "homeRunsPer9": "0.85",
    }


def _read_team(games_table_name: str, season: int, team_id: int) -> dict[str, Any]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    return (
        table.get_item(Key={"PK": f"TEAMSTATS#{season}", "SK": f"TEAMSTATS#{team_id}"}).get("Item")
        or {}
    )


def _read_all(games_table_name: str, season: int) -> list[dict[str, Any]]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"TEAMSTATS#{season}"},
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
    teams = [_team(100 + i, f"Team {i}") for i in range(30)]
    cw = _CWCapture()
    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch(
            "ingest_team_stats.handler.fetch_team_season_stats",
            return_value={"hitting": _hitting_stat(), "pitching": _pitching_stat()},
        ),
    ):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is True
    assert result["teams_total"] == 30
    assert result["teams_ingested"] == 30
    assert result["teams_failed"] == 0
    assert len(_read_all(games_table_name, 2026)) == 30


def test_pk_sk_shape_and_projection(games_table_name, patched_now):
    teams = [_team(147, "Yankees")]
    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch(
            "ingest_team_stats.handler.fetch_team_season_stats",
            return_value={"hitting": _hitting_stat(), "pitching": _pitching_stat()},
        ),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    item = _read_team(games_table_name, 2026, 147)
    assert item["PK"] == "TEAMSTATS#2026"
    assert item["SK"] == "TEAMSTATS#147"
    assert int(item["team_id"]) == 147
    assert item["team_name"] == "Yankees"
    assert item["hitting"]["avg"] == ".229"
    assert int(item["hitting"]["home_runs"]) == 48
    assert int(item["hitting"]["stolen_bases"]) == 32
    assert item["pitching"]["era"] == "3.11"
    assert int(item["pitching"]["wins"]) == 20
    assert int(item["pitching"]["strikeouts"]) == 270
    assert item["pitching"]["opp_avg"] == ".222"


def test_per_team_failure_other_teams_succeed(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    teams = [_team(101, "A"), _team(102, "B"), _team(103, "C")]

    def stats_side(team_id: int, season: int):
        if team_id == 102:
            raise MLBAPIError("503", status=503)
        return {"hitting": _hitting_stat(), "pitching": _pitching_stat()}

    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch("ingest_team_stats.handler.fetch_team_season_stats", side_effect=stats_side),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["teams_ingested"] == 2
    assert result["teams_failed"] == 1
    assert result["ok"] is False  # any failure flips ok=False per pattern


def test_teams_fetch_failure_aborts(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    cw = _CWCapture()
    with patch("ingest_team_stats.handler.fetch_teams", side_effect=MLBAPIError("503", status=503)):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is False
    assert result["reason"] == "teams_fetch_failed"
    assert result["teams_ingested"] == 0


def test_idempotent_rerun(games_table_name, patched_now):
    teams = [_team(147, "Yankees")]
    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch(
            "ingest_team_stats.handler.fetch_team_season_stats",
            return_value={"hitting": _hitting_stat(), "pitching": _pitching_stat()},
        ),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_all(games_table_name, 2026)
    assert len(items) == 1


def test_partial_groups_handled(games_table_name, patched_now):
    """If MLB returns only one of {hitting, pitching}, the missing side is null."""
    teams = [_team(147, "Yankees")]
    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch(
            "ingest_team_stats.handler.fetch_team_season_stats",
            return_value={"hitting": _hitting_stat()},  # no pitching
        ),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    item = _read_team(games_table_name, 2026, 147)
    assert item["pitching"] is None
    assert item["hitting"]["avg"] == ".229"


def test_metrics_namespace_and_values(games_table_name, patched_now):
    teams = [_team(100), _team(101)]
    cw = _CWCapture()
    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch(
            "ingest_team_stats.handler.fetch_team_season_stats",
            return_value={"hitting": _hitting_stat(), "pitching": _pitching_stat()},
        ),
    ):
        lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now)
    assert cw.calls[0]["Namespace"] == "DiamondIQ/TeamStats"
    names = {m["MetricName"] for m in cw.calls[0]["MetricData"]}
    assert names == {"TeamsIngested", "TeamsFailed", "IngestionElapsedMs"}
    metric_map = {m["MetricName"]: m["Value"] for m in cw.calls[0]["MetricData"]}
    assert metric_map["TeamsIngested"] == 2


def test_metric_emission_failure_does_not_break(games_table_name, patched_now):
    class BoomCW:
        def put_metric_data(self, **_kw):
            raise RuntimeError("CW down")

    teams = [_team(100)]
    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch(
            "ingest_team_stats.handler.fetch_team_season_stats",
            return_value={"hitting": _hitting_stat(), "pitching": _pitching_stat()},
        ),
    ):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=BoomCW(), now=patched_now
        )
    assert result["ok"] is True


def test_summary_includes_required_fields(games_table_name, patched_now):
    teams = [_team(100)]
    with (
        patch("ingest_team_stats.handler.fetch_teams", return_value=teams),
        patch(
            "ingest_team_stats.handler.fetch_team_season_stats",
            return_value={"hitting": _hitting_stat(), "pitching": _pitching_stat()},
        ),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    for f in ("ok", "season", "teams_total", "teams_ingested", "teams_failed", "elapsed_ms"):
        assert f in result, f"missing {f}"
