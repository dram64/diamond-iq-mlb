"""GET /api/teams/{teamId}/roster — team roster with player metadata enrichment."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import boto3
from api_responses import build_data_response, build_error_response
from boto3.dynamodb.conditions import Key
from shared.keys import player_global_pk, player_sk, roster_pk

CACHE_MAX_AGE_SECONDS = 3600
BATCH_GET_CHUNK_SIZE = 100  # DynamoDB hard limit


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _strip_pk_sk(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def handle(
    event: dict[str, Any],
    *,
    table: Any,
    table_name: str,
    dynamodb_resource: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
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
    roster_resp = table.query(KeyConditionExpression=Key("PK").eq(roster_pk(season, team_id)))
    roster_items = roster_resp.get("Items") or []
    if not roster_items:
        return build_error_response(
            404, "team_not_found", f"No roster for teamId={team_id} in season {season}"
        )

    person_ids: list[int] = []
    for entry in roster_items:
        pid = entry.get("person_id")
        if isinstance(pid, int) or hasattr(pid, "to_integral_value"):
            person_ids.append(int(pid))

    metadata_by_id: dict[int, dict[str, Any]] = {}
    if person_ids:
        resource = dynamodb_resource or boto3.resource("dynamodb")
        for chunk_start in range(0, len(person_ids), BATCH_GET_CHUNK_SIZE):
            chunk = person_ids[chunk_start : chunk_start + BATCH_GET_CHUNK_SIZE]
            request_keys = [{"PK": player_global_pk(), "SK": player_sk(pid)} for pid in chunk]
            resp = resource.batch_get_item(RequestItems={table_name: {"Keys": request_keys}})
            for item in resp.get("Responses", {}).get(table_name, []):
                pid = item.get("person_id")
                if pid is not None:
                    metadata_by_id[int(pid)] = item

    enriched = []
    for entry in roster_items:
        pid = int(entry["person_id"]) if entry.get("person_id") is not None else None
        row = _strip_pk_sk(entry)
        if pid is not None and pid in metadata_by_id:
            row["metadata"] = _strip_pk_sk(metadata_by_id[pid])
        enriched.append(row)

    payload = {"team_id": team_id, "roster": enriched}
    return build_data_response(payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)
