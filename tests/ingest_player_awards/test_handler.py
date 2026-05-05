"""Tests for the diamond-iq-ingest-player-awards Lambda."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from ingest_player_awards.handler import _aggregate, lambda_handler

pytestmark = pytest.mark.usefixtures("dynamodb_table")


def _award(award_id: str, season: str | int) -> dict[str, Any]:
    return {"id": award_id, "season": str(season)}


@pytest.fixture
def patched_now():
    return datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_a, **_kw: None)


def _seed_player(games_table_name: str, person_id: int, name: str = "Test Player") -> None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    table.put_item(
        Item={
            "PK": "PLAYER#GLOBAL",
            "SK": f"PLAYER#{person_id}",
            "person_id": person_id,
            "full_name": name,
        }
    )


def _read_award(games_table_name: str, person_id: int) -> dict[str, Any]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    return (
        table.get_item(Key={"PK": "AWARDS#GLOBAL", "SK": f"AWARDS#{person_id}"}).get("Item") or {}
    )


class _CWCapture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


# ── Pure-aggregator tests ──────────────────────────────────────────────


def test_aggregate_filters_minor_league_noise():
    raw = [
        _award("SALMSAS", 2014),  # SAL Mid-Season All-Star — drop
        _award("MLBASG", 2017),
        _award("ALMVP", 2017),
    ]
    summary = _aggregate(raw)
    assert summary["total_awards"] == 2
    assert summary["all_star_count"] == 1
    assert summary["all_star_years"] == [2017]
    assert summary["mvp_count"] == 1
    assert summary["mvp_years"] == [2017]


def test_aggregate_dedupes_repeat_award_in_same_year():
    """If the upstream lists the same All-Star Game twice in the same year
    (e.g. selection + game), we count the year once."""
    raw = [_award("MLBASG", 2017), _award("MLBASG", 2017), _award("MLBASG", 2018)]
    summary = _aggregate(raw)
    assert summary["all_star_count"] == 2  # distinct years
    assert summary["all_star_years"] == [2017, 2018]


def test_aggregate_handles_empty_list():
    summary = _aggregate([])
    assert summary["total_awards"] == 0
    assert summary["all_star_count"] == 0
    assert summary["mvp_years"] == []


def test_aggregate_skips_unknown_id():
    summary = _aggregate([_award("RANDOM_UNKNOWN", 2020)])
    assert summary["total_awards"] == 0


def test_aggregate_classifies_world_series_ring():
    summary = _aggregate([_award("WSC", 2009), _award("WSC", 2017)])
    assert summary["world_series_count"] == 2
    assert summary["world_series_years"] == [2009, 2017]


def test_aggregate_classifies_all_categories():
    raw = [
        _award("ALMVP", 2017),
        _award("NLCY", 2020),
        _award("ALROY", 2013),
        _award("ALGG", 2019),
        _award("ALSS", 2021),
        _award("MLBASG", 2018),
        _award("WSC", 2009),
    ]
    summary = _aggregate(raw)
    assert summary["mvp_count"] == 1
    assert summary["cy_young_count"] == 1
    assert summary["rookie_of_the_year_count"] == 1
    assert summary["gold_glove_count"] == 1
    assert summary["silver_slugger_count"] == 1
    assert summary["all_star_count"] == 1
    assert summary["world_series_count"] == 1


# ── Lambda-handler tests ───────────────────────────────────────────────


def test_happy_path_writes_award_row(games_table_name, patched_now):
    _seed_player(games_table_name, 592450, "Aaron Judge")
    awards_raw = [_award("ALMVP", 2024), _award("MLBASG", 2017), _award("MLBASG", 2018)]
    cw = _CWCapture()
    with patch("ingest_player_awards.handler.fetch_player_awards", return_value=awards_raw):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is True
    assert result["players_total"] == 1
    assert result["players_ingested"] == 1
    item = _read_award(games_table_name, 592450)
    assert item["PK"] == "AWARDS#GLOBAL"
    assert item["SK"] == "AWARDS#592450"
    assert int(item["mvp_count"]) == 1
    assert int(item["all_star_count"]) == 2


def test_per_player_failure_continues(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    _seed_player(games_table_name, 1)
    _seed_player(games_table_name, 2)
    _seed_player(games_table_name, 3)

    def side(person_id: int):
        if person_id == 2:
            raise MLBAPIError("503", status=503)
        return [_award("MLBASG", 2024)]

    with patch("ingest_player_awards.handler.fetch_player_awards", side_effect=side):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["players_ingested"] == 2
    assert result["players_failed"] == 1


def test_404_is_treated_as_zero_awards(games_table_name, patched_now):
    """A 404 from MLB means the player has no recorded awards. Write the
    empty summary so the API serves a deterministic shape."""
    from shared.mlb_client import MLBNotFoundError

    _seed_player(games_table_name, 1)
    with patch(
        "ingest_player_awards.handler.fetch_player_awards",
        side_effect=MLBNotFoundError("no awards", status=404),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["players_ingested"] == 1
    assert result["players_failed"] == 0
    item = _read_award(games_table_name, 1)
    assert int(item["total_awards"]) == 0


def test_idempotent_rerun(games_table_name, patched_now):
    _seed_player(games_table_name, 1)
    awards_raw = [_award("ALMVP", 2024)]
    with patch("ingest_player_awards.handler.fetch_player_awards", return_value=awards_raw):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": "AWARDS#GLOBAL"},
    )
    assert len(resp.get("Items") or []) == 1


def test_metrics_namespace_and_values(games_table_name, patched_now):
    _seed_player(games_table_name, 1)
    cw = _CWCapture()
    with patch("ingest_player_awards.handler.fetch_player_awards", return_value=[]):
        lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now)
    assert cw.calls[0]["Namespace"] == "DiamondIQ/PlayerAwards"
    names = {m["MetricName"] for m in cw.calls[0]["MetricData"]}
    assert names == {"PlayersTotal", "PlayersIngested", "PlayersFailed", "IngestionElapsedMs"}


def test_metric_emission_failure_does_not_break(games_table_name, patched_now):
    class BoomCW:
        def put_metric_data(self, **_kw):
            raise RuntimeError("CW down")

    _seed_player(games_table_name, 1)
    with patch("ingest_player_awards.handler.fetch_player_awards", return_value=[]):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=BoomCW(), now=patched_now
        )
    assert result["ok"] is True


def test_no_players_returns_zero_summary(games_table_name, patched_now):
    """Empty PLAYER#GLOBAL partition → ok=False (no work done) but no crash."""
    cw = _CWCapture()
    with patch("ingest_player_awards.handler.fetch_player_awards") as fetch_mock:
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    fetch_mock.assert_not_called()
    assert result["players_total"] == 0
    assert result["players_ingested"] == 0
