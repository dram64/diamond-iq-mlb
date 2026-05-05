"""Internal data models for Diamond IQ games.

Frozen dataclasses, stdlib only. The shape here is the contract between the
ingestion Lambda (writes) and the API Lambda (reads).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

GameStatus = Literal["live", "final", "scheduled", "preview", "postponed"]

# 7 days, expressed in seconds — used for the DynamoDB TTL attribute.
TTL_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class Team:
    id: int
    name: str
    abbreviation: str


@dataclass(frozen=True, slots=True)
class Linescore:
    inning: int | None = None
    inning_half: str | None = None
    balls: int | None = None
    strikes: int | None = None
    outs: int | None = None
    away_runs: int | None = None
    home_runs: int | None = None


@dataclass(frozen=True, slots=True)
class ProbablePitcher:
    """Schedule-endpoint probable pitcher — id + fullName only, by design.

    Hydrated from /api/v1/schedule?hydrate=probablePitcher. Used by the
    featured-game tile on the home page to render a Preview-status game
    with starter context. ERA enrichment intentionally deferred to a
    future phase to avoid the player-stats join on the schedule path.
    """

    id: int
    full_name: str


@dataclass(frozen=True, slots=True)
class Game:
    game_pk: int
    date: str  # yyyy-mm-dd
    status: GameStatus
    detailed_state: str
    away_team: Team
    home_team: Team
    away_score: int
    home_score: int
    venue: str | None
    start_time_utc: str  # ISO 8601, exactly as MLB returned it
    linescore: Linescore | None = None
    away_probable_pitcher: ProbablePitcher | None = None
    home_probable_pitcher: ProbablePitcher | None = None


# MLB's abstractGameState → our normalized status. detailedState ("Postponed",
# "Final", etc.) overrides the abstract state when it tells us something more
# specific.
_ABSTRACT_TO_STATUS: dict[str, GameStatus] = {
    "Live": "live",
    "Final": "final",
    "Preview": "preview",
}


def _map_status(raw: dict[str, Any]) -> GameStatus:
    status = raw.get("status") or {}
    detailed = status.get("detailedState", "")
    if "Postponed" in detailed:
        return "postponed"
    abstract = status.get("abstractGameState", "")
    return _ABSTRACT_TO_STATUS.get(abstract, "scheduled")


def _team(raw_team: dict[str, Any]) -> Team:
    inner = raw_team.get("team") or {}
    return Team(
        id=int(inner.get("id") or 0),
        name=str(inner.get("name") or ""),
        abbreviation=str(inner.get("abbreviation") or inner.get("teamCode") or ""),
    )


def _linescore(raw: dict[str, Any]) -> Linescore | None:
    raw_ls = raw.get("linescore") or {}
    if not raw_ls:
        return None
    teams_ls = raw_ls.get("teams") or {}
    away_ls = teams_ls.get("away") or {}
    home_ls = teams_ls.get("home") or {}
    return Linescore(
        inning=raw_ls.get("currentInning"),
        inning_half=raw_ls.get("inningHalf"),
        balls=raw_ls.get("balls"),
        strikes=raw_ls.get("strikes"),
        outs=raw_ls.get("outs"),
        away_runs=away_ls.get("runs"),
        home_runs=home_ls.get("runs"),
    )


def _probable_pitcher(raw_team: dict[str, Any]) -> ProbablePitcher | None:
    """Pull the probable starter from one side's hydrated schedule block.

    Returns None when the hydrate didn't include the field (older API
    versions, or games where MLB hasn't yet announced a starter). Caller
    treats None as a TBD placeholder.
    """
    pp = raw_team.get("probablePitcher") or {}
    pid = pp.get("id")
    name = pp.get("fullName")
    if not pid or not name:
        return None
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return None
    return ProbablePitcher(id=pid_int, full_name=str(name))


def normalize_game(raw: dict[str, Any]) -> Game:
    """Convert one MLB Stats API game dict to a Game.

    Defensive against missing fields — many fields on the schedule endpoint are
    conditional on game state (no linescore for not-yet-started games, no
    score for previews, etc.).
    """
    teams = raw.get("teams") or {}
    away = teams.get("away") or {}
    home = teams.get("home") or {}

    start = str(raw.get("gameDate") or "")
    date_only = start[:10] if len(start) >= 10 else ""

    venue = (raw.get("venue") or {}).get("name")

    return Game(
        game_pk=int(raw.get("gamePk") or 0),
        date=date_only,
        status=_map_status(raw),
        detailed_state=str((raw.get("status") or {}).get("detailedState") or ""),
        away_team=_team(away),
        home_team=_team(home),
        away_score=int(away.get("score") or 0),
        home_score=int(home.get("score") or 0),
        venue=venue,
        start_time_utc=start,
        linescore=_linescore(raw),
        away_probable_pitcher=_probable_pitcher(away),
        home_probable_pitcher=_probable_pitcher(home),
    )


def game_to_api_response(game: Game) -> dict[str, Any]:
    """Convert a Game to the public API response shape.

    Explicit boundary between our internal data model and what we expose to
    the frontend. None values are stripped so the response stays small and
    JSON-friendly. If we ever add internal-only fields to Game, this is
    where they get filtered out.
    """
    body: dict[str, Any] = {
        "game_pk": game.game_pk,
        "date": game.date,
        "status": game.status,
        "detailed_state": game.detailed_state,
        "away": asdict(game.away_team),
        "home": asdict(game.home_team),
        "away_score": game.away_score,
        "home_score": game.home_score,
        "venue": game.venue,
        "start_time_utc": game.start_time_utc,
    }
    if game.linescore is not None:
        body["linescore"] = {k: v for k, v in asdict(game.linescore).items() if v is not None}
    return {k: v for k, v in body.items() if v is not None}


def content_item_to_api_response(item: dict[str, Any]) -> dict[str, Any]:
    """Project a stored content item to the public response shape.

    Drops operational attrs (`PK`, `SK`, `key_suffix`, `ttl`, `input_tokens`,
    `output_tokens`, `date`) and coerces DynamoDB-returned `Decimal`s to int
    so json.dumps doesn't choke. Returns:
      - text, content_type, model_id, generated_at_utc (always)
      - game_pk (always — RECAP/PREVIEW/FEATURED all carry it)
      - rank (FEATURED only)
    """
    out: dict[str, Any] = {
        "text": item.get("text"),
        "content_type": item.get("content_type"),
        "model_id": item.get("model_id"),
        "generated_at_utc": item.get("generated_at_utc"),
    }
    if "game_pk" in item:
        out["game_pk"] = int(item["game_pk"])
    if item.get("content_type") == "FEATURED" and "rank" in item:
        out["rank"] = int(item["rank"])
    return out


def game_to_dynamodb_item(game: Game) -> dict[str, Any]:
    """Convert a Game to a DynamoDB item dict.

    PK is GAME#<date>, SK is GAME#<game_pk>. TTL is 7 days from now (Unix epoch).
    Values use plain Python types — the boto3 resource API handles the type
    mapping when writing. None values are stripped to keep items tidy.
    """
    item: dict[str, Any] = {
        "PK": f"GAME#{game.date}",
        "SK": f"GAME#{game.game_pk}",
        "game_pk": game.game_pk,
        "date": game.date,
        "status": game.status,
        "detailed_state": game.detailed_state,
        "away_team": asdict(game.away_team),
        "home_team": asdict(game.home_team),
        "away_score": game.away_score,
        "home_score": game.home_score,
        "venue": game.venue,
        "start_time_utc": game.start_time_utc,
        "ttl": int(time.time()) + TTL_SECONDS,
    }
    if game.linescore is not None:
        item["linescore"] = {k: v for k, v in asdict(game.linescore).items() if v is not None}

    return {k: v for k, v in item.items() if v is not None}
