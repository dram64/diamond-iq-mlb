"""Phase 6 Bedrock smoke-test (cost + latency gate).

Hits Claude Haiku 4.5 via Bedrock with the actual production prompt
shapes against 5 representative compare scenarios:
    1. 2-player comparison (hitter vs hitter)
    2. 2-player comparison (pitcher vs pitcher)
    3. 3-player comparison
    4. 4-player comparison
    5. 2-team comparison

For each scenario, records per-call latency, input/output token counts,
and a sample output. Computes p50/p95 latency and per-call cost using
public Haiku 4.5 pricing ($1/Mtok input, $5/Mtok output as of 2026-01).

This is the Gate before /api/compare-analysis/* go live. Run from the
repo root:

    uv run python scripts/smoke_test_bedrock_haiku.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from typing import Any

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "functions"))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "functions", "ai_compare")
)

from ai_compare.handler import (
    DEFAULT_MODEL,
    MAX_TOKENS,
    SYSTEM_PROMPT_PLAYERS,
    SYSTEM_PROMPT_TEAMS,
    _build_player_user_text,
    _build_team_user_text,
    _invoke_bedrock,
)

# Public Haiku 4.5 pricing per million tokens (USD).
PRICE_INPUT_PER_MTOK = 1.00
PRICE_OUTPUT_PER_MTOK = 5.00


def _player(
    pid: int,
    name: str,
    team_id: int,
    *,
    hitting: dict | None = None,
    pitching: dict | None = None,
    awards: dict | None = None,
) -> dict:
    return {
        "person_id": pid,
        "metadata": {
            "person_id": pid,
            "full_name": name,
            "primary_position_abbr": "RF" if hitting else "SP",
            "current_age": 30,
        },
        "hitting": hitting,
        "pitching": pitching,
        "awards": awards,
    }


def _team(tid: int, name: str) -> dict:
    return {
        "team_id": tid,
        "team_name": name,
        "season": 2026,
        "hitting": {
            "games_played": 31,
            "avg": ".265",
            "home_runs": 48,
            "rbi": 145,
            "ops": ".748",
            "stolen_bases": 25,
        },
        "pitching": {
            "era": "3.45",
            "whip": "1.18",
            "strikeouts": 268,
            "wins": 18,
            "saves": 8,
            "opp_avg": ".232",
        },
    }


def _hitter(avg: str, hr: int, ops: str, woba: float, ops_plus: float, team_id: int) -> dict:
    return {
        "team_id": team_id,
        "games_played": 31,
        "at_bats": 110,
        "avg": avg,
        "home_runs": hr,
        "rbi": 28,
        "ops": ops,
        "obp": ".390",
        "slg": ".510",
        "woba": woba,
        "ops_plus": ops_plus,
    }


def _pitcher(era: str, whip: str, k: int, team_id: int, fip: float) -> dict:
    return {
        "team_id": team_id,
        "games_played": 6,
        "innings_pitched": "38.1",
        "wins": 3,
        "losses": 1,
        "saves": 0,
        "era": era,
        "whip": whip,
        "strikeouts": k,
        "fip": fip,
    }


def _awards(mvp_count: int, all_star_count: int, ws_count: int = 0) -> dict:
    return {
        "person_id": 0,
        "total_awards": mvp_count + all_star_count + ws_count,
        "all_star_count": all_star_count,
        "all_star_years": [2017, 2018, 2019][:all_star_count],
        "mvp_count": mvp_count,
        "mvp_years": [2024][:mvp_count],
        "cy_young_count": 0,
        "cy_young_years": [],
        "rookie_of_the_year_count": 0,
        "rookie_of_the_year_years": [],
        "gold_glove_count": 0,
        "gold_glove_years": [],
        "silver_slugger_count": 0,
        "silver_slugger_years": [],
        "world_series_count": ws_count,
        "world_series_years": [2009][:ws_count],
    }


def scenario_two_hitters() -> tuple[str, list[dict], str, str, str]:
    players = [
        _player(
            592450,
            "Aaron Judge",
            147,
            hitting=_hitter(".310", 12, ".980", 0.420, 165.0, 147),
            awards=_awards(mvp_count=1, all_star_count=3),
        ),
        _player(
            670541,
            "Yordan Alvarez",
            117,
            hitting=_hitter(".325", 11, "1.020", 0.450, 175.0, 117),
            awards=_awards(mvp_count=0, all_star_count=2, ws_count=1),
        ),
    ]
    return (
        "2-player (hitter vs hitter)",
        players,
        "players",
        SYSTEM_PROMPT_PLAYERS,
        _build_player_user_text(players, 2026),
    )


def scenario_two_pitchers() -> tuple[str, list[dict], str, str, str]:
    players = [
        _player(
            519242,
            "Chris Sale",
            144,
            pitching=_pitcher("2.85", "1.05", 65, 144, 3.10),
            awards=_awards(mvp_count=0, all_star_count=2),
        ),
        _player(
            667755,
            "José Soriano",
            108,
            pitching=_pitcher("2.40", "1.00", 58, 108, 2.95),
            awards=_awards(mvp_count=0, all_star_count=0),
        ),
    ]
    return (
        "2-player (pitcher vs pitcher)",
        players,
        "players",
        SYSTEM_PROMPT_PLAYERS,
        _build_player_user_text(players, 2026),
    )


def scenario_three_hitters() -> tuple[str, list[dict], str, str, str]:
    players = [
        _player(
            592450,
            "Aaron Judge",
            147,
            hitting=_hitter(".310", 12, ".980", 0.420, 165.0, 147),
            awards=_awards(mvp_count=1, all_star_count=3),
        ),
        _player(
            670541,
            "Yordan Alvarez",
            117,
            hitting=_hitter(".325", 11, "1.020", 0.450, 175.0, 117),
            awards=_awards(mvp_count=0, all_star_count=2, ws_count=1),
        ),
        _player(
            545361,
            "Mike Trout",
            108,
            hitting=_hitter(".290", 10, ".920", 0.395, 155.0, 108),
            awards=_awards(mvp_count=3, all_star_count=3),
        ),
    ]
    return (
        "3-player",
        players,
        "players",
        SYSTEM_PROMPT_PLAYERS,
        _build_player_user_text(players, 2026),
    )


def scenario_four_hitters() -> tuple[str, list[dict], str, str, str]:
    players = [
        _player(
            592450,
            "Aaron Judge",
            147,
            hitting=_hitter(".310", 12, ".980", 0.420, 165.0, 147),
            awards=_awards(1, 3),
        ),
        _player(
            670541,
            "Yordan Alvarez",
            117,
            hitting=_hitter(".325", 11, "1.020", 0.450, 175.0, 117),
            awards=_awards(0, 2, 1),
        ),
        _player(
            545361,
            "Mike Trout",
            108,
            hitting=_hitter(".290", 10, ".920", 0.395, 155.0, 108),
            awards=_awards(3, 3),
        ),
        _player(
            621566,
            "Matt Olson",
            144,
            hitting=_hitter(".275", 9, ".880", 0.380, 145.0, 144),
            awards=_awards(0, 2),
        ),
    ]
    return (
        "4-player",
        players,
        "players",
        SYSTEM_PROMPT_PLAYERS,
        _build_player_user_text(players, 2026),
    )


def scenario_two_teams() -> tuple[str, list[dict], str, str, str]:
    teams = [_team(147, "New York Yankees"), _team(121, "New York Mets")]
    return "2-team", teams, "teams", SYSTEM_PROMPT_TEAMS, _build_team_user_text(teams, 2026)


def main() -> int:
    client = boto3.client("bedrock-runtime", region_name="us-east-1")

    scenarios = [
        scenario_two_hitters(),
        scenario_two_pitchers(),
        scenario_three_hitters(),
        scenario_four_hitters(),
        scenario_two_teams(),
    ]

    results: list[dict[str, Any]] = []
    print(f"Smoke-testing {DEFAULT_MODEL} with {len(scenarios)} scenarios.\n")
    for label, _sources, kind, system, user_text in scenarios:
        started = time.monotonic()
        try:
            text, in_tok, out_tok = _invoke_bedrock(
                client,
                model_id=DEFAULT_MODEL,
                system=system,
                user_text=user_text,
                max_tokens=MAX_TOKENS,
            )
        except Exception as err:
            print(f"  [{label}] FAILED: {err}")
            return 1
        elapsed_ms = int((time.monotonic() - started) * 1000)
        cost_usd = (in_tok / 1_000_000) * PRICE_INPUT_PER_MTOK + (
            out_tok / 1_000_000
        ) * PRICE_OUTPUT_PER_MTOK
        results.append(
            {
                "label": label,
                "kind": kind,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "elapsed_ms": elapsed_ms,
                "cost_usd": cost_usd,
                "text": text,
            }
        )
        print(f"  [{label}] {elapsed_ms} ms | in={in_tok} out={out_tok} | ${cost_usd:.5f}")

    latencies = [r["elapsed_ms"] for r in results]
    costs = [r["cost_usd"] for r in results]
    p50 = statistics.median(latencies)
    p95 = max(latencies)  # 5 samples → max ≈ p95
    avg_cost = statistics.mean(costs)
    max_cost = max(costs)

    print("\n=== Aggregate results ===")
    print(f"  latency p50: {p50:.0f} ms")
    print(f"  latency p95: {p95:.0f} ms")
    print(f"  cost mean:   ${avg_cost:.5f}")
    print(f"  cost max:    ${max_cost:.5f}")
    print()

    print("=== Sample outputs ===")
    for r in results:
        print(f"\n--- {r['label']} ---")
        print(r["text"][:600])

    print("\n=== JSON dump (for archival) ===")
    print(
        json.dumps(
            {
                "model_id": DEFAULT_MODEL,
                "max_tokens": MAX_TOKENS,
                "results": [{**r, "text": r["text"][:200]} for r in results],
                "p50_ms": p50,
                "p95_ms": p95,
                "avg_cost_usd": avg_cost,
                "max_cost_usd": max_cost,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
