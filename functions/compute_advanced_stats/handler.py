from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from shared.keys import stats_pk
from shared.log import get_logger

logger = get_logger(__name__)

GAMES_TABLE_ENV = "GAMES_TABLE_NAME"
CLOUDWATCH_NAMESPACE = "DiamondIQ/AdvancedStats"
DEFAULT_FUNCTION_NAME = "diamond-iq-compute-advanced-stats"

# wOBA linear weights — Fangraphs Guts 2023 (fangraphs.com/guts.aspx?type=cn).
# Stable to within ~0.5% across seasons; portfolio-grade rather than
# season-keyed. Override is a one-line change if a future season needs it.
_WOBA_WEIGHTS = {
    "ubb": Decimal("0.69"),  # unintentional walk
    "hbp": Decimal("0.72"),
    "1b": Decimal("0.89"),
    "2b": Decimal("1.27"),
    "3b": Decimal("1.62"),
    "hr": Decimal("2.10"),
}

_DECIMAL_QUANTIZE = Decimal("0.001")  # 3 decimal places for stored stats


def _resolve_table_name(override: str | None) -> str:
    if override is not None:
        return override
    name = os.environ.get(GAMES_TABLE_ENV)
    if not name:
        raise RuntimeError(f"{GAMES_TABLE_ENV} env var not set and no override provided")
    return name


def _to_decimal(value: Any) -> Decimal | None:
    """Parse MLB-stat-as-string into a Decimal. Returns None on missing/unparseable.

    MLB returns rate stats as ".300" (no leading zero) and counting stats as
    plain ints. inningsPitched uses ".1" / ".2" baseball notation (1/3 / 2/3 of
    an inning) — handled separately by _parse_innings.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        s = value.strip()
        if not s or s in ("-", "-.--"):
            return None
        try:
            return Decimal(s)
        except (ArithmeticError, ValueError):
            return None
    return None


def _parse_innings(value: Any) -> Decimal | None:
    """Convert MLB inningsPitched ('100.1' = 100 1/3 IP) into Decimal innings."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        whole, _, frac = s.partition(".")
        whole_d = Decimal(whole or "0")
        if frac == "1":
            return whole_d + Decimal("1") / Decimal("3")
        if frac == "2":
            return whole_d + Decimal("2") / Decimal("3")
        if frac == "0" or frac == "":
            return whole_d
        # Unexpected fractional form; fall back to plain decimal parse.
        return Decimal(s)
    except (ArithmeticError, ValueError):
        return None


