"""GET /api/teams/compare?ids=<id1>,<id2>[,<id3>,<id4>] — side-by-side teams.

Same shape as /api/players/compare but team-keyed. Reads from the
TEAMSTATS#<season>/TEAMSTATS#<teamId> partition; missing teams produce a
404 (no row written = no team or no aggregates available yet).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api_responses import build_data_response, build_error_response
from shared.keys import team_stats_pk, team_stats_sk

CACHE_MAX_AGE_SECONDS = 900
MIN_IDS = 2
MAX_IDS = 4


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _strip_pk_sk(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def handle(event: dict[str, Any], *, table: Any, now: datetime | None = None) -> dict[str, Any]:
    qs = (event or {}).get("queryStringParameters") or {}
    raw_ids = qs.get("ids", "")
    parts = [p.strip() for p in raw_ids.split(",") if p.strip()]
    if len(parts) < MIN_IDS or len(parts) > MAX_IDS:
        return build_error_response(
            400,
            "invalid_ids_count",
            f"ids must contain between {MIN_IDS} and {MAX_IDS} comma-separated integers; got {len(parts)}",
        )
    try:
        team_ids = [int(p) for p in parts]
    except ValueError:
        return build_error_response(400, "invalid_ids", "all ids must be integers")

    season = _resolve_season(now)
    teams: list[dict[str, Any]] = []
    for tid in team_ids:
        item = table.get_item(Key={"PK": team_stats_pk(season), "SK": team_stats_sk(tid)}).get(
            "Item"
        )
        if not item:
            return build_error_response(
                404, "team_not_found", f"No team-stats row for team {tid} in season {season}"
            )
        teams.append(_strip_pk_sk(item))

    payload = {"season": season, "teams": teams}
    return build_data_response(payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)
