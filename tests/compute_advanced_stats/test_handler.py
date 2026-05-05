"""Tests for the diamond-iq-compute-advanced-stats Lambda."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import boto3
import pytest
from compute_advanced_stats.handler import (
    _cfip_and_lg_era,
    _fip,
    _league_hitting_means,
    _ops_plus,
    _parse_innings,
    _to_decimal,
    _woba,
    lambda_handler,
)

pytestmark = pytest.mark.usefixtures("dynamodb_table")


# ── Helpers ────────────────────────────────────────────────────────────


def _hitter(
    person_id: int,
    *,
    obp: str = ".380",
    slg: str = ".500",
    avg: str = ".300",
    at_bats: int = 100,
    hits: int = 30,
    doubles: int = 6,
    triples: int = 1,
    home_runs: int = 5,
    walks: int = 12,
    intentional_walks: int = 2,
    sacrifice_flies: int = 1,
    hit_by_pitch: int = 3,
) -> dict[str, Any]:
    return {
        "PK": "STATS#2026#hitting",
        "SK": f"STATS#{person_id}",
        "season": 2026,
        "group": "hitting",
        "person_id": person_id,
        "full_name": f"Hitter{person_id}",
        "obp": obp,
        "slg": slg,
        "avg": avg,
        "at_bats": at_bats,
        "hits": hits,
        "doubles": doubles,
        "triples": triples,
        "home_runs": home_runs,
        "walks": walks,
        "intentional_walks": intentional_walks,
        "sacrifice_flies": sacrifice_flies,
        "hit_by_pitch": hit_by_pitch,
    }


def _pitcher(
    person_id: int,
    *,
    innings: str = "100.0",
    home_runs: int = 8,
    walks: int = 25,
    hit_by_pitch: int = 4,
    strikeouts: int = 110,
    earned_runs: int = 30,
    era: str = "2.70",
) -> dict[str, Any]:
    return {
        "PK": "STATS#2026#pitching",
        "SK": f"STATS#{person_id}",
        "season": 2026,
        "group": "pitching",
        "person_id": person_id,
        "full_name": f"Pitcher{person_id}",
        "innings_pitched": innings,
        "home_runs": home_runs,
        "walks": walks,
        "hit_by_pitch": hit_by_pitch,
        "strikeouts": strikeouts,
        "earned_runs": earned_runs,
        "era": era,
    }


def _seed(games_table_name: str, items: list[dict[str, Any]]) -> None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    for item in items:
        table.put_item(Item=item)


def _read(games_table_name: str, pk: str, sk: str) -> dict[str, Any]:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    return table.get_item(Key={"PK": pk, "SK": sk}).get("Item") or {}


class _CWCapture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


# ── Pure-function tests (no DynamoDB) ─────────────────────────────────


def test_to_decimal_parses_strings_and_numbers() -> None:
    assert _to_decimal(".300") == Decimal(".300")
    assert _to_decimal("100") == Decimal("100")
    assert _to_decimal(42) == Decimal("42")
    assert _to_decimal(None) is None
    assert _to_decimal("") is None
    assert _to_decimal("not_a_number") is None


def test_parse_innings_handles_baseball_notation() -> None:
    """100.1 IP = 100 + 1/3 innings, NOT 100.1."""
    assert _parse_innings("100.0") == Decimal("100")
    one_third = _parse_innings("100.1")
    assert one_third is not None and abs(one_third - Decimal("100.333")) < Decimal("0.001")
    two_thirds = _parse_innings("100.2")
    assert two_thirds is not None and abs(two_thirds - Decimal("100.667")) < Decimal("0.001")
    assert _parse_innings(None) is None


def test_woba_canonical_formula() -> None:
    """30 hits = 18 1B, 6 2B, 1 3B, 5 HR. uBB = 12-2 = 10. HBP=3.

    num = .69*10 + .72*3 + .89*18 + 1.27*6 + 1.62*1 + 2.10*5
        = 6.9 + 2.16 + 16.02 + 7.62 + 1.62 + 10.5 = 44.82
    den = 100 + 12 - 2 + 1 + 3 = 114
    wOBA = 44.82 / 114 ≈ 0.393
    """
    h = _hitter(1)
    woba = _woba(h)
    assert woba is not None
    assert abs(woba - Decimal("0.393")) < Decimal("0.001")


def test_woba_zero_pa_returns_none() -> None:
    h = _hitter(1, at_bats=0, walks=0, intentional_walks=0, sacrifice_flies=0, hit_by_pitch=0)
    assert _woba(h) is None


def test_woba_missing_field_returns_none() -> None:
    h = _hitter(1)
    h.pop("doubles")
    assert _woba(h) is None


def test_woba_singles_clamp_at_zero() -> None:
    """If 2B+3B+HR > hits (data anomaly), singles clamps at 0 not negative."""
    h = _hitter(1, hits=2, doubles=3, triples=0, home_runs=0)
    woba = _woba(h)
    assert woba is not None  # should still compute, not crash


def test_ops_plus_above_average() -> None:
    """OBP=.380, SLG=.500 vs lg .333/.420.
    Ratio = .380/.333 + .500/.420 - 1 = 1.1411 + 1.1905 - 1 = 1.3316
    OPS+ = 100 * 1.332 ≈ 133.2
    """
    h = _hitter(1)
    out = _ops_plus(h, Decimal(".333"), Decimal(".420"))
    assert out is not None
    assert abs(out - Decimal("133.155")) < Decimal("0.5")  # ballpark — 3 dp


def test_ops_plus_below_average() -> None:
    h = _hitter(1, obp=".280", slg=".350")
    out = _ops_plus(h, Decimal(".333"), Decimal(".420"))
    assert out is not None
    assert out < Decimal("100")


def test_ops_plus_exactly_league_average() -> None:
    h = _hitter(1, obp=".333", slg=".420")
    out = _ops_plus(h, Decimal(".333"), Decimal(".420"))
    assert out is not None
    assert abs(out - Decimal("100")) < Decimal("0.01")


def test_ops_plus_zero_league_returns_none() -> None:
    h = _hitter(1)
    assert _ops_plus(h, Decimal("0"), Decimal(".420")) is None


def test_fip_canonical_formula() -> None:
    """100 IP, 8 HR, 25 BB, 4 HBP, 110 K, cFIP = 3.10.

    FIP = (13*8 + 3*(25+4) - 2*110) / 100 + 3.10
        = (104 + 87 - 220) / 100 + 3.10
        = -29/100 + 3.10 = -0.29 + 3.10 = 2.81
    """
    p = _pitcher(1)
    out = _fip(p, Decimal("3.10"))
    assert out is not None
    assert abs(out - Decimal("2.81")) < Decimal("0.005")


def test_fip_zero_innings_returns_none() -> None:
    p = _pitcher(1, innings="0.0")
    assert _fip(p, Decimal("3.10")) is None


def test_fip_missing_field_returns_none() -> None:
    p = _pitcher(1)
    p.pop("hit_by_pitch")
    assert _fip(p, Decimal("3.10")) is None


def test_league_hitting_means_simple() -> None:
    pool = [_hitter(i, obp=".300", slg=".400") for i in range(3)] + [
        _hitter(99, obp=".400", slg=".500")
    ]
    lg_obp, lg_slg = _league_hitting_means(pool)
    assert lg_obp is not None and abs(lg_obp - Decimal("0.325")) < Decimal("0.001")
    assert lg_slg is not None and abs(lg_slg - Decimal("0.425")) < Decimal("0.001")


def test_cfip_backsolves_to_league_era() -> None:
    """cFIP is defined so that lg-aggregate FIP equals lg ERA. Verify."""
    pitchers = [
        _pitcher(
            1,
            innings="100.0",
            home_runs=8,
            walks=25,
            hit_by_pitch=4,
            strikeouts=110,
            earned_runs=30,
        ),
        _pitcher(
            2, innings="80.0", home_runs=10, walks=30, hit_by_pitch=3, strikeouts=70, earned_runs=40
        ),
    ]
    cfip, lg_era = _cfip_and_lg_era(pitchers)
    assert cfip is not None and lg_era is not None
    # Apply cFIP to the league-aggregate inputs and confirm == lg_era.
    sum_hr = Decimal("18")
    sum_bb = Decimal("55")
    sum_hbp = Decimal("7")
    sum_k = Decimal("180")
    sum_ip = Decimal("180")
    fip_no_constant = (
        Decimal("13") * sum_hr + Decimal("3") * (sum_bb + sum_hbp) - Decimal("2") * sum_k
    ) / sum_ip
    reconstructed = (fip_no_constant + cfip).quantize(Decimal("0.001"))
    assert abs(reconstructed - lg_era) < Decimal("0.005")


# ── Handler integration tests (with DynamoDB) ─────────────────────────


def test_happy_path_writes_woba_ops_plus_and_fip(games_table_name) -> None:
    _seed(
        games_table_name,
        [
            _hitter(1),
            _hitter(2, obp=".300", slg=".400"),
            _pitcher(1),
            _pitcher(
                2,
                innings="80.0",
                home_runs=10,
                walks=30,
                hit_by_pitch=3,
                strikeouts=70,
                earned_runs=40,
            ),
        ],
    )
    cw = _CWCapture()
    result = lambda_handler(
        {"season": 2026}, None, table_name=games_table_name, cloudwatch_client=cw
    )
    assert result["ok"] is True
    assert result["hitters_computed"] == 2
    assert result["pitchers_computed"] == 2
    h1 = _read(games_table_name, "STATS#2026#hitting", "STATS#1")
    assert "woba" in h1
    assert "ops_plus" in h1
    p1 = _read(games_table_name, "STATS#2026#pitching", "STATS#1")
    assert "fip" in p1


def test_existing_attributes_preserved_after_update(games_table_name) -> None:
    """UpdateItem must not overwrite avg, obp, full_name, etc."""
    _seed(games_table_name, [_hitter(1), _pitcher(1)])
    lambda_handler({"season": 2026}, None, table_name=games_table_name)
    h1 = _read(games_table_name, "STATS#2026#hitting", "STATS#1")
    # Confirm originals still present.
    assert h1["full_name"] == "Hitter1"
    assert h1["obp"] == ".380"
    assert h1["slg"] == ".500"
    # And computed fields written.
    assert "woba" in h1
    assert "ops_plus" in h1


def test_empty_pool_returns_no_qualified_records(games_table_name) -> None:
    """never ran. Lambda fails loud, writes nothing."""
    cw = _CWCapture()
    result = lambda_handler(
        {"season": 2026}, None, table_name=games_table_name, cloudwatch_client=cw
    )
    assert result["ok"] is False
    assert result["reason"] == "no_qualified_records"


def test_hitters_only_returns_no_qualified_records(games_table_name) -> None:
    """Hitters present but no pitchers — still degenerate."""
    _seed(games_table_name, [_hitter(1)])
    result = lambda_handler({"season": 2026}, None, table_name=games_table_name)
    assert result["ok"] is False
    assert result["reason"] == "no_qualified_records"


def test_metric_namespace_and_league_values(games_table_name) -> None:
    _seed(games_table_name, [_hitter(1), _hitter(2, obp=".300", slg=".400"), _pitcher(1)])
    cw = _CWCapture()
    lambda_handler({"season": 2026}, None, table_name=games_table_name, cloudwatch_client=cw)
    assert len(cw.calls) == 1
    assert cw.calls[0]["Namespace"] == "DiamondIQ/AdvancedStats"
    names = {m["MetricName"] for m in cw.calls[0]["MetricData"]}
    assert {"HittersComputed", "PitchersComputed", "LeagueOBP", "LeagueSLG", "LeagueERA"} <= names


def test_metric_emission_failure_does_not_break(games_table_name) -> None:
    class BoomCW:
        def put_metric_data(self, **_kw):
            raise RuntimeError("CW down")

    _seed(games_table_name, [_hitter(1), _pitcher(1)])
    result = lambda_handler(
        {"season": 2026}, None, table_name=games_table_name, cloudwatch_client=BoomCW()
    )
    assert result["ok"] is True


def test_idempotent_rerun(games_table_name) -> None:
    """Running twice produces identical computed values."""
    _seed(games_table_name, [_hitter(1), _pitcher(1)])
    lambda_handler({"season": 2026}, None, table_name=games_table_name)
    first = _read(games_table_name, "STATS#2026#hitting", "STATS#1")
    woba1 = first["woba"]
    ops1 = first["ops_plus"]
    lambda_handler({"season": 2026}, None, table_name=games_table_name)
    second = _read(games_table_name, "STATS#2026#hitting", "STATS#1")
    assert second["woba"] == woba1
    assert second["ops_plus"] == ops1


def test_summary_includes_required_fields(games_table_name) -> None:
    _seed(games_table_name, [_hitter(1), _pitcher(1)])
    result = lambda_handler({"season": 2026}, None, table_name=games_table_name)
    for f in (
        "ok",
        "season",
        "hitter_count",
        "pitcher_count",
        "hitters_computed",
        "pitchers_computed",
        "hitters_skipped",
        "pitchers_skipped",
        "league_obp",
        "league_slg",
        "league_era",
        "cfip",
        "elapsed_ms",
    ):
        assert f in result, f"missing {f}"


def test_per_player_skipped_on_missing_inputs(games_table_name) -> None:
    bad = _hitter(1)
    bad.pop("doubles")  # wOBA can't compute
    bad.pop("obp")  # OPS+ can't compute either
    good = _hitter(2)
    _seed(games_table_name, [bad, good, _pitcher(1)])
    result = lambda_handler({"season": 2026}, None, table_name=games_table_name)
    assert result["hitters_computed"] == 1
    assert result["hitters_skipped"] == 1