def _read_qualified_records(table: Any, season: int, group: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    last_key: dict[str, Any] | None = None
    while True:
        kwargs: dict[str, Any] = {"KeyConditionExpression": Key("PK").eq(stats_pk(season, group))}
        if last_key is not None:
            kwargs["ExclusiveStartKey"] = last_key
        resp = table.query(**kwargs)
        items.extend(resp.get("Items") or [])
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return items


# ── Per-player formulas ──────────────────────────────────────────────────


def _woba(record: dict[str, Any]) -> Decimal | None:
    """Per-player wOBA. Returns None if PA-equivalent denominator is 0."""
    hits = _to_decimal(record.get("hits"))
    doubles = _to_decimal(record.get("doubles"))
    triples = _to_decimal(record.get("triples"))
    home_runs = _to_decimal(record.get("home_runs"))
    walks = _to_decimal(record.get("walks"))
    intentional_walks = _to_decimal(record.get("intentional_walks"))
    sacrifice_flies = _to_decimal(record.get("sacrifice_flies"))
    hbp = _to_decimal(record.get("hit_by_pitch"))
    at_bats = _to_decimal(record.get("at_bats"))
    if any(
        x is None
        for x in (
            hits,
            doubles,
            triples,
            home_runs,
            walks,
            intentional_walks,
            sacrifice_flies,
            hbp,
            at_bats,
        )
    ):
        return None
    singles = max(hits - doubles - triples - home_runs, Decimal("0"))
    ubb = max(walks - intentional_walks, Decimal("0"))
    numerator = (
        _WOBA_WEIGHTS["ubb"] * ubb
        + _WOBA_WEIGHTS["hbp"] * hbp
        + _WOBA_WEIGHTS["1b"] * singles
        + _WOBA_WEIGHTS["2b"] * doubles
        + _WOBA_WEIGHTS["3b"] * triples
        + _WOBA_WEIGHTS["hr"] * home_runs
    )
    denominator = at_bats + walks - intentional_walks + sacrifice_flies + hbp
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(_DECIMAL_QUANTIZE)


def _ops_plus(record: dict[str, Any], lg_obp: Decimal, lg_slg: Decimal) -> Decimal | None:
    """League-relative OPS+. No park adjustment (documented limitation)."""
    obp = _to_decimal(record.get("obp"))
    slg = _to_decimal(record.get("slg"))
    if obp is None or slg is None:
        return None
    if lg_obp == 0 or lg_slg == 0:
        return None
    raw = (obp / lg_obp) + (slg / lg_slg) - Decimal("1")
    return (Decimal("100") * raw).quantize(_DECIMAL_QUANTIZE)


def _fip(record: dict[str, Any], cfip: Decimal) -> Decimal | None:
    """Per-pitcher FIP. None if IP is zero or required fields are missing."""
    home_runs = _to_decimal(record.get("home_runs"))
    walks = _to_decimal(record.get("walks"))
    hbp = _to_decimal(record.get("hit_by_pitch"))
    strikeouts = _to_decimal(record.get("strikeouts"))
    ip = _parse_innings(record.get("innings_pitched"))
    if any(x is None for x in (home_runs, walks, hbp, strikeouts, ip)):
        return None
    if ip == 0:
        return None
    inner = Decimal("13") * home_runs + Decimal("3") * (walks + hbp) - Decimal("2") * strikeouts
    return ((inner / ip) + cfip).quantize(_DECIMAL_QUANTIZE)


# ── League aggregates ────────────────────────────────────────────────────


def _league_hitting_means(hitters: list[dict[str, Any]]) -> tuple[Decimal | None, Decimal | None]:
    """Mean OBP and mean SLG across qualified hitters."""
    obps: list[Decimal] = []
    slgs: list[Decimal] = []
    for h in hitters:
        o = _to_decimal(h.get("obp"))
        s = _to_decimal(h.get("slg"))
        if o is not None:
            obps.append(o)
        if s is not None:
            slgs.append(s)
    lg_obp = (sum(obps) / Decimal(len(obps))).quantize(_DECIMAL_QUANTIZE) if obps else None
    lg_slg = (sum(slgs) / Decimal(len(slgs))).quantize(_DECIMAL_QUANTIZE) if slgs else None
    return lg_obp, lg_slg


def _cfip_and_lg_era(pitchers: list[dict[str, Any]]) -> tuple[Decimal | None, Decimal | None]:
    """cFIP backsolved from league-aggregate pitching totals + lg ERA.

    cFIP = lgERA - ((13*lgHR + 3*(lgBB + lgHBP) - 2*lgK) / lgIP)
    """
    sum_hr = Decimal("0")
    sum_bb = Decimal("0")
    sum_hbp = Decimal("0")
    sum_k = Decimal("0")
    sum_ip = Decimal("0")
    sum_er = Decimal("0")
    valid = 0
    for p in pitchers:
        hr = _to_decimal(p.get("home_runs"))
        bb = _to_decimal(p.get("walks"))
        hbp = _to_decimal(p.get("hit_by_pitch"))
        k = _to_decimal(p.get("strikeouts"))
        ip = _parse_innings(p.get("innings_pitched"))
        er = _to_decimal(p.get("earned_runs"))
        if any(x is None for x in (hr, bb, hbp, k, ip, er)):
            continue
        sum_hr += hr
        sum_bb += bb
        sum_hbp += hbp
        sum_k += k
        sum_ip += ip
        sum_er += er
        valid += 1
    if valid == 0 or sum_ip == 0:
        return None, None
    lg_era = (Decimal("9") * sum_er / sum_ip).quantize(_DECIMAL_QUANTIZE)
    fip_no_constant = (
        Decimal("13") * sum_hr + Decimal("3") * (sum_bb + sum_hbp) - Decimal("2") * sum_k
    ) / sum_ip
    cfip = (lg_era - fip_no_constant).quantize(_DECIMAL_QUANTIZE)
    return cfip, lg_era


# ── DynamoDB writes ──────────────────────────────────────────────────────


def _update_hitter(table: Any, record: dict[str, Any], woba: Decimal, ops_plus: Decimal) -> None:
    table.update_item(
        Key={"PK": record["PK"], "SK": record["SK"]},
        UpdateExpression="SET woba = :w, ops_plus = :o",
        ExpressionAttributeValues={":w": woba, ":o": ops_plus},
        ReturnValues="NONE",
    )


def _update_pitcher(table: Any, record: dict[str, Any], fip: Decimal) -> None:
    table.update_item(
        Key={"PK": record["PK"], "SK": record["SK"]},
        UpdateExpression="SET fip = :f",
        ExpressionAttributeValues={":f": fip},
        ReturnValues="NONE",
    )


# ── Metrics ──────────────────────────────────────────────────────────────


def _emit_metrics(
    cw_client: Any,
    function_name: str,
    *,
    hitters_computed: int,
    pitchers_computed: int,
    league_obp: Decimal | None,
    league_slg: Decimal | None,
    league_era: Decimal | None,
) -> None:
    dims = [{"Name": "LambdaFunction", "Value": function_name}]
    md: list[dict[str, Any]] = [
        {
            "MetricName": "HittersComputed",
            "Value": hitters_computed,
            "Unit": "Count",
            "Dimensions": dims,
        },
        {
            "MetricName": "PitchersComputed",
            "Value": pitchers_computed,
            "Unit": "Count",
            "Dimensions": dims,
        },
    ]
    if league_obp is not None:
        md.append(
            {
                "MetricName": "LeagueOBP",
                "Value": float(league_obp),
                "Unit": "None",
                "Dimensions": dims,
            }
        )
    if league_slg is not None:
        md.append(
            {
                "MetricName": "LeagueSLG",
                "Value": float(league_slg),
                "Unit": "None",
                "Dimensions": dims,
            }
        )
    if league_era is not None:
        md.append(
            {
                "MetricName": "LeagueERA",
                "Value": float(league_era),
                "Unit": "None",
                "Dimensions": dims,
            }
        )
    cw_client.put_metric_data(Namespace=CLOUDWATCH_NAMESPACE, MetricData=md)


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
            hitters_computed=int(summary.get("hitters_computed", 0)),
            pitchers_computed=int(summary.get("pitchers_computed", 0)),
            league_obp=summary.get("league_obp"),
            league_slg=summary.get("league_slg"),
            league_era=summary.get("league_era"),
        )
    except Exception as err:  # noqa: BLE001 - emission must not fail the Lambda
        logger.warning(
            "CloudWatch metric emission failed",
            extra={**log_ctx, "error_class": type(err).__name__, "error_message": str(err)},
        )


