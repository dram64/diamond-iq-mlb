from __future__ import annotations

import os
import sys

# Match the api_players bootstrap pattern so the sibling api_responses.py is
# importable both inside the Lambda zip (everything at zip root) and in
# pytest (where this file is at functions/ai_compare/handler.py).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
import time  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

import boto3  # noqa: E402
from api_responses import build_data_response, build_error_response  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from shared.keys import (  # noqa: E402
    ai_analysis_pk,
    ai_analysis_sk,
    awards_pk,
    awards_sk,
    player_global_pk,
    player_sk,
    stats_pk,
    stats_sk,
    team_stats_pk,
    team_stats_sk,
)
from shared.log import get_logger  # noqa: E402

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
DEFAULT_FUNCTION_NAME = "diamond-iq-ai-compare"
CLOUDWATCH_NAMESPACE = "DiamondIQ/AICompare"

# with Haiku 3.5 (4.5 daily quota was exhausted during smoke-test in this
# account; quota increase ticket filed). Swappable via env var without
# code change once 4.5 quota lands.
DEFAULT_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
ANTHROPIC_BEDROCK_VERSION = "bedrock-2023-05-31"
MAX_TOKENS = 400  # ~300 words; 150-200 word analyses fit with headroom

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
CACHE_MAX_AGE_SECONDS = 600  # browser/CloudFront — short; cache freshness lives in DDB

MIN_IDS = 2
MAX_IDS = 4

TRANSIENT_ERROR_CODES = frozenset(
    {"ThrottlingException", "ServiceUnavailableException", "InternalServerException"}
)


SYSTEM_PROMPT_PLAYERS = """You are a baseball analyst writing for a stats-savvy audience. Compare \
the players using the structured stat lines and career hardware provided. \
Produce a single tight paragraph of 150-200 words. Lead with the most \
distinguishing statistical or career difference, then cover hitting/pitching \
production, then any meaningful gap in accolades. Stay grounded in the \
numbers given; do not invent stats or projections. Avoid hype language and \
exclamation points. Do not address the reader directly. Do not editorialize \
about future performance."""

SYSTEM_PROMPT_TEAMS = """You are a baseball analyst writing for a stats-savvy audience. Compare \
the teams using the structured aggregate hitting and pitching stat lines \
provided. Produce a single tight paragraph of 150-200 words. Lead with the \
biggest gap in run production or run prevention, support with secondary \
metrics (OPS, ERA, WHIP, OPP_AVG), and note any obvious profile contrast \
(power-vs-contact, rotation-vs-bullpen). Stay grounded in the numbers \
given; do not invent stats. Avoid hype language and exclamation points. \
Do not address the reader directly. Do not editorialize about future \
performance."""


# ── helpers ─────────────────────────────────────────────────────────────


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _strip_pk_sk(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def _decimal_safe(obj: Any) -> Any:
    """Recursively coerce Decimal / set / nested types to JSON-friendly forms."""
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    if isinstance(obj, dict):
        return {k: _decimal_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_decimal_safe(v) for v in obj]
    return obj


def _parse_ids(qs: dict[str, Any]) -> tuple[list[int] | None, dict[str, Any] | None]:
    raw_ids = (qs or {}).get("ids", "")
    parts = [p.strip() for p in raw_ids.split(",") if p.strip()]
    if len(parts) < MIN_IDS or len(parts) > MAX_IDS:
        return None, build_error_response(
            400,
            "invalid_ids_count",
            f"ids must be {MIN_IDS}..{MAX_IDS} comma-separated integers; got {len(parts)}",
        )
    try:
        return [int(p) for p in parts], None
    except ValueError:
        return None, build_error_response(400, "invalid_ids", "all ids must be integers")


# ── cache layer ─────────────────────────────────────────────────────────


def _read_cache(table: Any, kind: str, ids: list[int], season: int) -> dict[str, Any] | None:
    pk = ai_analysis_pk(kind, ids, season)
    item = table.get_item(Key={"PK": pk, "SK": ai_analysis_sk()}).get("Item")
    if not item:
        return None
    # TTL is a guard for the read side too: if a row is past its TTL but
    # DynamoDB hasn't reaped it yet, treat it as a miss.
    ttl = item.get("ttl")
    try:
        ttl_int = int(ttl) if ttl is not None else 0
    except (TypeError, ValueError):
        ttl_int = 0
    if ttl_int and ttl_int < int(time.time()):
        return None
    return item


def _write_cache(
    table: Any,
    kind: str,
    ids: list[int],
    season: int,
    *,
    text: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    elapsed_ms: int,
) -> None:
    expires_at = int(time.time()) + CACHE_TTL_SECONDS
    table.put_item(
        Item={
            "PK": ai_analysis_pk(kind, ids, season),
            "SK": ai_analysis_sk(),
            "kind": kind,
            "ids": sorted(ids),
            "season": season,
            "text": text,
            "model_id": model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "generation_elapsed_ms": elapsed_ms,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "ttl": expires_at,
        }
    )


# ── prompt assembly ─────────────────────────────────────────────────────


def _gather_players(table: Any, ids: list[int], season: int) -> list[dict[str, Any]]:
    """Fetch metadata + season stats + awards for each id. Raises if any
    metadata is missing — a comparison without one player's name is useless."""
    out: list[dict[str, Any]] = []
    for pid in ids:
        metadata = table.get_item(Key={"PK": player_global_pk(), "SK": player_sk(pid)}).get("Item")
        if not metadata:
            raise LookupError(f"player_not_found:{pid}")
        hitting = table.get_item(Key={"PK": stats_pk(season, "hitting"), "SK": stats_sk(pid)}).get(
            "Item"
        )
        pitching = table.get_item(
            Key={"PK": stats_pk(season, "pitching"), "SK": stats_sk(pid)}
        ).get("Item")
        awards = table.get_item(Key={"PK": awards_pk(), "SK": awards_sk(pid)}).get("Item")
        out.append(
            {
                "person_id": pid,
                "metadata": _strip_pk_sk(metadata),
                "hitting": _strip_pk_sk(hitting),
                "pitching": _strip_pk_sk(pitching),
                "awards": _strip_pk_sk(awards),
            }
        )
    return out


def _gather_teams(table: Any, ids: list[int], season: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tid in ids:
        item = table.get_item(Key={"PK": team_stats_pk(season), "SK": team_stats_sk(tid)}).get(
            "Item"
        )
        if not item:
            raise LookupError(f"team_not_found:{tid}")
        out.append(_strip_pk_sk(item))
    return out


def _build_player_user_text(players: list[dict[str, Any]], season: int) -> str:
    """Stable, deterministic JSON-shaped prompt body. Bedrock cache-friendly."""
    blob = {"season": season, "players": _decimal_safe(players)}
    return (
        f"Compare these {len(players)} MLB players' {season} season profiles. "
        f"Use only the fields in the JSON.\n\n"
        f"```json\n{json.dumps(blob, sort_keys=True)}\n```"
    )


def _build_team_user_text(teams: list[dict[str, Any]], season: int) -> str:
    blob = {"season": season, "teams": _decimal_safe(teams)}
    return (
        f"Compare these {len(teams)} MLB teams' {season} season aggregates. "
        f"Use only the fields in the JSON.\n\n"
        f"```json\n{json.dumps(blob, sort_keys=True)}\n```"
    )


# ── Bedrock invocation ──────────────────────────────────────────────────


def _invoke_bedrock(
    client: Any, *, model_id: str, system: str, user_text: str, max_tokens: int
) -> tuple[str, int, int]:
    body = {
        "anthropic_version": ANTHROPIC_BEDROCK_VERSION,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_text}],
    }
    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload = json.loads(response["body"].read().decode("utf-8"))
    text_blocks = [b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text"]
    text = "".join(text_blocks).strip()
    usage = payload.get("usage") or {}
    return text, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)


