from __future__ import annotations

from typing import Any

from api_responses import build_data_response, build_error_response
from boto3.dynamodb.conditions import Key

CACHE_MAX_AGE_SECONDS = 900


def _strip_pk_sk(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def handle(event: dict[str, Any], *, table: Any) -> dict[str, Any]:
    path_params = (event or {}).get("pathParameters") or {}
    raw_season = path_params.get("season")
    try:
        season = int(raw_season) if raw_season is not None else None
    except (TypeError, ValueError):
        season = None
    if season is None:
        return build_error_response(400, "invalid_season", "season must be an integer year")

    resp = table.query(KeyConditionExpression=Key("PK").eq(f"STANDINGS#{season}"))
    items = resp.get("Items") or []
    if not items:
        return build_error_response(
            503,
            "data_not_yet_available",
            f"Standings ingestion not yet enabled for season {season}",
            details={"season": season},
        )

    teams = [_strip_pk_sk(item) for item in items]
    payload = {"season": season, "teams": teams}
    return build_data_response(payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)
