"""Tests for the content-item helpers in shared.dynamodb."""

from __future__ import annotations

import time

import boto3
import pytest
from shared.dynamodb import get_todays_content, put_content_item

pytestmark = pytest.mark.usefixtures("dynamodb_table")


def _put_recap(date: str, game_pk: int, table_name: str, *, text: str = "Body.") -> None:
    put_content_item(
        content_type="RECAP",
        date=date,
        key_suffix=game_pk,
        text=text,
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=200,
        generated_at_utc="2026-04-26T15:00:00+00:00",
        table_name=table_name,
    )


def _put_preview(date: str, game_pk: int, table_name: str, *, text: str = "Body.") -> None:
    put_content_item(
        content_type="PREVIEW",
        date=date,
        key_suffix=game_pk,
        text=text,
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=80,
        output_tokens=100,
        generated_at_utc="2026-04-26T15:00:00+00:00",
        table_name=table_name,
    )


def _put_featured(
    date: str, rank: int, table_name: str, *, text: str = "Body.", game_pk: int = 99999
) -> None:
    put_content_item(
        content_type="FEATURED",
        date=date,
        key_suffix=rank,
        text=text,
        model_id="us.anthropic.claude-sonnet-4-6",
        input_tokens=120,
        output_tokens=300,
        generated_at_utc="2026-04-26T15:00:00+00:00",
        game_pk=game_pk,
        table_name=table_name,
    )


def _read_item(date: str, sk: str, table_name: str) -> dict:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)
    return table.get_item(Key={"PK": f"CONTENT#{date}", "SK": sk})["Item"]


# ── put_content_item ─────────────────────────────────────────────────


def test_put_recap_writes_pk_sk_and_dual_attrs(games_table_name: str) -> None:
    _put_recap("2026-04-26", 12345, games_table_name)

    item = _read_item("2026-04-26", "RECAP#12345", games_table_name)
    assert item["PK"] == "CONTENT#2026-04-26"
    assert item["SK"] == "RECAP#12345"
    assert item["content_type"] == "RECAP"
    assert int(item["key_suffix"]) == 12345
    assert int(item["game_pk"]) == 12345
    assert "rank" not in item


def test_put_preview_writes_correct_sk_and_game_pk(games_table_name: str) -> None:
    _put_preview("2026-04-26", 67890, games_table_name)

    item = _read_item("2026-04-26", "PREVIEW#67890", games_table_name)
    assert item["SK"] == "PREVIEW#67890"
    assert item["content_type"] == "PREVIEW"
    assert int(item["game_pk"]) == 67890
    assert "rank" not in item


def test_put_featured_writes_rank_and_explicit_game_pk(games_table_name: str) -> None:
    _put_featured("2026-04-26", 1, games_table_name, game_pk=12345)

    item = _read_item("2026-04-26", "FEATURED#1", games_table_name)
    assert item["SK"] == "FEATURED#1"
    assert item["content_type"] == "FEATURED"
    assert int(item["rank"]) == 1
    # FEATURED carries an explicit game_pk so consumers can resolve which
    # game the slot refers to without re-querying anywhere.
    assert int(item["game_pk"]) == 12345


def test_put_featured_requires_explicit_game_pk(games_table_name: str) -> None:
    with pytest.raises(ValueError, match="game_pk is required for FEATURED"):
        put_content_item(
            content_type="FEATURED",
            date="2026-04-26",
            key_suffix=1,
            text="x",
            model_id="m",
            input_tokens=1,
            output_tokens=1,
            generated_at_utc="2026-04-26T00:00:00+00:00",
            table_name=games_table_name,
        )


def test_put_content_item_sets_ttl_within_expected_window(games_table_name: str) -> None:
    """TTL should be ~14 days from now. Allow 60s of clock drift."""
    before = int(time.time())
    _put_recap("2026-04-26", 1, games_table_name)
    after = int(time.time())

    item = _read_item("2026-04-26", "RECAP#1", games_table_name)
    ttl = int(item["ttl"])
    fourteen_days = 14 * 24 * 60 * 60
    assert before + fourteen_days <= ttl <= after + fourteen_days + 60


