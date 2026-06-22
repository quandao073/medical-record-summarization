"""Structured JSON logging for the application."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import IO


class JSONFormatter(logging.Formatter):

    EXTRA_FIELDS = ("patient_id", "request_id", "section_id", "latency_ms")

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        for field in self.EXTRA_FIELDS:
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    stream: IO | None = None,
    level: int = logging.INFO,
) -> None:
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
