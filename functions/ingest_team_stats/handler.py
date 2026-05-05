from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from shared.keys import team_stats_pk, team_stats_sk
from shared.log import get_logger
from shared.mlb_client import MLBAPIError, fetch_team_season_stats, fetch_teams

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
INTER_CALL_SLEEP_SECONDS = 0.1
CLOUDWATCH_NAMESPACE = "DiamondIQ/TeamStats"
DEFAULT_FUNCTION_NAME = "diamond-iq-ingest-team-stats"


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _resolve_season(now: datetime | None = None) -> int:
    return (now or datetime.now(UTC)).year


def _hitting_projection(stat: dict[str, Any]) -> dict[str, Any]:
    """Map MLB upstream hitting fields to our schema. Preserves API-side
    string formatting for rate stats (avg / obp / slg / ops) so the
    frontend can pass them through unchanged."""
    return {
        "games_played": stat.get("gamesPlayed"),
        "plate_appearances": stat.get("plateAppearances"),
        "at_bats": stat.get("atBats"),
        "runs": stat.get("runs"),
        "hits": stat.get("hits"),
        "doubles": stat.get("doubles"),
        "triples": stat.get("triples"),
        "home_runs": stat.get("homeRuns"),
        "rbi": stat.get("rbi"),
        "walks": stat.get("baseOnBalls"),
        "intentional_walks": stat.get("intentionalWalks"),
        "strikeouts": stat.get("strikeOuts"),
        "stolen_bases": stat.get("stolenBases"),
        "caught_stealing": stat.get("caughtStealing"),
        "hit_by_pitch": stat.get("hitByPitch"),
        "sacrifice_flies": stat.get("sacFlies"),
        "ground_into_double_play": stat.get("groundIntoDoublePlay"),
        "left_on_base": stat.get("leftOnBase"),
        "total_bases": stat.get("totalBases"),
        "avg": stat.get("avg"),
        "obp": stat.get("obp"),
        "slg": stat.get("slg"),
        "ops": stat.get("ops"),
        "babip": stat.get("babip"),
    }


def _pitching_projection(stat: dict[str, Any]) -> dict[str, Any]:
    """Map MLB upstream pitching fields to our schema."""
    return {
        "games_played": stat.get("gamesPlayed"),
        "games_started": stat.get("gamesStarted"),
        "complete_games": stat.get("completeGames"),
        "shutouts": stat.get("shutouts"),
        "wins": stat.get("wins"),
        "losses": stat.get("losses"),
        "saves": stat.get("saves"),
        "save_opportunities": stat.get("saveOpportunities"),
        "blown_saves": stat.get("blownSaves"),
        "holds": stat.get("holds"),
        "innings_pitched": stat.get("inningsPitched"),
        "hits_allowed": stat.get("hits"),
        "runs_allowed": stat.get("runs"),
        "earned_runs": stat.get("earnedRuns"),
        "home_runs_allowed": stat.get("homeRuns"),
        "walks_allowed": stat.get("baseOnBalls"),
        "intentional_walks_allowed": stat.get("intentionalWalks"),
        "hit_batsmen": stat.get("hitBatsmen"),
        "strikeouts": stat.get("strikeOuts"),
        "batters_faced": stat.get("battersFaced"),
        "wild_pitches": stat.get("wildPitches"),
        "balks": stat.get("balks"),
        "era": stat.get("era"),
        "whip": stat.get("whip"),
        "opp_avg": stat.get("avg"),
        "opp_obp": stat.get("obp"),
        "opp_slg": stat.get("slg"),
        "opp_ops": stat.get("ops"),
        "hits_per_9": stat.get("hitsPer9Inn"),
        "home_runs_per_9": stat.get("homeRunsPer9"),
        "pitches_per_inning": stat.get("pitchesPerInning"),
        "runs_scored_per_9": stat.get("runsScoredPer9"),
    }


def _team_item(
    season: int, team_id: int, team_name: str | None, groups: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    return {
        "PK": team_stats_pk(season),
        "SK": team_stats_sk(team_id),
        "season": season,
        "team_id": team_id,
        "team_name": team_name,
        "hitting": (
            _hitting_projection(groups.get("hitting") or {}) if groups.get("hitting") else None
        ),
        "pitching": (
            _pitching_projection(groups.get("pitching") or {}) if groups.get("pitching") else None
        ),
        # No TTL — daily overwrite.
    }


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    teams_ingested: int,
    teams_failed: int,
    elapsed_ms: int,
) -> None:
    dims = [{"Name": "LambdaFunction", "Value": function_name}]
    cw_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                "MetricName": "TeamsIngested",
                "Value": teams_ingested,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "TeamsFailed",
                "Value": teams_failed,
                "Unit": "Count",
                "Dimensions": dims,
            },
            {
                "MetricName": "IngestionElapsedMs",
                "Value": elapsed_ms,
                "Unit": "Milliseconds",
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
            teams_ingested=int(summary.get("teams_ingested", 0)),
            teams_failed=int(summary.get("teams_failed", 0)),
            elapsed_ms=int(summary.get("elapsed_ms", 0)),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def lambda_handler(
    event: dict[str, Any],  # noqa: ARG001 - reserved
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

    season = _resolve_season(now)
    log_ctx: dict[str, Any] = {"request_id": request_id, "season": season}

    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    try:
        teams = fetch_teams(season)
    except MLBAPIError as err:
        logger.error("Failed to fetch teams; aborting", extra={**log_ctx, "error": str(err)})
        summary = {
            "ok": False,
            "reason": "teams_fetch_failed",
            "season": season,
            "teams_total": 0,
            "teams_ingested": 0,
            "teams_failed": 0,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    teams_ingested = 0
    teams_failed = 0
    for team in teams:
        team_id = team.get("id")
        if not isinstance(team_id, int):
            teams_failed += 1
            continue
        try:
            groups = fetch_team_season_stats(team_id, season)
            item = _team_item(season, team_id, team.get("name"), groups)
            table.put_item(Item=item)
            teams_ingested += 1
        except Exception as err:  # noqa: BLE001 - per-team isolation
            teams_failed += 1
            logger.warning(
                "Team stats ingest failed; continuing",
                extra={**log_ctx, "team_id": team_id, "error": str(err)},
            )
        time.sleep(INTER_CALL_SLEEP_SECONDS)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary: dict[str, Any] = {
        "ok": teams_failed == 0 and teams_ingested > 0,
        "season": season,
        "teams_total": len(teams),
        "teams_ingested": teams_ingested,
        "teams_failed": teams_failed,
        "elapsed_ms": elapsed_ms,
    }
    logger.info("Team-stats ingest complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
