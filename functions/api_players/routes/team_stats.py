from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api_responses import build_data_response, build_error_response
from shared.keys import team_stats_pk, team_stats_sk

CACHE_MAX_AGE_SECONDS = 900


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _strip_pk_sk(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def handle(event: dict[str, Any], *, table: Any, now: datetime | None = None) -> dict[str, Any]:
    path_params = (event or {}).get("pathParameters") or {}
    raw_team_id = path_params.get("teamId")
    if raw_team_id is None:
        return build_error_response(400, "missing_team_id", "teamId is required")
    try:
        team_id = int(raw_team_id)
    except (TypeError, ValueError):
        return build_error_response(
            400, "invalid_team_id", f"teamId must be an integer, got {raw_team_id!r}"
        )

    season = _resolve_season(now)
    resp = table.get_item(Key={"PK": team_stats_pk(season), "SK": team_stats_sk(team_id)})
    item = resp.get("Item")
    if not item:
        return build_error_response(
            503,
            "data_not_yet_available",
            f"Team-stats ingestion has no data for team {team_id} in season {season}",
            details={"team_id": team_id, "season": season},
        )

    return build_data_response(
        _strip_pk_sk(item), season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS
    )
