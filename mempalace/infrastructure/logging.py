"""Structured logging utilities."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from mempalace.infrastructure.settings import LoggingSettings


_BUILTIN_LOG_RECORD_FIELDS = {
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
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _BUILTIN_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=True)


def configure_logging(settings: LoggingSettings, logger_name: str = "mempalace.memory") -> logging.Logger:
    """Configure and return a logger for the new service core."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, settings.level.upper(), logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter() if settings.json else logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a structured log event."""
    logger.log(level, event, extra={"event": event, **fields})
