"""Tests for the MLB Stats API HTTP client.

We use unittest.mock against urllib.request.urlopen because the client uses
stdlib urllib (smaller Lambda zip than the requests library, but the
responses library doesn't intercept urllib).
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from shared.mlb_client import (
    MLBAPIError,
    MLBNotFoundError,
    MLBTimeoutError,
    fetch_game,
    fetch_todays_schedule,
)


def _mock_response(payload: dict[str, Any]) -> MagicMock:
    """Build a MagicMock that quacks like an `http.client.HTTPResponse` context manager."""
    body = json.dumps(payload).encode("utf-8")
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://statsapi.mlb.com/x", code=code, msg="error", hdrs=None, fp=None
    )


@patch("shared.mlb_client.urllib.request.urlopen")
def test_fetch_todays_schedule_returns_payload(
    mock_urlopen: MagicMock, mlb_schedule_fixture: dict[str, Any]
) -> None:
    mock_urlopen.return_value = _mock_response(mlb_schedule_fixture)

    result = fetch_todays_schedule()

    assert result == mlb_schedule_fixture
    request = mock_urlopen.call_args[0][0]
    assert "schedule" in request.full_url
    assert "sportId=1" in request.full_url
    assert request.headers.get("User-agent", "").startswith("diamond-iq")


@patch("shared.mlb_client.urllib.request.urlopen")
def test_fetch_game_uses_live_feed_url(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value = _mock_response({"gamePk": 12345, "liveData": {}})

    result = fetch_game(12345)

    assert result["gamePk"] == 12345
    request = mock_urlopen.call_args[0][0]
    assert "/game/12345/feed/live" in request.full_url


@patch("shared.mlb_client.urllib.request.urlopen")
def test_404_raises_mlb_not_found(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = _http_error(404)
    with pytest.raises(MLBNotFoundError) as exc_info:
        fetch_game(99999)
    assert exc_info.value.status == 404


@patch("shared.mlb_client.urllib.request.urlopen")
def test_5xx_raises_mlb_api_error(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = _http_error(503)
    with pytest.raises(MLBAPIError) as exc_info:
        fetch_todays_schedule()
    assert exc_info.value.status == 503
    assert not isinstance(exc_info.value, MLBNotFoundError)


@patch("shared.mlb_client.urllib.request.urlopen")
def test_timeout_raises_mlb_timeout(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = TimeoutError("read timeout")
    with pytest.raises(MLBTimeoutError):
        fetch_todays_schedule()


@patch("shared.mlb_client.urllib.request.urlopen")
def test_url_error_wrapping_timeout_raises_mlb_timeout(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = urllib.error.URLError(reason=TimeoutError("connect timeout"))
    with pytest.raises(MLBTimeoutError):
        fetch_todays_schedule()


@patch("shared.mlb_client.urllib.request.urlopen")
def test_url_error_other_raises_mlb_api_error(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = urllib.error.URLError(reason="dns lookup failed")
    with pytest.raises(MLBAPIError):
        fetch_todays_schedule()
