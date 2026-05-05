from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

# Importing the handler first runs its sys.path bootstrap so the route
# module's flat `from api_responses import ...` resolves at test time.
import api_players.handler  # noqa: F401
import boto3
from api_players.routes import featured_game


def _patched_now(date_iso: str) -> datetime:
    return datetime.fromisoformat(date_iso + "T12:00:00+00:00").astimezone(UTC)


def _team_block(
    *,
    team_id: int,
    team_name: str,
    abbreviation: str,
    wins: int,
    losses: int,
    probable_id: int | None = None,
    probable_name: str | None = None,
) -> dict[str, Any]:
    side: dict[str, Any] = {
        "team": {"id": team_id, "name": team_name, "abbreviation": abbreviation},
        "leagueRecord": {"wins": wins, "losses": losses, "pct": ".500"},
    }
    if probable_id is not None and probable_name is not None:
        side["probablePitcher"] = {
            "id": probable_id,
            "fullName": probable_name,
            "link": f"/api/v1/people/{probable_id}",
        }
    return side


def _game_block(
    *,
    game_pk: int,
    game_date: str,
    abstract_state: str,
    detailed_state: str,
    away: dict[str, Any],
    home: dict[str, Any],
    venue: str = "Test Stadium",
) -> dict[str, Any]:
    return {
        "gamePk": game_pk,
        "gameDate": game_date,
        "status": {
            "abstractGameState": abstract_state,
            "detailedState": detailed_state,
        },
        "venue": {"name": venue},
        "teams": {"away": away, "home": home},
    }


def _schedule(games: list[dict[str, Any]]) -> dict[str, Any]:
    if not games:
        return {"totalGames": 0, "dates": []}
    return {"totalGames": len(games), "dates": [{"games": games}]}


def _seed_standings(table: Any, season: int, *, team_id: int, run_diff: int) -> None:
    table.put_item(
        Item={
            "PK": f"STANDINGS#{season}",
            "SK": f"STANDINGS#{team_id}",
            "season": season,
            "team_id": team_id,
            "run_differential": run_diff,
        }
    )


def _invoke(table: Any, *, now: datetime, payload: dict[str, Any]) -> dict[str, Any]:
    return featured_game.handle(
        {},
        table=table,
        now=now,
        schedule_fetcher=lambda: payload,
    )


def test_picks_a_non_final_game_and_includes_probable_pitchers(dynamodb_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_standings(table, 2026, team_id=109, run_diff=-22)
    _seed_standings(table, 2026, team_id=158, run_diff=15)

    payload = _schedule(
        [
            _game_block(
                game_pk=823795,
                game_date="2026-04-30T17:40:00Z",
                abstract_state="Preview",
                detailed_state="Pre-Game",
                away=_team_block(
                    team_id=109,
                    team_name="Arizona Diamondbacks",
                    abbreviation="AZ",
                    wins=13,
                    losses=17,
                    probable_id=605288,
                    probable_name="Adrian Houser",
                ),
                home=_team_block(
                    team_id=158,
                    team_name="Milwaukee Brewers",
                    abbreviation="MIL",
                    wins=18,
                    losses=12,
                    probable_id=641835,
                    probable_name="Tim Mayza",
                ),
                venue="American Family Field",
            ),
        ]
    )

    response = _invoke(table, now=_patched_now("2026-04-30"), payload=payload)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["game_pk"] == 823795
    assert body["data"]["status"] == "preview"
    assert body["data"]["venue"] == "American Family Field"
    assert body["data"]["away"]["team_id"] == 109
    assert body["data"]["away"]["wins"] == 13
    assert body["data"]["away"]["run_differential"] == -22
    assert body["data"]["away"]["probable_pitcher"]["id"] == 605288
    assert body["data"]["away"]["probable_pitcher"]["full_name"] == "Adrian Houser"
    assert body["data"]["home"]["team_id"] == 158
    assert body["data"]["home"]["run_differential"] == 15
    assert body["data"]["home"]["probable_pitcher"]["full_name"] == "Tim Mayza"
    assert body["data"]["selection_reason"].startswith("Date-seeded")


def test_off_day_when_schedule_returns_zero_games(dynamodb_table, games_table_name):  # noqa: ARG001
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    response = _invoke(table, now=_patched_now("2026-12-25"), payload=_schedule([]))
    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"]["code"] == "off_day"


def test_503_when_mlb_api_raises(dynamodb_table, games_table_name):  # noqa: ARG001
    """When the upstream schedule fetch raises (timeout / 5xx), the
    route returns 503 data_not_yet_available — the frontend renders the
    same off-day banner path."""
    from shared.mlb_client import MLBTimeoutError

    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)

    def _raise() -> dict[str, Any]:
        raise MLBTimeoutError("simulated timeout")

    response = featured_game.handle(
        {},
        table=table,
        now=_patched_now("2026-04-30"),
        schedule_fetcher=_raise,
    )
    assert response["statusCode"] == 503
    body = json.loads(response["body"])
    assert body["error"]["code"] == "data_not_yet_available"


