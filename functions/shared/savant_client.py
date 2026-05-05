from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request

USER_AGENT = "diamond-iq/0.1 (+https://github.com/dram64/diamond-iq)"
SAVANT_BASE = "https://baseballsavant.mlb.com"
DEFAULT_TIMEOUT_SECONDS = 30.0


class SavantAPIError(Exception):
    """Raised on a non-success response from Baseball Savant."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SavantTimeoutError(SavantAPIError):
    """Raised when a request to Baseball Savant times out."""


def _request_csv(url: str, *, timeout: float) -> str:
    """Fetch a CSV body. Returns the raw text (handles BOM strip).

    Raises SavantAPIError on 4xx/5xx, SavantTimeoutError on timeout.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/csv"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https only
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise SavantAPIError(f"Savant {e.code}: {url}", status=e.code) from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise SavantTimeoutError(f"Savant timeout: {url}") from e
        raise SavantAPIError(f"Savant request failed: {url} ({e.reason})") from e
    except TimeoutError as e:
        raise SavantTimeoutError(f"Savant timeout: {url}") from e

    text = raw.decode("utf-8-sig", errors="replace")
    return text


def _request_with_backoff(url: str, *, timeout: float, max_retries: int = 3) -> str:
    """Fetch with 1s/2s/4s backoff on 5xx + timeout. 4xx propagates immediately."""
    import time

    last_err: SavantAPIError | None = None
    for attempt in range(max_retries):
        try:
            return _request_csv(url, timeout=timeout)
        except SavantAPIError as e:
            last_err = e
            status = getattr(e, "status", None)
            if status is not None and 500 <= status < 600:
                time.sleep(2**attempt)
                continue
            if isinstance(e, SavantTimeoutError):
                time.sleep(2**attempt)
                continue
            raise
    assert last_err is not None  # noqa: S101 - loop always raises
    raise last_err


def _parse_csv(text: str) -> list[dict[str, str]]:
    """Parse a Savant CSV body into a list of row-dicts (column-name → value)."""
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _normalize_player_id(row: dict[str, str]) -> int | None:
    """Extract the player_id from a row, handling both `player_id` (custom /
    statcast) and `id` (bat-tracking / batted-ball) column shapes."""
    raw = row.get("player_id") or row.get("id")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ── Endpoint fetchers ──────────────────────────────────────────────────


def fetch_custom_batter(
    season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, str]]:
    """Hitter expected stats + sweet spot % + sprint speed."""
    selections = "xba,xslg,xwoba,sweet_spot_percent,sprint_speed"
    url = (
        f"{SAVANT_BASE}/leaderboard/custom?year={season}&type=batter&min=q"
        f"&selections={selections}&csv=true"
    )
    return _parse_csv(_request_with_backoff(url, timeout=timeout))


def fetch_statcast_batter(
    season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, str]]:
    """Hitter avg/max EV, barrel %, hard-hit %."""
    url = f"{SAVANT_BASE}/leaderboard/statcast?year={season}&abs=25&player_type=batter&csv=true"
    return _parse_csv(_request_with_backoff(url, timeout=timeout))


def fetch_custom_pitcher(
    season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, str]]:
    """Pitcher xERA, xBA against, whiff/chase %, fastball velo + spin."""
    selections = "xera,xba,whiff_percent,oz_swing_miss_percent,fastball_avg_speed,fastball_avg_spin"
    url = (
        f"{SAVANT_BASE}/leaderboard/custom?year={season}&type=pitcher&min=q"
        f"&selections={selections}&csv=true"
    )
    return _parse_csv(_request_with_backoff(url, timeout=timeout))


def fetch_bat_tracking(
    season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, str]]:
    """Bat speed, swing length, hard-swing % — 2024+ only."""
    url = f"{SAVANT_BASE}/leaderboard/bat-tracking?year={season}&min=10&csv=true"
    return _parse_csv(_request_with_backoff(url, timeout=timeout))


def fetch_batted_ball(
    season: int, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, str]]:
    """Pull / center / oppo splits with ground/air sub-splits."""
    url = f"{SAVANT_BASE}/leaderboard/batted-ball?year={season}&min=q&type=batter&csv=true"
    return _parse_csv(_request_with_backoff(url, timeout=timeout))


# Re-export the normalizer so the ingest handler doesn't need to know
# about the column-name drift across endpoints.
__all__ = [
    "SAVANT_BASE",
    "SavantAPIError",
    "SavantTimeoutError",
    "USER_AGENT",
    "_normalize_player_id",
    "fetch_bat_tracking",
    "fetch_batted_ball",
    "fetch_custom_batter",
    "fetch_custom_pitcher",
    "fetch_statcast_batter",
]
