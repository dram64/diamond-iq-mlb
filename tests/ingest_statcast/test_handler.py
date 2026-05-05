from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from ingest_statcast.handler import lambda_handler

pytestmark = pytest.mark.usefixtures("dynamodb_table")


# ── CSV fixture builders ───────────────────────────────────────────────


def _custom_batter_row(pid: int, name: str = "Judge, Aaron") -> dict[str, str]:
    return {
        "last_name, first_name": name,
        "player_id": str(pid),
        "year": "2026",
        "xba": ".290",
        "xslg": ".707",
        "xwoba": ".466",
        "sweet_spot_percent": "38.9",
        "sprint_speed": "26.8",
    }


def _statcast_batter_row(pid: int, name: str = "Judge, Aaron") -> dict[str, str]:
    return {
        "last_name, first_name": name,
        "player_id": str(pid),
        "attempts": "111",
        "avg_hit_speed": "94.7",
        "max_hit_speed": "115.8",
        "ev95percent": "55.6",
        "brl_percent": "21.5",
        "brl_pa": "12.3",
        "max_distance": "475",
        "avg_distance": "260",
        "avg_hr_distance": "418",
    }


def _custom_pitcher_row(pid: int, name: str = "Sale, Chris") -> dict[str, str]:
    return {
        "last_name, first_name": name,
        "player_id": str(pid),
        "year": "2026",
        "xera": "2.98",
        "xba": ".200",
        "whiff_percent": "26",
        "oz_swing_miss_percent": "37.4",
        "fastball_avg_speed": "95",
        "fastball_avg_spin": "2263",
    }


def _bat_tracking_row(pid: int, name: str = "Judge, Aaron") -> dict[str, str]:
    return {
        "id": str(pid),
        "name": name,
        "avg_bat_speed": "75.2",
        "swing_length": "7.8",
        "hard_swing_rate": "0.55",
        "squared_up_per_swing": "0.21",
        "blast_per_swing": "0.18",
    }


def _batted_ball_row(pid: int, name: str = "Judge, Aaron") -> dict[str, str]:
    return {
        "id": str(pid),
        "name": name,
        "bbe": "72",
        "gb_rate": "0.36",
        "fb_rate": "0.32",
        "ld_rate": "0.22",
        "pull_rate": "0.49",
        "straight_rate": "0.31",
        "oppo_rate": "0.21",
    }


def _read(games_table_name: str, season: int, person_id: int) -> dict[str, Any]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    return (
        table.get_item(Key={"PK": f"STATCAST#{season}", "SK": f"STATCAST#{person_id}"}).get("Item")
        or {}
    )


@pytest.fixture
def patched_now():
    return datetime(2026, 4, 30, 9, 30, 0, tzinfo=UTC)


def _patch_all(
    *,
    custom_batter: list[dict[str, str]] | None = None,
    statcast_batter: list[dict[str, str]] | None = None,
    custom_pitcher: list[dict[str, str]] | None = None,
    bat_tracking: list[dict[str, str]] | None = None,
    batted_ball: list[dict[str, str]] | None = None,
):
    """Helper that returns the 5 patch context managers (callers `with`-stack them)."""
    return (
        patch(
            "ingest_statcast.handler.fetch_custom_batter",
            return_value=custom_batter if custom_batter is not None else [],
        ),
        patch(
            "ingest_statcast.handler.fetch_statcast_batter",
            return_value=statcast_batter if statcast_batter is not None else [],
        ),
        patch(
            "ingest_statcast.handler.fetch_custom_pitcher",
            return_value=custom_pitcher if custom_pitcher is not None else [],
        ),
        patch(
            "ingest_statcast.handler.fetch_bat_tracking",
            return_value=bat_tracking if bat_tracking is not None else [],
        ),
        patch(
            "ingest_statcast.handler.fetch_batted_ball",
            return_value=batted_ball if batted_ball is not None else [],
        ),
    )


# ── Happy path ─────────────────────────────────────────────────────────


def test_happy_path_merges_all_five_csvs(games_table_name, patched_now):
    pid = 592450
    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(
        custom_batter=[_custom_batter_row(pid)],
        statcast_batter=[_statcast_batter_row(pid)],
        bat_tracking=[_bat_tracking_row(pid)],
        batted_ball=[_batted_ball_row(pid)],
    )
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)

    assert result["ok"] is True
    assert result["players_written"] == 1
    # All 5 endpoints succeeded; custom_pitcher just returned an empty result
    # set (our fixture is hitter-only) which is not a failure mode.
    assert result["csvs_succeeded"] == 5
    assert result["csvs_failed"] == 0

    item = _read(games_table_name, 2026, pid)
    assert item["PK"] == "STATCAST#2026"
    assert item["SK"] == "STATCAST#592450"
    assert int(item["person_id"]) == pid
    assert item["display_name"] == "Judge, Aaron"
    # Hitter merge: custom + statcast fields both present.
    assert item["hitting"]["xba"] == ".290"
    assert item["hitting"]["xwoba"] == ".466"
    assert float(item["hitting"]["avg_hit_speed"]) == 94.7
    assert float(item["hitting"]["max_hit_speed"]) == 115.8
    assert float(item["hitting"]["ev95_percent"]) == 55.6
    assert float(item["hitting"]["barrel_percent"]) == 21.5
    # Pitcher null since this player only appeared in batter CSVs.
    assert item["pitching"] is None
    # Bat-tracking + batted-ball blocks present.
    assert float(item["bat_tracking"]["avg_bat_speed"]) == 75.2
    assert float(item["batted_ball"]["pull_rate"]) == 0.49


