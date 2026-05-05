from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import boto3
from api_players.handler import lambda_handler

LEAGUE_AL = 103
LEAGUE_NL = 104


def _seed_standings_row(
    table: Any,
    season: int,
    *,
    team_id: int,
    team_name: str,
    league_id: int,
    league_rank: int,
    wins: int = 20,
    losses: int = 10,
    games_back: str = "-",
    run_differential: int = 30,
) -> None:
    table.put_item(
        Item={
            "PK": f"STANDINGS#{season}",
            "SK": f"STANDINGS#{team_id}",
            "season": season,
            "team_id": team_id,
            "team_name": team_name,
            "league_id": league_id,
            "league_rank": str(league_rank),
            "wins": wins,
            "losses": losses,
            "games_back": games_back,
            "run_differential": run_differential,
        }
    )


def _seed_team_stats(
    table: Any,
    season: int,
    *,
    team_id: int,
    team_name: str,
    avg: str = ".265",
    ops: str = ".784",
    era: str = "3.21",
    whip: str = "1.18",
) -> None:
    table.put_item(
        Item={
            "PK": f"TEAMSTATS#{season}",
            "SK": f"TEAMSTATS#{team_id}",
            "season": season,
            "team_id": team_id,
            "team_name": team_name,
            "hitting": {"avg": avg, "ops": ops, "home_runs": 48, "rbi": 145},
            "pitching": {"era": era, "whip": whip, "strikeouts": 268, "wins": 20},
        }
    )


def _invoke(games_table_name: str) -> dict[str, Any]:
    event = {"routeKey": "GET /api/featured-matchup", "pathParameters": {}}
    return lambda_handler(event, None, table_name=games_table_name)


def _patched_now(date_iso: str) -> datetime:
    return datetime.fromisoformat(date_iso + "T12:00:00+00:00").astimezone(UTC)


def _seed_baseline_standings(table: Any, season: int) -> None:
    """Two AL teams (NYY rank 1, BOS rank 2), two NL teams (LAD rank 1, NYM rank 2)."""
    _seed_standings_row(
        table,
        season,
        team_id=147,
        team_name="Yankees",
        league_id=LEAGUE_AL,
        league_rank=1,
        wins=21,
        losses=10,
        run_differential=47,
    )
    _seed_standings_row(
        table,
        season,
        team_id=111,
        team_name="Red Sox",
        league_id=LEAGUE_AL,
        league_rank=2,
        wins=18,
        losses=13,
    )
    _seed_standings_row(
        table,
        season,
        team_id=119,
        team_name="Dodgers",
        league_id=LEAGUE_NL,
        league_rank=1,
        wins=22,
        losses=9,
        run_differential=58,
    )
    _seed_standings_row(
        table,
        season,
        team_id=121,
        team_name="Mets",
        league_id=LEAGUE_NL,
        league_rank=2,
        wins=17,
        losses=14,
    )
    _seed_team_stats(table, season, team_id=147, team_name="Yankees")
    _seed_team_stats(table, season, team_id=119, team_name="Dodgers")


