#!/usr/bin/env python3
"""Core blueprint: public pages and health checks."""

import json
import os
import time
from datetime import datetime

from flask import Blueprint, jsonify, make_response, request, session, current_app

from shared import (
    config,
    load_state,
    get_office_name_from_identity,
    ensure_electron_standalone_snapshot,
    _maybe_apply_random_home_favorite,
)
from metrics import get_metrics as prometheus_metrics

bp = Blueprint('core', __name__)


@bp.route("/", methods=["GET"])
def index():
    """Serve the pixel office UI with built-in version cache busting"""
    # Optional: auto-rotate home background on page load if configured
    _maybe_apply_random_home_favorite()

    if '_INDEX_HTML_CACHE' not in current_app.config:
        index_path = config.FRONTEND_INDEX_FILE
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                raw_html = f.read()
            current_app.config['_INDEX_HTML_CACHE'] = raw_html.replace("{{VERSION_TIMESTAMP}}", current_app.config.get("VERSION_TIMESTAMP", ""))
        except FileNotFoundError:
            return jsonify({"status": "error", "msg": "index.html not found"}), 404

    resp = make_response(current_app.config['_INDEX_HTML_CACHE'])
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@bp.route("/electron-standalone", methods=["GET"])
def electron_standalone_page():
    """Serve Electron-only standalone frontend page."""
    ensure_electron_standalone_snapshot()
    target = config.FRONTEND_ELECTRON_STANDALONE_FILE
    if not os.path.exists(target):
        target = config.FRONTEND_INDEX_FILE

    try:
        with open(target, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return jsonify({"status": "error", "msg": "frontend not found"}), 404

    html = html.replace("{{VERSION_TIMESTAMP}}", current_app.config.get("VERSION_TIMESTAMP", ""))
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@bp.route("/join", methods=["GET"])
def join_page():
    """Serve the agent join page"""
    join_path = os.path.join(config.FRONTEND_DIR, "join.html")
    try:
        with open(join_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return jsonify({"status": "error", "msg": "join.html not found"}), 404
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@bp.route("/invite", methods=["GET"])
def invite_page():
    """Serve human-facing invite instruction page"""
    invite_path = os.path.join(config.FRONTEND_DIR, "invite.html")
    try:
        with open(invite_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return jsonify({"status": "error", "msg": "invite.html not found"}), 404
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@bp.route("/health", methods=["GET"])
def health():
    """Comprehensive health check."""
    checks = {}
    overall_status = "healthy"
    now = datetime.now().isoformat()

    # 1) State file
    try:
        if os.path.exists(config.STATE_FILE):
            with open(config.STATE_FILE, "r", encoding="utf-8") as f:
                json.load(f)
            checks["state_file"] = "ok"
        else:
            checks["state_file"] = "missing"
            overall_status = "degraded"
    except Exception as e:
        checks["state_file"] = f"error: {e}"
        overall_status = "unhealthy"

    # 2) Agents state file
    try:
        if os.path.exists(config.AGENTS_STATE_FILE):
            with open(config.AGENTS_STATE_FILE, "r", encoding="utf-8") as f:
                json.load(f)
            checks["agents_file"] = "ok"
        else:
            checks["agents_file"] = "missing (will be created on first agent)"
    except Exception as e:
        checks["agents_file"] = f"error: {e}"
        overall_status = "unhealthy"

    # 3) Join keys file
    try:
        if os.path.exists(config.JOIN_KEYS_FILE):
            with open(config.JOIN_KEYS_FILE, "r", encoding="utf-8") as f:
                json.load(f)
            checks["join_keys_file"] = "ok"
        else:
            checks["join_keys_file"] = "missing (will use defaults)"
    except Exception as e:
        checks["join_keys_file"] = f"error: {e}"
        overall_status = "unhealthy"

    # 4) Frontend directory
    try:
        if os.path.isdir(config.FRONTEND_DIR) and os.path.isfile(os.path.join(config.FRONTEND_DIR, "index.html")):
            checks["frontend_dir"] = "ok"
        else:
            checks["frontend_dir"] = "missing or incomplete"
            overall_status = "degraded"
    except Exception as e:
        checks["frontend_dir"] = f"error: {e}"
        overall_status = "unhealthy"

    # f) Disk space
    try:
        import shutil as _shutil
        total, used, free = _shutil.disk_usage(config.ROOT_DIR)
        free_mb = free // (1024 * 1024)
        checks["disk_free_mb"] = free_mb
        if free_mb < 100:
            checks["disk"] = "critical"
            overall_status = "unhealthy"
        else:
            checks["disk"] = "ok"
    except Exception as e:
        checks["disk"] = f"error: {e}"
        overall_status = "degraded"

    # g) Redis connectivity
    if config.REDIS_URL:
        try:
            import redis
            r = redis.from_url(config.REDIS_URL, socket_connect_timeout=2)
            r.ping()
            checks["redis"] = "connected"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            overall_status = "degraded"
    else:
        checks["redis"] = "not configured"

    # h) Gemini env
    try:
        runtime_cfg = {}
        if os.path.exists(config.RUNTIME_CONFIG_FILE):
            with open(config.RUNTIME_CONFIG_FILE, "r", encoding="utf-8") as f:
                runtime_cfg = json.load(f)
        if runtime_cfg.get("gemini_api_key"):
            if os.path.exists(config.GEMINI_SCRIPT) and os.path.exists(config.GEMINI_PYTHON):
                checks["gemini_env"] = "ready"
            else:
                checks["gemini_env"] = "script missing (gemini will fail)"
                overall_status = "degraded"
        else:
            checks["gemini_env"] = "no api key"
    except Exception as e:
        checks["gemini_env"] = f"error: {e}"
        overall_status = "degraded"

    response = {
        "status": overall_status,
        "checks": checks,
        "timestamp": now,
        "service": "star-office-ui",
        "uptime": time.time() - current_app.config.get('_start_time', time.time()),
    }
    status_code = 200 if overall_status == "healthy" else (503 if overall_status == "unhealthy" else 200)
    return jsonify(response), status_code


@bp.route("/metrics", methods=["GET"])
def metrics():
    """Prometheus metrics endpoint."""
    # Optionally update dynamic metrics before generating
    try:
        from shared import load_agents_state
        agents = load_agents_state()
        from metrics import update_agent_metrics
        update_agent_metrics(agents)
    except Exception:
        pass
    data = prometheus_metrics()
    return current_app.response_class(data, mimetype="text/plain; version=0.0.4; charset=utf-8")
