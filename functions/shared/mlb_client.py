"""HTTP client for the MLB Stats API.

Stdlib-only on purpose: keeps the Lambda zip small and cold start fast.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date
from typing import Any

USER_AGENT = "diamond-iq/0.1 (+https://github.com/dram64/diamond-iq)"
SCHEDULE_BASE = "https://statsapi.mlb.com/api/v1"
LIVE_BASE = "https://statsapi.mlb.com/api/v1.1"
DEFAULT_TIMEOUT_SECONDS = 10.0


class MLBAPIError(Exception):
    """Raised on a non-success response from the MLB Stats API."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class MLBNotFoundError(MLBAPIError):
    """Raised on a 404 from the MLB Stats API."""


class MLBTimeoutError(MLBAPIError):
    """Raised when a request to the MLB Stats API times out."""


def _request(url: str, *, timeout: float) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https only
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise MLBNotFoundError(f"MLB API 404: {url}", status=404) from e
        raise MLBAPIError(f"MLB API {e.code}: {url}", status=e.code) from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise MLBTimeoutError(f"MLB API timeout: {url}") from e
        raise MLBAPIError(f"MLB API request failed: {url} ({e.reason})") from e
    except TimeoutError as e:
        raise MLBTimeoutError(f"MLB API timeout: {url}") from e


