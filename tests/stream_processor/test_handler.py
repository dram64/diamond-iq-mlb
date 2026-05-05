"""Tests for the stream-processor Lambda."""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.exceptions import ClientError
from shared.connections import put_connection_meta, subscribe_connection
from stream_processor.handler import lambda_handler

# ── Helpers ──────────────────────────────────────────────────────────


def _typed(value: Any) -> dict[str, Any]:
    """Build a single DynamoDB-typed attribute dict."""
    if isinstance(value, int):
        return {"N": str(value)}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, dict):
        return {"M": {k: _typed(v) for k, v in value.items()}}
    raise NotImplementedError(f"unsupported test value type: {type(value)}")


def _img(**fields: Any) -> dict[str, Any]:
    return {k: _typed(v) for k, v in fields.items()}


def _modify_record(
    *,
    game_pk: int,
    old: dict[str, Any],
    new: dict[str, Any],
) -> dict[str, Any]:
    return {
        "eventName": "MODIFY",
        "dynamodb": {
            "OldImage": {**old, "game_pk": _typed(game_pk)},
            "NewImage": {**new, "game_pk": _typed(game_pk)},
        },
    }


def _insert_record(game_pk: int, new: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventName": "INSERT",
        "dynamodb": {"NewImage": {**new, "game_pk": _typed(game_pk)}},
    }


def _remove_record(game_pk: int, old: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventName": "REMOVE",
        "dynamodb": {"OldImage": {**old, "game_pk": _typed(game_pk)}},
    }


def _seed_connection(connection_id: str, game_pk: int, table_name: str) -> None:
    put_connection_meta(
        connection_id=connection_id,
        domain_name="d.example.com",
        stage="production",
        connected_at_utc="2026-04-27T00:00:00+00:00",
        table_name=table_name,
    )
    subscribe_connection(connection_id=connection_id, game_pk=game_pk, table_name=table_name)


def _row_count(connection_id: str, table_name: str) -> int:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": connection_id},
    )
    return len(resp.get("Items", []))


