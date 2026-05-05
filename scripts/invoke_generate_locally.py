"""Manually invoke the deployed daily-content Lambda.

Calls `diamond-iq-generate-daily-content` synchronously via the AWS
Lambda API and prints the response. Useful for ad-hoc reruns and
specific-date backfills outside the EventBridge schedule.

Unlike `invoke_ingest_locally.py`, this script does NOT run the
handler in-process — it calls the deployed Lambda. Side effects
(Bedrock invocations, DynamoDB writes, custom CloudWatch metrics)
land in the live AWS account exactly as a scheduled run would.

AWS credentials come from the environment via boto3's default
credential resolution chain (env vars, config file, role).

Usage:
    python scripts/invoke_generate_locally.py
    python scripts/invoke_generate_locally.py --date 2026-04-25

Exit codes:
    0  Lambda returned StatusCode=200 AND body's `ok` field is true.
    1  Lambda invocation succeeded at the API level but the handler
       returned ok=false (e.g., Bedrock throttle), OR the invoke
       call itself returned a Lambda function error / non-200.
    2  Unexpected exception in the script — invoke API call failed
       with a network/IAM error, response was not parseable, etc.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from datetime import UTC, datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

FUNCTION_NAME = "diamond-iq-generate-daily-content"
DEFAULT_REGION = "us-east-1"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today_utc_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def _valid_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        default=None,
        help="UTC date to generate content for (YYYY-MM-DD). Defaults to today UTC.",
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"AWS region (default: {DEFAULT_REGION}).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    target_date = args.date or _today_utc_iso()
    if not _valid_date(target_date):
        print(
            f"error: --date must be YYYY-MM-DD with a real calendar date, got {target_date!r}",
            file=sys.stderr,
        )
        return 2

    payload = {"date": target_date}
    print(f"Invoking {FUNCTION_NAME} (region={args.region}, date={target_date})...")

    try:
        # Read timeout has to exceed the Lambda's worst-case duration
        # (300s timeout + the Bedrock 4-retry chain on throttles).
        config = boto3.session.Config(read_timeout=420, connect_timeout=10)
        client = boto3.client("lambda", region_name=args.region, config=config)
        response = client.invoke(
            FunctionName=FUNCTION_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
    except (BotoCoreError, ClientError) as err:
        print(f"error: lambda.invoke failed: {err}", file=sys.stderr)
        return 1

    status_code = response.get("StatusCode", 0)
    function_error = response.get("FunctionError")
    body_bytes = response["Payload"].read()
    try:
        body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except json.JSONDecodeError:
        print("error: lambda response payload was not valid JSON:", file=sys.stderr)
        print(body_bytes.decode("utf-8", errors="replace"), file=sys.stderr)
        return 1

    print()
    print(f"StatusCode: {status_code}")
    if function_error:
        print(f"FunctionError: {function_error}")
    print("Payload:")
    print(json.dumps(body, indent=2))
    print()

    if function_error or status_code != 200:
        print("Lambda invocation failed at the AWS layer (FunctionError or non-200 StatusCode).")
        return 1

    ok = bool(body.get("ok"))
    summary = (
        f"items_written={body.get('items_written', 0)}  "
        f"bedrock_failures={body.get('bedrock_failures', 0)}  "
        f"dynamodb_failures={body.get('dynamodb_failures', 0)}"
    )

    if ok:
        print(f"OK — {summary}")
        return 0

    # Lambda invoked cleanly but the handler reports ok=false. The script
    # ran correctly; the truth being relayed is that the run failed.
    # Distinguish this from a script/infrastructure failure.
    print(f"Handler returned ok=false — {summary}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - top-level safety net
        traceback.print_exc()
        sys.exit(2)
