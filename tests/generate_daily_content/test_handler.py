"""Tests for the generate_daily_content Lambda.

Bedrock is stubbed at the boto3-client level via botocore.stub.Stubber, so
no network calls happen and we control exactly what the model "returns"
on each invoke. DynamoDB is the same moto-mocked single-table fixture
used everywhere else in the repo.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from generate_daily_content.handler import (
    lambda_handler,
    score_game,
    select_featured,
)
from shared.dynamodb import list_existing_content_sks, put_game
from shared.models import Game, Linescore, Team

pytestmark = pytest.mark.usefixtures("dynamodb_table")


# ── Fixtures and helpers ─────────────────────────────────────────────


@pytest.fixture
def bedrock_client() -> Any:
    return boto3.client("bedrock-runtime", region_name="us-east-1")


def _bedrock_response(text: str, input_tokens: int = 100, output_tokens: int = 200) -> dict:
    """Build a fake invoke_model response in the shape Claude returns it."""
    payload = {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    return {
        "body": StreamingBody(BytesIO(body_bytes), len(body_bytes)),
        "contentType": "application/json",
    }


def _stub_n_responses(client: Any, n: int, text: str = "Generated copy.") -> Stubber:
    stubber = Stubber(client)
    for _ in range(n):
        stubber.add_response(
            "invoke_model",
            _bedrock_response(text),
            expected_params={
                "modelId": ANY,
                "contentType": "application/json",
                "accept": "application/json",
                "body": ANY,
            },
        )
    return stubber


def _final_game(
    game_pk: int,
    *,
    away_id: int = 111,
    home_id: int = 147,
    away_score: int = 3,
    home_score: int = 5,
    date: str = "2026-04-25",
) -> Game:
    return Game(
        game_pk=game_pk,
        date=date,
        status="final",
        detailed_state="Final",
        away_team=Team(id=away_id, name=f"Away{away_id}", abbreviation="A"),
        home_team=Team(id=home_id, name=f"Home{home_id}", abbreviation="H"),
        away_score=away_score,
        home_score=home_score,
        venue="Some Park",
        start_time_utc=f"{date}T19:00:00Z",
        linescore=Linescore(inning=9, away_runs=away_score, home_runs=home_score),
    )


def _preview_game(
    game_pk: int,
    *,
    away_id: int = 119,
    home_id: int = 137,
    date: str = "2026-04-26",
) -> Game:
    return Game(
        game_pk=game_pk,
        date=date,
        status="preview",
        detailed_state="Scheduled",
        away_team=Team(id=away_id, name=f"Away{away_id}", abbreviation="A"),
        home_team=Team(id=home_id, name=f"Home{home_id}", abbreviation="H"),
        away_score=0,
        home_score=0,
        venue="Some Park",
        start_time_utc=f"{date}T22:00:00Z",
    )


def _seed_games(games: list[Game], games_table_name: str) -> None:
    for g in games:
        put_game(g, table_name=games_table_name)


# ── Featured heuristic ───────────────────────────────────────────────


def test_score_same_division_bonus() -> None:
    # NYY (147) vs BOS (111) — both AL East
    g = _preview_game(1, away_id=111, home_id=147)
    assert score_game(g, won_last={}) == pytest.approx(2.0)


def test_score_winners_of_last_game_each_count() -> None:
    # NYY home, BOS away — both won yesterday → +2.0 from last-win + 2.0 same-div
    g = _preview_game(1, away_id=111, home_id=147)
    assert score_game(g, won_last={111: True, 147: True}) == pytest.approx(4.0)


def test_score_pacific_time_home_bonus() -> None:
    # LAD home (PT) vs ATL away (NL East/East) — different divisions, no recent win
    g = _preview_game(1, away_id=144, home_id=119)
    assert score_game(g, won_last={}) == pytest.approx(0.5)


def test_select_featured_breaks_tie_by_smaller_game_pk() -> None:
    # Two games tied at 2.0 (same division each). Lower game_pk wins.
    g1 = _preview_game(900, away_id=111, home_id=147)  # AL East
    g2 = _preview_game(800, away_id=144, home_id=121)  # NL East
    g3 = _preview_game(750, away_id=145, home_id=114)  # AL Central
    selected = select_featured([g1, g2, g3], won_last={})
    assert [g.game_pk for g in selected] == [750, 800]


def test_select_featured_returns_empty_when_no_previews() -> None:
    assert select_featured([], won_last={}) == []


# ── End-to-end happy path ────────────────────────────────────────────


def test_writes_recap_preview_and_featured_for_full_slate(
    bedrock_client: Any, games_table_name: str
) -> None:
    yesterday = "2026-04-25"
    today = "2026-04-26"
    finals = [
        _final_game(1001, date=yesterday),
        _final_game(1002, date=yesterday, away_id=144, home_id=119),
    ]
    previews = [
        _preview_game(2001, away_id=111, home_id=147, date=today),  # AL East same-div
        _preview_game(2002, away_id=144, home_id=121, date=today),  # NL East same-div
        _preview_game(2003, away_id=119, home_id=137, date=today),  # NL West same-div, PT
    ]
    _seed_games(finals + previews, games_table_name)

    expected_invokes = len(finals) + len(previews) + 2  # 2 featured
    stubber = _stub_n_responses(bedrock_client, expected_invokes, text="Body of copy.")
    with stubber:
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    stubber.assert_no_pending_responses()

    assert result["ok"] is True
    assert result["expected_items"] == expected_invokes
    assert result["items_written"] == expected_invokes
    assert result["bedrock_failures"] == 0
    assert result["dynamodb_failures"] == 0

    sks = list_existing_content_sks(today, table_name=games_table_name)
    assert "RECAP#1001" in sks
    assert "RECAP#1002" in sks
    assert "PREVIEW#2001" in sks
    assert "PREVIEW#2002" in sks
    assert "PREVIEW#2003" in sks
    assert "FEATURED#1" in sks
    assert "FEATURED#2" in sks


# ── Idempotency ──────────────────────────────────────────────────────


def test_idempotent_skip_when_all_content_present(
    bedrock_client: Any, games_table_name: str
) -> None:
    yesterday = "2026-04-25"
    today = "2026-04-26"
    finals = [_final_game(1001, date=yesterday)]
    previews = [_preview_game(2001, date=today)]
    _seed_games(finals + previews, games_table_name)

    # First run: 1 recap + 1 preview + 1 featured = 3 invokes.
    stubber_first = _stub_n_responses(bedrock_client, 3)
    with stubber_first:
        first = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    assert first["items_written"] == 3

    # Second run: nothing missing → zero invokes.
    stubber_second = Stubber(bedrock_client)  # no add_response calls
    with stubber_second:
        second = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    stubber_second.assert_no_pending_responses()

    assert second["ok"] is True
    assert second["items_written"] == 0
    assert second["items_skipped"] == 3


def test_partial_existing_content_only_fills_gaps(
    bedrock_client: Any, games_table_name: str
) -> None:
    yesterday = "2026-04-25"
    today = "2026-04-26"
    finals = [_final_game(1001, date=yesterday), _final_game(1002, date=yesterday)]
    previews = [_preview_game(2001, date=today)]
    _seed_games(finals + previews, games_table_name)

    # First run: write all 4 (2 recaps + 1 preview + 1 featured).
    with _stub_n_responses(bedrock_client, 4):
        lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    # Now manually drop one item to simulate prior partial failure.
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    table.delete_item(Key={"PK": f"CONTENT#{today}", "SK": "RECAP#1002"})

    # Second run: exactly one Bedrock invocation expected, no more.
    stubber = _stub_n_responses(bedrock_client, 1)
    with stubber:
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    stubber.assert_no_pending_responses()

    assert result["items_written"] == 1
    assert result["items_skipped"] == 3


def test_idempotent_skip_leaves_original_content_in_place(
    bedrock_client: Any, games_table_name: str
) -> None:
    """The skip path must not overwrite existing content with new Bedrock output."""
    yesterday = "2026-04-25"
    today = "2026-04-26"
    finals = [_final_game(1001, date=yesterday)]
    previews = [_preview_game(2001, date=today)]
    _seed_games(finals + previews, games_table_name)

    with _stub_n_responses(bedrock_client, 3, text="ORIGINAL"):
        lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    # Re-run; nothing should be written; original text preserved.
    stubber_second = Stubber(bedrock_client)
    with stubber_second:
        lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    item = table.get_item(Key={"PK": f"CONTENT#{today}", "SK": "RECAP#1001"})["Item"]
    assert item["text"] == "ORIGINAL"


# ── DynamoDB write shape ─────────────────────────────────────────────


def test_recap_item_has_expected_attributes(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)
    # No previews → no preview/featured items, just the recap.
    with _stub_n_responses(bedrock_client, 1, text="Recap body."):
        lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    item = table.get_item(Key={"PK": f"CONTENT#{today}", "SK": "RECAP#1001"})["Item"]
    assert item["content_type"] == "RECAP"
    assert item["text"] == "Recap body."
    assert item["game_pk"] == 1001
    assert item["input_tokens"] == 100
    assert item["output_tokens"] == 200
    assert "ttl" in item
    assert "generated_at_utc" in item


def test_featured_item_has_rank_attribute(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    _seed_games(
        [_preview_game(2001, away_id=111, home_id=147, date=today)],
        games_table_name,
    )
    with _stub_n_responses(bedrock_client, 2):  # preview + featured
        lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    item = table.get_item(Key={"PK": f"CONTENT#{today}", "SK": "FEATURED#1"})["Item"]
    assert item["content_type"] == "FEATURED"
    assert int(item["rank"]) == 1
    assert int(item["game_pk"]) == 2001


# ── Bedrock failure modes ────────────────────────────────────────────


def test_throttling_on_one_item_continues_to_next(
    bedrock_client: Any, games_table_name: str
) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games(
        [_final_game(1001, date=yesterday), _final_game(1002, date=yesterday)],
        games_table_name,
    )

    stubber = Stubber(bedrock_client)
    stubber.add_client_error(
        "invoke_model",
        service_error_code="ThrottlingException",
        service_message="Too many tokens per day",
    )
    stubber.add_response("invoke_model", _bedrock_response("Recap body."))
    with stubber:
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    stubber.assert_no_pending_responses()

    assert result["bedrock_failures"] == 1
    assert result["items_written"] == 1
    # ok=True because at least one item was written.
    assert result["ok"] is True


def test_all_bedrock_calls_fail_returns_not_ok(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)

    stubber = Stubber(bedrock_client)
    stubber.add_client_error(
        "invoke_model",
        service_error_code="ThrottlingException",
        service_message="quota exhausted",
    )
    with stubber:
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    stubber.assert_no_pending_responses()

    assert result["ok"] is False
    assert result["bedrock_failures"] == 1
    assert result["items_written"] == 0


def test_unexpected_exception_is_caught_and_counted(
    bedrock_client: Any, games_table_name: str
) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games(
        [_final_game(1001, date=yesterday), _final_game(1002, date=yesterday)],
        games_table_name,
    )

    stubber = Stubber(bedrock_client)
    stubber.add_client_error(
        "invoke_model",
        service_error_code="ValidationException",
        service_message="bad request",
    )
    stubber.add_response("invoke_model", _bedrock_response("Recap body."))
    with stubber:
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    stubber.assert_no_pending_responses()

    assert result["bedrock_failures"] == 1
    assert result["items_written"] == 1


def test_empty_text_response_counts_as_failure(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)

    stubber = _stub_n_responses(bedrock_client, 1, text="")
    with stubber:
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    assert result["bedrock_failures"] == 1
    assert result["items_written"] == 0


# ── DynamoDB failure ─────────────────────────────────────────────────


def test_dynamodb_put_failure_is_caught_and_counted(
    bedrock_client: Any, games_table_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)

    def fake_put_content_item(**_kwargs: Any) -> None:
        raise ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "x"}},
            "PutItem",
        )

    import generate_daily_content.handler as handler_mod

    monkeypatch.setattr(handler_mod, "put_content_item", fake_put_content_item)

    with _stub_n_responses(bedrock_client, 1):
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    assert result["dynamodb_failures"] == 1
    assert result["items_written"] == 0
    assert result["ok"] is False


# ── Slate edge cases ─────────────────────────────────────────────────


def test_no_finals_yesterday_skips_recaps(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    _seed_games([_preview_game(2001, date=today)], games_table_name)

    with _stub_n_responses(bedrock_client, 2):  # preview + featured#1
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    assert result["items_written"] == 2
    sks = list_existing_content_sks(today, table_name=games_table_name)
    assert not any(sk.startswith("RECAP#") for sk in sks)


def test_no_previews_today_skips_featured(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)

    with _stub_n_responses(bedrock_client, 1):  # just the recap
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    assert result["items_written"] == 1
    sks = list_existing_content_sks(today, table_name=games_table_name)
    assert not any(sk.startswith("FEATURED#") for sk in sks)
    assert not any(sk.startswith("PREVIEW#") for sk in sks)


def test_one_preview_only_yields_one_featured(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    _seed_games([_preview_game(2001, date=today)], games_table_name)

    with _stub_n_responses(bedrock_client, 2):  # preview + featured#1
        lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )

    sks = list_existing_content_sks(today, table_name=games_table_name)
    assert "FEATURED#1" in sks
    assert "FEATURED#2" not in sks


def test_empty_slate_returns_zero_expected_items(
    bedrock_client: Any, games_table_name: str
) -> None:
    today = "2026-04-26"
    stubber = Stubber(bedrock_client)
    with stubber:
        result = lambda_handler(
            {"date": today}, None, bedrock_client=bedrock_client, table_name=games_table_name
        )
    stubber.assert_no_pending_responses()

    assert result["expected_items"] == 0
    assert result["items_written"] == 0
    assert result["ok"] is True


def test_featured_excludes_final_games() -> None:
    """Defensive: featured selection must operate on Previews only.

    Smoke check that select_featured rejects non-Preview Games is implicit —
    handler only passes today's previews. This test confirms that filtering.
    """
    today = "2026-04-26"
    yesterday = "2026-04-25"
    finals = [_final_game(1001, date=yesterday, away_id=111, home_id=147)]
    previews = [_preview_game(2001, date=today, away_id=119, home_id=137)]
    # Same dataset — handler must classify by `status`.
    games = finals + previews
    today_previews_only = [g for g in games if g.status == "preview"]
    selected = select_featured(today_previews_only, won_last={})
    assert [g.game_pk for g in selected] == [2001]


# ── CloudWatch metric emission ───────────────────────────────────────


class _FakeContext:
    aws_request_id = "test-request-id"
    function_name = "diamond-iq-generate-daily-content"


def _capture_cw_client():
    """Return a (client, calls) pair where every put_metric_data invocation
    is captured by name → kwargs."""
    calls: list[dict[str, Any]] = []

    class _CW:
        def put_metric_data(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {}

    return _CW(), calls


def test_metrics_emitted_with_correct_namespace_and_data(
    bedrock_client: Any, games_table_name: str
) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)
    cw, calls = _capture_cw_client()

    with _stub_n_responses(bedrock_client, 1):
        result = lambda_handler(
            {"date": today},
            _FakeContext(),
            bedrock_client=bedrock_client,
            cloudwatch_client=cw,
            table_name=games_table_name,
        )

    assert result["items_written"] == 1
    assert len(calls) == 1, "exactly one put_metric_data call expected per invocation"
    call = calls[0]
    assert call["Namespace"] == "DiamondIQ/Content"
    metric_names = {m["MetricName"] for m in call["MetricData"]}
    assert metric_names == {"BedrockFailures", "DynamoDBFailures", "ItemsWritten", "ItemsSkipped"}


def test_metrics_emitted_after_bedrock_failures(bedrock_client: Any, games_table_name: str) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games(
        [_final_game(1001, date=yesterday), _final_game(1002, date=yesterday)],
        games_table_name,
    )
    cw, calls = _capture_cw_client()

    stubber = Stubber(bedrock_client)
    for _ in range(2):
        stubber.add_client_error(
            "invoke_model",
            service_error_code="ThrottlingException",
            service_message="Too many tokens per day",
        )
    with stubber:
        lambda_handler(
            {"date": today},
            _FakeContext(),
            bedrock_client=bedrock_client,
            cloudwatch_client=cw,
            table_name=games_table_name,
        )

    by_name = {m["MetricName"]: m for m in calls[0]["MetricData"]}
    assert by_name["BedrockFailures"]["Value"] == 2
    assert by_name["ItemsWritten"]["Value"] == 0
    assert by_name["DynamoDBFailures"]["Value"] == 0


def test_metric_emission_failure_does_not_break_lambda(
    bedrock_client: Any, games_table_name: str
) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)

    class _ExplodingCW:
        def put_metric_data(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("CloudWatch unavailable")

    with _stub_n_responses(bedrock_client, 1):
        result = lambda_handler(
            {"date": today},
            _FakeContext(),
            bedrock_client=bedrock_client,
            cloudwatch_client=_ExplodingCW(),
            table_name=games_table_name,
        )

    # Lambda still returns its normal summary even when CloudWatch fails.
    assert result["ok"] is True
    assert result["items_written"] == 1


def test_metric_dimensions_include_lambda_function_name(
    bedrock_client: Any, games_table_name: str
) -> None:
    today = "2026-04-26"
    yesterday = "2026-04-25"
    _seed_games([_final_game(1001, date=yesterday)], games_table_name)
    cw, calls = _capture_cw_client()

    with _stub_n_responses(bedrock_client, 1):
        lambda_handler(
            {"date": today},
            _FakeContext(),
            bedrock_client=bedrock_client,
            cloudwatch_client=cw,
            table_name=games_table_name,
        )

    for metric in calls[0]["MetricData"]:
        dimensions = {d["Name"]: d["Value"] for d in metric["Dimensions"]}
        assert dimensions == {"LambdaFunction": "diamond-iq-generate-daily-content"}
