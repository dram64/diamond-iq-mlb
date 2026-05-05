"""Tests for the diamond-iq-ai-compare Lambda."""

from __future__ import annotations

import io
import json
import time
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from ai_compare.handler import lambda_handler
from botocore.exceptions import ClientError

pytestmark = pytest.mark.usefixtures("dynamodb_table")


# ── Mock Bedrock client ────────────────────────────────────────────────


class _FakeBedrock:
    """Minimal bedrock-runtime stand-in. Records inputs; returns a fixed text."""

    def __init__(
        self,
        *,
        text: str = "Aaron Judge has more home runs and a higher OPS than Yordan Alvarez.",
        input_tokens: int = 250,
        output_tokens: int = 80,
        raise_error: ClientError | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._text = text
        self._in = input_tokens
        self._out = output_tokens
        self._raise = raise_error

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raise is not None:
            raise self._raise
        body = {
            "content": [{"type": "text", "text": self._text}],
            "usage": {"input_tokens": self._in, "output_tokens": self._out},
        }
        return {"body": io.BytesIO(json.dumps(body).encode("utf-8"))}


def _seed_player(table: Any, pid: int, name: str) -> None:
    table.put_item(
        Item={
            "PK": "PLAYER#GLOBAL",
            "SK": f"PLAYER#{pid}",
            "person_id": pid,
            "full_name": name,
            "primary_position_abbr": "RF",
        }
    )


def _seed_player_hitting(table: Any, pid: int, season: int = 2026) -> None:
    table.put_item(
        Item={
            "PK": f"STATS#{season}#hitting",
            "SK": f"STATS#{pid}",
            "person_id": pid,
            "season": season,
            "avg": ".310",
            "home_runs": 35,
            "rbi": 100,
            "ops": ".920",
        }
    )


def _seed_team_stats(table: Any, team_id: int, name: str, season: int = 2026) -> None:
    table.put_item(
        Item={
            "PK": f"TEAMSTATS#{season}",
            "SK": f"TEAMSTATS#{team_id}",
            "season": season,
            "team_id": team_id,
            "team_name": name,
            "hitting": {"avg": ".260", "home_runs": 45},
            "pitching": {"era": "3.50", "whip": "1.20"},
        }
    )


def _patched_now() -> datetime:
    return datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)


def _invoke_players(games_table_name: str, ids: str, bedrock: Any | None = None) -> dict[str, Any]:
    event = {
        "routeKey": "GET /api/compare-analysis/players",
        "queryStringParameters": {"ids": ids},
    }
    return lambda_handler(
        event,
        None,
        table_name=games_table_name,
        bedrock_client=bedrock,
        now=_patched_now(),
    )


def _invoke_teams(games_table_name: str, ids: str, bedrock: Any | None = None) -> dict[str, Any]:
    event = {
        "routeKey": "GET /api/compare-analysis/teams",
        "queryStringParameters": {"ids": ids},
    }
    return lambda_handler(
        event,
        None,
        table_name=games_table_name,
        bedrock_client=bedrock,
        now=_patched_now(),
    )


# ── Player route ────────────────────────────────────────────────────────


def test_players_happy_path_invokes_bedrock_and_caches(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 100, "Player A")
    _seed_player_hitting(table, 100)
    _seed_player(table, 200, "Player B")
    _seed_player_hitting(table, 200)

    fake = _FakeBedrock()
    response = _invoke_players(games_table_name, "100,200", bedrock=fake)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["text"].startswith("Aaron Judge")
    assert body["data"]["cache_hit"] is False
    assert body["data"]["ids"] == [100, 200]
    assert len(fake.calls) == 1
    # Cache row written
    cached = table.get_item(Key={"PK": "AIANALYSIS#players#2026#100-200", "SK": "ANALYSIS"}).get(
        "Item"
    )
    assert cached is not None
    assert cached["text"].startswith("Aaron Judge")


def test_players_second_call_returns_cache_hit(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 100, "Player A")
    _seed_player_hitting(table, 100)
    _seed_player(table, 200, "Player B")
    _seed_player_hitting(table, 200)

    fake = _FakeBedrock()
    _invoke_players(games_table_name, "100,200", bedrock=fake)
    second_fake = _FakeBedrock()
    response = _invoke_players(games_table_name, "100,200", bedrock=second_fake)
    body = json.loads(response["body"])
    assert body["data"]["cache_hit"] is True
    assert second_fake.calls == []  # Bedrock not re-invoked