def test_put_content_item_rejects_invalid_content_type(games_table_name: str) -> None:
    with pytest.raises(ValueError, match="content_type must be one of"):
        put_content_item(
            content_type="recap",  # lowercase — invalid by design
            date="2026-04-26",
            key_suffix=1,
            text="x",
            model_id="m",
            input_tokens=1,
            output_tokens=1,
            generated_at_utc="2026-04-26T00:00:00+00:00",
            table_name=games_table_name,
        )


def test_put_content_item_persists_token_and_model_metadata(games_table_name: str) -> None:
    _put_featured("2026-04-26", 2, games_table_name)
    item = _read_item("2026-04-26", "FEATURED#2", games_table_name)
    assert item["model_id"] == "us.anthropic.claude-sonnet-4-6"
    assert int(item["input_tokens"]) == 120
    assert int(item["output_tokens"]) == 300
    assert item["generated_at_utc"] == "2026-04-26T15:00:00+00:00"


# ── get_todays_content ───────────────────────────────────────────────


def test_get_todays_content_empty_when_nothing_written(games_table_name: str) -> None:
    result = get_todays_content("2026-04-26", table_name=games_table_name)
    assert result == {"recap": [], "previews": [], "featured": []}


def test_get_todays_content_returns_categorized_lists(games_table_name: str) -> None:
    date = "2026-04-26"
    _put_recap(date, 1001, games_table_name, text="recap-1001")
    _put_recap(date, 1002, games_table_name, text="recap-1002")
    _put_preview(date, 2001, games_table_name, text="preview-2001")
    _put_featured(date, 1, games_table_name, text="featured-1")
    _put_featured(date, 2, games_table_name, text="featured-2")

    result = get_todays_content(date, table_name=games_table_name)
    assert len(result["recap"]) == 2
    assert len(result["previews"]) == 1
    assert len(result["featured"]) == 2
    assert {r["text"] for r in result["recap"]} == {"recap-1001", "recap-1002"}
    assert result["previews"][0]["text"] == "preview-2001"


def test_get_todays_content_sorts_featured_by_rank(games_table_name: str) -> None:
    date = "2026-04-26"
    # Insert out of natural query order — DynamoDB returns by SK ascending,
    # which is lexicographic. "FEATURED#10" sorts before "FEATURED#2" on a
    # raw string sort, so the helper must sort numerically.
    _put_featured(date, 2, games_table_name, text="rank-2")
    _put_featured(date, 1, games_table_name, text="rank-1")

    result = get_todays_content(date, table_name=games_table_name)
    ranks = [int(item["rank"]) for item in result["featured"]]
    assert ranks == [1, 2]


def test_get_todays_content_ignores_game_items_for_same_date(
    games_table_name: str,
) -> None:
    """Defensive: GAME#<date> items must not bleed into a CONTENT#<date> read."""
    from shared.models import Game, Team

    date = "2026-04-26"
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    # Seed a game item under the same date partition.
    from shared.dynamodb import put_game

    put_game(
        Game(
            game_pk=999,
            date=date,
            status="preview",
            detailed_state="Scheduled",
            away_team=Team(id=1, name="A", abbreviation="A"),
            home_team=Team(id=2, name="H", abbreviation="H"),
            away_score=0,
            home_score=0,
            venue="P",
            start_time_utc=f"{date}T22:00:00Z",
        ),
        table_name=games_table_name,
    )
    _put_recap(date, 1001, games_table_name)

    # Sanity: both items exist in the table.
    scan = table.scan(Limit=10)
    assert len(scan["Items"]) == 2

    # But get_todays_content scopes to PK=CONTENT#<date>.
    result = get_todays_content(date, table_name=games_table_name)
    assert len(result["recap"]) == 1
    assert len(result["previews"]) == 0


def test_get_todays_content_dates_are_isolated(games_table_name: str) -> None:
    _put_recap("2026-04-26", 1001, games_table_name, text="today-recap")
    _put_recap("2026-04-25", 1002, games_table_name, text="yesterday-recap")

    today = get_todays_content("2026-04-26", table_name=games_table_name)
    yesterday = get_todays_content("2026-04-25", table_name=games_table_name)

    assert len(today["recap"]) == 1
    assert today["recap"][0]["text"] == "today-recap"
    assert len(yesterday["recap"]) == 1
    assert yesterday["recap"][0]["text"] == "yesterday-recap"
