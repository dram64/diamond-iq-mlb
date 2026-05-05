"""Tests for the diamond-iq-ingest-hardest-hit Lambda."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from ingest_hardest_hit.handler import lambda_handler

pytestmark = pytest.mark.usefixtures("dynamodb_table")


def _final_game(game_pk: int) -> dict[str, Any]:
    return {"gamePk": game_pk, "status": {"detailedState": "Final"}}


def _play_event(
    launch_speed: float, *, trajectory: str = "line_drive", launch_angle: float | None = 25.0
) -> dict[str, Any]:
    hd: dict[str, Any] = {"launchSpeed": launch_speed, "trajectory": trajectory}
    if launch_angle is not None:
        hd["launchAngle"] = launch_angle
    hd["totalDistance"] = 350.0
    return {"hitData": hd}


def _play(
    *,
    batter_id: int = 592450,
    batter_name: str = "Aaron Judge",
    inning: int = 1,
    half_inning: str = "top",
    result_event: str = "Single",
    play_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "matchup": {"batter": {"id": batter_id, "fullName": batter_name}},
        "about": {"inning": inning, "halfInning": half_inning},
        "result": {"event": result_event, "eventType": "single"},
        "playEvents": play_events or [],
    }


def _feed(plays: list[dict[str, Any]]) -> dict[str, Any]:
    return {"liveData": {"plays": {"allPlays": plays}}}


def _read_hits(games_table_name: str, date_iso: str) -> list[dict[str, Any]]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"HITS#{date_iso}"},
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


def test_happy_path_top_n_written(games_table_name, patched_now):
    finals = [_final_game(1001), _final_game(1002)]
    feed_a = _feed(
        [
            _play(batter_id=1, batter_name="A", play_events=[_play_event(115.4)]),
            _play(batter_id=2, batter_name="B", play_events=[_play_event(112.0)]),
        ]
    )
    feed_b = _feed(
        [
            _play(batter_id=3, batter_name="C", play_events=[_play_event(118.2)]),
            _play(batter_id=4, batter_name="D", play_events=[_play_event(105.5)]),
        ]
    )
    feeds = {1001: feed_a, 1002: feed_b}
    cw = _CWCapture()
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", side_effect=lambda gp: feeds[gp]),
    ):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is True
    assert result["games_processed"] == 2
    assert result["events_parsed"] == 4
    assert result["hits_ingested"] == 4
    assert result["max_launch_speed"] == 118.2
    items = _read_hits(games_table_name, "2026-04-26")
    assert len(items) == 4


def test_top_n_clamps_to_25(games_table_name, patched_now):
    """Generate 30 events; top 25 written."""
    finals = [_final_game(1001)]
    plays = [_play(batter_id=i, play_events=[_play_event(110.0 + i * 0.1)]) for i in range(30)]
    feed = _feed(plays)
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=feed),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["events_parsed"] == 30
    assert result["hits_ingested"] == 25
    items = _read_hits(games_table_name, "2026-04-26")
    assert len(items) == 25


def test_sk_encodes_descending_velocity(games_table_name, patched_now):
    """Sample SKs verify the inversion encoding sorts top-velocity first."""
    finals = [_final_game(1001)]
    plays = [
        _play(batter_id=1, play_events=[_play_event(100.0)]),
        _play(batter_id=2, play_events=[_play_event(118.0)]),
        _play(batter_id=3, play_events=[_play_event(105.0)]),
    ]
    feed = _feed(plays)
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=feed),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_hits(games_table_name, "2026-04-26")
    # Default Query result (above) is ascending by SK; first item should be the
    # 118.0 mph hit because its inverted velocity (8819) sorts before others.
    assert float(items[0]["launch_speed"]) == 118.0
    assert float(items[1]["launch_speed"]) == 105.0
    assert float(items[2]["launch_speed"]) == 100.0


def test_pk_sk_shape_and_ttl(games_table_name, patched_now):
    finals = [_final_game(1234)]
    plays = [_play(play_events=[_play_event(115.5)])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_hits(games_table_name, "2026-04-26")
    item = items[0]
    assert item["PK"] == "HITS#2026-04-26"
    assert item["SK"].startswith("HIT#")
    parts = item["SK"].split("#")
    assert len(parts) == 4
    assert parts[2] == "1234"
    assert int(item["ttl"]) > int(time.time()) + (29 * 24 * 60 * 60)


def test_no_final_games_yesterday_returns_ok_false(games_table_name, patched_now):
    cw = _CWCapture()
    with patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=[]):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is False
    assert result["reason"] == "no_qualifying_hits"
    assert result["games_total"] == 0


def test_per_game_5xx_other_games_succeed(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    finals = [_final_game(1001), _final_game(1002), _final_game(1003)]

    def feed_side(gp):
        if gp == 1002:
            raise MLBAPIError("503", status=503)
        return _feed([_play(play_events=[_play_event(110.0 + gp * 0.001)])])

    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", side_effect=feed_side),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["games_processed"] == 2
    assert result["games_failed"] == 1
    assert result["hits_ingested"] == 2


def test_event_with_no_launch_speed_filtered(games_table_name, patched_now):
    finals = [_final_game(1001)]
    plays = [
        _play(
            play_events=[
                {"hitData": {"launchAngle": 25.0}},  # missing launchSpeed
                _play_event(115.0),
            ]
        ),
    ]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["events_parsed"] == 1
    assert result["hits_ingested"] == 1


def test_event_with_zero_launch_speed_filtered(games_table_name, patched_now):
    finals = [_final_game(1001)]
    plays = [_play(play_events=[_play_event(0.0), _play_event(115.0)])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["events_parsed"] == 1


def test_bunts_filtered(games_table_name, patched_now):
    finals = [_final_game(1001)]
    plays = [
        _play(batter_id=1, play_events=[_play_event(118.0, trajectory="bunt_groundball")]),
        _play(batter_id=2, play_events=[_play_event(60.0, trajectory="bunt_popup")]),
        _play(batter_id=3, play_events=[_play_event(110.0, trajectory="line_drive")]),
    ]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_hits(games_table_name, "2026-04-26")
    assert result["events_parsed"] == 1
    assert len(items) == 1
    assert int(items[0]["batter_id"]) == 3


def test_inning_and_half_inning_extracted(games_table_name, patched_now):
    finals = [_final_game(1001)]
    plays = [_play(inning=7, half_inning="bottom", play_events=[_play_event(115.0)])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_hits(games_table_name, "2026-04-26")
    assert int(items[0]["inning"]) == 7
    assert items[0]["half_inning"] == "bottom"


def test_batter_id_and_name_extracted(games_table_name, patched_now):
    finals = [_final_game(1001)]
    plays = [_play(batter_id=592450, batter_name="Aaron Judge", play_events=[_play_event(115.0)])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_hits(games_table_name, "2026-04-26")
    assert int(items[0]["batter_id"]) == 592450
    assert items[0]["batter_name"] == "Aaron Judge"


def test_string_launch_speed_parsed(games_table_name, patched_now):
    """MLB sometimes returns numeric stats as strings; verify string parses."""
    finals = [_final_game(1001)]
    plays = [_play(play_events=[{"hitData": {"launchSpeed": "115.5", "trajectory": "line_drive"}}])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["events_parsed"] == 1


def test_tied_velocity_deterministic_order(games_table_name, patched_now):
    """Two events with identical exit velocity tiebreak by gamePk + event idx."""
    finals = [_final_game(1001), _final_game(1002)]
    feed_a = _feed([_play(batter_id=1, play_events=[_play_event(115.0)])])
    feed_b = _feed([_play(batter_id=2, play_events=[_play_event(115.0)])])
    feeds = {1001: feed_a, 1002: feed_b}
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", side_effect=lambda gp: feeds[gp]),
    ):
        lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    items = _read_hits(games_table_name, "2026-04-26")
    # Same SK velocity prefix; tiebreak by gamePk → 1001 sorts before 1002.
    assert int(items[0]["game_pk"]) == 1001
    assert int(items[1]["game_pk"]) == 1002


def test_metric_namespace_and_values(games_table_name, patched_now):
    finals = [_final_game(1001)]
    plays = [_play(play_events=[_play_event(115.0)])]
    cw = _CWCapture()
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        lambda_handler({}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now)
    assert cw.calls[0]["Namespace"] == "DiamondIQ/HardestHit"
    names = {m["MetricName"] for m in cw.calls[0]["MetricData"]}
    assert {
        "GamesProcessed",
        "EventsParsed",
        "HitsIngested",
        "GamesFailed",
        "MaxLaunchSpeed",
    } <= names


def test_metric_emission_failure_does_not_break(games_table_name, patched_now):
    class BoomCW:
        def put_metric_data(self, **_kw):
            raise RuntimeError("CW down")

    finals = [_final_game(1001)]
    plays = [_play(play_events=[_play_event(115.0)])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=BoomCW(), now=patched_now
        )
    assert result["ok"] is True


def test_schedule_fetch_failure_aborts(games_table_name, patched_now):
    from shared.mlb_client import MLBAPIError

    cw = _CWCapture()
    with patch(
        "ingest_hardest_hit.handler.fetch_schedule_finals",
        side_effect=MLBAPIError("503", status=503),
    ):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=patched_now
        )
    assert result["ok"] is False
    assert result["reason"] == "schedule_fetch_failed"


def test_empty_play_events_handled(games_table_name, patched_now):
    """A play with no playEvents (rare) is just skipped — no exception."""
    finals = [_final_game(1001)]
    plays = [_play(play_events=[]), _play(play_events=[_play_event(115.0)])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    assert result["events_parsed"] == 1


def test_yesterday_computed_across_utc_midnight(games_table_name):
    pinned = datetime(2026, 5, 1, 0, 30, 0, tzinfo=UTC)
    cw = _CWCapture()
    with patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=[]):
        result = lambda_handler(
            {}, None, table_name=games_table_name, cloudwatch_client=cw, now=pinned
        )
    assert result["date"] == "2026-04-30"


def test_summary_includes_required_fields(games_table_name, patched_now):
    finals = [_final_game(1001)]
    plays = [_play(play_events=[_play_event(115.0)])]
    with (
        patch("ingest_hardest_hit.handler.fetch_schedule_finals", return_value=finals),
        patch("ingest_hardest_hit.handler.fetch_game_feed_live", return_value=_feed(plays)),
    ):
        result = lambda_handler({}, None, table_name=games_table_name, now=patched_now)
    for f in (
        "ok",
        "date",
        "games_total",
        "games_processed",
        "games_failed",
        "events_parsed",
        "hits_ingested",
        "max_launch_speed",
        "elapsed_ms",
    ):
        assert f in result, f"missing {f}"
