#!/usr/bin/env python3
"""Centralized configuration management for Star Office backend.

All paths, ports, and runtime constants are defined here.
Validates configuration on startup and fails fast with clear errors.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final


class Config:
    """Configuration container with environment-based overrides and validation."""

    # === Environment Detection ===
    @staticmethod
    def _get_env(name: str, default: str | None = None) -> str:
        """Get environment variable or default."""
        return os.getenv(name, default) if default is not None else os.getenv(name, "")

    # === Networking ===
    PORT: int = int(_get_env.__func__("STAR_BACKEND_PORT", "19000") or 19000)
    if PORT <= 0 or PORT > 65535:
        raise ValueError(f"Invalid PORT: {PORT} (must be 1-65535)")

    WORKERS: int = int(_get_env.__func__("WORKERS", "0") or 0)
    if WORKERS < 0:
        raise ValueError(f"WORKERS must be non-negative")

    # === Paths ===
    ROOT_DIR: Final[str] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    FRONTEND_DIR: Final[str] = os.path.join(ROOT_DIR, "frontend")
    FRONTEND_PATH: Final[Path] = Path(FRONTEND_DIR)
    FRONTEND_INDEX_FILE: Final[str] = os.path.join(FRONTEND_DIR, "index.html")
    FRONTEND_ELECTRON_STANDALONE_FILE: Final[str] = os.path.join(ROOT_DIR, "electron-standalone.html")

    # Data files (in project root, not in backend/)
    STATE_FILE: Final[str] = os.path.join(ROOT_DIR, "state.json")
    AGENTS_STATE_FILE: Final[str] = os.path.join(ROOT_DIR, "agents-state.json")
    JOIN_KEYS_FILE: Final[str] = os.path.join(ROOT_DIR, "join-keys.json")

    # Asset management
    ASSET_POSITIONS_FILE: Final[str] = os.path.join(ROOT_DIR, "asset-positions.json")
    ASSET_DEFAULTS_FILE: Final[str] = os.path.join(ROOT_DIR, "asset-defaults.json")
    RUNTIME_CONFIG_FILE: Final[str] = os.path.join(ROOT_DIR, "runtime-config.json")
    UPLOAD_DIR: Final[str] = FRONTEND_DIR  # uploads go into frontend tree

    # Logging
    LOG_DIR: Final[str] = os.getenv("LOG_DIR", os.path.join(ROOT_DIR, "logs"))
    LOG_LEVEL: Final[str] = _get_env.__func__("LOG_LEVEL", "INFO").upper()
    MAX_LOG_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: Final[int] = 10

    # === OpenClaw Integration ===
    WORKSPACE_DIR: Final[str] = os.path.dirname(ROOT_DIR)
    OPENCLAW_WORKSPACE: Final[str] = os.getenv(
        "OPENCLAW_WORKSPACE",
        os.path.join(os.path.expanduser("~"), ".openclaw", "workspace")
    )
    IDENTITY_FILE: Final[str] = os.path.join(OPENCLAW_WORKSPACE, "IDENTITY.md")

    # Gemini image generation paths
    GEMINI_SCRIPT: Final[str] = os.path.join(WORKSPACE_DIR, "skills", "gemini-image-generate", "scripts", "gemini_image_generate.py")
    GEMINI_PYTHON: Final[str] = os.path.join(WORKSPACE_DIR, "skills", "gemini-image-generate", ".venv", "bin", "python")

    # === Asset Defaults ===
    ASSET_ALLOWED_EXTS: Final[set[str]] = {".png", ".webp", ".jpg", ".jpeg", ".gif", ".svg", ".avif"}
    ASSET_TEMPLATE_ZIP: Final[str] = os.path.join(ROOT_DIR, "assets-replace-template.zip")
    ROOM_REFERENCE_IMAGE: Final[str] = (
        os.path.join(ROOT_DIR, "assets", "room-reference.webp")
        if os.path.exists(os.path.join(ROOT_DIR, "assets", "room-reference.webp"))
        else os.path.join(ROOT_DIR, "assets", "room-reference.png")
    )
    BG_HISTORY_DIR: Final[str] = os.path.join(ROOT_DIR, "assets", "bg-history")
    HOME_FAVORITES_DIR: Final[str] = os.path.join(ROOT_DIR, "assets", "home-favorites")
    HOME_FAVORITES_INDEX_FILE: Final[str] = os.path.join(HOME_FAVORITES_DIR, "index.json")
    HOME_FAVORITES_MAX: Final[int] = 30

    # === Canvas & Display ===
    CANVAS_WIDTH: Final[int] = 1280
    CANVAS_HEIGHT: Final[int] = 720

    # === State & Push ===
    PUSH_INTERVAL: Final[int] = 15  # seconds (remote agent push interval)
    STALE_STATE_TTL_SECONDS: Final[int] = 600  # 10 minutes
    AUTO_IDLE_TTL: Final[int] = 300  # 5 minutes (auto idle fallback)

    # === Upload ===
    MAX_UPLOAD_SIZE: Final[int] = 10 * 1024 * 1024  # 10 MB

    # === Cleanup ===
    CLEANUP_REJECTED_AFTER_SECONDS: Final[int] = 3600  # 1 hour
    CLEANUP_INTERVAL_SECONDS: Final[int] = 60  # background cleanup every minute

    # === Session ===
    SESSION_PERMANENT_LIFETIME_HOURS: Final[int] = 12

    # === Asset Rotation ===
    AUTO_ROTATE_HOME_ON_PAGE_OPEN: Final[bool] = os.getenv("AUTO_ROTATE_HOME_ON_PAGE_OPEN", "0").strip().lower() in {"1", "true", "yes", "on"}
    AUTO_ROTATE_MIN_INTERVAL_SECONDS: Final[int] = int(os.getenv("AUTO_ROTATE_MIN_INTERVAL_SECONDS", "60"))

    # === Gemini AI ===
    GEMINI_MODEL_DEFAULT: Final[str] = "nanobanana-pro"

    # === Redis (rate limiting, future DB) ===
    REDIS_URL: Final[str | None] = os.getenv("REDIS_URL")

    # === Validation Limits ===
    MAX_AGENT_NAME_LENGTH: Final[int] = 50
    MAX_DETAIL_LENGTH: Final[int] = 500
    MAX_JOIN_KEY_LENGTH: Final[int] = 64

    # === Gunicorn ===
    GUNICORN_TIMEOUT: Final[int] = int(os.getenv("TIMEOUT", "120"))
    GUNICORN_WORKER_CONNECTIONS: Final[int] = int(os.getenv("WORKER_CONNECTIONS", "1000"))

    # === File Locking ===
    FILELOCK_TIMEOUT: Final[float] = 60.0
    FILELOCK_MAX_AGE: Final[float] = 120.0

    # === Runtime computed paths ===
    MEMORY_DIR: Final[str] = os.path.join(os.path.dirname(ROOT_DIR), "memory")

    @classmethod
    def validate_paths(cls) -> None:
        """Validate that critical directories exist and are writable."""
        paths_to_check = [
            cls.ROOT_DIR,
            cls.FRONTEND_DIR,
            cls.WORKSPACE_DIR,
        ]
        for p in paths_to_check:
            if not os.path.isdir(p):
                raise RuntimeError(f"Required directory not found: {p}")
            if not os.access(p, os.W_OK):
                raise RuntimeError(f"Directory not writable: {p}")

        # Ensure log directory can be created
        try:
            os.makedirs(cls.LOG_DIR, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Cannot create log directory: {cls.LOG_DIR} - {e}")

    @classmethod
    def validate(cls) -> None:
        """Run all validations. Call at application startup."""
        cls.validate_paths()
        # Additional validation specific to production mode can be done separately


# Instantiate config at module load to validate immediately
try:
    config = Config()
    Config.validate()
except Exception as e:
    # Log to stderr as logger may not be ready
    print(f"[CONFIG ERROR] {e}", file=sys.stderr)
    raise
