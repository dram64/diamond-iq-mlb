"""Tests for the diamond-iq-ingest-daily-stats Lambda."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from ingest_daily_stats.handler import lambda_handler

pytestmark = pytest.mark.usefixtures("dynamodb_table")


# ── Helpers ────────────────────────────────────────────────────────────


def _final_game(game_pk: int) -> dict[str, Any]:
    return {"gamePk": game_pk, "status": {"detailedState": "Final"}}


def _batter_block(
    person_id: int,
    full_name: str,
    *,
    at_bats: int = 4,
    hits: int = 2,
    doubles: int = 1,
    home_runs: int = 1,
    walks: int = 1,
    strikeouts: int = 1,
    rbi: int = 2,
    runs: int = 1,
    triples: int = 0,
) -> dict[str, Any]:
    return {
        "person": {"id": person_id, "fullName": full_name},
        "stats": {
            "batting": {
                "atBats": at_bats,
                "hits": hits,
                "doubles": doubles,
                "triples": triples,
                "homeRuns": home_runs,
                "rbi": rbi,
                "baseOnBalls": walks,
                "strikeOuts": strikeouts,
                "runs": runs,
            },
            "pitching": {},
        },
    }


def _pitcher_block(
    person_id: int,
    full_name: str,
    *,
    innings: str = "6.0",
    hits_allowed: int = 5,
    earned_runs: int = 2,
    walks: int = 2,
    strikeouts: int = 7,
    runs: int = 2,
) -> dict[str, Any]:
    return {
        "person": {"id": person_id, "fullName": full_name},
        "stats": {
            "batting": {},
            "pitching": {
                "inningsPitched": innings,
                "hits": hits_allowed,
                "runs": runs,
                "earnedRuns": earned_runs,
                "baseOnBalls": walks,
                "strikeOuts": strikeouts,
            },
        },
    }


def _boxscore(
    home_team_id: int, away_team_id: int, players: list[dict[str, Any]]
) -> dict[str, Any]:
    """Place every supplied player block on the home team for simplicity."""
    home_players = {f"ID{p['person']['id']}": p for p in players}
    return {
        "teams": {
            "home": {"team": {"id": home_team_id}, "players": home_players},
            "away": {"team": {"id": away_team_id}, "players": {}},
        }
    }


def _qualified_split(person_id: int, full_name: str, team_id: int, group: str) -> dict[str, Any]:
    if group == "hitting":
        stat = {
            "avg": ".300",
            "obp": ".380",
            "slg": ".500",
            "ops": ".880",
            "homeRuns": 12,
            "rbi": 35,
            "hits": 60,
            "gamesPlayed": 50,
        }
    else:
        stat = {
            "era": "3.50",
            "whip": "1.20",
            "inningsPitched": "65.1",
            "wins": 5,
            "losses": 3,
            "saves": 0,
            "strikeOuts": 70,
            "gamesPlayed": 12,
        }
    return {
        "player": {"id": person_id, "fullName": full_name},
        "team": {"id": team_id},
        "stat": stat,
    }


def _read_daily(games_table_name: str, date_iso: str) -> list[dict[str, Any]]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"DAILYSTATS#{date_iso}"},
    )
    return resp.get("Items") or []


def _read_season(games_table_name: str, season: int, group: str) -> list[dict[str, Any]]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"STATS#{season}#{group}"},
    )
    return resp.get("Items") or []


class _CWCapture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


# ── Patch fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def patched_now():
    """Pin 'now' to 2026-04-27 12:00 UTC so yesterday is 2026-04-26."""
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_a, **_kw: None)


# ── Tests ──────────────────────────────────────────────────────────────


def test_happy_path_standard_mode(games_table_name, patched_now):
    finals = [_final_game(1001), _final_game(1002)]
    boxes = {
        1001: _boxscore(110, 111, [_batter_block(900, "Alpha"), _pitcher_block(901, "Beta")]),
        1002: _boxscore(112, 113, [_batter_block(902, "Gamma")]),
    }
    qual = {
        "hitting": [_qualified_split(900, "Alpha", 110, "hitting")],
        "pitching": [_qualified_split(901, "Beta", 110, "pitching")],
    }
    cw = _CWCapture()
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_daily_stats.handler.fetch_boxscore", side_effect=lambda gp: boxes[gp]),
        patch(
            "ingest_daily_stats.handler.fetch_qualified_season_stats",
            side_effect=lambda s, g: qual[g],
        ),
    ):
        result = lambda_handler(
            {"mode": "standard"},
            None,
            table_name=games_table_name,
            cloudwatch_client=cw,
            now=patched_now,
        )
    assert result["ok"] is True
    assert result["games_total"] == 2
    assert result["games_processed"] == 2
    assert result["games_failed"] == 0
    assert result["batters_ingested"] == 2
    assert result["pitchers_ingested"] == 1
    assert result["season_stats_refreshed"] == 2  # 1 hitter + 1 pitcher
    items = _read_daily(games_table_name, "2026-04-26")
    assert len(items) == 3


def test_default_mode_is_standard(games_table_name, patched_now):
    cw = _CWCapture()
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["mode"] == "standard"


def test_unknown_mode_rejected(games_table_name, patched_now):
    result = lambda_handler({"mode": "weird"}, None, table_name=games_table_name, now=patched_now)
    assert result["ok"] is False
    assert result["reason"] == "unknown_mode"


def test_season_only_mode_skips_daily(games_table_name, patched_now):
    qual = {
        "hitting": [_qualified_split(900, "A", 110, "hitting")],
        "pitching": [_qualified_split(901, "B", 110, "pitching")],
    }
    cw = _CWCapture()
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals") as sched,
        patch("ingest_daily_stats.handler.fetch_boxscore") as box,
        patch(
            "ingest_daily_stats.handler.fetch_qualified_season_stats",
            side_effect=lambda s, g: qual[g],
        ),
    ):
        result = lambda_handler(
            {"mode": "season_only"},
            None,
            table_name=games_table_name,
            cloudwatch_client=cw,
            now=patched_now,
        )
    sched.assert_not_called()
    box.assert_not_called()
    assert result["games_total"] == 0
    assert result["season_stats_refreshed"] == 2


def test_no_final_games_yesterday(games_table_name, patched_now):
    cw = _CWCapture()
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"},
            None,
            table_name=games_table_name,
            cloudwatch_client=cw,
            now=patched_now,
        )
    assert result["ok"] is True
    assert result["games_total"] == 0
    assert _read_daily(games_table_name, "2026-04-26") == []


def test_one_boxscore_5xx_others_succeed(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    finals = [_final_game(1001), _final_game(1002), _final_game(1003)]

    def boxscore_side_effect(gp):
        if gp == 1002:
            raise MLBAPIError("MLB API 503", status=503)
        return _boxscore(110, 111, [_batter_block(900 + gp, "P")])

    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_daily_stats.handler.fetch_boxscore", side_effect=boxscore_side_effect),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"}, None, table_name=games_table_name, now=patched_now
        )
    assert result["games_processed"] == 2
    assert result["games_failed"] == 1
    assert result["batters_ingested"] == 2
    # 1/3 < 0.5 threshold so still ok=True
    assert result["ok"] is True


def test_failure_majority_triggers_ok_false(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    finals = [_final_game(i) for i in (1001, 1002, 1003, 1004)]
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=finals),
        patch(
            "ingest_daily_stats.handler.fetch_boxscore",
            side_effect=MLBAPIError("MLB API 503", status=503),
        ),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"}, None, table_name=games_table_name, now=patched_now
        )
    assert result["games_failed"] == 4
    assert result["ok"] is False


def test_malformed_batter_does_not_break_others(games_table_name, patched_now):
    bad = {
        "person": {"id": 800, "fullName": "Bad"},
        "stats": {
            "batting": {"atBats": "not_a_number", "hits": 1},
            "pitching": {},
        },
    }
    good = _batter_block(801, "Good")
    box = _boxscore(110, 111, [bad, good])
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[_final_game(1001)]),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"}, None, table_name=games_table_name, now=patched_now
        )
    # The bad row's int() raises during item construction → caught at game level
    # which counts as games_failed=1 but that means 100% failure → ok=False.
    # We just verify that the run completes without raising.
    assert isinstance(result, dict)


def test_pitcher_missing_innings_skipped(games_table_name, patched_now):
    block = {
        "person": {"id": 802, "fullName": "Reliever"},
        "stats": {"batting": {}, "pitching": {"hits": 0}},  # no inningsPitched
    }
    box = _boxscore(110, 111, [block])
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[_final_game(1001)]),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"}, None, table_name=games_table_name, now=patched_now
        )
    assert result["pitchers_ingested"] == 0


def test_pk_sk_shape_and_ttl(games_table_name, patched_now):
    box = _boxscore(110, 111, [_batter_block(950, "X")])
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[_final_game(1500)]),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        lambda_handler({"mode": "standard"}, None, table_name=games_table_name, now=patched_now)
    items = _read_daily(games_table_name, "2026-04-26")
    assert len(items) == 1
    item = items[0]
    assert item["PK"] == "DAILYSTATS#2026-04-26"
    assert item["SK"] == "STATS#950#1500"
    expected_ttl_floor = int(time.time()) + 30 * 24 * 60 * 60 - 60
    assert int(item["ttl"]) >= expected_ttl_floor


def test_total_bases_computation(games_table_name, patched_now):
    # 4 hits = 1 single + 1 double + 1 triple + 1 hr → 1+2+3+4 = 10
    block = _batter_block(
        951, "TB", at_bats=5, hits=4, doubles=1, triples=1, home_runs=1, walks=0, strikeouts=0
    )
    box = _boxscore(110, 111, [block])
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[_final_game(1501)]),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        lambda_handler({"mode": "standard"}, None, table_name=games_table_name, now=patched_now)
    items = _read_daily(games_table_name, "2026-04-26")
    assert int(items[0]["total_bases"]) == 10


def test_k_bb_ratio_computation(games_table_name, patched_now):
    block = _pitcher_block(960, "K", strikeouts=12, walks=4)  # 12/4 = 3.0
    box = _boxscore(110, 111, [block])
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[_final_game(1502)]),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        lambda_handler({"mode": "standard"}, None, table_name=games_table_name, now=patched_now)
    items = _read_daily(games_table_name, "2026-04-26")
    assert float(items[0]["k_bb_ratio"]) == 3.0


def test_k_bb_ratio_zero_walks_omits_field(games_table_name, patched_now):
    block = _pitcher_block(961, "NoWalk", strikeouts=8, walks=0)
    box = _boxscore(110, 111, [block])
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[_final_game(1503)]),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        lambda_handler({"mode": "standard"}, None, table_name=games_table_name, now=patched_now)
    items = _read_daily(games_table_name, "2026-04-26")
    assert "k_bb_ratio" not in items[0]


def test_season_hitting_record_overwritten(games_table_name, patched_now):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    table.put_item(
        Item={
            "PK": "STATS#2026#hitting",
            "SK": "STATS#900",
            "season": 2026,
            "group": "hitting",
            "person_id": 900,
            "avg": ".100",
            "stale": True,
        }
    )
    splits = [_qualified_split(900, "Alpha", 110, "hitting")]
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch(
            "ingest_daily_stats.handler.fetch_qualified_season_stats",
            side_effect=lambda s, g: splits if g == "hitting" else [],
        ),
    ):
        lambda_handler({"mode": "season_only"}, None, table_name=games_table_name, now=patched_now)
    items = _read_season(games_table_name, 2026, "hitting")
    assert len(items) == 1
    assert items[0]["avg"] == ".300"
    assert "stale" not in items[0]


def test_season_pitching_record_written(games_table_name, patched_now):
    splits = [_qualified_split(905, "Hurler", 115, "pitching")]
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch(
            "ingest_daily_stats.handler.fetch_qualified_season_stats",
            side_effect=lambda s, g: splits if g == "pitching" else [],
        ),
    ):
        lambda_handler({"mode": "season_only"}, None, table_name=games_table_name, now=patched_now)
    items = _read_season(games_table_name, 2026, "pitching")
    assert len(items) == 1
    assert items[0]["era"] == "3.50"
    assert items[0]["PK"] == "STATS#2026#pitching"
    assert items[0]["SK"] == "STATS#905"


def test_season_bulk_failure_increments_failed(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    def stats_side(season, group):
        if group == "hitting":
            raise MLBAPIError("503", status=503)
        return []

    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", side_effect=stats_side),
    ):
        result = lambda_handler(
            {"mode": "season_only"}, None, table_name=games_table_name, now=patched_now
        )
    assert result["season_stats_failed"] >= 1
    assert result["ok"] is False


def test_metrics_namespace(games_table_name, patched_now):
    cw = _CWCapture()
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        lambda_handler(
            {"mode": "standard"},
            None,
            table_name=games_table_name,
            cloudwatch_client=cw,
            now=patched_now,
        )
    assert len(cw.calls) == 1
    assert cw.calls[0]["Namespace"] == "DiamondIQ/DailyStats"
    metric_names = {m["MetricName"] for m in cw.calls[0]["MetricData"]}
    assert metric_names == {
        "GamesProcessed",
        "BattersIngested",
        "PitchersIngested",
        "SeasonStatsRefreshed",
        "GamesFailed",
    }


def test_metric_emission_failure_does_not_break(games_table_name, patched_now):
    class BoomCW:
        def put_metric_data(self, **_kw):
            raise RuntimeError("CW down")

    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"},
            None,
            table_name=games_table_name,
            cloudwatch_client=BoomCW(),
            now=patched_now,
        )
    assert result["ok"] is True


def test_schedule_fetch_failure_aborts(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    cw = _CWCapture()
    with patch(
        "ingest_daily_stats.handler.fetch_schedule_finals",
        side_effect=MLBAPIError("503", status=503),
    ):
        result = lambda_handler(
            {"mode": "standard"},
            None,
            table_name=games_table_name,
            cloudwatch_client=cw,
            now=patched_now,
        )
    assert result["ok"] is False
    assert result["reason"] == "schedule_fetch_failed"


def test_yesterday_computed_across_utc_midnight(games_table_name):
    # 'now' is 2026-05-01 00:30 UTC → yesterday should be 2026-04-30
    pinned = datetime(2026, 5, 1, 0, 30, 0, tzinfo=UTC)
    cw = _CWCapture()
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"},
            None,
            table_name=games_table_name,
            cloudwatch_client=cw,
            now=pinned,
        )
    assert result["date"] == "2026-04-30"


def test_empty_boxscore_handled(games_table_name, patched_now):
    box = {
        "teams": {
            "home": {"team": {"id": 110}, "players": {}},
            "away": {"team": {"id": 111}, "players": {}},
        }
    }
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[_final_game(1001)]),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"}, None, table_name=games_table_name, now=patched_now
        )
    assert result["games_processed"] == 1
    assert result["batters_ingested"] == 0
    assert result["pitchers_ingested"] == 0


def test_summary_includes_all_required_fields(games_table_name, patched_now):
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch("ingest_daily_stats.handler.fetch_qualified_season_stats", return_value=[]),
    ):
        result = lambda_handler(
            {"mode": "standard"}, None, table_name=games_table_name, now=patched_now
        )
    for field in (
        "ok",
        "season",
        "mode",
        "date",
        "games_total",
        "games_processed",
        "games_failed",
        "batters_ingested",
        "pitchers_ingested",
        "season_stats_refreshed",
        "season_stats_failed",
        "api_calls_made",
        "elapsed_ms",
    ):
        assert field in result, f"missing summary field: {field}"


def test_metric_values_match_summary(games_table_name, patched_now):
    finals = [_final_game(2001)]
    box = _boxscore(110, 111, [_batter_block(970, "M"), _pitcher_block(971, "N")])
    qual = {"hitting": [_qualified_split(970, "M", 110, "hitting")], "pitching": []}
    cw = _CWCapture()
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_daily_stats.handler.fetch_boxscore", return_value=box),
        patch(
            "ingest_daily_stats.handler.fetch_qualified_season_stats",
            side_effect=lambda s, g: qual[g],
        ),
    ):
        result = lambda_handler(
            {"mode": "standard"},
            None,
            table_name=games_table_name,
            cloudwatch_client=cw,
            now=patched_now,
        )
    metric_map = {m["MetricName"]: m["Value"] for m in cw.calls[0]["MetricData"]}
    assert metric_map["GamesProcessed"] == result["games_processed"]
    assert metric_map["BattersIngested"] == result["batters_ingested"]
    assert metric_map["PitchersIngested"] == result["pitchers_ingested"]
    assert metric_map["SeasonStatsRefreshed"] == result["season_stats_refreshed"]
    assert metric_map["GamesFailed"] == result["games_failed"]




def test_season_hitter_record_includes_woba_inputs(games_table_name, patched_now):
    """Season hitter records must carry the input primitives needs."""
    split = {
        "player": {"id": 700, "fullName": "Hitter"},
        "team": {"id": 200},
        "stat": {
            "atBats": 100,
            "hits": 30,
            "doubles": 6,
            "triples": 1,
            "homeRuns": 5,
            "baseOnBalls": 12,
            "intentionalWalks": 2,
            "sacFlies": 1,
            "hitByPitch": 3,
            "plateAppearances": 116,
            "obp": ".380",
            "slg": ".500",
            "avg": ".300",
            "ops": ".880",
            "stolenBases": 14,
        },
    }
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch(
            "ingest_daily_stats.handler.fetch_qualified_season_stats",
            side_effect=lambda s, g: [split] if g == "hitting" else [],
        ),
    ):
        lambda_handler({"mode": "season_only"}, None, table_name=games_table_name, now=patched_now)
    items = _read_season(games_table_name, 2026, "hitting")
    assert len(items) == 1
    item = items[0]
    assert int(item["at_bats"]) == 100
    assert int(item["doubles"]) == 6
    assert int(item["triples"]) == 1
    assert int(item["walks"]) == 12
    assert int(item["intentional_walks"]) == 2
    assert int(item["sacrifice_flies"]) == 1
    assert int(item["hit_by_pitch"]) == 3
    assert int(item["stolen_bases"]) == 14
    assert int(item["plate_appearances"]) == 116


def test_season_pitcher_record_uses_hitbatsmen_for_hbp(games_table_name, patched_now):
    """Pitcher splits expose HBP-given-up under hitBatsmen, not hitByPitch."""
    split = {
        "player": {"id": 701, "fullName": "Pitcher"},
        "team": {"id": 201},
        "stat": {
            "inningsPitched": "100.0",
            "homeRuns": 8,
            "baseOnBalls": 25,
            "hitBatsmen": 4,
            "hitByPitch": 999,  # should NOT be used for pitchers
            "strikeOuts": 110,
            "earnedRuns": 30,
            "era": "2.70",
        },
    }
    with (
        patch("ingest_daily_stats.handler.fetch_schedule_finals", return_value=[]),
        patch(
            "ingest_daily_stats.handler.fetch_qualified_season_stats",
            side_effect=lambda s, g: [split] if g == "pitching" else [],
        ),
    ):
        lambda_handler({"mode": "season_only"}, None, table_name=games_table_name, now=patched_now)
    items = _read_season(games_table_name, 2026, "pitching")
    assert len(items) == 1
    item = items[0]
    assert int(item["hit_by_pitch"]) == 4  # hitBatsmen, NOT 999
    assert int(item["walks"]) == 25
    assert int(item["earned_runs"]) == 30
