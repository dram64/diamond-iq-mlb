"""Tests for the GET /content/today API route."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from api_scoreboard.handler import lambda_handler
from shared.dynamodb import put_content_item

pytestmark = pytest.mark.usefixtures("dynamodb_table")


def _content_event(date: str | None = None) -> dict[str, Any]:
    return {
        "routeKey": "GET /content/today",
        "rawPath": "/content/today",
        "queryStringParameters": {"date": date} if date else None,
    }


def _body(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["body"])


def _seed_recap(date: str, game_pk: int, table_name: str, *, text: str = "Recap.") -> None:
    put_content_item(
        content_type="RECAP",
        date=date,
        key_suffix=game_pk,
        text=text,
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=200,
        generated_at_utc=f"{date}T15:00:00+00:00",
        table_name=table_name,
    )


def _seed_preview(date: str, game_pk: int, table_name: str, *, text: str = "Preview.") -> None:
    put_content_item(
        content_type="PREVIEW",
        date=date,
        key_suffix=game_pk,
        text=text,
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=80,
        output_tokens=100,
        generated_at_utc=f"{date}T15:00:00+00:00",
        table_name=table_name,
    )


def _seed_featured(
    date: str, rank: int, game_pk: int, table_name: str, *, text: str = "Featured."
) -> None:
    put_content_item(
        content_type="FEATURED",
        date=date,
        key_suffix=rank,
        text=text,
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=120,
        output_tokens=300,
        generated_at_utc=f"{date}T15:00:00+00:00",
        game_pk=game_pk,
        table_name=table_name,
    )


# ── Happy paths ──────────────────────────────────────────────────────


def test_returns_empty_structure_when_no_content() -> None:
    response = lambda_handler(_content_event("2026-04-26"), None)

    assert response["statusCode"] == 200
    body = _body(response)
    assert body == {
        "date": "2026-04-26",
        "recap": [],
        "previews": [],
        "featured": [],
    }


def test_returns_categorized_content_when_seeded(games_table_name: str) -> None:
    date = "2026-04-26"
    _seed_recap(date, 1001, games_table_name, text="recap-1001")
    _seed_preview(date, 2001, games_table_name, text="preview-2001")
    _seed_featured(date, 1, 3001, games_table_name, text="featured-1")
    _seed_featured(date, 2, 3002, games_table_name, text="featured-2")

    response = lambda_handler(_content_event(date), None)

    assert response["statusCode"] == 200
    body = _body(response)
    assert body["date"] == date
    assert len(body["recap"]) == 1
    assert len(body["previews"]) == 1
    assert len(body["featured"]) == 2

    assert body["recap"][0]["text"] == "recap-1001"
    assert body["recap"][0]["game_pk"] == 1001
    assert body["recap"][0]["content_type"] == "RECAP"

    assert body["previews"][0]["game_pk"] == 2001

    assert body["featured"][0]["rank"] == 1
    assert body["featured"][0]["game_pk"] == 3001
    assert body["featured"][1]["rank"] == 2
    assert body["featured"][1]["game_pk"] == 3002


def test_defaults_to_today_utc_when_no_date_query_param() -> None:
    today = datetime.now(UTC).date().isoformat()
    response = lambda_handler(_content_event(None), None)

    assert response["statusCode"] == 200
    assert _body(response)["date"] == today


def test_explicit_date_query_param_respected(games_table_name: str) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_recap(today, 999, games_table_name, text="today-recap")
    _seed_recap(yesterday, 888, games_table_name, text="yesterday-recap")

    response = lambda_handler(_content_event(yesterday), None)

    body = _body(response)
    assert body["date"] == yesterday
    assert len(body["recap"]) == 1
    assert body["recap"][0]["text"] == "yesterday-recap"


# ── Validation ───────────────────────────────────────────────────────


def test_400_on_malformed_date_query_param() -> None:
    response = lambda_handler(_content_event("banana"), None)

    assert response["statusCode"] == 400
    body = _body(response)
    assert body["error"]["code"] == "invalid_date"


def test_400_on_impossible_date() -> None:
    # Regex passes; strptime rejects.
    response = lambda_handler(_content_event("2026-13-99"), None)

    assert response["statusCode"] == 400
    assert _body(response)["error"]["code"] == "invalid_date"


# ── Headers and projection ───────────────────────────────────────────


def test_cache_control_header_set_to_max_age_300_on_success() -> None:
    response = lambda_handler(_content_event("2026-04-26"), None)

    assert response["statusCode"] == 200
    assert response["headers"]["Cache-Control"] == "max-age=300"


def test_cache_control_header_absent_on_400_error() -> None:
    response = lambda_handler(_content_event("banana"), None)

    assert response["statusCode"] == 400
    # 400 errors do not get cached — caching errors is a footgun.
    assert "Cache-Control" not in response["headers"]


def test_response_excludes_internal_attrs(games_table_name: str) -> None:
    date = "2026-04-26"
    _seed_recap(date, 1001, games_table_name)
    _seed_preview(date, 2001, games_table_name)
    _seed_featured(date, 1, 3001, games_table_name)

    body = _body(lambda_handler(_content_event(date), None))

    forbidden = {"PK", "SK", "key_suffix", "ttl", "input_tokens", "output_tokens", "date"}
    for category in ("recap", "previews", "featured"):
        for item in body[category]:
            for attr in forbidden:
                assert attr not in item, f"{category} item leaked internal attr {attr!r}: {item}"


def test_featured_items_sorted_by_rank(games_table_name: str) -> None:
    date = "2026-04-26"
    # Seed out of natural order; the helper must sort numerically.
    _seed_featured(date, 2, 3002, games_table_name, text="rank-2")
    _seed_featured(date, 1, 3001, games_table_name, text="rank-1")

    body = _body(lambda_handler(_content_event(date), None))

    ranks = [item["rank"] for item in body["featured"]]
    assert ranks == [1, 2]
    assert body["featured"][0]["text"] == "rank-1"