def test_falls_back_to_most_recent_final_when_all_finals(dynamodb_table, games_table_name):  # noqa: ARG001
    """If every game on today's slate is already Final, surface the
    latest one as a wrap-up tile (no probable pitchers rendered)."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)

    payload = _schedule(
        [
            _game_block(
                game_pk=1,
                game_date="2026-04-30T16:15:00Z",
                abstract_state="Final",
                detailed_state="Final",
                away=_team_block(
                    team_id=116,
                    team_name="Detroit Tigers",
                    abbreviation="DET",
                    wins=16,
                    losses=16,
                ),
                home=_team_block(
                    team_id=144,
                    team_name="Atlanta Braves",
                    abbreviation="ATL",
                    wins=18,
                    losses=12,
                ),
            ),
            _game_block(
                game_pk=2,
                game_date="2026-04-30T19:05:00Z",
                abstract_state="Final",
                detailed_state="Final",
                away=_team_block(
                    team_id=118, team_name="Royals", abbreviation="KC", wins=14, losses=18
                ),
                home=_team_block(
                    team_id=133, team_name="Athletics", abbreviation="ATH", wins=10, losses=22
                ),
            ),
        ]
    )

    response = _invoke(table, now=_patched_now("2026-04-30"), payload=payload)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    # Latest Final by start_time wins.
    assert body["data"]["game_pk"] == 2
    assert body["data"]["status"] == "final"
    # Probable pitchers hidden on Final.
    assert body["data"]["away"]["probable_pitcher"] is None
    assert body["data"]["home"]["probable_pitcher"] is None
    assert "Most recent Final" in body["data"]["selection_reason"]


def test_pick_is_stable_within_a_utc_day(dynamodb_table, games_table_name):  # noqa: ARG001
    """Two invocations on the same UTC day with the same slate must
    return the same game_pk."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    payload = _schedule(
        [
            _game_block(
                game_pk=10 + i,
                game_date=f"2026-04-30T{17 + i}:00:00Z",
                abstract_state="Preview",
                detailed_state="Pre-Game",
                away=_team_block(
                    team_id=100 + i,
                    team_name=f"Away{i}",
                    abbreviation=f"A{i}",
                    wins=10,
                    losses=10,
                ),
                home=_team_block(
                    team_id=200 + i,
                    team_name=f"Home{i}",
                    abbreviation=f"H{i}",
                    wins=12,
                    losses=8,
                ),
            )
            for i in range(5)
        ]
    )
    a = json.loads(_invoke(table, now=_patched_now("2026-04-30"), payload=payload)["body"])
    b = json.loads(_invoke(table, now=_patched_now("2026-04-30"), payload=payload)["body"])
    assert a["data"]["game_pk"] == b["data"]["game_pk"]


def test_pick_rotates_across_utc_days(dynamodb_table, games_table_name):  # noqa: ARG001
    """Across several UTC days with the same 5-game slate, the seeded
    pick should yield at least 2 distinct game_pk values."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    payload = _schedule(
        [
            _game_block(
                game_pk=10 + i,
                game_date=f"2026-04-30T{17 + i}:00:00Z",
                abstract_state="Preview",
                detailed_state="Pre-Game",
                away=_team_block(
                    team_id=100 + i,
                    team_name=f"Away{i}",
                    abbreviation=f"A{i}",
                    wins=10,
                    losses=10,
                ),
                home=_team_block(
                    team_id=200 + i,
                    team_name=f"Home{i}",
                    abbreviation=f"H{i}",
                    wins=12,
                    losses=8,
                ),
            )
            for i in range(5)
        ]
    )
    picks: set[int] = set()
    for date_iso in ("2026-04-28", "2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02"):
        body = json.loads(_invoke(table, now=_patched_now(date_iso), payload=payload)["body"])
        picks.add(int(body["data"]["game_pk"]))
    assert len(picks) >= 2


def test_works_when_standings_unseeded(dynamodb_table, games_table_name):  # noqa: ARG001
    """If STANDINGS isn't ingested yet, run_differential degrades to None
    but the schedule-derived fields still ship."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    payload = _schedule(
        [
            _game_block(
                game_pk=5,
                game_date="2026-04-30T18:00:00Z",
                abstract_state="Preview",
                detailed_state="Scheduled",
                away=_team_block(
                    team_id=147, team_name="Yankees", abbreviation="NYY", wins=21, losses=10
                ),
                home=_team_block(
                    team_id=119, team_name="Dodgers", abbreviation="LAD", wins=22, losses=9
                ),
            )
        ]
    )
    response = _invoke(table, now=_patched_now("2026-04-30"), payload=payload)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["away"]["wins"] == 21
    assert body["data"]["away"]["run_differential"] is None
    assert body["data"]["home"]["run_differential"] is None
