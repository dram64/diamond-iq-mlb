from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from api_responses import build_data_response, build_error_response
from boto3.dynamodb.conditions import Key
from shared.keys import standings_pk
from shared.mlb_client import (
    MLBAPIError,
    MLBTimeoutError,
    fetch_todays_schedule,
)
from shared.models import normalize_game

CACHE_MAX_AGE_SECONDS = 180  # 3 min — pair stable across reloads, refreshes mid-day
NON_FINAL_STATUSES = {"scheduled", "preview", "live"}


def _seed(date_iso: str) -> int:
    digest = hashlib.sha256(date_iso.encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).date().isoformat()


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _read_standings_by_team(table: Any, season: int) -> dict[int, dict[str, Any]]:
    """Return STANDINGS rows for the season keyed by team_id, for the
    run_differential / wins / losses join.
    """
    resp = table.query(KeyConditionExpression=Key("PK").eq(standings_pk(season)))
    rows: dict[int, dict[str, Any]] = {}
    for r in resp.get("Items") or []:
        try:
            tid = int(r.get("team_id"))
        except (TypeError, ValueError):
            continue
        rows[tid] = r
    return rows


def _games_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for d in payload.get("dates") or []:
        for g in d.get("games") or []:
            games.append(g)
    return games


def _pick_featured(raw_games: list[dict[str, Any]], date_iso: str) -> dict[str, Any] | None:
    """Date-seeded pick among non-final games, falling back to the most
    recent Final if every game on today's slate is already over.
    """
    if not raw_games:
        return None

    normalized = []
    for g in raw_games:
        try:
            normalized.append(normalize_game(g))
        except (TypeError, ValueError, KeyError):
            # Defensive: malformed game in the schedule payload — skip it.
            continue

    candidates = [g for g in normalized if g.status in NON_FINAL_STATUSES]
    if candidates:
        seed = _seed(date_iso)
        return {"normalized": candidates[seed % len(candidates)], "is_fallback_final": False}

    # All games are Final — surface the latest one as a "wrap-up" tile.
    finals = [g for g in normalized if g.status == "final"]
    if not finals:
        return None
    finals.sort(key=lambda g: g.start_time_utc, reverse=True)
    return {"normalized": finals[0], "is_fallback_final": True}


def _team_record_from_schedule(side: dict[str, Any]) -> tuple[int, int]:
    """Pull current W-L from the schedule payload's leagueRecord block,
    which is populated for every status (Preview through Final).
    """
    rec = side.get("leagueRecord") or {}
    try:
        wins = int(rec.get("wins") or 0)
        losses = int(rec.get("losses") or 0)
    except (TypeError, ValueError):
        wins, losses = 0, 0
    return wins, losses


def handle(
    event: dict[str, Any],  # noqa: ARG001 - reserved
    *,
    table: Any,
    now: datetime | None = None,
    schedule_fetcher: Any = None,
) -> dict[str, Any]:
    """Build today's featured-game tile.

    schedule_fetcher is injected for tests; defaults to the live MLB
    Stats API client. Same dependency-injection pattern as the existing
    routes that hit DynamoDB.
    """
    date_iso = _today_iso(now)
    season = _resolve_season(now)

    fetcher = schedule_fetcher or (lambda: fetch_todays_schedule(today=now.date() if now else None))
    try:
        schedule_payload = fetcher()
    except (MLBAPIError, MLBTimeoutError, OSError):
        return build_error_response(
            503,
            "data_not_yet_available",
            "Schedule unavailable from upstream",
            details={"date": date_iso},
        )

    raw_games = _games_from_payload(schedule_payload)
    if not raw_games or schedule_payload.get("totalGames") == 0:
        return build_error_response(
            503,
            "off_day",
            "No MLB games scheduled today",
            details={"date": date_iso},
        )

    pick = _pick_featured(raw_games, date_iso)
    if pick is None:
        return build_error_response(
            503,
            "off_day",
            "No MLB games scheduled today",
            details={"date": date_iso},
        )

    chosen_norm = pick["normalized"]
    is_fallback_final = pick["is_fallback_final"]

    # Find the same game in the raw list to recover leagueRecord (the
    # normalizer dropped it). game_pk is the join key.
    raw_chosen: dict[str, Any] | None = None
    for g in raw_games:
        if int(g.get("gamePk") or 0) == chosen_norm.game_pk:
            raw_chosen = g
            break
    if raw_chosen is None:
        # Should not happen — defensive. Treat as off-day.
        return build_error_response(
            503,
            "off_day",
            "Failed to resolve picked game in schedule payload",
            details={"date": date_iso},
        )

    raw_teams = raw_chosen.get("teams") or {}
    raw_away = raw_teams.get("away") or {}
    raw_home = raw_teams.get("home") or {}

    try:
        standings_by_team = _read_standings_by_team(table, season)
    except Exception:  # noqa: BLE001 — DynamoDB read failure shouldn't block the tile.
        standings_by_team = {}

    # Probable pitchers: only Preview / Scheduled. Live + Final hide them.
    include_probable = chosen_norm.status in {"scheduled", "preview"} and not is_fallback_final

    away_payload = _build_side(
        chosen_norm.away_team,
        chosen_norm.away_probable_pitcher,
        raw_away,
        standings_by_team.get(chosen_norm.away_team.id),
        include_probable=include_probable,
    )
    home_payload = _build_side(
        chosen_norm.home_team,
        chosen_norm.home_probable_pitcher,
        raw_home,
        standings_by_team.get(chosen_norm.home_team.id),
        include_probable=include_probable,
    )

    selection_reason = (
        "Most recent Final — no upcoming games today"
        if is_fallback_final
        else "Date-seeded among today's non-final games"
    )

    body = {
        "date": date_iso,
        "game_pk": chosen_norm.game_pk,
        "status": chosen_norm.status,
        "detailed_state": chosen_norm.detailed_state,
        "start_time_utc": chosen_norm.start_time_utc,
        "venue": chosen_norm.venue,
        "away": away_payload,
        "home": home_payload,
        "selection_reason": selection_reason,
    }
    return build_data_response(body, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)


def _build_side(
    team: Any,
    probable: Any,
    raw_side: dict[str, Any],
    standings_row: dict[str, Any] | None,
    *,
    include_probable: bool,
) -> dict[str, Any]:
    wins, losses = _team_record_from_schedule(raw_side)
    run_diff: int | None = None
    if standings_row is not None and standings_row.get("run_differential") is not None:
        try:
            run_diff = int(standings_row["run_differential"])
        except (TypeError, ValueError):
            run_diff = None

    side: dict[str, Any] = {
        "team_id": team.id,
        "team_name": team.name,
        "abbreviation": team.abbreviation,
        "wins": wins,
        "losses": losses,
        "run_differential": run_diff,
        "probable_pitcher": None,
    }
    if include_probable and probable is not None:
        side["probable_pitcher"] = {
            "id": probable.id,
            "full_name": probable.full_name,
        }
    return side
