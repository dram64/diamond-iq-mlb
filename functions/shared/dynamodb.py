"""DynamoDB read/write helpers for the games table.

Single-table design with composite keys for two item types:
    Games:    PK = "GAME#<yyyy-mm-dd>"      SK = "GAME#<game_pk>"
    Content:  PK = "CONTENT#<yyyy-mm-dd>"   SK = "RECAP#<game_pk>"
                                                "PREVIEW#<game_pk>"
                                                "FEATURED#<rank>"

The boto3 resource API does serialization for us — callers pass plain Python
types in and get plain Python types back (Decimals for any numeric attribute,
which we coerce back to int).
"""

from __future__ import annotations

import os
import time
from typing import Any

import boto3

from .models import Game, Linescore, Team, game_to_dynamodb_item

_TABLE_NAME_ENV = "GAMES_TABLE_NAME"

# Content TTL is 14 days from write time. Long enough to keep yesterday's
# recap visible after a Saturday-night Pacific game rolls past UTC midnight,
# short enough that DynamoDB does the cleanup for us without manual sweeps.
CONTENT_TTL_SECONDS = 14 * 24 * 60 * 60


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(_TABLE_NAME_ENV)
    if not name:
        raise RuntimeError(
            f"{_TABLE_NAME_ENV} environment variable not set and no override provided"
        )
    return name


def _get_table(table_name: str | None):
    # Resolve the name first so a missing env var fails before any AWS SDK call.
    name = _resolve_table_name(table_name)
    return boto3.resource("dynamodb").Table(name)


def put_game(game: Game, table_name: str | None = None) -> None:
    table = _get_table(table_name)
    table.put_item(Item=game_to_dynamodb_item(game))


def get_game(game_pk: int, date: str, table_name: str | None = None) -> Game | None:
    table = _get_table(table_name)
    resp = table.get_item(Key={"PK": f"GAME#{date}", "SK": f"GAME#{game_pk}"})
    item = resp.get("Item")
    if not item:
        return None
    return _item_to_game(item)


def list_todays_games(date: str, table_name: str | None = None) -> list[Game]:
    table = _get_table(table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"GAME#{date}"},
    )
    return [_item_to_game(it) for it in resp.get("Items", [])]


def _opt_int(d: dict[str, Any], key: str) -> int | None:
    v = d.get(key)
    return int(v) if v is not None else None


def _item_to_game(item: dict[str, Any]) -> Game:
    away = item["away_team"]
    home = item["home_team"]

    raw_ls = item.get("linescore")
    linescore: Linescore | None = None
    if raw_ls:
        linescore = Linescore(
            inning=_opt_int(raw_ls, "inning"),
            inning_half=raw_ls.get("inning_half"),
            balls=_opt_int(raw_ls, "balls"),
            strikes=_opt_int(raw_ls, "strikes"),
            outs=_opt_int(raw_ls, "outs"),
            away_runs=_opt_int(raw_ls, "away_runs"),
            home_runs=_opt_int(raw_ls, "home_runs"),
        )

    return Game(
        game_pk=int(item["game_pk"]),
        date=item["date"],
        status=item["status"],
        detailed_state=item["detailed_state"],
        away_team=Team(
            id=int(away["id"]),
            name=away["name"],
            abbreviation=away["abbreviation"],
        ),
        home_team=Team(
            id=int(home["id"]),
            name=home["name"],
            abbreviation=home["abbreviation"],
        ),
        away_score=int(item["away_score"]),
        home_score=int(item["home_score"]),
        venue=item.get("venue"),
        start_time_utc=item["start_time_utc"],
        linescore=linescore,
    )


_CONTENT_TYPES: frozenset[str] = frozenset({"RECAP", "PREVIEW", "FEATURED"})


def put_content_item(
    *,
    content_type: str,
    date: str,
    key_suffix: int,
    text: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    generated_at_utc: str,
    game_pk: int | None = None,
    ttl_days: int = 14,
    table_name: str | None = None,
) -> None:
    """Write one content item (recap, preview, or featured).

    `content_type` is one of RECAP, PREVIEW, FEATURED. `key_suffix` is the
    game_pk for RECAP/PREVIEW or the rank (1 or 2) for FEATURED. Both
    `key_suffix` and a semantic field are stored: RECAP/PREVIEW get a
    `game_pk` attr derived from `key_suffix`; FEATURED gets a `rank` attr
    derived from `key_suffix` plus an explicit `game_pk` attr passed by the
    caller (so consumers can resolve a featured slot to its game without
    parsing keys).
    """
    if content_type not in _CONTENT_TYPES:
        raise ValueError(
            f"content_type must be one of {sorted(_CONTENT_TYPES)}; got {content_type!r}"
        )
    if content_type == "FEATURED" and game_pk is None:
        raise ValueError("game_pk is required for FEATURED content items")

    table = _get_table(table_name)
    ttl_seconds = ttl_days * 24 * 60 * 60
    item: dict[str, Any] = {
        "PK": f"CONTENT#{date}",
        "SK": f"{content_type}#{key_suffix}",
        "date": date,
        "content_type": content_type,
        "key_suffix": key_suffix,
        "text": text,
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "generated_at_utc": generated_at_utc,
        "ttl": int(time.time()) + ttl_seconds,
    }
    # Dual attrs so consumers don't have to parse key_suffix.
    if content_type in ("RECAP", "PREVIEW"):
        item["game_pk"] = key_suffix
    else:  # FEATURED
        item["rank"] = key_suffix
        item["game_pk"] = game_pk
    table.put_item(Item=item)


def list_existing_content_sks(date: str, table_name: str | None = None) -> set[str]:
    """Return the set of SKs already present under CONTENT#<date>.

    Used by the idempotency check to skip Bedrock calls for items that are
    already in the table from an earlier scheduled tick.
    """
    table = _get_table(table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"CONTENT#{date}"},
        ProjectionExpression="SK",
    )
    return {item["SK"] for item in resp.get("Items", [])}


def get_todays_content(date: str, table_name: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Read every content item for `date` and categorize by type.

    Returns a dict with three keys: `recap`, `previews`, `featured`. Each is
    a list of plain item dicts in their stored shape. Featured items are
    sorted by rank ascending. Missing categories are empty lists, not
    absent keys.
    """
    table = _get_table(table_name)
    resp = table.query(
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": f"CONTENT#{date}"},
    )

    recap: list[dict[str, Any]] = []
    previews: list[dict[str, Any]] = []
    featured: list[dict[str, Any]] = []

    for item in resp.get("Items", []):
        content_type = item.get("content_type")
        if content_type == "RECAP":
            recap.append(item)
        elif content_type == "PREVIEW":
            previews.append(item)
        elif content_type == "FEATURED":
            featured.append(item)
        # Items with missing/unknown content_type are silently dropped — the
        # writer is the only producer and validates content_type at write time.

    featured.sort(key=lambda it: int(it.get("rank") or it.get("key_suffix") or 0))

    return {"recap": recap, "previews": previews, "featured": featured}
