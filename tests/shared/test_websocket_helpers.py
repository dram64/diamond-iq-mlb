"""Tests for shared.websocket_helpers."""

from __future__ import annotations

from shared.websocket_helpers import (
    build_payload,
    image_to_python,
    meaningful_change,
)


# DynamoDB Streams images come through with typed-attribute encoding.
# Build them in the same shape AWS would emit.
def _img(**fields: object) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for k, v in fields.items():
        if isinstance(v, int):
            out[k] = {"N": str(v)}
        elif isinstance(v, str):
            out[k] = {"S": v}
        elif isinstance(v, dict):
            out[k] = {"M": _img(**v)}  # nested map
        else:
            raise NotImplementedError(f"unsupported test value type for {k}: {type(v)}")
    return out


def test_meaningful_change_score_change_returns_diff() -> None:
    old = _img(away_score=3, home_score=2, ttl=999)
    new = _img(away_score=4, home_score=2, ttl=1000)

    changes = meaningful_change(old, new)
    assert changes == {"away_score": {"old": 3, "new": 4}}


def test_meaningful_change_linescore_changes_nest_correctly() -> None:
    old = _img(linescore={"inning": 5, "outs": 2, "balls": 1, "strikes": 0})
    new = _img(linescore={"inning": 6, "outs": 0, "balls": 0, "strikes": 0})

    changes = meaningful_change(old, new)
    assert changes is not None
    assert "linescore" in changes
    assert changes["linescore"]["inning"] == {"old": 5, "new": 6}
    assert changes["linescore"]["outs"] == {"old": 2, "new": 0}
    assert changes["linescore"]["balls"] == {"old": 1, "new": 0}
    # strikes didn't change → not in the diff
    assert "strikes" not in changes["linescore"]


def test_meaningful_change_returns_none_for_ttl_only_update() -> None:
    """Most ingest writes are TTL-only refreshes — must NOT trigger a push."""
    old = _img(away_score=3, home_score=2, ttl=1000)
    new = _img(away_score=3, home_score=2, ttl=1060)

    assert meaningful_change(old, new) is None


def test_meaningful_change_returns_none_for_equal_images() -> None:
    img = _img(away_score=3, home_score=2)
    assert meaningful_change(img, img) is None


def test_build_payload_shape() -> None:
    payload = build_payload(
        game_pk=822909,
        timestamp="2026-04-27T01:23:45.678+00:00",
        changes={"away_score": {"old": 3, "new": 4}},
    )
    assert payload["type"] == "score_update"
    assert payload["game_pk"] == 822909
    assert payload["timestamp"] == "2026-04-27T01:23:45.678+00:00"
    assert payload["changes"] == {"away_score": {"old": 3, "new": 4}}


def test_image_to_python_decimal_coercion() -> None:
    """Decimal coercion to int when whole; preserves arbitrary nesting."""
    img = _img(game_pk=822909, away_score=3, linescore={"inning": 5})
    out = image_to_python(img)
    assert out["game_pk"] == 822909
    assert isinstance(out["game_pk"], int)
    assert out["linescore"]["inning"] == 5
