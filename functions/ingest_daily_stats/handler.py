from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
from shared.keys import daily_stats_pk, daily_stats_sk, stats_pk, stats_sk
from shared.log import get_logger
from shared.mlb_client import (
    MLBAPIError,
    fetch_boxscore,
    fetch_qualified_season_stats,
    fetch_schedule_finals,
)

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
DAILY_STATS_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
INTER_CALL_SLEEP_SECONDS = 0.1
ALLOWED_MODES = frozenset({"standard", "season_only"})
GROUPS = ("hitting", "pitching")
FAILURE_RATIO_THRESHOLD = 0.5

CLOUDWATCH_NAMESPACE = "DiamondIQ/DailyStats"
DEFAULT_FUNCTION_NAME = "diamond-iq-ingest-daily-stats"


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _yesterday_utc(now: datetime | None = None) -> str:
    """Return yesterday's date in ISO form, anchored to UTC."""
    when = (now or datetime.now(UTC)) - timedelta(days=1)
    return when.date().isoformat()


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _ttl_now() -> int:
    return int(time.time()) + DAILY_STATS_TTL_SECONDS


def _safe_get(d: dict[str, Any] | None, *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _total_bases(b: dict[str, Any]) -> int:
    """1B + 2*2B + 3*3B + 4*HR.  1B = hits - 2B - 3B - HR."""
    hits = int(b.get("hits") or 0)
    doubles = int(b.get("doubles") or 0)
    triples = int(b.get("triples") or 0)
    home_runs = int(b.get("homeRuns") or 0)
    singles = max(hits - doubles - triples - home_runs, 0)
    return singles + 2 * doubles + 3 * triples + 4 * home_runs


def _k_bb_ratio(p: dict[str, Any]) -> float | None:
    """Strikeouts / walks. None if no walks (avoid divide-by-zero)."""
    walks = int(p.get("baseOnBalls") or 0)
    if walks == 0:
        return None
    strikeouts = int(p.get("strikeOuts") or 0)
    return strikeouts / walks


def _batter_item(
    *,
    date_iso: str,
    game_pk: int,
    person_id: int,
    team_id: int | None,
    full_name: str | None,
    batting: dict[str, Any],
) -> dict[str, Any]:
    return {
        "PK": daily_stats_pk(date_iso),
        "SK": daily_stats_sk(person_id, game_pk),
        "person_id": person_id,
        "game_pk": game_pk,
        "game_date": date_iso,
        "team_id": team_id,
        "full_name": full_name,
        "group": "hitting",
        "at_bats": int(batting.get("atBats") or 0),
        "hits": int(batting.get("hits") or 0),
        "doubles": int(batting.get("doubles") or 0),
        "triples": int(batting.get("triples") or 0),
        "home_runs": int(batting.get("homeRuns") or 0),
        "rbi": int(batting.get("rbi") or 0),
        "walks": int(batting.get("baseOnBalls") or 0),
        "strikeouts": int(batting.get("strikeOuts") or 0),
        "runs": int(batting.get("runs") or 0),
        "total_bases": _total_bases(batting),
        "ttl": _ttl_now(),
    }


def _pitcher_item(
    *,
    date_iso: str,
    game_pk: int,
    person_id: int,
    team_id: int | None,
    full_name: str | None,
    pitching: dict[str, Any],
) -> dict[str, Any]:
    ratio = _k_bb_ratio(pitching)
    item: dict[str, Any] = {
        "PK": daily_stats_pk(date_iso),
        "SK": daily_stats_sk(person_id, game_pk),
        "person_id": person_id,
        "game_pk": game_pk,
        "game_date": date_iso,
        "team_id": team_id,
        "full_name": full_name,
        "group": "pitching",
        "innings_pitched": pitching.get("inningsPitched"),
        "hits_allowed": int(pitching.get("hits") or 0),
        "runs": int(pitching.get("runs") or 0),
        "earned_runs": int(pitching.get("earnedRuns") or 0),
        "walks": int(pitching.get("baseOnBalls") or 0),
        "strikeouts": int(pitching.get("strikeOuts") or 0),
        "ttl": _ttl_now(),
    }
    if ratio is not None:
        item["k_bb_ratio"] = Decimal(str(round(ratio, 3)))
    return item


def _season_item(season: int, group: str, split: dict[str, Any]) -> dict[str, Any] | None:
    """Project a /stats?playerPool=Qualified split into a STATS#<season>#<group> row.

    The projection includes both display fields (avg, obp, slg, ops, era, whip,
    wins, losses, saves) and the input primitives needs to compute
    wOBA, OPS+, and FIP (at_bats, doubles, triples, walks, intentional_walks,
    sacrifice_flies, hit_by_pitch, earned_runs). The MLB API exposes both
    groups' season payloads with overlapping keys; we just pass them through.
    """
    person_id = _safe_get(split, "player", "id")
    if not isinstance(person_id, int):
        return None
    stat = split.get("stat") or {}

    # MLB API uses hitBatsmen for pitcher HBP-given-up (canonical field name on
    # pitcher splits). We store it as hit_by_pitch for consistency with hitter
    # records' field naming. The semantic distinction is record group: hitter
    # hit_by_pitch = HBP-received, pitcher hit_by_pitch = HBP-given-up.
    hbp = stat.get("hitBatsmen") if group == "pitching" else stat.get("hitByPitch")

    return {
        "PK": stats_pk(season, group),
        "SK": stats_sk(person_id),
        "season": season,
        "group": group,
        "person_id": person_id,
        "full_name": _safe_get(split, "player", "fullName"),
        "team_id": _safe_get(split, "team", "id"),
        "games_played": stat.get("gamesPlayed"),
        # Direct stat fields the dashboard renders.
        "avg": stat.get("avg"),
        "obp": stat.get("obp"),
        "slg": stat.get("slg"),
        "ops": stat.get("ops"),
        "hits": stat.get("hits"),
        "home_runs": stat.get("homeRuns"),
        "rbi": stat.get("rbi"),
        "era": stat.get("era"),
        "whip": stat.get("whip"),
        "innings_pitched": stat.get("inningsPitched"),
        "wins": stat.get("wins"),
        "losses": stat.get("losses"),
        "saves": stat.get("saves"),
        "strikeouts": stat.get("strikeOuts"),
        "stolen_bases": stat.get("stolenBases"),
        "at_bats": stat.get("atBats"),
        "doubles": stat.get("doubles"),
        "triples": stat.get("triples"),
        "plate_appearances": stat.get("plateAppearances"),
        "walks": stat.get("baseOnBalls"),
        "intentional_walks": stat.get("intentionalWalks"),
        "sacrifice_flies": stat.get("sacFlies"),
        "hit_by_pitch": hbp,
        "earned_runs": stat.get("earnedRuns"),
        # No TTL — season records refresh daily, never expire.
    }


def _walk_team_players(
    boxscore: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Yield (side, player_block) for every player on home and away."""
    out: list[tuple[str, dict[str, Any]]] = []
    teams = boxscore.get("teams") or {}
    for side in ("home", "away"):
        team_block = teams.get(side) or {}
        players = team_block.get("players") or {}
        for entry in players.values():
            out.append((side, entry))
    return out


def _process_game(
    *,
    game: dict[str, Any],
    date_iso: str,
    table: Any,
    log_ctx: dict[str, Any],
) -> tuple[int, int, int, int]:
    """Fetch one boxscore and write all per-player rows.

    Returns (batters_written, pitchers_written, batters_failed, pitchers_failed).
    Raises MLBAPIError when the boxscore fetch fails so the caller can
    isolate per-game.
    """
    game_pk = game.get("gamePk")
    if not isinstance(game_pk, int):
        return 0, 0, 0, 0
    boxscore = fetch_boxscore(game_pk)
    teams = boxscore.get("teams") or {}
    home_team_id = _safe_get(teams, "home", "team", "id")
    away_team_id = _safe_get(teams, "away", "team", "id")
    side_to_team = {"home": home_team_id, "away": away_team_id}

    batters_written = 0
    pitchers_written = 0
    batters_failed = 0
    pitchers_failed = 0

    for side, entry in _walk_team_players(boxscore):
        person_id = _safe_get(entry, "person", "id")
        if not isinstance(person_id, int):
            continue
        full_name = _safe_get(entry, "person", "fullName")
        team_id = side_to_team.get(side)
        stats = entry.get("stats") or {}
        batting = stats.get("batting") or {}
        pitching = stats.get("pitching") or {}

        if batting and (batting.get("atBats") is not None or batting.get("plateAppearances")):
            try:
                table.put_item(
                    Item=_batter_item(
                        date_iso=date_iso,
                        game_pk=game_pk,
                        person_id=person_id,
                        team_id=team_id,
                        full_name=full_name,
                        batting=batting,
                    )
                )
                batters_written += 1
            except Exception as err:  # noqa: BLE001 - per-player isolation
                batters_failed += 1
                logger.warning(
                    "Batter put_item failed; continuing",
                    extra={
                        **log_ctx,
                        "game_pk": game_pk,
                        "person_id": person_id,
                        "error": str(err),
                    },
                )

        if pitching and pitching.get("inningsPitched") is not None:
            try:
                table.put_item(
                    Item=_pitcher_item(
                        date_iso=date_iso,
                        game_pk=game_pk,
                        person_id=person_id,
                        team_id=team_id,
                        full_name=full_name,
                        pitching=pitching,
                    )
                )
                pitchers_written += 1
            except Exception as err:  # noqa: BLE001 - per-player isolation
                pitchers_failed += 1
                logger.warning(
                    "Pitcher put_item failed; continuing",
                    extra={
                        **log_ctx,
                        "game_pk": game_pk,
                        "person_id": person_id,
                        "error": str(err),
                    },
                )

    return batters_written, pitchers_written, batters_failed, pitchers_failed


def _refresh_season_stats(
    *,
    season: int,
    table: Any,
    log_ctx: dict[str, Any],
) -> tuple[int, int, int]:
    """Pull qualified-player season stats for both groups and overwrite rows.

    Returns (api_calls, season_stats_refreshed, season_stats_failed).
    """
    api_calls = 0
    refreshed = 0
    failed = 0
    for group in GROUPS:
        try:
            splits = fetch_qualified_season_stats(season, group)
            api_calls += 1
        except Exception as err:  # noqa: BLE001 - per-group isolation
            failed += 1
            logger.warning(
                "Bulk season stats fetch failed; counting group as failed",
                extra={**log_ctx, "group": group, "error": str(err)},
            )
            time.sleep(INTER_CALL_SLEEP_SECONDS)
            continue
        for split in splits:
            item = _season_item(season, group, split)
            if item is None:
                continue
            try:
                table.put_item(Item=item)
                refreshed += 1
            except Exception as err:  # noqa: BLE001 - per-row isolation
                failed += 1
                logger.warning(
                    "Season stats put_item failed; continuing",
                    extra={
                        **log_ctx,
                        "group": group,
                        "person_id": item.get("person_id"),
                        "error": str(err),
                    },
                )
        time.sleep(INTER_CALL_SLEEP_SECONDS)
    return api_calls, refreshed, failed


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    games_processed: int,
    batters_ingested: int,
    pitchers_ingested: int,
    season_stats_refreshed: int,
    games_failed: int,
) -> None:
    dims = [{"Name": "LambdaFunction", "Value": function_name}]
    cw_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                "MetricName": "GamesProcessed",
                "Value": games_processed,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "BattersIngested",
                "Value": batters_ingested,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "PitchersIngested",
                "Value": pitchers_ingested,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "SeasonStatsRefreshed",
                "Value": season_stats_refreshed,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "GamesFailed",
                "Value": games_failed,
                "Unit": "Count",
                "Dimensions": dims,
            },
        ],
    )


def _safe_emit_metrics(
    cw_client: Any | None,
    function_name: str,
    summary: dict[str, Any],
    log_ctx: dict[str, Any],
) -> None:
    if cw_client is None:
        return
    try:
        _emit_metrics(
            cw_client,
            function_name,
            games_processed=int(summary.get("games_processed", 0)),
            batters_ingested=int(summary.get("batters_ingested", 0)),
            pitchers_ingested=int(summary.get("pitchers_ingested", 0)),
            season_stats_refreshed=int(summary.get("season_stats_refreshed", 0)),
            games_failed=int(summary.get("games_failed", 0)),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    table_name: str | None = None,
    cloudwatch_client: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    request_id = getattr(context, "aws_request_id", None) if context else None
    function_name = (
        getattr(context, "function_name", None) if context else None
    ) or DEFAULT_FUNCTION_NAME

    mode = (event or {}).get("mode") or "standard"
    if mode not in ALLOWED_MODES:
        logger.error("Unknown mode; rejecting", extra={"request_id": request_id, "mode": mode})
        return {"ok": False, "reason": "unknown_mode", "mode": mode}

    season = _resolve_season(now)
    date_iso = _yesterday_utc(now)
    log_ctx: dict[str, Any] = {
        "request_id": request_id,
        "season": season,
        "mode": mode,
        "date": date_iso,
    }

    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    api_calls = 0
    games_processed = 0
    games_failed = 0
    batters_ingested = 0
    pitchers_ingested = 0
    batters_failed = 0
    pitchers_failed = 0
    games_total = 0

    if mode == "standard":
        try:
            yesterday_date = ((now or datetime.now(UTC)) - timedelta(days=1)).date()
            finals = fetch_schedule_finals(yesterday_date)
            api_calls += 1
        except MLBAPIError as err:
            logger.error(
                "Failed to fetch schedule; aborting daily-stats run",
                extra={**log_ctx, "error": str(err)},
            )
            summary = {
                "ok": False,
                "reason": "schedule_fetch_failed",
                "season": season,
                "mode": mode,
                "date": date_iso,
                "games_total": 0,
                "games_processed": 0,
                "games_failed": 0,
                "batters_ingested": 0,
                "pitchers_ingested": 0,
                "batters_failed": 0,
                "pitchers_failed": 0,
                "season_stats_refreshed": 0,
                "season_stats_failed": 0,
                "api_calls_made": api_calls,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
            _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
            return summary

        games_total = len(finals)
        for game in finals:
            try:
                bw, pw, bf, pf = _process_game(
                    game=game, date_iso=date_iso, table=table, log_ctx=log_ctx
                )
                api_calls += 1
                batters_ingested += bw
                pitchers_ingested += pw
                batters_failed += bf
                pitchers_failed += pf
                games_processed += 1
            except Exception as err:  # noqa: BLE001 - per-game isolation
                games_failed += 1
                logger.warning(
                    "Boxscore fetch/process failed; continuing",
                    extra={**log_ctx, "game_pk": game.get("gamePk"), "error": str(err)},
                )
            time.sleep(INTER_CALL_SLEEP_SECONDS)

    season_api_calls, season_refreshed, season_failed = _refresh_season_stats(
        season=season, table=table, log_ctx=log_ctx
    )
    api_calls += season_api_calls

    elapsed_ms = int((time.monotonic() - started) * 1000)
    failure_ratio = (games_failed / games_total) if games_total else 0.0
    summary: dict[str, Any] = {
        "ok": failure_ratio <= FAILURE_RATIO_THRESHOLD and season_failed == 0,
        "season": season,
        "mode": mode,
        "date": date_iso,
        "games_total": games_total,
        "games_processed": games_processed,
        "games_failed": games_failed,
        "batters_ingested": batters_ingested,
        "pitchers_ingested": pitchers_ingested,
        "batters_failed": batters_failed,
        "pitchers_failed": pitchers_failed,
        "season_stats_refreshed": season_refreshed,
        "season_stats_failed": season_failed,
        "api_calls_made": api_calls,
        "elapsed_ms": elapsed_ms,
    }
    logger.info("Daily stats ingest complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
