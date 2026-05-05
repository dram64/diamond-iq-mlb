"""Structured JSON logging.

Each log line is a single JSON object that CloudWatch Logs Insights can
parse natively. Pass `extra={"request_id": ctx.aws_request_id, ...}` from a
Lambda handler to get correlated logs.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

# Built-in LogRecord attributes we don't want to repeat in the JSON payload.
_RESERVED_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    """Formats LogRecords as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for JSON output on stdout.

    Idempotent — repeated calls with the same name return the already-configured
    logger without stacking handlers. Default level is INFO; override with the
    LOG_LEVEL environment variable.
    """
    logger = logging.getLogger(name)
    if getattr(logger, "_diq_configured", False):
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False

    logger._diq_configured = True  # type: ignore[attr-defined]
    return logger