def test_happy_path_pitcher_only_player(games_table_name, patched_now):
    """A pitcher who isn't in any batter CSV still gets a row with hitting=None."""
    pid = 519242
    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(
        custom_pitcher=[_custom_pitcher_row(pid)],
    )
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)

    # All 5 endpoints succeeded; 4 returned empty (hitter-side) — not a failure.
    assert result["ok"] is True
    assert result["players_written"] == 1
    item = _read(games_table_name, 2026, pid)
    assert item["hitting"] is None
    assert float(item["pitching"]["xera"]) == 2.98
    assert item["pitching"]["xba_against"] == ".200"
    assert float(item["pitching"]["fastball_avg_speed"]) == 95.0


def test_partial_failure_one_csv_down(games_table_name, patched_now):
    """If bat-tracking 5xx's, hitter rows still merge with the other 4 CSVs."""
    from shared.savant_client import SavantAPIError

    pid = 592450
    cb_p, sb_p, cp_p, bb_p = (
        patch(
            "ingest_statcast.handler.fetch_custom_batter", return_value=[_custom_batter_row(pid)]
        ),
        patch(
            "ingest_statcast.handler.fetch_statcast_batter",
            return_value=[_statcast_batter_row(pid)],
        ),
        patch("ingest_statcast.handler.fetch_custom_pitcher", return_value=[]),
        patch("ingest_statcast.handler.fetch_batted_ball", return_value=[_batted_ball_row(pid)]),
    )
    bt_p = patch(
        "ingest_statcast.handler.fetch_bat_tracking",
        side_effect=SavantAPIError("503", status=503),
    )
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)

    assert result["players_written"] == 1
    assert result["csvs_failed"] >= 1
    item = _read(games_table_name, 2026, pid)
    # Bat-tracking gracefully null; everything else present.
    assert item["bat_tracking"] is None
    assert item["hitting"]["xba"] == ".290"
    assert float(item["hitting"]["avg_hit_speed"]) == 94.7
    assert float(item["batted_ball"]["pull_rate"]) == 0.49


def test_missing_fields_handled_gracefully(games_table_name, patched_now):
    """Empty cells in the CSV should serialize as None, not as the literal string ''."""
    pid = 592450
    custom_row = _custom_batter_row(pid)
    custom_row["sprint_speed"] = ""  # field present but empty
    statcast_row = _statcast_batter_row(pid)
    del statcast_row["max_hit_speed"]  # field absent entirely

    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(
        custom_batter=[custom_row],
        statcast_batter=[statcast_row],
    )
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)

    assert result["players_written"] == 1
    item = _read(games_table_name, 2026, pid)
    assert item["hitting"]["sprint_speed"] is None
    assert item["hitting"]["max_hit_speed"] is None
    # Other fields still populated.
    assert item["hitting"]["xba"] == ".290"


def test_unknown_column_drift_does_not_break_ingest(games_table_name, patched_now):
    """A future Savant schema change adds a new column; we ignore it."""
    pid = 592450
    custom_row = _custom_batter_row(pid)
    custom_row["new_metric_2027"] = "42.0"  # noise

    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(custom_batter=[custom_row])
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["players_written"] == 1
    item = _read(games_table_name, 2026, pid)
    assert "new_metric_2027" not in item["hitting"]
    assert item["hitting"]["xba"] == ".290"


def test_idempotent_rerun(games_table_name, patched_now):
    pid = 592450
    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(custom_batter=[_custom_batter_row(pid)])
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": "STATCAST#2026"},
    )
    assert len(resp.get("Items") or []) == 1


def test_player_id_normalized_from_id_column(games_table_name, patched_now):
    """bat-tracking and batted-ball use 'id' instead of 'player_id'.
    The ingest must merge on a unified player_id."""
    pid = 592450
    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(
        custom_batter=[_custom_batter_row(pid)],
        bat_tracking=[_bat_tracking_row(pid)],  # uses "id"
        batted_ball=[_batted_ball_row(pid)],  # uses "id"
    )
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["players_written"] == 1  # merged into one row, not three
    item = _read(games_table_name, 2026, pid)
    assert item["hitting"] is not None
    assert item["bat_tracking"] is not None
    assert item["batted_ball"] is not None


def test_metrics_emitted_with_correct_namespace(games_table_name, patched_now):
    class _CW:
        def __init__(self):
            self.calls: list[dict] = []

        def put_metric_data(self, **kwargs):
            self.calls.append(kwargs)

    pid = 592450
    cw = _CW()
    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(custom_batter=[_custom_batter_row(pid)])
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now)
    assert cw.calls[0]["Namespace"] == "DiamondIQ/Statcast"
    names = {m["MetricName"] for m in cw.calls[0]["MetricData"]}
    assert names == {"PlayersWritten", "CSVsSucceeded", "CSVsFailed", "IngestionElapsedMs"}


def test_metric_emission_failure_does_not_break(games_table_name, patched_now):
    class _BoomCW:
        def put_metric_data(self, **_kw):
            raise RuntimeError("CW down")

    pid = 592450
    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(custom_batter=[_custom_batter_row(pid)])
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=_BoomCW(), now=patched_now
        )
    assert result["players_written"] == 1


def test_summary_includes_required_fields(games_table_name, patched_now):
    cb_p, sb_p, cp_p, bt_p, bb_p = _patch_all(custom_batter=[_custom_batter_row(1)])
    with cb_p, sb_p, cp_p, bt_p, bb_p:
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    for f in ("ok", "season", "csvs_succeeded", "csvs_failed", "players_written", "elapsed_ms"):
        assert f in result, f"missing {f}"
