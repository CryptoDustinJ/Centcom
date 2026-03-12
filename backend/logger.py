#!/usr/bin/env python3
"""Structured logging for Star Office backend.

Provides JSON-formatted logging with consistent field names, log rotation,
and contextual information (route, agent_id, duration, etc.).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

# Log level from environment
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_FILE = os.path.join(LOG_DIR, "star-office.log")

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        # Base payload
        payload: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name or "star-office",
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Add extra fields from record.__dict__ that start with underscore
        for key, value in record.__dict__.items():
            if key.startswith("_") and not key.startswith("__"):
                # Strip leading underscore for JSON field name
                payload[key[1:]] = value

        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    """
    Configure root logger with JSON formatting and file rotation.

    Returns:
        Root logger instance
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Remove any existing handlers
    logger.handlers.clear()

    # Console handler (stdout) - JSON format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    logger.addHandler(console_handler)

    # File handler with rotation (10 MB max, keep 10 files)
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=10,
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    except Exception as e:
        # If file logging fails, still keep console
        console_handler.emit(
            logging.LogRecord(
                name="logger",
                level=logging.WARNING,
                pathname=__file__,
                lineno=0,
                msg=f"Failed to set up file logging: {e}",
                args=(),
                exc_info=None,
            )
        )

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger with the given name. If name is None, returns root logger.

    Args:
        name: Logger name (typically module name like 'app' or 'validation')

    Returns:
        Logger instance
    """
    if name is None:
        return logging.getLogger()
    return logging.getLogger(name)


# Convenience functions for common log levels with structured context
def log_request(logger: logging.Logger, method: str, path: str, status: int, duration_ms: float):
    """Log an HTTP request with timing."""
    logger.info(
        "HTTP request",
        extra={
            "_event": "http_request",
            "_method": method,
            "_path": path,
            "_status": status,
            "_duration_ms": duration_ms,
        },
    )


def log_agent_action(logger: logging.Logger, action: str, agent_id: str, **kwargs: Any):
    """Log agent-related action."""
    logger.info(
        f"Agent {action}",
        extra={"_event": "agent_action", "agent_id": agent_id, **{f"_{k}": v for k, v in kwargs.items()}},
    )


def log_error(logger: logging.Logger, error: Exception, context: str = "", **kwargs: Any):
    """Log an error with context."""
    logger.error(
        f"{context}: {error}" if context else str(error),
        exc_info=True,
        extra={"_event": "error", "_context": context, **{f"_{k}": v for k, v in kwargs.items()}},
    )