# ── Lambda handler ──────────────────────────────────────────────────────


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    table_name: str | None = None,
    bedrock_client: Any | None = None,
    model_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    request_id = getattr(context, "aws_request_id", None) if context else None
    log_ctx: dict[str, Any] = {"request_id": request_id}

    route_key = (event or {}).get("routeKey") or ""
    if route_key == "GET /api/compare-analysis/players":
        kind = "players"
        system = SYSTEM_PROMPT_PLAYERS
    elif route_key == "GET /api/compare-analysis/teams":
        kind = "teams"
        system = SYSTEM_PROMPT_TEAMS
    else:
        return build_error_response(404, "route_not_found", f"No handler for {route_key!r}")

    qs = (event or {}).get("queryStringParameters") or {}
    ids, err = _parse_ids(qs)
    if err is not None:
        return err

    season = _resolve_season(now)
    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))

    cached = _read_cache(table, kind, ids, season)
    if cached:
        payload = {
            "kind": kind,
            "ids": sorted(ids),
            "text": cached.get("text"),
            "model_id": cached.get("model_id"),
            "generated_at": cached.get("generated_at"),
            "cache_hit": True,
        }
        return build_data_response(
            payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS
        )

    try:
        if kind == "players":
            sources = _gather_players(table, ids, season)
            user_text = _build_player_user_text(sources, season)
        else:
            sources = _gather_teams(table, ids, season)
            user_text = _build_team_user_text(sources, season)
    except LookupError as err:
        message = str(err)
        if message.startswith("player_not_found:"):
            return build_error_response(404, "player_not_found", message)
        return build_error_response(404, "team_not_found", message)

    bedrock = bedrock_client or boto3.client("bedrock-runtime", region_name="us-east-1")
    resolved_model = model_id or DEFAULT_MODEL

    bedrock_started = time.monotonic()
    try:
        text, in_tok, out_tok = _invoke_bedrock(
            bedrock,
            model_id=resolved_model,
            system=system,
            user_text=user_text,
            max_tokens=MAX_TOKENS,
        )
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "Unknown")
        severity = "warning" if code in TRANSIENT_ERROR_CODES else "error"
        getattr(logger, severity)(
            "Bedrock invocation failed",
            extra={**log_ctx, "code": code, "kind": kind, "ids": ids},
        )
        return build_error_response(502, "bedrock_unavailable", f"Bedrock error: {code}")
    bedrock_ms = int((time.monotonic() - bedrock_started) * 1000)

    if not text:
        logger.error("Bedrock returned empty text", extra={**log_ctx, "kind": kind, "ids": ids})
        return build_error_response(502, "bedrock_empty", "Model returned empty analysis")

    try:
        _write_cache(
            table,
            kind,
            ids,
            season,
            text=text,
            model_id=resolved_model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            elapsed_ms=bedrock_ms,
        )
    except Exception as err:  # noqa: BLE001 - cache write must not break the response
        logger.warning(
            "AI cache write failed; serving uncached response",
            extra={**log_ctx, "error": str(err)},
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "AI compare analysis generated",
        extra={
            **log_ctx,
            "kind": kind,
            "ids": ids,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "bedrock_ms": bedrock_ms,
            "elapsed_ms": elapsed_ms,
            "model_id": resolved_model,
        },
    )

    payload = {
        "kind": kind,
        "ids": sorted(ids),
        "text": text,
        "model_id": resolved_model,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "cache_hit": False,
    }
    return build_data_response(payload, season=season, cache_max_age_seconds=CACHE_MAX_AGE_SECONDS)
