"""Sub-phase 9A: Bedrock end-to-end smoke test from a Lambda execution role.

Calls Claude Sonnet 4.6 once via the cross-region inference profile and
returns the model's response text plus token usage. Runs once to verify
IAM, then this Lambda + its Terraform are removed.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from shared.log import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_PROMPT = "Say hello to Diamond IQ in exactly one short sentence."


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", None) if context else None
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL)
    prompt = (event or {}).get("prompt") or DEFAULT_PROMPT

    log_ctx = {"request_id": request_id, "model_id": model_id}

    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 80,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload = json.loads(response["body"].read().decode("utf-8"))

    text_blocks = [
        block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
    ]
    text = "".join(text_blocks).strip()

    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)

    summary = {
        "ok": True,
        "model_id": model_id,
        "stop_reason": payload.get("stop_reason"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "response_text": text,
    }
    logger.info("Bedrock smoke invocation complete", extra={**log_ctx, **summary})
    return summary
