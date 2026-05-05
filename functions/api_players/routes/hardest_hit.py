from __future__ import annotations

import re
from typing import Any

from api_responses import build_data_response, build_error_response
from boto3.dynamodb.conditions import Key

CACHE_MAX_AGE_SECONDS = 3600
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _strip_pk_sk(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def handle(event: dict[str, Any], *, table: Any) -> dict[str, Any]:
    path_params = (event or {}).get("pathParameters") or {}
    date_iso = path_params.get("date")
    if not date_iso or not _DATE_RE.match(date_iso):
        return build_error_response(400, "invalid_date", "date must be YYYY-MM-DD")

    qs = (event or {}).get("queryStringParameters") or {}
    raw_limit = qs.get("limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    # Default ascending Query order returns top-velocity-first thanks to the
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"HITS#{date_iso}"),
        Limit=limit,
    )
    items = resp.get("Items") or []
    if not items:
        return build_error_response(
            503,
            "data_not_yet_available",
            f"Hardest-hit ingestion has no data for {date_iso}",
            details={"date": date_iso},
        )

    hits = [_strip_pk_sk(item) for item in items]
    payload = {"date": date_iso, "limit": limit, "hits": hits}
    season = int(date_iso[:4])
    return build_data_response(payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)
