"""Shared fixtures + seed helpers for api_players tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import boto3
import pytest


@pytest.fixture
def seeded_table(games_table_name: str, dynamodb_table) -> Any:
    """Seed the moto-mocked games table with one team's worth of records."""
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    items = [
        # Player metadata
        {
            "PK": "PLAYER#GLOBAL",
            "SK": "PLAYER#1",
            "person_id": 1,
            "full_name": "Alpha",
            "primary_number": "10",
            "current_age": 30,
            "primary_position_abbr": "RF",
        },
        {
            "PK": "PLAYER#GLOBAL",
            "SK": "PLAYER#2",
            "person_id": 2,
            "full_name": "Bravo",
            "primary_number": "21",
            "current_age": 28,
            "primary_position_abbr": "SP",
        },
        {
            "PK": "PLAYER#GLOBAL",
            "SK": "PLAYER#3",
            "person_id": 3,
            "full_name": "Charlie",
            "primary_number": "5",
            "current_age": 26,
            "primary_position_abbr": "2B",
        },
        # Roster
        {
            "PK": "ROSTER#2026#147",
            "SK": "ROSTER#1",
            "person_id": 1,
            "team_id": 147,
            "full_name": "Alpha",
            "jersey_number": "10",
            "position_abbr": "RF",
            "status_code": "A",
            "season": 2026,
        },
        {
            "PK": "ROSTER#2026#147",
            "SK": "ROSTER#2",
            "person_id": 2,
            "team_id": 147,
            "full_name": "Bravo",
            "jersey_number": "21",
            "position_abbr": "SP",
            "status_code": "A",
            "season": 2026,
        },
        {
            "PK": "ROSTER#2026#147",
            "SK": "ROSTER#3",
            "person_id": 3,
            "team_id": 147,
            "full_name": "Charlie",
            "jersey_number": "5",
            "position_abbr": "2B",
            "status_code": "A",
            "season": 2026,
        },
        # Hitting season stats
        {
            "PK": "STATS#2026#hitting",
            "SK": "STATS#1",
            "person_id": 1,
            "season": 2026,
            "group": "hitting",
            "full_name": "Alpha",
            "avg": ".320",
            "obp": ".410",
            "slg": ".620",
            "ops": "1.030",
            "home_runs": Decimal("25"),
            "rbi": Decimal("60"),
            "woba": Decimal("0.420"),
            "ops_plus": Decimal("160.5"),
        },
        {
            "PK": "STATS#2026#hitting",
            "SK": "STATS#3",
            "person_id": 3,
            "season": 2026,
            "group": "hitting",
            "full_name": "Charlie",
            "avg": ".280",
            "obp": ".340",
            "slg": ".430",
            "ops": ".770",
            "home_runs": Decimal("8"),
            "rbi": Decimal("30"),
            "woba": Decimal("0.330"),
            "ops_plus": Decimal("100.0"),
        },
        # Pitching season stats
        {
            "PK": "STATS#2026#pitching",
            "SK": "STATS#2",
            "person_id": 2,
            "season": 2026,
            "group": "pitching",
            "full_name": "Bravo",
            "era": "2.50",
            "whip": "1.05",
            "innings_pitched": "60.0",
            "strikeouts": Decimal("75"),
            "wins": Decimal("8"),
            "saves": Decimal("0"),
            "fip": Decimal("3.10"),
        },
    ]
    for item in items:
        table.put_item(Item=item)
    return table