def fetch_todays_schedule(
    *,
    today: date | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return the raw MLB Stats API schedule payload for the given date (defaults to today).

    Hydrates linescore + team (used by ingest_live_games) and probablePitcher
    (used by /api/games/featured for Preview-status game tiles). The
    probablePitcher hydrate adds ~1KB to the payload and is null-safe for
    games where MLB hasn't announced a starter yet.
    """
    when = today or date.today()
    url = (
        f"{SCHEDULE_BASE}/schedule?sportId=1&date={when.isoformat()}"
        "&hydrate=linescore,team,probablePitcher"
    )
    return _request(url, timeout=timeout)


def fetch_game(game_pk: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Return the raw MLB Stats API live-feed payload for a single game."""
    url = f"{LIVE_BASE}/game/{game_pk}/feed/live"
    return _request(url, timeout=timeout)


def _request_with_backoff(url: str, *, timeout: float, max_retries: int = 3) -> Any:
    """Issue a request, backing off exponentially on 5xx responses.

    Delays: 1s, 2s, 4s. After max_retries 5xx responses, the last error is
    re-raised so the caller can decide whether to swallow it (per-team
    isolation) or fail the run.
    """
    import time

    last_err: MLBAPIError | None = None
    for attempt in range(max_retries):
        try:
            return _request(url, timeout=timeout)
        except MLBAPIError as e:
            last_err = e
            # Only retry on 5xx and timeout. 4xx and other errors propagate.
            status = getattr(e, "status", None)
            if status is not None and 500 <= status < 600:
                time.sleep(2**attempt)
                continue
            if isinstance(e, MLBTimeoutError):
                time.sleep(2**attempt)
                continue
            raise
    assert last_err is not None  # noqa: S101 - mypy/clarity, loop always raises
    raise last_err


def fetch_teams(season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    """Return the list of MLB teams for the given season (sportId=1)."""
    url = f"{SCHEDULE_BASE}/teams?sportId=1&season={season}"
    payload = _request_with_backoff(url, timeout=timeout)
    return payload.get("teams") or []


def fetch_roster(
    team_id: int, season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """Return the active roster for one team in a given season."""
    url = f"{SCHEDULE_BASE}/teams/{team_id}/roster?season={season}&rosterType=Active"
    payload = _request_with_backoff(url, timeout=timeout)
    return payload.get("roster") or []


def fetch_people_bulk(
    person_ids: list[int], *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """Bulk-fetch player metadata for up to 50 personIds at a time.

    The API silently drops unknown IDs (returns 200 with whatever subset it
    knows). Caller compares requested vs returned to spot drops.
    """
    if not person_ids:
        return []
    csv = ",".join(str(pid) for pid in person_ids)
    url = f"{SCHEDULE_BASE}/people?personIds={csv}"
    payload = _request_with_backoff(url, timeout=timeout)
    return payload.get("people") or []


def fetch_schedule_finals(
    when: date, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """Return the list of games on `when` whose status is Final.

    Filters out Suspended/Postponed/Cancelled at the source so the caller
    only sees games with a complete-or-near-complete boxscore.
    """
    url = f"{SCHEDULE_BASE}/schedule?sportId=1&date={when.isoformat()}"
    payload = _request_with_backoff(url, timeout=timeout)
    games: list[dict[str, Any]] = []
    for d in payload.get("dates") or []:
        for g in d.get("games") or []:
            if (g.get("status") or {}).get("detailedState") == "Final":
                games.append(g)
    return games


def fetch_boxscore(game_pk: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Return the lightweight boxscore for a single game.

    /api/v1/game/{gamePk}/boxscore is materially smaller than the full
    /feed/live payload and contains everything we need: per-player stats,
    seasonStats, jerseyNumber, position, parentTeamId.
    """
    url = f"{SCHEDULE_BASE}/game/{game_pk}/boxscore"
    return _request_with_backoff(url, timeout=timeout)


def fetch_team_season_stats(
    team_id: int, season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> dict[str, dict[str, Any]]:
    """Return season-aggregate hitting + pitching stats for one team.

    `/teams/{id}/stats?stats=season&group=hitting,pitching` returns two
    `stats` blocks; we flatten to {"hitting": {...stat fields...},
    "pitching": {...}}. Either side may be missing if MLB hasn't published
    full aggregates yet (very rare); caller writes whichever sides exist.
    """
    url = (
        f"{SCHEDULE_BASE}/teams/{team_id}/stats?stats=season&group=hitting,pitching&season={season}"
    )
    payload = _request_with_backoff(url, timeout=timeout)
    out: dict[str, dict[str, Any]] = {}
    for block in payload.get("stats") or []:
        group = (block.get("group") or {}).get("displayName")
        splits = block.get("splits") or []
        if not splits or group not in ("hitting", "pitching"):
            continue
        # Each block has one split for season totals; take its `stat` dict.
        out[group] = splits[0].get("stat") or {}
    return out


def fetch_standings(
    season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """Return the raw standings records (one per division) for AL + NL.

    The MLB Stats API returns 6 division records (3 AL + 3 NL); each
    record has a `teamRecords` array with 5 teams. flattens
    these into 30 STANDINGS#<season>/STANDINGS#<teamId> rows.
    """
    url = f"{SCHEDULE_BASE}/standings?leagueId=103,104&season={season}"
    payload = _request_with_backoff(url, timeout=timeout)
    return payload.get("records") or []


def fetch_game_feed_live(
    game_pk: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Return the full /feed/live payload for a single game.

    Heavier than /boxscore (~100-500 KB) but includes plays.allPlays[]
    with per-pitch hitData — required for hardest-hit ingestion.
    """
    url = f"{LIVE_BASE}/game/{game_pk}/feed/live"
    return _request_with_backoff(url, timeout=timeout)


def fetch_player_awards(
    person_id: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """Return the raw awards list for a single player.

    `/api/v1/people/{id}/awards` returns mixed major-league and
    minor-league entries (SAL Mid-Season All-Star, etc.). Caller is
    responsible for filtering to MLB-tier awards (see ADR
    amendment for the allowlist of recognized id codes).
    """
    url = f"{SCHEDULE_BASE}/people/{person_id}/awards"
    payload = _request_with_backoff(url, timeout=timeout)
    return payload.get("awards") or []


def fetch_qualified_season_stats(
    season: int, group: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS, limit: int = 200
) -> list[dict[str, Any]]:
    """Return the bulk season stats splits for qualified players in one group.

    `group` ∈ {"hitting", "pitching"}. Each split contains player.id,
    team.id, and the full stat object — directly mappable to a
    STATS#<season>#<group> row. Pagination supported via offset; one page
    of 200 covers a full season's qualified pool with headroom.
    """
    url = (
        f"{SCHEDULE_BASE}/stats?stats=season&group={group}&season={season}"
        f"&playerPool=Qualified&limit={limit}"
    )
    payload = _request_with_backoff(url, timeout=timeout)
    stats_blocks = payload.get("stats") or []
    if not stats_blocks:
        return []
    return stats_blocks[0].get("splits") or []