# A capture-only fake of the API Gateway Management API client.
class _FakeMgmtClient:
    def __init__(self, *, gone_for: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._gone_for = set(gone_for or [])

    # boto3 surfaces AWS API kwargs in CamelCase; we mirror it here.
    def post_to_connection(self, *, ConnectionId: str, Data: bytes) -> dict[str, Any]:  # noqa: N803
        self.calls.append({"ConnectionId": ConnectionId, "Data": Data})
        if ConnectionId in self._gone_for:
            err = ClientError(
                {
                    "Error": {"Code": "GoneException", "Message": "stale"},
                    "ResponseMetadata": {"HTTPStatusCode": 410},
                },
                "PostToConnection",
            )
            raise err
        return {}


# ── Diff detection paths (driven through the full handler) ───────────


def test_score_change_triggers_push(connections_table: str) -> None:
    _seed_connection("conn-A", 822909, connections_table)
    fake = _FakeMgmtClient()

    event = {
        "Records": [
            _modify_record(
                game_pk=822909,
                old=_img(away_score=3, home_score=2, ttl=100),
                new=_img(away_score=4, home_score=2, ttl=200),
            )
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )

    assert summary["sent"] == 1
    assert len(fake.calls) == 1
    payload = json.loads(fake.calls[0]["Data"].decode("utf-8"))
    assert payload["type"] == "score_update"
    assert payload["game_pk"] == 822909
    assert payload["changes"]["away_score"] == {"old": 3, "new": 4}


def test_inning_change_triggers_push(connections_table: str) -> None:
    _seed_connection("conn-A", 1, connections_table)
    fake = _FakeMgmtClient()

    event = {
        "Records": [
            _modify_record(
                game_pk=1,
                old=_img(linescore={"inning": 5, "inning_half": "Top"}),
                new=_img(linescore={"inning": 5, "inning_half": "Bottom"}),
            )
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )

    assert summary["sent"] == 1
    payload = json.loads(fake.calls[0]["Data"].decode("utf-8"))
    assert payload["changes"]["linescore"]["inning_half"] == {
        "old": "Top",
        "new": "Bottom",
    }


def test_count_change_triggers_push(connections_table: str) -> None:
    _seed_connection("conn-A", 1, connections_table)
    fake = _FakeMgmtClient()

    event = {
        "Records": [
            _modify_record(
                game_pk=1,
                old=_img(linescore={"balls": 0, "strikes": 0, "outs": 0}),
                new=_img(linescore={"balls": 1, "strikes": 2, "outs": 0}),
            )
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )
    assert summary["sent"] == 1


def test_status_change_triggers_push(connections_table: str) -> None:
    _seed_connection("conn-A", 1, connections_table)
    fake = _FakeMgmtClient()

    event = {
        "Records": [
            _modify_record(
                game_pk=1,
                old=_img(status="live", detailed_state="In Progress"),
                new=_img(status="final", detailed_state="Final"),
            )
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )
    assert summary["sent"] == 1
    payload = json.loads(fake.calls[0]["Data"].decode("utf-8"))
    assert payload["changes"]["status"] == {"old": "live", "new": "final"}


def test_ttl_only_update_skipped(connections_table: str) -> None:
    _seed_connection("conn-A", 1, connections_table)
    fake = _FakeMgmtClient()

    event = {
        "Records": [
            _modify_record(
                game_pk=1,
                old=_img(away_score=3, home_score=2, ttl=100),
                new=_img(away_score=3, home_score=2, ttl=200),
            )
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )
    assert summary["skipped"] == 1
    assert summary["sent"] == 0
    assert fake.calls == []


def test_equal_images_skipped(connections_table: str) -> None:
    fake = _FakeMgmtClient()
    img = _img(away_score=3, home_score=2)
    event = {"Records": [_modify_record(game_pk=1, old=img, new=img)]}
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )
    assert summary["skipped"] == 1
    assert fake.calls == []


# ── Fan-out paths ────────────────────────────────────────────────────


def test_posts_to_all_subscribed_connections(connections_table: str) -> None:
    _seed_connection("conn-A", 822909, connections_table)
    _seed_connection("conn-B", 822909, connections_table)
    _seed_connection("conn-C", 999, connections_table)  # different game
    fake = _FakeMgmtClient()

    event = {
        "Records": [
            _modify_record(
                game_pk=822909,
                old=_img(away_score=0),
                new=_img(away_score=1),
            )
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )

    assert summary["sent"] == 2
    posted_to = sorted(c["ConnectionId"] for c in fake.calls)
    assert posted_to == ["conn-A", "conn-B"]  # conn-C subscribed to a different game


def test_skips_record_with_no_subscribers(connections_table: str) -> None:
    fake = _FakeMgmtClient()
    event = {
        "Records": [
            _modify_record(
                game_pk=822999,
                old=_img(away_score=0),
                new=_img(away_score=1),
            )
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )
    assert summary["skipped"] == 1
    assert summary["sent"] == 0
    assert fake.calls == []


def test_410_gone_deletes_stale_connection(connections_table: str) -> None:
    _seed_connection("conn-stale", 1, connections_table)
    assert _row_count("conn-stale", connections_table) == 2  # META + GAME#1
    fake = _FakeMgmtClient(gone_for=["conn-stale"])

    event = {"Records": [_modify_record(game_pk=1, old=_img(away_score=0), new=_img(away_score=1))]}
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )

    assert summary["stale"] == 1
    assert _row_count("conn-stale", connections_table) == 0


def test_mixed_batch_meaningful_and_noise(connections_table: str) -> None:
    _seed_connection("conn-A", 1, connections_table)
    _seed_connection("conn-A", 2, connections_table)
    fake = _FakeMgmtClient()

    event = {
        "Records": [
            # Real change for game 1.
            _modify_record(game_pk=1, old=_img(away_score=0), new=_img(away_score=1)),
            # No-op TTL refresh for game 2 — must NOT trigger a post.
            _modify_record(
                game_pk=2,
                old=_img(away_score=3, ttl=100),
                new=_img(away_score=3, ttl=200),
            ),
        ]
    }
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )

    assert summary["sent"] == 1
    assert summary["skipped"] == 1
    assert len(fake.calls) == 1
    assert fake.calls[0]["ConnectionId"] == "conn-A"


# ── Event type filtering ─────────────────────────────────────────────


def test_insert_event_skipped(connections_table: str) -> None:
    _seed_connection("conn-A", 1, connections_table)
    fake = _FakeMgmtClient()

    event = {"Records": [_insert_record(1, _img(away_score=0))]}
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )
    assert summary["skipped"] == 1
    assert fake.calls == []


def test_remove_event_skipped(connections_table: str) -> None:
    _seed_connection("conn-A", 1, connections_table)
    fake = _FakeMgmtClient()

    event = {"Records": [_remove_record(1, _img(away_score=0))]}
    summary = lambda_handler(
        event, None, management_client=fake, connections_table_name=connections_table
    )
    assert summary["skipped"] == 1
    assert fake.calls == []


# ── Edge cases ───────────────────────────────────────────────────────


def test_empty_batch_is_graceful_no_op(connections_table: str) -> None:
    fake = _FakeMgmtClient()
    summary = lambda_handler(
        {"Records": []},
        None,
        management_client=fake,
        connections_table_name=connections_table,
    )
    assert summary["records_processed"] == 0
    assert fake.calls == []
