#!/usr/bin/env python3
"""Star Office UI - Modular Backend Application

This module creates the Flask application and registers all blueprints.
All route implementations are in the blueprints/ directory.
"""

from datetime import datetime, timedelta
import os
import threading
import time
from flask import Flask, g, request, session, jsonify

# === Configuration & Logging ===
from config import config as cfg
from logger import setup_logging, get_logger, log_request
from security_utils import is_production_mode, is_strong_secret, is_strong_drawer_pass

# Initialize structured logging early
logger = setup_logging()
log = get_logger(__name__)

# === Blueprints ===
from blueprints.core import bp as core_bp
from blueprints.agents import bp as agents_bp
from blueprints.state import bp as state_bp
from blueprints.assets import bp as assets_bp
from blueprints.config import bp as config_bp
from blueprints.office import bp as office_bp
from blueprints.growth import bp as growth_bp

# === Shared utilities ===
from shared import ensure_electron_standalone_snapshot

# === Global state for background tasks ===
_bg_tasks = {}  # task_id -> task info
_bg_tasks_lock = threading.Lock()

# Cleanup thread lock
agents_cleanup_lock = threading.Lock()

# Startup timestamp for health checks
_start_time = time.time()

# Constants from config (aliases for backward compatibility)
ROOT_DIR = cfg.ROOT_DIR
FRONTEND_DIR = cfg.FRONTEND_DIR
STATE_FILE = cfg.STATE_FILE
AGENTS_STATE_FILE = cfg.AGENTS_STATE_FILE
JOIN_KEYS_FILE = cfg.JOIN_KEYS_FILE
MEMORY_DIR = cfg.MEMORY_DIR
ASSET_ALLOWED_EXTS = cfg.ASSET_ALLOWED_EXTS
MAX_UPLOAD_SIZE = cfg.MAX_UPLOAD_SIZE
STALE_STATE_TTL_SECONDS = cfg.STALE_STATE_TTL_SECONDS
CLEANUP_REJECTED_AFTER_SECONDS = cfg.CLEANUP_REJECTED_AFTER_SECONDS
CLEANUP_INTERVAL_SECONDS = cfg.CLEANUP_INTERVAL_SECONDS
AUTO_IDLE_TTL = cfg.AUTO_IDLE_TTL


# === Background cleanup thread ===

def _cleanup_stale_agents():
    """Remove stale or long-rejected agents."""
    with agents_cleanup_lock:
        try:
            from shared import load_agents_state as _load, save_agents_state as _save
            agents = _load()
            now = datetime.now()
            changed = False
            to_remove = []

            for agent in agents:
                if agent.get("isMain"):
                    continue

                # Remove stale non-idle agents
                last_push = agent.get("lastPushAt") or agent.get("updated_at")
                if last_push:
                    try:
                        dt = datetime.fromisoformat(last_push.replace("Z", "+00:00"))
                        age_seconds = (now - dt).total_seconds()
                        state = agent.get("state", "idle")
                        if state != "idle" and age_seconds > STALE_STATE_TTL_SECONDS:
                            to_remove.append(agent)
                            changed = True
                            continue
                    except Exception:
                        pass

                # Remove old rejected/expired agents
                auth_status = agent.get("authStatus")
                if auth_status in ("rejected", "expired"):
                    left_at = agent.get("leftAt")
                    if left_at:
                        try:
                            dt = datetime.fromisoformat(left_at.replace("Z", "+00:00"))
                            age_seconds = (now - dt).total_seconds()
                            if age_seconds > CLEANUP_REJECTED_AFTER_SECONDS:
                                to_remove.append(agent)
                                changed = True
                        except Exception:
                            pass

            if changed:
                new_agents = [a for a in agents if a not in to_remove]
                _save(new_agents)
        except Exception:
            pass  # best effort


def _cleanup_thread_loop():
    """Background loop for stale agent cleanup."""
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            _cleanup_stale_agents()
        except Exception:
            pass


# Start cleanup daemon
_cleanup_thread = threading.Thread(target=_cleanup_thread_loop, daemon=True)
_cleanup_thread.start()


# === Application factory ===

