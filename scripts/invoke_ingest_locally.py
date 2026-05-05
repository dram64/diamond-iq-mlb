"""Invoke the ingest Lambda handler locally against MLB Stats API.

Two modes:
    --dry-run            spin up a moto-mocked DynamoDB table and write to it
    --table-name NAME    write to a real DynamoDB table you have access to

Always hits the real MLB Stats API (no fixture replay). Useful for sanity
checking the ingest path without deploying.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add functions/ to sys.path so we can import the handler outside pytest.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))


def _run_against_real_table(table_name: str, region: str) -> dict:
    os.environ["GAMES_TABLE_NAME"] = table_name
    os.environ.setdefault("AWS_DEFAULT_REGION", region)
    from ingest_live_games.handler import lambda_handler

    return lambda_handler({}, None)


def _run_dry(region: str) -> dict:
    """Run inside a moto context so no real AWS is touched."""
    import boto3
    from moto import mock_aws

    table_name = "diamond-iq-games-local"
    os.environ["GAMES_TABLE_NAME"] = table_name
    os.environ["AWS_DEFAULT_REGION"] = region
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

    with mock_aws():
        client = boto3.client("dynamodb", region_name=region)
        client.create_table(
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
        from ingest_live_games.handler import lambda_handler

        return lambda_handler({}, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Use moto-mocked DynamoDB.")
    mode.add_argument("--table-name", help="Write to this real DynamoDB table.")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default us-east-1).")
    args = parser.parse_args()

    if args.dry_run:
        result = _run_dry(args.region)
    else:
        result = _run_against_real_table(args.table_name, args.region)

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
