"""Lightweight structured logger (structlog-compatible)."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

_logger = logging.getLogger("manhuaju")
if not _logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)


def log_event(event: str, **fields: Any) -> None:
    """Emit a single structured JSON line."""
    rec: dict[str, Any] = {"ts": time.time(), "event": event, **fields}
    try:
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
    except Exception:
        line = f'{{"event": {event!r}, "fields": "<unencodable>"}}'
    _logger.info(line)


def configure(level: int = logging.INFO) -> None:
    _logger.setLevel(level)
