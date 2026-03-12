#!/usr/bin/env python3
"""Append-only audit logging for critical operations.

Provides a simple interface to log events with structured data to a rotating
JSON lines file. Supports operator review and integration with SIEM.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from config import config as cfg
from logger import get_logger

logger = get_logger(__name__)

# Audit log file path (in project root)
AUDIT_LOG_FILE = os.path.join(cfg.ROOT_DIR, "audit.log")

# Ensure audit log directory exists
os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)


def log_event(
    event: str,
    actor: str | None = None,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """
    Write an audit log entry as a JSON line.

    Args:
        event: Event type (e.g., 'agent_joined', 'state_changed', 'key_revoked')
        actor: Who performed the action (agent_id, username, 'system', or 'admin')
        target: What was affected (agent_id, resource identifier)
        details: Additional structured data
        ip: Source IP address if available
    """
    entry: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": event,
    }
    if actor:
        entry["actor"] = actor
    if target:
        entry["target"] = target
    if details:
        entry["details"] = details
    if ip:
        entry["ip"] = ip

    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Audit log write failed: {e}", exc_info=True)


def get_recent_audit_lines(count: int = 100) -> list[dict[str, Any]]:
    """
    Read the most recent audit log entries (from end of file).
    Returns list of parsed JSON dicts in reverse chronological order.
    """
    lines = []
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            # Take last 'count' lines
            for line in all_lines[-count:]:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.error(f"Audit log read failed: {e}", exc_info=True)
    return list(reversed(lines))  # newest first


def rotate_if_needed(max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> None:
    """
    Rotate audit log if it exceeds max_bytes.
    Simple rotation: rename current to .1, .2, etc.
    """
    try:
        if os.path.exists(AUDIT_LOG_FILE):
            size = os.path.getsize(AUDIT_LOG_FILE)
            if size >= max_bytes:
                # Rotate
                for i in range(backup_count - 1, 0, -1):
                    src = f"{AUDIT_LOG_FILE}.{i}"
                    dst = f"{AUDIT_LOG_FILE}.{i+1}"
                    if os.path.exists(src):
                        os.rename(src, dst)
                os.rename(AUDIT_LOG_FILE, f"{AUDIT_LOG_FILE}.1")
                # Create new empty file (with header comment? no)
                open(AUDIT_LOG_FILE, "w").close()
    except Exception as e:
        logger.error(f"Audit log rotation failed: {e}", exc_info=True)