def test_featured_matchup_picks_al1_vs_nl1(dynamodb_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_baseline_standings(table, 2026)

    fixed_now = _patched_now("2026-04-30")
    with patch("routes.featured_matchup.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        response = _invoke(games_table_name)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["date"] == "2026-04-30"
    assert body["data"]["team_ids"] == [147, 119]
    assert len(body["data"]["teams"]) == 2

    al, nl = body["data"]["teams"]
    assert al["team_id"] == 147 and al["league"] == "AL"
    assert al["team_name"] == "Yankees"
    assert al["abbreviation"] == "NYY"
    assert int(al["wins"]) == 21
    assert int(al["losses"]) == 10
    assert int(al["run_differential"]) == 47
    assert al["highlight_stats"]["era"] == "3.21"
    assert al["highlight_stats"]["ops"] == ".784"

    assert nl["team_id"] == 119 and nl["league"] == "NL"
    assert nl["team_name"] == "Dodgers"
    assert nl["abbreviation"] == "LAD"
    assert int(nl["run_differential"]) == 58


def test_featured_matchup_503_when_standings_empty(dynamodb_table, games_table_name):  # noqa: ARG001
    fixed_now = _patched_now("2026-04-30")
    with patch("routes.featured_matchup.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        response = _invoke(games_table_name)
    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"]["code"] == "data_not_yet_available"


def test_featured_matchup_503_when_one_league_empty(dynamodb_table, games_table_name):  # noqa: ARG001
    """If standings has AL teams but no NL teams (or vice versa), 503."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_standings_row(
        table,
        2026,
        team_id=147,
        team_name="Yankees",
        league_id=LEAGUE_AL,
        league_rank=1,
    )

    fixed_now = _patched_now("2026-04-30")
    with patch("routes.featured_matchup.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        response = _invoke(games_table_name)
    assert response["statusCode"] == 503


def test_featured_matchup_deterministic_within_day(dynamodb_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_baseline_standings(table, 2026)

    fixed_now = _patched_now("2026-04-30")
    with patch("routes.featured_matchup.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        first = json.loads(_invoke(games_table_name)["body"])
        second = json.loads(_invoke(games_table_name)["body"])
    assert first["data"]["team_ids"] == second["data"]["team_ids"]


def test_featured_matchup_seeded_tiebreaker_when_multiple_at_rank_1(
    dynamodb_table, games_table_name
):  # noqa: ARG001
    """When 2+ teams tie at rank 1 in a league, the seed picks deterministically.
    Seeding by date means the pick can rotate across days even with the same tied set."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    # Three AL teams all tied at rank 1, one NL leader.
    _seed_standings_row(
        table, 2026, team_id=147, team_name="Yankees", league_id=LEAGUE_AL, league_rank=1
    )
    _seed_standings_row(
        table, 2026, team_id=141, team_name="Blue Jays", league_id=LEAGUE_AL, league_rank=1
    )
    _seed_standings_row(
        table, 2026, team_id=117, team_name="Astros", league_id=LEAGUE_AL, league_rank=1
    )
    _seed_standings_row(
        table, 2026, team_id=119, team_name="Dodgers", league_id=LEAGUE_NL, league_rank=1
    )
    _seed_team_stats(table, 2026, team_id=147, team_name="Yankees")
    _seed_team_stats(table, 2026, team_id=141, team_name="Blue Jays")
    _seed_team_stats(table, 2026, team_id=117, team_name="Astros")
    _seed_team_stats(table, 2026, team_id=119, team_name="Dodgers")

    picked_ids: set[int] = set()
    for date_iso in ("2026-04-28", "2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02"):
        fixed_now = _patched_now(date_iso)
        with patch("routes.featured_matchup.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.fromisoformat = datetime.fromisoformat
            body = json.loads(_invoke(games_table_name)["body"])
            picked_ids.add(int(body["data"]["teams"][0]["team_id"]))
    # Across 5 days, the tiebreaker should yield at least 2 distinct AL picks.
    assert len(picked_ids) >= 2
    # NL pick is always Dodgers — the only NL leader.
    fixed_now = _patched_now("2026-04-30")
    with patch("routes.featured_matchup.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        body = json.loads(_invoke(games_table_name)["body"])
    assert body["data"]["teams"][1]["team_id"] == 119


def test_featured_matchup_works_without_team_stats(dynamodb_table, games_table_name):  # noqa: ARG001
    """If TEAMSTATS isn't ingested yet, highlight_stats degrade to nulls but the
    standings-based pick still ships."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_standings_row(
        table, 2026, team_id=147, team_name="Yankees", league_id=LEAGUE_AL, league_rank=1
    )
    _seed_standings_row(
        table, 2026, team_id=119, team_name="Dodgers", league_id=LEAGUE_NL, league_rank=1
    )
    # Intentionally skip _seed_team_stats.

    fixed_now = _patched_now("2026-04-30")
    with patch("routes.featured_matchup.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        response = _invoke(games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["team_ids"] == [147, 119]
    assert body["data"]["teams"][0]["highlight_stats"]["era"] is None
