"""Invoke the api_scoreboard Lambda handler locally with a fake API Gateway event.

Spins up moto-mocked DynamoDB, seeds it from the MLB fixture (or live data
via --ingest-live), then invokes the handler for the chosen route.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))


def _build_event(route: str, game_id: str | None, date: str | None) -> dict:
    if route == "scoreboard":
        return {
            "routeKey": "GET /scoreboard/today",
            "rawPath": "/scoreboard/today",
            "queryStringParameters": {"date": date} if date else None,
        }
    return {
        "routeKey": "GET /games/{gameId}",
        "rawPath": f"/games/{game_id}",
        "pathParameters": {"gameId": game_id or ""},
        "queryStringParameters": {"date": date} if date else None,
    }


def _seed_from_fixture(table_name: str, region: str) -> None:
    """Load tests/fixtures/mlb_schedule.json and write its games to the mock table."""
    from shared.models import normalize_game

    sys.path.insert(0, str(ROOT / "functions"))
    from shared.dynamodb import put_game

    fixture = ROOT / "tests" / "fixtures" / "mlb_schedule.json"
    with fixture.open(encoding="utf-8") as f:
        payload = json.load(f)

    for d in payload.get("dates") or []:
        for raw in d.get("games") or []:
            put_game(normalize_game(raw), table_name=table_name)


def _seed_from_live_mlb(table_name: str) -> None:
    """Run the ingest Lambda once against the real MLB API to populate the table."""
    from ingest_live_games.handler import lambda_handler as ingest

    print("[seed] ingesting today's live MLB games...", file=sys.stderr)
    summary = ingest({}, None)
    print(f"[seed] ingest summary: {json.dumps(summary)}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--route", choices=["scoreboard", "game"], required=True, help="Which route to call."
    )
    parser.add_argument("--game-id", help="MLB gamePk for the game route.")
    parser.add_argument("--date", help="YYYY-MM-DD date param.")
    parser.add_argument(
        "--seed",
        choices=["fixture", "live", "none"],
        default="fixture",
        help="How to populate the mock table before the call (default: fixture).",
    )
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    if args.route == "game" and not args.game_id:
        parser.error("--game-id is required when --route=game")

    table_name = "diamond-iq-games-local"
    os.environ["GAMES_TABLE_NAME"] = table_name
    os.environ["AWS_DEFAULT_REGION"] = args.region
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

    import boto3
    from moto import mock_aws

    with mock_aws():
        boto3.client("dynamodb", region_name=args.region).create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        if args.seed == "fixture":
            _seed_from_fixture(table_name, args.region)
        elif args.seed == "live":
            _seed_from_live_mlb(table_name)

        from api_scoreboard.handler import lambda_handler

        event = _build_event(args.route, args.game_id, args.date)
        response = lambda_handler(event, None)

    print(json.dumps(response, indent=2))
    body = json.loads(response["body"])
    return 0 if response["statusCode"] < 400 else (1 if "error" in body else 0)


if __name__ == "__main__":
    sys.exit(main())
