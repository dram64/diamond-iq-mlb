from __future__ import annotations

import json
from decimal import Decimal

import boto3
from api_players.handler import lambda_handler


def _seed_statcast(games_table_name: str, person_id: int, season: int = 2026) -> None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(games_table_name)
    table.put_item(
        Item={
            "PK": f"STATCAST#{season}",
            "SK": f"STATCAST#{person_id}",
            "person_id": person_id,
            "season": season,
            "display_name": "Alpha",
            "hitting": {
                "xba": ".290",
                "xslg": ".707",
                "xwoba": ".466",
                "avg_hit_speed": Decimal("94.7"),
                "max_hit_speed": Decimal("115.8"),
                "ev95_percent": Decimal("55.6"),
                "barrel_percent": Decimal("21.5"),
                "sweet_spot_percent": Decimal("38.9"),
                "sprint_speed": Decimal("26.8"),
            },
            "pitching": None,
            "bat_tracking": {
                "avg_bat_speed": Decimal("75.2"),
                "swing_length": Decimal("7.8"),
            },
            "batted_ball": {
                "pull_rate": Decimal("0.49"),
                "straight_rate": Decimal("0.31"),
                "oppo_rate": Decimal("0.21"),
            },
        }
    )


def test_player_endpoint_includes_statcast_when_present(seeded_table, games_table_name):  # noqa: ARG001
    _seed_statcast(games_table_name, 1)
    event = {"routeKey": "GET /api/players/{personId}", "pathParameters": {"personId": "1"}}
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    sc = body["data"]["statcast"]
    assert sc is not None
    assert sc["display_name"] == "Alpha"
    assert sc["hitting"]["xba"] == ".290"
    assert float(sc["hitting"]["avg_hit_speed"]) == 94.7
    assert sc["pitching"] is None
    assert float(sc["bat_tracking"]["avg_bat_speed"]) == 75.2
    assert float(sc["batted_ball"]["pull_rate"]) == 0.49
    # PK / SK stripped from the projected payload.
    assert "PK" not in sc
    assert "SK" not in sc


def test_player_endpoint_returns_null_statcast_when_absent(seeded_table, games_table_name):  # noqa: ARG001
    """Player exists in PLAYER#GLOBAL but has no STATCAST row yet (e.g.
    not in the qualified pool). Endpoint returns 200 with statcast=None
    rather than 404."""
    event = {"routeKey": "GET /api/players/{personId}", "pathParameters": {"personId": "1"}}
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["data"]["statcast"] is None


def test_compare_endpoint_includes_statcast_per_player(seeded_table, games_table_name):  # noqa: ARG001
    _seed_statcast(games_table_name, 1)
    # Player 2 has no statcast row.
    event = {
        "routeKey": "GET /api/players/compare",
        "pathParameters": {},
        "queryStringParameters": {"ids": "1,2"},
    }
    response = lambda_handler(event, None, table_name=games_table_name)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    players = body["data"]["players"]
    assert len(players) == 2
    by_id = {p["person_id"]: p for p in players}
    assert by_id[1]["statcast"] is not None
    assert by_id[1]["statcast"]["hitting"]["xba"] == ".290"
    assert by_id[2]["statcast"] is None
