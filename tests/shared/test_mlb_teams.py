"""Tests for the static MLB team table."""

from __future__ import annotations

from shared.mlb_teams import all_teams, get_team


def test_all_thirty_teams_are_present() -> None:
    teams = all_teams()
    assert len(teams) == 30
    # Three real MLB ids that have to be in the table — sanity check.
    assert get_team(147) is not None  # NYY
    assert get_team(119) is not None  # LAD
    assert get_team(133) is not None  # ATH


def test_pacific_time_flag_only_pt_clubs() -> None:
    """Six PT-park clubs should be the only `pacific_time=True` rows."""
    pt_ids = {t.id for t in all_teams() if t.pacific_time}
    expected = {
        108,  # LAA
        133,  # ATH
        136,  # SEA
        119,  # LAD
        135,  # SD
        137,  # SF
    }
    assert pt_ids == expected
    # AL West Central-Time outliers are NOT flagged.
    assert get_team(117).pacific_time is False  # HOU
    assert get_team(140).pacific_time is False  # TEX