def _resolve_season(now: Any | None = None) -> int:
    from datetime import UTC, datetime

    return (now or datetime.now(UTC)).year


# ── Lambda entrypoint ────────────────────────────────────────────────────


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    table_name: str | None = None,
    cloudwatch_client: Any | None = None,
    now: Any | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    request_id = getattr(context, "aws_request_id", None) if context else None
    function_name = (
        getattr(context, "function_name", None) if context else None
    ) or DEFAULT_FUNCTION_NAME

    season = (event or {}).get("season") or _resolve_season(now)
    log_ctx: dict[str, Any] = {"request_id": request_id, "season": season}

    table = boto3.resource("dynamodb").Table(_resolve_table_name(table_name))
    cw_client = cloudwatch_client or boto3.client("cloudwatch", region_name="us-east-1")

    hitters = _read_qualified_records(table, season, "hitting")
    pitchers = _read_qualified_records(table, season, "pitching")

    if not hitters or not pitchers:
        logger.error(
            "Empty qualified pool; cannot compute advanced stats",
            extra={
                **log_ctx,
                "hitter_count": len(hitters),
                "pitcher_count": len(pitchers),
            },
        )
        summary = {
            "ok": False,
            "reason": "no_qualified_records",
            "season": season,
            "hitter_count": len(hitters),
            "pitcher_count": len(pitchers),
            "hitters_computed": 0,
            "pitchers_computed": 0,
            "hitters_skipped": 0,
            "pitchers_skipped": 0,
            "league_obp": None,
            "league_slg": None,
            "league_era": None,
            "cfip": None,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    lg_obp, lg_slg = _league_hitting_means(hitters)
    cfip, lg_era = _cfip_and_lg_era(pitchers)

    if lg_obp is None or lg_slg is None or lg_obp == 0 or lg_slg == 0:
        logger.error(
            "League OBP/SLG aggregate degenerate; aborting",
            extra={**log_ctx, "lg_obp": str(lg_obp), "lg_slg": str(lg_slg)},
        )
        summary = {
            "ok": False,
            "reason": "empty_league_aggregates",
            "season": season,
            "hitter_count": len(hitters),
            "pitcher_count": len(pitchers),
            "hitters_computed": 0,
            "pitchers_computed": 0,
            "hitters_skipped": 0,
            "pitchers_skipped": 0,
            "league_obp": lg_obp,
            "league_slg": lg_slg,
            "league_era": lg_era,
            "cfip": cfip,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
        return summary

    hitters_computed = 0
    hitters_skipped = 0
    for record in hitters:
        woba = _woba(record)
        ops_plus = _ops_plus(record, lg_obp, lg_slg)
        if woba is None and ops_plus is None:
            hitters_skipped += 1
            continue
        # Build the partial UpdateExpression on the fly so a None stat doesn't
        # become an attribute.
        sets: list[str] = []
        values: dict[str, Any] = {}
        if woba is not None:
            sets.append("woba = :w")
            values[":w"] = woba
        if ops_plus is not None:
            sets.append("ops_plus = :o")
            values[":o"] = ops_plus
        try:
            table.update_item(
                Key={"PK": record["PK"], "SK": record["SK"]},
                UpdateExpression="SET " + ", ".join(sets),
                ExpressionAttributeValues=values,
                ReturnValues="NONE",
            )
            hitters_computed += 1
        except Exception as err:  # noqa: BLE001 - per-record isolation
            hitters_skipped += 1
            logger.warning(
                "Hitter UpdateItem failed; continuing",
                extra={**log_ctx, "person_id": record.get("person_id"), "error": str(err)},
            )

    pitchers_computed = 0
    pitchers_skipped = 0
    if cfip is not None:
        for record in pitchers:
            fip = _fip(record, cfip)
            if fip is None:
                pitchers_skipped += 1
                continue
            try:
                _update_pitcher(table, record, fip)
                pitchers_computed += 1
            except Exception as err:  # noqa: BLE001 - per-record isolation
                pitchers_skipped += 1
                logger.warning(
                    "Pitcher UpdateItem failed; continuing",
                    extra={**log_ctx, "person_id": record.get("person_id"), "error": str(err)},
                )
    else:
        pitchers_skipped = len(pitchers)
        logger.warning(
            "cFIP could not be computed; skipping pitcher updates",
            extra={**log_ctx, "pitcher_count": len(pitchers)},
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary: dict[str, Any] = {
        "ok": hitters_computed > 0 and pitchers_computed > 0,
        "season": season,
        "hitter_count": len(hitters),
        "pitcher_count": len(pitchers),
        "hitters_computed": hitters_computed,
        "hitters_skipped": hitters_skipped,
        "pitchers_computed": pitchers_computed,
        "pitchers_skipped": pitchers_skipped,
        "league_obp": lg_obp,
        "league_slg": lg_slg,
        "league_era": lg_era,
        "cfip": cfip,
        "elapsed_ms": elapsed_ms,
    }
    logger.info("Advanced stats compute complete", extra={**log_ctx, **summary})
    _safe_emit_metrics(cw_client, function_name, summary, log_ctx)
    return summary
