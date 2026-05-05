"""Daily content generation Lambda — recaps, previews, featured analysis.

Triggered three times per day (15:00, 16:00, 17:00 UTC) by EventBridge.
Idempotency check makes the second and third ticks no-ops if the first
succeeded; if the first partially failed, later ticks fill in the gaps.

Pipeline per invocation:
  1. Determine target date (today UTC, override via event.date).
  2. Look up which content SKs already exist for the date.
  3. Read yesterday's Final games (recap source) and today's Preview
     games (preview + featured source) from DynamoDB.
  4. Pick the top-2 featured games via the heuristic in `score_game`.
  5. For each missing item: call Bedrock, write the result, update
     counters. Per-item failures are caught and logged; one bad item
     does not abort the run.

Bedrock client and DynamoDB table are dependency-injected so tests can
stub them with botocore.stub.Stubber and a moto-mocked table.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError
from shared.dynamodb import (
    list_existing_content_sks,
    list_todays_games,
    put_content_item,
)
from shared.log import get_logger
from shared.mlb_teams import get_team
from shared.models import Game
from shared.prompts import (
    FEATURED_SYSTEM,
    FEATURED_TEMPLATE,
    PREVIEW_SYSTEM,
    PREVIEW_TEMPLATE,
    RECAP_SYSTEM,
    RECAP_TEMPLATE,
    render_linescore_block,
    render_recent_form_block,
    render_top_performers_block,
)

logger = get_logger(__name__)

DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
ANTHROPIC_BEDROCK_VERSION = "bedrock-2023-05-31"
MAX_TOKENS_RECAP = 800
MAX_TOKENS_PREVIEW = 300
MAX_TOKENS_FEATURED = 800
TRANSIENT_ERROR_CODES = frozenset(
    {"ThrottlingException", "ServiceUnavailableException", "InternalServerException"}
)

CLOUDWATCH_NAMESPACE = "DiamondIQ/Content"


def _today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def _yesterday_iso(today_iso: str) -> str:
    return (datetime.fromisoformat(today_iso).date() - timedelta(days=1)).isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def score_game(game: Game, won_last: dict[int, bool]) -> float:
    """Rank a Preview game for featured selection.

    Heuristic:
      +2.0 same-division matchup
      +1.0 per team that won its previous game
      +0.5 home team plays in Pacific Time
    """
    score = 0.0
    away = get_team(game.away_team.id)
    home = get_team(game.home_team.id)

    if away is not None and home is not None and away.division == home.division:
        score += 2.0

    score += 1.0 if won_last.get(game.away_team.id, False) else 0.0
    score += 1.0 if won_last.get(game.home_team.id, False) else 0.0

    if home is not None and home.pacific_time:
        score += 0.5

    return score


def select_featured(previews: list[Game], won_last: dict[int, bool]) -> list[Game]:
    """Pick up to two featured games. Tie-break: smaller game_pk wins."""
    ranked = sorted(previews, key=lambda g: (-score_game(g, won_last), g.game_pk))
    return ranked[:2]


def _build_won_last_map(yesterday_finals: list[Game]) -> dict[int, bool]:
    """Map team_id → True if that team won its game yesterday.

    Teams that were not on yesterday's slate are not in the map; callers should
    treat absence as False.
    """
    result: dict[int, bool] = {}
    for game in yesterday_finals:
        if game.away_score > game.home_score:
            result[game.away_team.id] = True
            result[game.home_team.id] = False
        elif game.home_score > game.away_score:
            result[game.home_team.id] = True
            result[game.away_team.id] = False
        # Ties (rare; suspended games) leave both unset.
    return result


def _full_name(game_team_id: int, fallback_name: str) -> str:
    team = get_team(game_team_id)
    return team.full_name if team else fallback_name


def _invoke_bedrock(
    client: Any, *, model_id: str, system: str, user_text: str, max_tokens: int
) -> tuple[str, int, int]:
    """Call Bedrock invoke_model and return (text, input_tokens, output_tokens)."""
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


def _render_recap_user(game: Game, top_performers: list[dict[str, object]] | None = None) -> str:
    return RECAP_TEMPLATE.format(
        away_full_name=_full_name(game.away_team.id, game.away_team.name),
        home_full_name=_full_name(game.home_team.id, game.home_team.name),
        away_score=game.away_score,
        home_score=game.home_score,
        detailed_state=game.detailed_state or "Final",
        date=game.date,
        venue_or_unknown=game.venue or "unknown",
        linescore_block=render_linescore_block(
            {
                "inning": game.linescore.inning if game.linescore else None,
                "away_runs": game.linescore.away_runs if game.linescore else None,
                "home_runs": game.linescore.home_runs if game.linescore else None,
            }
            if game.linescore
            else None
        ),
        top_performers_block=render_top_performers_block(top_performers),
    )


def _render_preview_user(game: Game) -> str:
    return PREVIEW_TEMPLATE.format(
        away_full_name=_full_name(game.away_team.id, game.away_team.name),
        home_full_name=_full_name(game.home_team.id, game.home_team.name),
        start_time_utc=game.start_time_utc,
        venue_or_unknown=game.venue or "unknown",
        recent_form_block=render_recent_form_block(None),
    )


def _render_featured_user(game: Game) -> str:
    away = get_team(game.away_team.id)
    home = get_team(game.home_team.id)
    same_division = bool(away and home and away.division == home.division)
    return FEATURED_TEMPLATE.format(
        away_full_name=_full_name(game.away_team.id, game.away_team.name),
        home_full_name=_full_name(game.home_team.id, game.home_team.name),
        start_time_utc=game.start_time_utc,
        venue_or_unknown=game.venue or "unknown",
        same_division="yes" if same_division else "no",
        recent_form_block=render_recent_form_block(None),
    )


def _classify_bedrock_error(err: ClientError) -> tuple[str, str]:
    code = err.response.get("Error", {}).get("Code", "Unknown")
    severity = "warning" if code in TRANSIENT_ERROR_CODES else "error"
    return code, severity


def _generate_one(
    *,
    bedrock_client: Any,
    model_id: str,
    system: str,
    user_text: str,
    max_tokens: int,
    content_type: str,
    key_suffix: int,
    date: str,
    game_pk: int | None = None,
    table_name: str | None,
    log_ctx: dict[str, Any],
    counters: dict[str, int],
) -> None:
    """Run one content item end-to-end. Mutates counters in place."""
    sk = f"{content_type}#{key_suffix}"
    item_ctx = {**log_ctx, "sk": sk, "content_type": content_type}
    try:
        text, input_tokens, output_tokens = _invoke_bedrock(
            bedrock_client,
            model_id=model_id,
            system=system,
            user_text=user_text,
            max_tokens=max_tokens,
        )
    except ClientError as err:
        code, severity = _classify_bedrock_error(err)
        counters["bedrock_failures"] += 1
        log_fn = logger.warning if severity == "warning" else logger.error
        log_fn(
            "Bedrock invocation failed",
            extra={**item_ctx, "error_code": code, "error_message": str(err)},
        )
        return
    except Exception as err:  # noqa: BLE001 - per-item isolation
        counters["bedrock_failures"] += 1
        logger.error(
            "Bedrock invocation raised unexpected exception",
            extra={**item_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )
        return

    if not text:
        counters["bedrock_failures"] += 1
        logger.error("Bedrock returned empty text", extra=item_ctx)
        return

    try:
        put_content_item(
            content_type=content_type,
            date=date,
            key_suffix=key_suffix,
            text=text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            generated_at_utc=_now_iso(),
            game_pk=game_pk,
            table_name=table_name,
        )
        counters["items_written"] += 1
    except Exception as err:  # noqa: BLE001 - per-item isolation
        counters["dynamodb_failures"] += 1
        logger.error(
            "DynamoDB put_content_item failed",
            extra={**item_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def _emit_metrics(
    cloudwatch_client: Any,
    function_name: str,
    *,
    items_written: int,
    items_skipped: int,
    bedrock_failures: int,
    dynamodb_failures: int,
) -> None:
    """Publish run counters to CloudWatch under DiamondIQ/Content.

    Wrapped at the call site in try/except — emission must never fail the
    Lambda. Metric values are integers (Count unit). Dimension is
    LambdaFunction so multiple Lambdas could share the namespace later.
    """
    dimensions = [{"Name": "LambdaFunction", "Value": function_name}]
    cloudwatch_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                "MetricName": "BedrockFailures",
                "Value": bedrock_failures,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "DynamoDBFailures",
                "Value": dynamodb_failures,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "ItemsWritten",
                "Value": items_written,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "ItemsSkipped",
                "Value": items_skipped,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
        ],
    )


def _safe_emit_metrics(
    cloudwatch_client: Any | None,
    function_name: str | None,
    summary: dict[str, Any],
    log_ctx: dict[str, Any],
) -> None:
    if cloudwatch_client is None or function_name is None:
        return
    try:
        _emit_metrics(
            cloudwatch_client,
            function_name,
            items_written=int(summary.get("items_written", 0)),
            items_skipped=int(summary.get("items_skipped", 0)),
            bedrock_failures=int(summary.get("bedrock_failures", 0)),
            dynamodb_failures=int(summary.get("dynamodb_failures", 0)),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    bedrock_client: Any | None = None,
    cloudwatch_client: Any | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", None) if context else None
    function_name = getattr(context, "function_name", None) if context else None
    today = (event or {}).get("date") or _today_utc()
    yesterday = _yesterday_iso(today)
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL)
    log_ctx: dict[str, Any] = {
        "request_id": request_id,
        "date": today,
        "yesterday": yesterday,
        "model_id": model_id,
    }
    client = bedrock_client or boto3.client("bedrock-runtime", region_name="us-east-1")
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    yesterday_finals = [
        g for g in list_todays_games(yesterday, table_name=table_name) if g.status == "final"
    ]
    today_previews = [
        g for g in list_todays_games(today, table_name=table_name) if g.status == "preview"
    ]
    won_last = _build_won_last_map(yesterday_finals)
    featured = select_featured(today_previews, won_last)

    expected_sks: set[str] = set()
    expected_sks.update(f"RECAP#{g.game_pk}" for g in yesterday_finals)
    expected_sks.update(f"PREVIEW#{g.game_pk}" for g in today_previews)
    expected_sks.update(f"FEATURED#{i + 1}" for i in range(len(featured)))

    existing_sks = list_existing_content_sks(today, table_name=table_name)
    missing_sks = expected_sks - existing_sks

    if not expected_sks:
        logger.info("No qualifying games; nothing to generate", extra=log_ctx)
        empty_summary = {
            "ok": True,
            "date": today,
            "expected_items": 0,
            "items_written": 0,
            "items_skipped": 0,
            "bedrock_failures": 0,
            "dynamodb_failures": 0,
        }
        _safe_emit_metrics(cw_client, function_name, empty_summary, log_ctx)
        return empty_summary

    if not missing_sks:
        logger.info(
            "All content already present; idempotent skip",
            extra={**log_ctx, "expected_items": len(expected_sks)},
        )
        skip_summary = {
            "ok": True,
            "date": today,
            "expected_items": len(expected_sks),
            "items_written": 0,
            "items_skipped": len(expected_sks),
            "bedrock_failures": 0,
            "dynamodb_failures": 0,
        }
        _safe_emit_metrics(cw_client, function_name, skip_summary, log_ctx)
        return skip_summary

    counters = {"items_written": 0, "bedrock_failures": 0, "dynamodb_failures": 0}

    for game in yesterday_finals:
        if f"RECAP#{game.game_pk}" in existing_sks:
            continue
        _generate_one(
            bedrock_client=client,
            model_id=model_id,
            system=RECAP_SYSTEM,
            user_text=_render_recap_user(game),
            max_tokens=MAX_TOKENS_RECAP,
            content_type="RECAP",
            key_suffix=game.game_pk,
            date=today,
            table_name=table_name,
            log_ctx=log_ctx,
            counters=counters,
        )

    for game in today_previews:
        if f"PREVIEW#{game.game_pk}" in existing_sks:
            continue
        _generate_one(
            bedrock_client=client,
            model_id=model_id,
            system=PREVIEW_SYSTEM,
            user_text=_render_preview_user(game),
            max_tokens=MAX_TOKENS_PREVIEW,
            content_type="PREVIEW",
            key_suffix=game.game_pk,
            date=today,
            table_name=table_name,
            log_ctx=log_ctx,
            counters=counters,
        )

    for rank, game in enumerate(featured, start=1):
        if f"FEATURED#{rank}" in existing_sks:
            continue
        _generate_one(
            bedrock_client=client,
            model_id=model_id,
            system=FEATURED_SYSTEM,
            user_text=_render_featured_user(game),
            max_tokens=MAX_TOKENS_FEATURED,
            content_type="FEATURED",
            key_suffix=rank,
            date=today,
            game_pk=game.game_pk,
            table_name=table_name,
            log_ctx=log_ctx,
            counters=counters,
        )

    items_skipped = len(expected_sks) - len(missing_sks)
    total_failures = counters["bedrock_failures"] + counters["dynamodb_failures"]
    ok = counters["items_written"] > 0 or total_failures == 0

    summary = {
        "ok": ok,
        "date": today,
        "expected_items": len(expected_sks),
        "items_written": counters["items_written"],
        "items_skipped": items_skipped,
        "bedrock_failures": counters["bedrock_failures"],
        "dynamodb_failures": counters["dynamodb_failures"],
    }
    logger.info("Daily content generation complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
