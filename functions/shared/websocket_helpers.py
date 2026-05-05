from __future__ import annotations

from typing import Any

from boto3.dynamodb.types import TypeDeserializer

_DESERIALIZER = TypeDeserializer()

# Top-level fields whose changes are user-visible and worth pushing.
_TOPLEVEL_PUSH_FIELDS: tuple[str, ...] = (
    "away_score",
    "home_score",
    "status",
    "detailed_state",
    "winProbability",
)

# Linescore sub-fields we push for.
_LINESCORE_PUSH_FIELDS: tuple[str, ...] = (
    "inning",
    "inning_half",
    "inning_state",
    "balls",
    "strikes",
    "outs",
    "bases",
)


def image_to_python(image: dict[str, Any] | None) -> dict[str, Any]:
    """Convert a DynamoDB Streams image (dict of typed attributes) to plain Python.

    Decimal values are coerced to int (when whole) or float (when fractional)
    so the result is JSON-friendly without further coercion. Returns {} for
    None or empty input.
    """
    if not image:
        return {}
    return {k: _coerce(_DESERIALIZER.deserialize(v)) for k, v in image.items()}


def _changed(old: dict[str, Any], new: dict[str, Any], key: str) -> dict[str, Any] | None:
    """If `old[key] != new[key]`, return the {old, new} diff entry. Else None.

    Treats missing-on-both as not-changed; missing-on-one-side as a change.
    Numbers come through as Decimal from boto3 — we coerce to int/float for
    a clean JSON payload.
    """
    o = old.get(key)
    n = new.get(key)
    if o == n:
        return None
    return {"old": _coerce(o), "new": _coerce(n)}


def _coerce(v: Any) -> Any:
    """Coerce DynamoDB-deserialized values for JSON-friendly output.

    Decimal → int when whole, float when fractional. Sets become sorted lists.
    Dicts/lists pass through (recursively coerced if needed).
    """
    from decimal import Decimal

    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, set):
        return sorted(_coerce(x) for x in v)
    if isinstance(v, list):
        return [_coerce(x) for x in v]
    if isinstance(v, dict):
        return {k: _coerce(val) for k, val in v.items()}
    return v


def meaningful_change(
    old_image: dict[str, Any] | None, new_image: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Diff two DynamoDB Streams images. Return a payload `changes` dict, or None.

    A None return means "no user-visible change happened in this MODIFY"
    and the caller should skip fan-out. The vast majority of ingest writes
    are TTL-only refreshes that produce None.
    """
    old = image_to_python(old_image)
    new = image_to_python(new_image)
    if not new:
        return None  # no NewImage means we have nothing to push

    changes: dict[str, Any] = {}

    for field in _TOPLEVEL_PUSH_FIELDS:
        diff = _changed(old, new, field)
        if diff is not None:
            changes[field] = diff

    old_ls = old.get("linescore") or {}
    new_ls = new.get("linescore") or {}
    if not isinstance(old_ls, dict):
        old_ls = {}
    if not isinstance(new_ls, dict):
        new_ls = {}

    linescore_changes: dict[str, Any] = {}
    for field in _LINESCORE_PUSH_FIELDS:
        diff = _changed(old_ls, new_ls, field)
        if diff is not None:
            linescore_changes[field] = diff

    if linescore_changes:
        changes["linescore"] = linescore_changes

    if not changes:
        return None
    return changes


def build_payload(*, game_pk: int, timestamp: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Build the JSON payload that gets sent to a WebSocket client."""
    return {
        "type": "score_update",
        "game_pk": game_pk,
        "timestamp": timestamp,
        "changes": changes,
    }
