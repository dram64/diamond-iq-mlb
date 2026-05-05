from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from api_responses import build_data_response, build_error_response
from boto3.dynamodb.conditions import Key
from shared.keys import standings_pk, team_stats_pk, team_stats_sk

CACHE_MAX_AGE_SECONDS = 3600  # 1 hour — pair is stable through the UTC day

LEAGUE_AL = 103
LEAGUE_NL = 104

# Static team-id → abbreviation table for the top-of-card chip. The full
# mlbTeams catalog lives frontend-side; we hardcode just the abbreviation
# here to avoid duplicating the static team list backend-side.
_TEAM_ABBREV: dict[int, str] = {
    108: "LAA",
    109: "AZ",
    110: "BAL",
    111: "BOS",
    112: "CHC",
    113: "CIN",
    114: "CLE",
    115: "COL",
    116: "DET",
    117: "HOU",
    118: "KC",
    119: "LAD",
    120: "WSH",
    121: "NYM",
    133: "ATH",
    134: "PIT",
    135: "SD",
    136: "SEA",
    137: "SF",
    138: "STL",
    139: "TB",
    140: "TEX",
    141: "TOR",
    142: "MIN",
    143: "PHI",
    144: "ATL",
    145: "CWS",
    146: "MIA",
    147: "NYY",
    158: "MIL",
}


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).date().isoformat()


def _seed_for(date_iso: str, season: int, league: str) -> int:
    """Stable 32-bit seed derived from date + season + league."""
    digest = hashlib.sha256(f"{date_iso}#{season}#{league}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _read_standings(table: Any, season: int) -> list[dict[str, Any]]:
    resp = table.query(KeyConditionExpression=Key("PK").eq(standings_pk(season)))
    return resp.get("Items") or []


def _read_team_stats(table: Any, season: int, team_id: int) -> dict[str, Any] | None:
    return table.get_item(Key={"PK": team_stats_pk(season), "SK": team_stats_sk(team_id)}).get(
        "Item"
    )


def _league_label(league_id: Any) -> str:
    try:
        n = int(league_id)
    except (TypeError, ValueError):
        return "MLB"
    return "AL" if n == LEAGUE_AL else "NL" if n == LEAGUE_NL else "MLB"


def _pick_top_team(rows: list[dict[str, Any]], league_id: int, seed: int) -> dict[str, Any] | None:
    """Among teams in the given league, return the one with the lowest
    league_rank. If multiple teams tie at the minimum rank, seed-pick one
    deterministically.
    """
    in_league: list[dict[str, Any]] = []
    for r in rows:
        try:
            rid = int(r.get("league_id")) if r.get("league_id") is not None else None
        except (TypeError, ValueError):
            rid = None
        if rid != league_id:
            continue
        in_league.append(r)

    if not in_league:
        return None

    # league_rank is stored as a string (e.g. "1", "2", …). Parse defensively.
    def _rank(item: dict[str, Any]) -> int:
        raw = item.get("league_rank")
        try:
            return int(raw) if raw is not None else 99
        except (TypeError, ValueError):
            return 99

    min_rank = min(_rank(r) for r in in_league)
    tied = [r for r in in_league if _rank(r) == min_rank]
    if len(tied) == 1:
        return tied[0]

    # Sort tied rows by team_id for a stable index, then seed-pick.
    tied.sort(key=lambda r: int(r.get("team_id", 0)))
    return tied[seed % len(tied)]


def _team_payload(
    standings_row: dict[str, Any], stats_row: dict[str, Any] | None
) -> dict[str, Any]:
    try:
        team_id = int(standings_row.get("team_id"))
    except (TypeError, ValueError):
        team_id = 0

    hitting = (stats_row or {}).get("hitting") or {}
    pitching = (stats_row or {}).get("pitching") or {}

    return {
        "team_id": team_id,
        "team_name": standings_row.get("team_name"),
        "abbreviation": _TEAM_ABBREV.get(team_id),
        "league": _league_label(standings_row.get("league_id")),
        "wins": int(standings_row.get("wins") or 0),
        "losses": int(standings_row.get("losses") or 0),
        "games_back": standings_row.get("games_back"),
        "run_differential": (
            int(standings_row["run_differential"])
            if standings_row.get("run_differential") is not None
            else None
        ),
        "highlight_stats": {
            "avg": hitting.get("avg"),
            "ops": hitting.get("ops"),
            "era": pitching.get("era"),
            "whip": pitching.get("whip"),
        },
    }


def handle(
    event: dict[str, Any],  # noqa: ARG001 - reserved
    *,
    table: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    season = _resolve_season(now)
    date_iso = _today_iso(now)

    rows = _read_standings(table, season)
    if not rows:
        return build_error_response(
            503,
            "data_not_yet_available",
            "Standings partition is empty for this season",
            details={"season": season},
        )

    seed_al = _seed_for(date_iso, season, "AL")
    seed_nl = _seed_for(date_iso, season, "NL")
    pick_al = _pick_top_team(rows, LEAGUE_AL, seed_al)
    pick_nl = _pick_top_team(rows, LEAGUE_NL, seed_nl)

    if pick_al is None or pick_nl is None:
        return build_error_response(
            503,
            "data_not_yet_available",
            "Standings missing one or both league leaders",
            details={
                "season": season,
                "al_present": pick_al is not None,
                "nl_present": pick_nl is not None,
            },
        )

    al_team_id = int(pick_al["team_id"])
    nl_team_id = int(pick_nl["team_id"])

    al_stats = _read_team_stats(table, season, al_team_id)
    nl_stats = _read_team_stats(table, season, nl_team_id)

    payload = {
        "date": date_iso,
        "team_ids": [al_team_id, nl_team_id],
        "teams": [
            _team_payload(pick_al, al_stats),
            _team_payload(pick_nl, nl_stats),
        ],
        "selection_reason": "AL & NL standings leaders, deterministic by date",
    }
    return build_data_response(
        payload,
        season=season,
        cache_max_age_seconds=CACHE_MAX_AGE_SECONDS,
    )
