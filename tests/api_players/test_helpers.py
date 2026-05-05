"""Tests for response helpers."""

from __future__ import annotations

import json
from decimal import Decimal

from api_players.api_responses import (
    _decimal_default,
    build_data_response,
    build_error_response,
)


def test_decimal_default_integral_returns_int() -> None:
    assert _decimal_default(Decimal("42")) == 42
    assert isinstance(_decimal_default(Decimal("42")), int)


def test_decimal_default_fractional_returns_float() -> None:
    out = _decimal_default(Decimal("0.399"))
    assert isinstance(out, float)
    assert abs(out - 0.399) < 1e-9


def test_data_response_meta_block() -> None:
    resp = build_data_response({"x": 1}, season=2026, cache_max_age_seconds=300)
    assert resp["statusCode"] == 200
    assert "Cache-Control" in resp["headers"]
    assert "max-age=300" in resp["headers"]["Cache-Control"]
    body = json.loads(resp["body"])
    assert body["meta"]["season"] == 2026
    assert body["meta"]["cache_max_age_seconds"] == 300
    assert "timestamp" in body["meta"]


def test_error_response_includes_details() -> None:
    resp = build_error_response(503, "data_not_yet_available", "stub", details={"season": 2026})
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 503
    assert body["error"]["code"] == "data_not_yet_available"
    assert body["error"]["details"] == {"season": 2026}
