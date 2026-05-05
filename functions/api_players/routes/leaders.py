from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from api_responses import build_data_response, build_error_response
from boto3.dynamodb.conditions import Key
from shared.keys import statcast_pk, stats_pk

CACHE_MAX_AGE_SECONDS = 600
DEFAULT_LIMIT = 10
MAX_LIMIT = 50

# Single source of truth for supported leaders + sort direction.
#
# Required keys per stat:
#   field      — display label / response field key (URL token may differ;
#                see "k" → strikeouts).
#   direction  — "asc" (lower is better — ERA, WHIP, xERA) or "desc".
#
# Optional keys:
#   source     — "stats" (default; reads STATS#<season>#<group>) or
#                "statcast" (reads STATCAST#<season>; the value is
#                pulled via dotted `path`).
#   path       — only required when source="statcast". Dotted path
#                into the per-player Statcast item, e.g.
#                "hitting.barrel_percent", "bat_tracking.avg_bat_speed",
#                "pitching.xera". Must match the keys written by
#                ingest_statcast/handler.py.
_LEADER_STATS: dict[str, dict[str, dict[str, str]]] = {
    "hitting": {
        "avg": {"field": "avg", "direction": "desc"},
        "hr": {"field": "home_runs", "direction": "desc"},
        "rbi": {"field": "rbi", "direction": "desc"},
        "ops": {"field": "ops", "direction": "desc"},
        "woba": {"field": "woba", "direction": "desc"},
        "ops_plus": {"field": "ops_plus", "direction": "desc"},
        "bat_speed": {
            "field": "avg_bat_speed",
            "direction": "desc",
            "source": "statcast",
            "path": "bat_tracking.avg_bat_speed",
        },
        "barrel_percent": {
            "field": "barrel_percent",
            "direction": "desc",
            "source": "statcast",
            "path": "hitting.barrel_percent",
        },
        "max_hit_speed": {
            "field": "max_hit_speed",
            "direction": "desc",
            "source": "statcast",
            "path": "hitting.max_hit_speed",
        },
        "xwoba": {
            "field": "xwoba",
            "direction": "desc",
            "source": "statcast",
            "path": "hitting.xwoba",
        },
        "sprint_speed": {
            "field": "sprint_speed",
            "direction": "desc",
            "source": "statcast",
            "path": "hitting.sprint_speed",
        },
    },
    "pitching": {
        "era": {"field": "era", "direction": "asc"},
        "k": {"field": "strikeouts", "direction": "desc"},
        "whip": {"field": "whip", "direction": "asc"},
        "fip": {"field": "fip", "direction": "asc"},
        "wins": {"field": "wins", "direction": "desc"},
        "saves": {"field": "saves", "direction": "desc"},
        "xera": {
            "field": "xera",
            "direction": "asc",
            "source": "statcast",
            "path": "pitching.xera",
        },
        "whiff_percent": {
            "field": "whiff_percent",
            "direction": "desc",
            "source": "statcast",
            "path": "pitching.whiff_percent",
        },
        "fastball_avg_speed": {
            "field": "fastball_avg_speed",
            "direction": "desc",
            "source": "statcast",
            "path": "pitching.fastball_avg_speed",
        },
    },
}


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except (ArithmeticError, ValueError):
            return None
    return None


def _strip_pk_sk(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def _resolve_dotted(item: dict[str, Any], path: str) -> Any:
    """Walk a dotted path into a nested dict. 'hitting.barrel_percent'
    over {'hitting': {'barrel_percent': 18.4}} returns 18.4. Returns None
    on any missing key.
    """
    cur: Any = item
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def handle(event: dict[str, Any], *, table: Any, now: datetime | None = None) -> dict[str, Any]:
    path_params = (event or {}).get("pathParameters") or {}
    group = path_params.get("group")
    stat_token = path_params.get("stat")
    if group not in _LEADER_STATS:
        return build_error_response(
            400,
            "invalid_group",
            f"group must be one of {sorted(_LEADER_STATS.keys())}, got {group!r}",
        )
    if stat_token not in _LEADER_STATS[group]:
        return build_error_response(
            400,
            "invalid_stat",
            f"stat must be one of {sorted(_LEADER_STATS[group].keys())}, got {stat_token!r}",
        )

    config = _LEADER_STATS[group][stat_token]
    field = config["field"]
    descending = config["direction"] == "desc"
    source = config.get("source", "stats")
    path = config.get("path")

    qs = (event or {}).get("queryStringParameters") or {}
    raw_limit = qs.get("limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    season = _resolve_season(now)
    if source == "statcast":
        resp = table.query(KeyConditionExpression=Key("PK").eq(statcast_pk(season)))
    else:
        resp = table.query(KeyConditionExpression=Key("PK").eq(stats_pk(season, group)))
    items = resp.get("Items") or []

    sortable: list[tuple[Decimal, dict[str, Any]]] = []
    for item in items:
        if source == "statcast" and path is not None:
            raw_value = _resolve_dotted(item, path)
        else:
            raw_value = item.get(field)
        v = _to_decimal(raw_value)
        if v is None:
            continue
        sortable.append((v, item))
    sortable.sort(key=lambda pair: pair[0], reverse=descending)

    leaders = []
    for rank, (_, item) in enumerate(sortable[:limit], start=1):
        row = _strip_pk_sk(item)
        # On Statcast rows, hoist the leaderboard value to the top-level
        # `field` key so the response shape matches the stats-source path
        # (frontend reads `row[field]` uniformly). Also hoist
        # display_name → full_name so the LeaderRecord contract stays
        # uniform across both partitions (STATS rows already carry
        # `full_name`; STATCAST rows store the player as `display_name`).
        if source == "statcast" and path is not None:
            value = _resolve_dotted(item, path)
            if value is not None:
                row[field] = value
            if "full_name" not in row and "display_name" in row:
                row["full_name"] = row["display_name"]
        row["rank"] = rank
        leaders.append(row)

    payload = {
        "group": group,
        "stat": stat_token,
        "field": field,
        "direction": config["direction"],
        "limit": limit,
        "leaders": leaders,
    }
    return build_data_response(payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)