def test_players_cache_key_is_id_order_independent(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 100, "A")
    _seed_player_hitting(table, 100)
    _seed_player(table, 200, "B")
    _seed_player_hitting(table, 200)

    fake = _FakeBedrock()
    _invoke_players(games_table_name, "100,200", bedrock=fake)
    second = _FakeBedrock()
    response = _invoke_players(games_table_name, "200,100", bedrock=second)
    body = json.loads(response["body"])
    assert body["data"]["cache_hit"] is True
    assert second.calls == []


def test_players_404_when_player_metadata_missing(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 100, "Player A")
    _seed_player_hitting(table, 100)
    # Second player intentionally missing.
    fake = _FakeBedrock()
    response = _invoke_players(games_table_name, "100,999", bedrock=fake)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "player_not_found"
    assert fake.calls == []  # never called Bedrock


def test_players_400_on_too_few_ids(games_table_name):
    response = _invoke_players(games_table_name, "100")
    assert response["statusCode"] == 400


def test_players_400_on_too_many_ids(games_table_name):
    response = _invoke_players(games_table_name, "1,2,3,4,5")
    assert response["statusCode"] == 400


def test_players_502_on_bedrock_throttle(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 100, "A")
    _seed_player_hitting(table, 100)
    _seed_player(table, 200, "B")
    _seed_player_hitting(table, 200)

    err = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "InvokeModel"
    )
    fake = _FakeBedrock(raise_error=err)
    response = _invoke_players(games_table_name, "100,200", bedrock=fake)
    assert response["statusCode"] == 502
    body = json.loads(response["body"])
    assert body["error"]["code"] == "bedrock_unavailable"


def test_players_502_on_empty_bedrock_text(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 100, "A")
    _seed_player_hitting(table, 100)
    _seed_player(table, 200, "B")
    _seed_player_hitting(table, 200)

    fake = _FakeBedrock(text="")
    response = _invoke_players(games_table_name, "100,200", bedrock=fake)
    assert response["statusCode"] == 502
    body = json.loads(response["body"])
    assert body["error"]["code"] == "bedrock_empty"


# ── Team route ──────────────────────────────────────────────────────────


def test_teams_happy_path(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_team_stats(table, 147, "Yankees")
    _seed_team_stats(table, 121, "Mets")

    fake = _FakeBedrock(text="Yankees lead in run production by 50 runs.")
    response = _invoke_teams(games_table_name, "147,121", bedrock=fake)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["text"].startswith("Yankees")
    assert body["data"]["kind"] == "teams"


def test_teams_404_when_id_missing(games_table_name):
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_team_stats(table, 147, "Yankees")
    # 121 not seeded.
    fake = _FakeBedrock()
    response = _invoke_teams(games_table_name, "147,121", bedrock=fake)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "team_not_found"


def test_teams_cache_separate_from_players_cache(games_table_name):
    """A players cache for ids [147,121] shouldn't satisfy a teams request
    for the same ids."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 147, "Player 147")
    _seed_player_hitting(table, 147)
    _seed_player(table, 121, "Player 121")
    _seed_player_hitting(table, 121)
    _seed_team_stats(table, 147, "Yankees")
    _seed_team_stats(table, 121, "Mets")

    fake_p = _FakeBedrock(text="Player analysis.")
    _invoke_players(games_table_name, "147,121", bedrock=fake_p)

    fake_t = _FakeBedrock(text="Team analysis.")
    response = _invoke_teams(games_table_name, "147,121", bedrock=fake_t)
    body = json.loads(response["body"])
    assert body["data"]["cache_hit"] is False  # different cache row
    assert len(fake_t.calls) == 1


# ── Routing / errors ────────────────────────────────────────────────────


def test_unknown_route_returns_404(games_table_name):
    event = {
        "routeKey": "GET /api/compare-analysis/unknown",
        "queryStringParameters": {"ids": "1,2"},
    }
    response = lambda_handler(event, None, table_name=games_table_name, now=_patched_now())
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["code"] == "route_not_found"


def test_cache_ttl_expiry_is_treated_as_miss(games_table_name):
    """A cache row whose TTL is in the past should not be served."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    _seed_player(table, 100, "A")
    _seed_player_hitting(table, 100)
    _seed_player(table, 200, "B")
    _seed_player_hitting(table, 200)
    # Pre-populate an expired cache row.
    table.put_item(
        Item={
            "PK": "AIANALYSIS#players#2026#100-200",
            "SK": "ANALYSIS",
            "kind": "players",
            "ids": [100, 200],
            "season": 2026,
            "text": "stale",
            "model_id": "stale",
            "ttl": int(time.time()) - 60,
        }
    )
    fake = _FakeBedrock(text="fresh analysis")
    response = _invoke_players(games_table_name, "100,200", bedrock=fake)
    body = json.loads(response["body"])
    assert body["data"]["text"] == "fresh analysis"
    assert body["data"]["cache_hit"] is False
