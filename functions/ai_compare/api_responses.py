"""Shared response builders + JSON serialization for the player API."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}


def _decimal_default(obj: Any) -> Any:
    """JSON encoder hook: lossy convert Decimal → int (if integral) or float.

    DynamoDB returns every numeric attribute as Decimal. json.dumps does not
    natively serialize them. We accept the float-precision loss because the
    project's stat values are display-precision (3 decimals max), well within
    float's representable range.
    """
    if isinstance(obj, Decimal):
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def build_data_response(
    data: Any,
    *,
    season: int,
    cache_max_age_seconds: int,
    additional_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = {
        "data": data,
        "meta": {
            "season": season,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "cache_max_age_seconds": cache_max_age_seconds,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": f"public, max-age={cache_max_age_seconds}",
        **CORS_HEADERS,
    }
    if additional_headers:
        headers.update(additional_headers)
    return {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps(body, default=_decimal_default),
    }


def build_error_response(
    status_code: int,
    error_code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": error_code, "message": message}}
    if details:
        body["error"]["details"] = details
    headers = {"Content-Type": "application/json", **CORS_HEADERS}
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, default=_decimal_default),
    }