def create_app():
    """Create and configure the Flask application."""
    # Serve static files from frontend directory at /static URL path
    app = Flask(__name__, static_folder=cfg.FRONTEND_DIR, static_url_path='/static')

    # Configuration
    app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("STAR_OFFICE_SECRET") or "star-office-dev-secret-change-me"
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_production_mode(),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=cfg.SESSION_PERMANENT_LIFETIME_HOURS),
    )

    # Store shared config and runtime data
    app.config['VERSION_TIMESTAMP'] = datetime.now().strftime("%Y%m%d_%H%M%S")
    app.config['_start_time'] = _start_time
    app.config['_bg_tasks'] = _bg_tasks

    # Security hardening in production
    if is_production_mode():
        hardening_errors = []
        if not is_strong_secret(str(app.secret_key)):
            hardening_errors.append("FLASK_SECRET_KEY / STAR_OFFICE_SECRET is weak (need >=24 chars)")
        drawer_pass = os.getenv("ASSET_DRAWER_PASS", "1234")
        if not is_strong_drawer_pass(drawer_pass):
            hardening_errors.append("ASSET_DRAWER_PASS is weak (recommend >=8 chars)")
        if hardening_errors:
            raise RuntimeError("Security hardening check failed: " + "; ".join(hardening_errors))

    # === Middleware registration ===

    @app.before_request
    def _before_request_log():
        """Record start time for request duration."""
        g._request_start_time = time.time()

    @app.after_request
    def _after_request_log(response):
        """Log HTTP request with duration and status; also record metrics."""
        start = getattr(g, '_request_start_time', None)
        if start is not None:
            duration_ms = (time.time() - start) * 1000
            try:
                log_request(
                    logger,
                    request.method or "UNKNOWN",
                    request.path or "unknown",
                    response.status_code,
                    duration_ms,
                )
            except Exception:
                pass
            try:
                from metrics import record_http_request
                record_http_request(
                    request.method or "UNKNOWN",
                    request.path or "unknown",
                    response.status_code,
                    duration_ms / 1000.0,
                )
            except Exception:
                pass
        return response

    @app.after_request
    def _add_no_cache_headers(response):
        """Apply cache policy."""
        path = (request.path or "")
        if path.startswith('/static/') and 200 <= response.status_code < 300:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers.pop("Pragma", None)
            response.headers.pop("Expires", None)
        else:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # === Register blueprints ===
    app.register_blueprint(core_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(state_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(office_bp)
    app.register_blueprint(growth_bp)

    # === Initialization ===
    try:
        if not os.path.exists(STATE_FILE):
            default_state = {
                "state": "idle",
                "detail": "等待任务中...",
                "progress": 0,
                "updated_at": datetime.now().isoformat()
            }
            from store_utils import _save_json
            _save_json(STATE_FILE, default_state)
        ensure_electron_standalone_snapshot()
    except Exception as e:
        logger.warning(f"Startup initialization warning: {e}")

    logger.info("Star Office UI backend initialized", extra={"_port": cfg.PORT})
    return app


# === Entrypoint ===

if __name__ == "__main__":
    # Determine port
    raw_port = os.environ.get("STAR_BACKEND_PORT", str(cfg.PORT))
    try:
        backend_port = int(raw_port)
    except ValueError:
        backend_port = cfg.PORT
    if backend_port <= 0 or backend_port > 65535:
        backend_port = cfg.PORT

    # Initialize app first (needed for secret_key checks)
    app = create_app()

    # Startup banner
    print("=" * 50)
    print("Star Office UI - Backend State Service")
    print("=" * 50)
    print(f"State file: {STATE_FILE}")
    print(f"Listening on: http://0.0.0.0:{backend_port}")
    if backend_port != cfg.PORT:
        print(f"(Port override: set STAR_BACKEND_PORT to change; current: {raw_port})")
    else:
        print(f"(Set STAR_BACKEND_PORT to use a different port, default: {cfg.PORT})")
    mode = "production" if is_production_mode() else "development"
    print(f"Mode: {mode}")
    if is_production_mode():
        print("Security hardening: ENABLED (strict checks)")
    else:
        weak_flags = []
        if not is_strong_secret(str(app.secret_key)):
            weak_flags.append("weak FLASK_SECRET_KEY/STAR_OFFICE_SECRET")
        drawer_pass = os.getenv("ASSET_DRAWER_PASS", "1234")
        if not is_strong_drawer_pass(drawer_pass):
            weak_flags.append("weak ASSET_DRAWER_PASS")
        if weak_flags:
            print("Security hardening: WARNING (dev mode) -> " + ", ".join(weak_flags))
        else:
            print("Security hardening: OK")
    print("=" * 50)

    app.run(host="0.0.0.0", port=backend_port, debug=False)
