"""GET /api/players/compare?ids=<id1>,<id2>[,<id3>,<id4>] — side-by-side."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api_responses import build_data_response, build_error_response
from shared.keys import (
    awards_pk,
    awards_sk,
    player_global_pk,
    player_sk,
    statcast_pk,
    statcast_sk,
    stats_pk,
    stats_sk,
)

CACHE_MAX_AGE_SECONDS = 300
MIN_IDS = 2
MAX_IDS = 4


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _strip_pk_sk(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
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
        person_ids = [int(p) for p in parts]
    except ValueError:
        return build_error_response(400, "invalid_ids", "all ids must be integers")

    season = _resolve_season(now)
    players: list[dict[str, Any]] = []
    for pid in person_ids:
        metadata = table.get_item(Key={"PK": player_global_pk(), "SK": player_sk(pid)}).get("Item")
        if not metadata:
            return build_error_response(404, "player_not_found", f"No player with id {pid}")
        hitting = table.get_item(Key={"PK": stats_pk(season, "hitting"), "SK": stats_sk(pid)}).get(
            "Item"
        )
        pitching = table.get_item(
            Key={"PK": stats_pk(season, "pitching"), "SK": stats_sk(pid)}
        ).get("Item")
        # Awards are optional — if the awards-ingest cron hasn't run yet
        # for this player, the payload simply lacks an `awards` block.
        awards = table.get_item(Key={"PK": awards_pk(), "SK": awards_sk(pid)}).get("Item")
        # player who isn't in the qualified pool for any of the 5 Savant
        # leaderboards simply lacks a statcast row.
        statcast = table.get_item(Key={"PK": statcast_pk(season), "SK": statcast_sk(pid)}).get(
            "Item"
        )
        players.append(
            {
                "person_id": pid,
                "metadata": _strip_pk_sk(metadata),
                "hitting": _strip_pk_sk(hitting),
                "pitching": _strip_pk_sk(pitching),
                "awards": _strip_pk_sk(awards),
                "statcast": _strip_pk_sk(statcast),
            }
        )

    payload = {"players": players}
    return build_data_response(payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)
