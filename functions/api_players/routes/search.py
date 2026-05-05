from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api_responses import build_data_response, build_error_response
from boto3.dynamodb.conditions import Key
from shared.keys import player_global_pk

CACHE_MAX_AGE_SECONDS = 60  # short — players are added/deactivated mid-season
DEFAULT_LIMIT = 10
MAX_LIMIT = 25
MIN_QUERY_LEN = 2


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _project(item: dict[str, Any]) -> dict[str, Any]:
    """Lean payload — typeahead row needs id + name + position + team."""
    return {
        "person_id": item.get("person_id"),
        "full_name": item.get("full_name"),
        "primary_position_abbr": item.get("primary_position_abbr"),
        "primary_number": item.get("primary_number"),
    }


def _scan_player_partition(table: Any) -> list[dict[str, Any]]:
    """Page through PLAYER#GLOBAL and return every metadata row."""
    items: list[dict[str, Any]] = []
    last_key: dict[str, Any] | None = None
    while True:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(player_global_pk()),
            "ProjectionExpression": "person_id, full_name, primary_position_abbr, primary_number",
        }
        if last_key is not None:
            kwargs["ExclusiveStartKey"] = last_key
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return items


def handle(event: dict[str, Any], *, table: Any, now: datetime | None = None) -> dict[str, Any]:
    qs = (event or {}).get("queryStringParameters") or {}
    raw_q = (qs.get("q") or "").strip()
    if len(raw_q) < MIN_QUERY_LEN:
        return build_error_response(
            400,
            "invalid_query",
            f"q must be at least {MIN_QUERY_LEN} characters",
        )

    raw_limit = qs.get("limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        return build_error_response(
            400, "invalid_limit", f"limit must be an integer, got {raw_limit!r}"
        )
    if limit < 1 or limit > MAX_LIMIT:
        return build_error_response(
            400, "invalid_limit", f"limit must be 1..{MAX_LIMIT}, got {limit}"
        )

    needle = raw_q.casefold()
    rows = _scan_player_partition(table)

    # Rank: prefix-match first, then substring — both alphabetized by full
    # name. This keeps "Aaron Judge" above "Mike Judge" when the user types
    # "judge", which matches typeahead expectations.
    prefixed: list[dict[str, Any]] = []
    contained: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("full_name") or ""
        if not isinstance(name, str):
            continue
        folded = name.casefold()
        if folded.startswith(needle):
            prefixed.append(row)
        elif needle in folded:
            contained.append(row)

    prefixed.sort(key=lambda r: (r.get("full_name") or "").casefold())
    contained.sort(key=lambda r: (r.get("full_name") or "").casefold())
    matches = (prefixed + contained)[:limit]

    payload = {
        "query": raw_q,
        "results": [_project(r) for r in matches],
        "count": len(matches),
    }
    return build_data_response(
        payload,
        season=_resolve_season(now),
        cache_max_age_seconds=CACHE_MAX_AGE_SECONDS,
    )
