#!/usr/bin/env python3
"""Agents blueprint: multi-agent management, joins, pushes, approvals."""

from flask import Blueprint, jsonify, request, session, current_app, Response
import random
import threading
import time
import os
import re
from datetime import datetime

from shared import (
    config,
    load_agents_state,
    save_agents_state,
    load_join_keys,
    save_join_keys,
    normalize_agent_state,
    state_to_area,
    VALID_AGENT_STATES as _VALID_AGENT_STATES,
    get_office_name_from_identity,
)
from pathlib import Path
import json
import subprocess
from validation import validate_agent_name, validate_state_detail, validate_invite_code, validate_agent_id, ValidationError as ValidationErrorExc


# === Skill Management (CM-17) ===
AGENT_SKILLS_FILE = Path(config.ROOT_DIR) / "agent_skills.json"


def _load_agent_skills():
    """Load agent skill authorizations."""
    if AGENT_SKILLS_FILE.exists():
        try:
            data = json.loads(AGENT_SKILLS_FILE.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _save_agent_skills(skills_data):
    """Save agent skill authorizations."""
    AGENT_SKILLS_FILE.write_text(json.dumps(skills_data, indent=2, ensure_ascii=False))
from rate_limit import rate_limit
from logger import log_agent_action
from audit import log_event as audit_log

bp = Blueprint('agents', __name__)

# Re-export VALID_AGENT_STATES for other modules if needed
VALID_AGENT_STATES = _VALID_AGENT_STATES

# Join lock for concurrency control
join_lock = threading.Lock()
agents_cleanup_lock = threading.Lock()


@bp.route("/agents", methods=["GET"])
@rate_limit(60, 60)
def get_agents():
    """Get full agents list (for multi-agent UI), with auto-cleanup on access"""
    agents = load_agents_state()
    now = datetime.now()

    # Opportunistic offline marking for non-main agents
    def _age_seconds(dt_str):
        if not dt_str:
            return None
        try:
            dt = datetime.fromisoformat(dt_str)
            return (now - dt).total_seconds()
        except Exception:
            return None

    changed = False
    for a in agents:
        if a.get("isMain"):
            continue
        if a.get("authStatus") != "approved":
            continue
        age = _age_seconds(a.get("lastPushAt"))
        if age is None:
            age = _age_seconds(a.get("updated_at"))
        if age is not None and age > 300:  # 5 min offline threshold
            a["authStatus"] = "offline"
            changed = True

    if changed:
        try:
            save_agents_state(agents)
        except Exception:
            pass

    return jsonify(agents)


@bp.route("/agent-approve", methods=["POST"])
def approve_agent():
    """Approve a pending agent (admin action)"""
    # Note: currently no auth, but should be protected in production
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400
        agent_id = (data.get("agentId") or "").strip()
        if not agent_id:
            return jsonify({"ok": False, "msg": "agentId required"}), 400

        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)
        if not agent:
            return jsonify({"ok": False, "msg": "Agent not found"}), 404

        if agent.get("authStatus") == "approved":
            return jsonify({"ok": False, "msg": "Already approved"}), 400

        agent["authStatus"] = "approved"
        agent["approvedAt"] = datetime.now().isoformat()
        save_agents_state(agents)

        log_agent_action(current_app.logger, "approved", agent_id)
        audit_log(
            event="agent_approved",
            actor=request.remote_addr or "unknown",
            target=agent_id,
            details={},
            ip=request.remote_addr,
        )
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"Approve agent error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agent-reject", methods=["POST"])
def reject_agent():
    """Reject a pending agent (admin action)"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400
        agent_id = (data.get("agentId") or "").strip()
        if not agent_id:
            return jsonify({"ok": False, "msg": "agentId required"}), 400

        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)
        if not agent:
            return jsonify({"ok": False, "msg": "Agent not found"}), 404

        agent["authStatus"] = "rejected"
        agent["rejectedAt"] = datetime.now().isoformat()
        # Mark to be cleaned up later
        agent["leftAt"] = datetime.now().isoformat()
        save_agents_state(agents)

        log_agent_action(current_app.logger, "rejected", agent_id)
        audit_log(
            event="agent_rejected",
            actor=request.remote_addr or "unknown",
            target=agent_id,
            details={},
            ip=request.remote_addr,
        )
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"Reject agent error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/join-agent", methods=["POST"])
@rate_limit(10, 300)  # 10 requests per 5 minutes per IP
def join_agent():
    """Add a new agent with one-time join key validation and pending auth"""
    try:
        data = request.get_json()
        if not isinstance(data, dict) or not data.get("name"):
            return jsonify({"ok": False, "msg": "请提供名字"}), 400

        try:
            name = validate_agent_name(data["name"])
        except ValidationErrorExc as e:
            return jsonify({"ok": False, "msg": f"Invalid agent name: {e}"}), 400

        state = data.get("state", "idle")
        detail = data.get("detail", "")
        join_key = data.get("joinKey", "").strip()

        if detail:
            try:
                detail = validate_state_detail(detail)
            except ValidationErrorExc as e:
                return jsonify({"ok": False, "msg": f"Invalid detail: {e}"}), 400
        else:
            detail = ""

        try:
            join_key = validate_invite_code(join_key)
        except ValidationErrorExc as e:
            return jsonify({"ok": False, "msg": f"Invalid join key: {e}"}), 400

        state = normalize_agent_state(state)

        if not join_key:
            return jsonify({"ok": False, "msg": "请提供接入密钥"}), 400

        keys_data = load_join_keys()
        key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
        if not key_item:
            return jsonify({"ok": False, "msg": "接入密钥无效"}), 403

        with join_lock:
            keys_data = load_join_keys()
            key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
            if not key_item:
                return jsonify({"ok": False, "msg": "接入密钥无效"}), 403

            # Key-level expiration check
            key_expires_at_str = key_item.get("expiresAt")
            if key_expires_at_str:
                try:
                    key_expires_at = datetime.fromisoformat(key_expires_at_str)
                    if datetime.now() > key_expires_at:
                        return jsonify({"ok": False, "msg": "该接入密钥已过期，活动已结束 🎉"}), 403
                except Exception:
                    pass

            agents = load_agents_state()

            # Concurrency limit: max concurrent per key (default 3)
            now = datetime.now()
            existing = next((a for a in agents if a.get("name") == name and not a.get("isMain")), None)
            existing_id = existing.get("agentId") if existing else None

            def _age_seconds(dt_str):
                if not dt_str:
                    return None
                try:
                    dt = datetime.fromisoformat(dt_str)
                    return (now - dt).total_seconds()
                except Exception:
                    return None

            # Mark stale offline
            for a in agents:
                if a.get("isMain"):
                    continue
                if a.get("authStatus") != "approved":
                    continue
                age = _age_seconds(a.get("lastPushAt"))
                if age is None:
                    age = _age_seconds(a.get("updated_at"))
                if age is not None and age > 300:
                    a["authStatus"] = "offline"

            max_concurrent = int(key_item.get("maxConcurrent", config.JOIN_KEY_DEFAULT_CONCURRENT if hasattr(config, 'JOIN_KEY_DEFAULT_CONCURRENT') else 3))
            active_count = 0
            for a in agents:
                if a.get("isMain"):
                    continue
                if a.get("agentId") == existing_id:
                    continue
                if a.get("joinKey") != join_key:
                    continue
                if a.get("authStatus") != "approved":
                    continue
                age = _age_seconds(a.get("lastPushAt"))
                if age is None:
                    age = _age_seconds(a.get("updated_at"))
                if age is None or age <= 300:
                    active_count += 1

            if active_count >= max_concurrent:
                save_agents_state(agents)
                return jsonify({"ok": False, "msg": f"该接入密钥当前并发已达上限（{max_concurrent}），请稍后或换另一个 key"}), 429

            if existing:
                existing["state"] = state
                existing["detail"] = detail
                existing["updated_at"] = datetime.now().isoformat()
                existing["area"] = state_to_area(state)
                existing["source"] = existing.get("source", "remote-openclaw")
                existing["joinKey"] = join_key
                existing["authStatus"] = "approved"
                existing["lastPushAt"] = datetime.now().isoformat()
                log_agent_action(current_app.logger, "rejoined", existing.get("agentId"), name=name)
            else:
                new_agent = {
                    "agentId": agent_id_generate(name),
                    "name": name,
                    "isMain": False,
                    "state": state,
                    "detail": detail,
                    "area": state_to_area(state),
                    "source": "remote-openclaw",
                    "joinKey": join_key,
                    "authStatus": "approved",
                    "avatar": "guest_role_" + str(random.randint(1, 5)),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "lastPushAt": datetime.now().isoformat(),
                }
                agents.append(new_agent)
                log_agent_action(current_app.logger, "joined", new_agent["agentId"], name=name)

            save_agents_state(agents)
            save_join_keys(keys_data)
            # Audit log
            aid = existing_id if existing else new_agent["agentId"]
            audit_log(
                event="agent_joined",
                actor=aid,
                target=aid,
                details={"name": name, "join_key": join_key},
                ip=request.remote_addr,
            )
            return jsonify({"ok": True, "agentId": aid, "authStatus": "approved"})

    except Exception as e:
        current_app.logger.error(f"Join agent error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


def agent_id_generate(name: str) -> str:
    """Generate a deterministic but pseudo-random agent ID from name + random."""
    import hashlib
    random.seed(name + str(time.time()))
    seed = int(random.random() * 1000000)
    return hashlib.md5(f"{name}_{seed}".encode()).hexdigest()[:12]


@bp.route("/leave-agent", methods=["POST"])
def leave_agent():
    """Agent voluntarily leaves (or timeout cleanup)."""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400

        agent_id = (data.get("agentId") or "").strip()
        if not agent_id:
            return jsonify({"ok": False, "msg": "agentId required"}), 400

        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)
        if not agent:
            return jsonify({"ok": False, "msg": "Agent not found"}), 404

        # Instead of deleting, mark as left so it can be cleaned up later
        agent["authStatus"] = "offline"
        agent["leftAt"] = datetime.now().isoformat()
        save_agents_state(agents)

        log_agent_action(current_app.logger, "left", agent_id)
        audit_log(
            event="agent_left",
            actor=agent_id,
            target=agent_id,
            details={},
            ip=request.remote_addr,
        )
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"Leave agent error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agent-push", methods=["POST"])
@rate_limit(60, 60)  # 60 requests per minute per IP
def agent_push():
    """Remote openclaw actively pushes status to office."""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400

        agent_id = (data.get("agentId") or "").strip()
        join_key = (data.get("joinKey") or "").strip()
        state = (data.get("state") or "").strip()
        detail = (data.get("detail") or "").strip()
        name = (data.get("name") or "").strip()

        if not agent_id or not join_key or not state:
            return jsonify({"ok": False, "msg": "缺少 agentId/joinKey/state"}), 400

        # Validate inputs
        try:
            agent_id = validate_agent_id(agent_id)
        except ValidationErrorExc as e:
            return jsonify({"ok": False, "msg": f"Invalid agentId: {e}"}), 400

        try:
            join_key = validate_invite_code(join_key)
        except ValidationErrorExc as e:
            return jsonify({"ok": False, "msg": f"Invalid joinKey: {e}"}), 400

        if name:
            try:
                name = validate_agent_name(name)
            except ValidationErrorExc as e:
                return jsonify({"ok": False, "msg": f"Invalid name: {e}"}), 400

        if detail:
            try:
                detail = validate_state_detail(detail)
            except ValidationErrorExc as e:
                return jsonify({"ok": False, "msg": f"Invalid detail: {e}"}), 400
        else:
            detail = ""

        state = normalize_agent_state(state)

        keys_data = load_join_keys()
        key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
        if not key_item:
            return jsonify({"ok": False, "msg": "joinKey 无效"}), 403

        # Key-level expiration check (optional but harmless)
        key_expires_at_str = key_item.get("expiresAt")
        if key_expires_at_str:
            try:
                key_expires_at = datetime.fromisoformat(key_expires_at_str)
                if datetime.now() > key_expires_at:
                    return jsonify({"ok": False, "msg": "接入密钥已过期"}), 403
            except Exception:
                pass

        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id), None)

        if agent:
            # Update existing agent
            # If agent was offline or rejected, re-approve on push
            if agent.get("authStatus") in ["offline", "rejected"]:
                agent["authStatus"] = "approved"
            agent["state"] = state
            agent["detail"] = detail
            if name:
                agent["name"] = name
            agent["lastPushAt"] = datetime.now().isoformat()
            agent["updated_at"] = datetime.now().isoformat()
            agent["area"] = state_to_area(state)
            agent["joinKey"] = join_key
        else:
            # Create new agent with automatic approval (key already validated)
            new_agent = {
                "agentId": agent_id,
                "name": name or f"Agent-{agent_id[:8]}",
                "isMain": False,
                "state": state,
                "detail": detail,
                "area": state_to_area(state),
                "source": "remote-openclaw",
                "joinKey": join_key,
                "authStatus": "approved",
                "avatar": "guest_role_" + str(random.randint(1, 5)),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "lastPushAt": datetime.now().isoformat(),
            }
            agents.append(new_agent)
            agent = new_agent
            log_agent_action(current_app.logger, "pushed_new", agent_id, name=new_agent["name"])

        save_agents_state(agents)
        audit_log(
            event="agent_state_updated",
            actor=agent_id,
            target=agent_id,
            details={"state": state, "detail": detail},
            ip=request.remote_addr,
        )
        return jsonify({"ok": True, "agent": agent})
    except Exception as e:
        current_app.logger.error(f"Agent push error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agent-messages", methods=["GET"])
@rate_limit(30, 60)
def agent_messages():
    """Get recent chat messages from OpenClaw agent sessions for the live chat feed."""
    try:
        limit = min(int(request.args.get("limit", 25)), 50)
        messages = _read_recent_agent_messages(limit)
        return jsonify({"ok": True, "messages": messages})
    except Exception as e:
        current_app.logger.error(f"Agent messages error: {e}", exc_info=True)
        return jsonify({"ok": True, "messages": []})


# Agent ID to display name mapping
_AGENT_DISPLAY_NAMES = {
    "main": "Rook",
    "ralph": "Ralph",
    "nova": "Nova",
    "codemaster": "CodeMaster",
}

# Cache to avoid re-reading unchanged files
_msg_cache = {"messages": [], "mtimes": {}, "last_refresh": 0}
_MSG_CACHE_TTL = 4  # seconds


def _read_recent_agent_messages(limit: int = 25) -> list:
    """Read recent assistant text messages from OpenClaw session logs."""
    import json as _json

    now = time.time()
    if now - _msg_cache["last_refresh"] < _MSG_CACHE_TTL and _msg_cache["messages"]:
        return _msg_cache["messages"][:limit]

    openclaw_agents_dir = os.path.join(
        os.path.expanduser("~"), ".openclaw", "agents"
    )
    if not os.path.isdir(openclaw_agents_dir):
        return []

    all_messages = []

    for agent_id in _AGENT_DISPLAY_NAMES:
        sessions_dir = os.path.join(openclaw_agents_dir, agent_id, "sessions")
        if not os.path.isdir(sessions_dir):
            continue

        # Find the most recent session file
        try:
            session_files = [
                os.path.join(sessions_dir, f)
                for f in os.listdir(sessions_dir)
                if f.endswith(".jsonl")
            ]
            if not session_files:
                continue
            latest = max(session_files, key=os.path.getmtime)
        except Exception:
            continue

        # Read last ~8KB of the file (enough for recent messages)
        try:
            fsize = os.path.getsize(latest)
            read_bytes = min(fsize, 16384)
            with open(latest, "r", encoding="utf-8", errors="ignore") as f:
                if fsize > read_bytes:
                    f.seek(fsize - read_bytes)
                    f.readline()  # skip partial line
                lines = f.readlines()
        except Exception:
            continue

        display_name = _AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = _json.loads(line)
            except _json.JSONDecodeError:
                continue

            if entry.get("type") != "message":
                continue

            msg = entry.get("message", {})
            role = msg.get("role")
            timestamp = entry.get("timestamp", "")

            # Only show assistant text messages (not tool calls/results)
            if role == "assistant":
                content = msg.get("content", [])
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            t = block.get("text", "")
                            # Strip <final> tags and <think> tags
                            t = re.sub(r"</?final>", "", t)
                            t = re.sub(r"<think>[\s\S]*?</think>", "", t)
                            t = t.strip()
                            if t:
                                text_parts.append(t)
                    text = " ".join(text_parts)
                else:
                    continue

                if not text or len(text) < 3:
                    continue
                # Skip stub/empty replies
                if text in ("NO_REPLY", "no_reply", "N/A", "n/a"):
                    continue

                # Truncate very long messages
                if len(text) > 300:
                    text = text[:297] + "..."

                all_messages.append({
                    "sender": display_name,
                    "text": text,
                    "timestamp": timestamp,
                })

    # Sort by timestamp descending (newest first) and limit
    all_messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    result = all_messages[:limit]

    _msg_cache["messages"] = result
    _msg_cache["last_refresh"] = now

    return result



# Command Center Mappings
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
SCRIPT_MAP = {
    "syscheck": os.path.join(SCRIPTS_DIR, "syscheck.sh"),
    "morning-briefing": os.path.join(SCRIPTS_DIR, "morning-briefing.sh"),
    "wallpaper": "/home/dustin/.openclaw/workspace/skills/daily-wallpaper/run_wallpaper.sh",
    "weather": os.path.join(SCRIPTS_DIR, "get_weather.sh"),
    "email-list": os.path.join(SCRIPTS_DIR, "get_emails.sh")
}

OPENCLAW_CMD_MAP = {
    "fullcheck": "📊 report",
    "self-heal": "🔧 system_doctor",
    "restart-both": "🔄 system_reboot",
    "kb-latest": "📚 kb_latest",
    "story": "📝 story_time",
    "storybook-list": "📚 list_stories",
    "watch-check": "👁️ watch_status",
}


@bp.route("/dispatch", methods=["POST"])
@rate_limit(20, 60)
def dispatch():
    """Command Center: Execute dashboard commands (restart-services, status, huddle, etc.)"""
    data = request.get_json() or {}
    command = data.get("command", "").strip()
    args = data.get("args", "")

    if not command:
        return jsonify({"ok": False, "msg": "No command provided"}), 400

    try:
        # 1. Handle specialized backend commands
        if command == "restart-services":
            result = subprocess.run(
                ["systemctl", "--user", "restart", "openclaw-gateway.service", "openclaw-node.service"],
                capture_output=True, text=True, timeout=30
            )
            return jsonify({"ok": result.returncode == 0, "msg": "Services restarted", "output": result.stdout})

        elif command == "status":
            env = os.environ.copy()
            env["PATH"] = "/home/linuxbrew/.linuxbrew/bin:" + env.get("PATH", "")
            result = subprocess.run(["openclaw", "status"], capture_output=True, text=True, timeout=10, env=env)
            return jsonify({"ok": result.returncode == 0, "output": result.stdout})

        # 2. Internal commands (huddle triggers)
        if command == "huddle":
            import requests as _req
            resp = _req.post("http://127.0.0.1:19000/office/huddle/start", timeout=30)
            if resp.status_code == 200:
                return jsonify(resp.json())
            return jsonify({"ok": False, "msg": f"Huddle failed: {resp.status_code}"}), 500

        if command == "huddle-execute":
            huddle_id = args
            if not huddle_id:
                return jsonify({"ok": False, "msg": "huddle-execute requires huddle_id in args"}), 400
            import requests as _req
            resp = _req.post(f"http://127.0.0.1:19000/office/plans/{huddle_id}/execute", timeout=60)
            if resp.status_code == 200:
                return jsonify(resp.json())
            return jsonify({"ok": False, "msg": f"Execute failed: {resp.status_code}"}), 500

        # 3. Handle Script-based commands
        if command in SCRIPT_MAP:
            script_path = SCRIPT_MAP[command]
            if not os.path.exists(script_path):
                return jsonify({"ok": False, "msg": f"Script not found: {script_path}"}), 500

            # Prepare environment with brew PATH
            env = {**os.environ, "PATH": "/home/linuxbrew/.linuxbrew/bin:" + os.environ.get("PATH", "")}

            # Inject Google API key for wallpaper command if available
            if command == "wallpaper":
                try:
                    auth_profile_path = Path("/home/dustin/.openclaw/agents/main/agent/auth-profiles.json")
                    if auth_profile_path.exists():
                        with open(auth_profile_path, 'r') as f:
                            auth_data = json.load(f)
                            google_profile = auth_data.get("profiles", {}).get("google:default", {})
                            if google_profile.get("key"):
                                env["GOOGLE_API_KEY"] = google_profile["key"]
                                current_app.logger.info("Injected GOOGLE_API_KEY for wallpaper command")
                except Exception as e:
                    current_app.logger.warning(f"Failed to load Google API key for wallpaper: {e}")

            result = subprocess.run(
                ["bash", script_path], capture_output=True, text=True, timeout=60,
                env=env
            )
            return jsonify({"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr})

        # 4. Handle OpenClaw-based commands
        if command in OPENCLAW_CMD_MAP or command == "search":
            message = OPENCLAW_CMD_MAP.get(command, "")
            if command == "search":
                if not args:
                    return jsonify({"ok": False, "msg": "Search requires args"}), 400
                message = f"🔍 search {args}"

            success, output = _dispatch_to_openclaw("rook", message)
            return jsonify({"ok": success, "output": output})

        return jsonify({"ok": False, "msg": f"Unknown command: {command}"}), 400

    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/dispatch/commands", methods=["GET"])
def list_dispatch_commands():
    """List all available command center commands for the UI."""
    commands = [
        {"id": "status", "label": "System Status", "icon": "📊", "category": "system"},
        {"id": "syscheck", "label": "Quick Syscheck", "icon": "🔍", "category": "system"},
        {"id": "restart-services", "label": "Restart Services", "icon": "🔄", "category": "system", "confirm": True},
        {"id": "weather", "label": "Current Weather", "icon": "🌤️", "category": "info"},
        {"id": "email-list", "label": "Email List", "icon": "📧", "category": "info"},
        {"id": "morning-briefing", "label": "Morning Briefing", "icon": "📋", "category": "info"},
        {"id": "huddle", "label": "Start Huddle", "icon": "🤝", "category": "collaboration"},
        {"id": "fullcheck", "label": "Full Report", "icon": "📊", "category": "openclaw"},
        {"id": "self-heal", "label": "Self Heal", "icon": "🔧", "category": "openclaw"},
        {"id": "kb-latest", "label": "KB Latest", "icon": "📚", "category": "openclaw"},
        {"id": "story", "label": "Story Time", "icon": "📝", "category": "openclaw"},
        {"id": "watch-check", "label": "Watch Status", "icon": "👁️", "category": "openclaw"},
        {"id": "wallpaper", "label": "New Wallpaper", "icon": "🎨", "category": "fun"},
    ]
    return jsonify({"ok": True, "commands": commands})
_OPENCLAW_AGENT_MAP = {
    "rook": {"discord_account": "rook", "target": "dustin"},
    "ralph": {"discord_account": "ralph", "target": "dustin"},
    "nova": {"discord_account": "nova", "target": "dustin"},
}


def _dispatch_to_openclaw(agent_name: str, message: str) -> tuple[bool, str]:
    """Send a message to an OpenClaw agent via the openclaw CLI.

    Returns (success, result_message).
    """
    import subprocess

    agent_key = agent_name.lower()
    mapping = _OPENCLAW_AGENT_MAP.get(agent_key)
    if not mapping:
        return False, f"Unknown agent: {agent_name}"

    discord_account = mapping["discord_account"]
    target = mapping["target"]

    # Use Homebrew node (system node 18.x is too old for OpenClaw)
    env = os.environ.copy()
    env["PATH"] = "/home/linuxbrew/.linuxbrew/bin:" + env.get("PATH", "")

    try:
        result = subprocess.run(
            [
                "openclaw", "message", "send",
                "--channel", "discord",
                "--account", discord_account,
                "--target", target,
                "--message", message,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if result.returncode == 0:
            return True, "Dispatched successfully"
        else:
            return False, f"CLI error: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "Dispatch timed out"
    except FileNotFoundError:
        return False, "openclaw CLI not found"
    except Exception as e:
        return False, str(e)


# === Interactive UI Endpoints ===

@bp.route("/agents/<agent_id>/memory", methods=["GET"])
@rate_limit(60, 60)
def get_agent_memory(agent_id):
    """Get memory entries for an agent (from OpenClaw workspace memory/*.md)"""
    try:
        from shared import config as cfg
        import glob

        # Determine workspace directory for this agent
        # For now, use main workspace; future: per-agent workspace from agents-state
        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id), None)
        if not agent:
            return jsonify({"ok": False, "msg": "Agent not found"}), 404

        # Map agentId to workspace (simple heuristic)
        workspace_dir = cfg.OPENCLAW_WORKSPACE
        if agent_id != "star" and agent_id in ["ralph", "nova", "main"]:
            workspace_dir = os.path.join(workspace_dir, "workspace-" + agent_id)

        memory_dir = os.path.join(workspace_dir, "memory")
        if not os.path.isdir(memory_dir):
            # Fallback: return empty list
            return jsonify({"entries": []})

        # Find markdown files
        pattern = os.path.join(memory_dir, "*.md")
        files = glob.glob(pattern)
        entries = []
        for fpath in files:
            try:
                stat = os.stat(fpath)
                filename = os.path.basename(fpath)
                # Extract date from filename if possible (e.g., 2026-03-12.md)
                date_str = filename.replace(".md", "")
                entries.append({
                    "filename": filename,
                    "path": fpath,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "date": date_str
                })
            except Exception:
                continue

        # Sort by date desc (newest first)
        entries.sort(key=lambda e: e.get("date", ""), reverse=True)
        return jsonify({"ok": True, "entries": entries[:50]})  # limit to 50
    except Exception as e:
        current_app.logger.error(f"Get agent memory error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agents/<agent_id>/memory/<path:filename>", methods=["GET"])
@rate_limit(60, 60)
def get_agent_memory_file(agent_id, filename):
    """Get content of a specific memory file"""
    try:
        from shared import config as cfg
        import html

        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id), None)
        if not agent:
            return jsonify({"ok": False, "msg": "Agent not found"}), 404

        workspace_dir = cfg.OPENCLAW_WORKSPACE
        if agent_id != "star" and agent_id in ["ralph", "nova", "main"]:
            workspace_dir = os.path.join(workspace_dir, "workspace-" + agent_id)

        memory_dir = os.path.join(workspace_dir, "memory")
        file_path = os.path.join(memory_dir, filename)

        # Security: ensure path is within memory_dir
        if not os.path.abspath(file_path).startswith(os.path.abspath(memory_dir)):
            return jsonify({"ok": False, "msg": "Invalid path"}), 400

        if not os.path.isfile(file_path):
            return jsonify({"ok": False, "msg": "File not found"}), 404

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Basic HTML escaping for safe display
        content = html.escape(content)
        return jsonify({"ok": True, "content": content, "filename": filename})
    except Exception as e:
        current_app.logger.error(f"Get memory file error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agents/<agent_id>/assign-task", methods=["POST"])
@rate_limit(30, 60)
def assign_task(agent_id):
    """Assign a task to an agent (dispatches via OpenClaw if available)"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400

        task = data.get("task", "").strip()
        if not task:
            return jsonify({"ok": False, "msg": "task required"}), 400

        # Try to dispatch via OpenClaw if available
        # Check if agent has a linked OpenClaw agent ID
        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id), None)
        if not agent:
            return jsonify({"ok": False, "msg": "Agent not found"}), 404

        # For main agent (Star/Rook), we can set state directly and log intention
        # For remote agents, we might push a message via their session
        # Here: update agent's state to show they're working on something
        agent["detail"] = f"Working on: {task[:100]}"
        agent["state"] = "writing"  # default to writing unless specified
        agent["updated_at"] = datetime.now().isoformat()
        agent["area"] = state_to_area(agent["state"])

        # Save and log
        save_agents_state(agents)
        log_agent_action(current_app.logger, "assigned_task", agent_id, detail=task)
        audit_log(
            event="task_assigned",
            actor=request.remote_addr or "unknown",
            target=agent_id,
            details={"task": task},
            ip=request.remote_addr,
        )

        # Dispatch to OpenClaw agent
        agent_name = agent.get("name", "")
        if agent_name:
            dispatch_msg = f"[Task from Dashboard] {task}"
            ok, result = _dispatch_to_openclaw(agent_name, dispatch_msg)
            if not ok:
                current_app.logger.warning(f"OpenClaw dispatch failed for {agent_name}: {result}")

        return jsonify({"ok": True, "msg": f"Task assigned to {agent_name or agent_id}"})
    except Exception as e:
        current_app.logger.error(f"Assign task error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agents/<agent_id>/send-message", methods=["POST"])
@rate_limit(30, 60)
def send_message(agent_id):
    """Send a chat message to an agent"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400

        message = data.get("message", "").strip()
        if not message:
            return jsonify({"ok": False, "msg": "message required"}), 400

        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id), None)
        if not agent:
            return jsonify({"ok": False, "msg": "Agent not found"}), 404

        agent["detail"] = f"Message: {message[:100]}"
        agent["updated_at"] = datetime.now().isoformat()
        save_agents_state(agents)

        log_agent_action(current_app.logger, "message_sent", agent_id, detail=message)
        audit_log(
            event="message_sent",
            actor=request.remote_addr or "unknown",
            target=agent_id,
            details={"message": message},
            ip=request.remote_addr,
        )

        # Dispatch message to OpenClaw agent
        agent_name = agent.get("name", "")
        if agent_name:
            ok, result = _dispatch_to_openclaw(agent_name, message)
            if not ok:
                current_app.logger.warning(f"OpenClaw dispatch failed for {agent_name}: {result}")
                return jsonify({"ok": True, "msg": f"Message logged (dispatch failed: {result})"})

        return jsonify({"ok": True, "msg": "Message sent"})
    except Exception as e:
        current_app.logger.error(f"Send message error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agents/<agent_id>/console", methods=["GET"])
@rate_limit(30, 60)
def get_agent_console(agent_id):
    """Get recent console/log output for an agent"""
    try:
        # For now, tail the main application log and filter by agent if possible
        log_lines = []
        log_file = os.path.join(config.LOG_DIR, "star-office.log")
        if os.path.isfile(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    # Get last 100 lines
                    lines = lines[-100:] if len(lines) > 100 else lines
                    for line in reversed(lines):  # newest first
                        line = line.rstrip("\n")
                        # Simple filter: if line contains agent_id, include it
                        if agent_id.lower() in line.lower():
                            log_lines.append(line)
                        if len(log_lines) >= 25:
                            break
            except Exception as e:
                current_app.logger.warning(f"Could not read log file: {e}")

        return jsonify({"ok": True, "lines": log_lines})
    except Exception as e:
        current_app.logger.error(f"Get console error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agents/<agent_id>/profile", methods=["GET"])
@rate_limit(60, 60)
def get_agent_profile(agent_id):
    """Get comprehensive agent profile with stats, badges, contributions, and skills."""
    try:
        # Resolve agent
        agents = load_agents_state()
        agent = next((a for a in agents if a.get("agentId") == agent_id), None)
        if not agent:
            # Try by name (e.g., "CodeMaster", "Rook")
            agent = next((a for a in agents if a.get("name", "").lower() == agent_id.lower()), None)
            if not agent:
                return jsonify({"ok": False, "msg": "Agent not found"}), 404

        agent_name = agent.get("name", "Unknown")
        growth_agent_name = _map_agent_name_to_growth(agent_name)

        # Load growth data
        growth_dir = Path(config.ROOT_DIR) / "growth"
        contributions_file = growth_dir / "contributions.json"
        agent_scores_file = growth_dir / "agent_scores.json"

        profile = {
            "ok": True,
            "agent": {
                "id": agent.get("agentId"),
                "name": agent_name,
                "state": agent.get("state"),
                "area": agent.get("area"),
                "detail": agent.get("detail"),
                "avatar": agent.get("avatar"),
                "isMain": agent.get("isMain", False),
                "created_at": agent.get("created_at"),
                "lastPushAt": agent.get("lastPushAt"),
                "source": agent.get("source"),
            },
            "stats": {
                "total_contributions": 0,
                "total_points": 0,
                "leaderboard_rank": None,
                "skill_matrix": {},
                "rooms_created": 0,
                "dashboards_created": 0,
                "tasks_completed": 0,
            },
            "recent_contributions": [],
            "badges": [],
        }

        # Load badges for this agent
        try:
            from blueprints.growth_badges import get_agent_badges
            badges = get_agent_badges(growth_agent_name)
            profile["badges"] = badges
            profile["stats"]["badge_points"] = sum(b.get("points", 0) for b in badges)
        except Exception as e:
            current_app.logger.warning(f"Could not load badges: {e}")

        # Load contributions for stats
        if contributions_file.exists():
            try:
                with open(contributions_file) as f:
                    contrib_data = json.load(f)
                all_contribs = contrib_data.get("contributions", [])
                agent_contribs = [c for c in all_contribs if c.get("agent") == growth_agent_name]

                profile["stats"]["total_contributions"] = len(agent_contribs)
                profile["stats"]["total_points"] = sum(c.get("points", 0) for c in agent_contribs)

                # Skill matrix: count by type
                skill_counts = {}
                for c in agent_contribs:
                    ctype = c.get("type", "other")
                    skill_counts[ctype] = skill_counts.get(ctype, 0) + 1
                profile["stats"]["skill_matrix"] = skill_counts

                # Specific counters
                profile["stats"]["rooms_created"] = sum(1 for c in agent_contribs if c.get("type") == "room_created")
                profile["stats"]["dashboards_created"] = sum(1 for c in agent_contribs if c.get("type") in ["dashboard_created", "room_dashboard"])
                profile["stats"]["tasks_completed"] = sum(1 for c in agent_contribs if c.get("type") == "task_completed")

                # Recent contributions (last 10)
                recent = sorted(agent_contribs, key=lambda c: c.get("timestamp", ""), reverse=True)[:10]
                profile["recent_contributions"] = [
                    {
                        "id": c.get("id"),
                        "type": c.get("type"),
                        "room": c.get("room"),
                        "description": c.get("description"),
                        "points": c.get("points"),
                        "timestamp": c.get("timestamp"),
                    }
                    for c in recent
                ]
            except Exception as e:
                current_app.logger.warning(f"Could not load contributions: {e}")

        # Load agent scores and compute leaderboard rank
        if agent_scores_file.exists():
            try:
                with open(agent_scores_file) as f:
                    scores_data = json.load(f)
                scores = scores_data.get("scores", {})
                if scores:
                    sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    for idx, (name, score) in enumerate(sorted_agents, 1):
                        if name == growth_agent_name:
                            profile["stats"]["leaderboard_rank"] = idx
                            profile["stats"]["leaderboard_score"] = score
                            break
            except Exception as e:
                current_app.logger.warning(f"Could not load scores: {e}")

        # Estimate experience level based on contributions
        total_contribs = profile["stats"]["total_contributions"]
        if total_contribs >= 20:
            profile["stats"]["experience"] = "veteran"
        elif total_contribs >= 10:
            profile["stats"]["experience"] = "experienced"
        elif total_contribs >= 5:
            profile["stats"]["experience"] = "regular"
        else:
            profile["stats"]["experience"] = "newcomer"

        # Load authorized skills for this agent
        try:
            all_skills = _load_agent_skills()
            agent_skills = all_skills.get(agent_id, [])
            profile["skills"] = agent_skills
        except Exception as e:
            current_app.logger.warning(f"Could not load skills: {e}")
            profile["skills"] = []

        return jsonify(profile)

    except Exception as e:
        current_app.logger.error(f"Get agent profile error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agents/<agent_id>/skills", methods=["GET"])
@rate_limit(60, 60)
def get_agent_skills(agent_id):
    """Get list of authorized skill IDs for an agent."""
    try:
        all_skills = _load_agent_skills()
        agent_skills = all_skills.get(agent_id, [])
        return jsonify({"ok": True, "skills": agent_skills})
    except Exception as e:
        current_app.logger.error(f"Get agent skills error: {e}")
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/agents/<agent_id>/skills", methods=["POST"])
@rate_limit(30, 60)
def update_agent_skills(agent_id):
    """
    Add or remove a skill from an agent's authorized list.
    Expected JSON: { "skill_id": "daily-wallpaper", "action": "add" | "remove" }
    """
    data = request.get_json()
    if not data or 'skill_id' not in data or 'action' not in data:
        return jsonify({"ok": False, "msg": "Missing skill_id or action"}), 400

    skill_id = data['skill_id']
    action = data['action']

    if action not in ['add', 'remove']:
        return jsonify({"ok": False, "msg": "Invalid action (must be add or remove)"}), 400

    # Basic validation for skill_id
    if not re.match(r'^[\w\-]+$', skill_id):
        return jsonify({"ok": False, "msg": "Invalid skill ID format"}), 400

    try:
        all_skills = _load_agent_skills()
        agent_skills = set(all_skills.get(agent_id, []))

        if action == 'add':
            agent_skills.add(skill_id)
        elif action == 'remove':
            agent_skills.discard(skill_id)

        all_skills[agent_id] = list(agent_skills)
        _save_agent_skills(all_skills)

        log_agent_action(current_app.logger, f"skill_{action}", agent_id, detail=f"Skill {skill_id}")
        audit_log(event=f"skill_{action}", actor=request.remote_addr or "unknown", target=agent_id, details={"skill_id": skill_id})

        return jsonify({"ok": True, "skills": list(agent_skills), "msg": f"Skill {skill_id} {action}ed"})
    except Exception as e:
        current_app.logger.error(f"Update agent skills error: {e}")
        return jsonify({"ok": False, "msg": str(e)}), 500


def _map_agent_name_to_growth(agent_name: str) -> str:
    """Map agents-state name to growth contribution name."""
    mapping = {
        "Star": "Rook",  # Main agent displayed as "Star" but growth uses "Rook"
        "Rook": "Rook",
        "Nova": "Nova",
        "Ralph": "Ralph",
    }
    return mapping.get(agent_name, agent_name)


@bp.route("/agent/<agent_id>", methods=["GET"])
def view_agent_profile(agent_id):
    """Render agent profile HTML page."""
    try:
        # Serve the static HTML file
        template_path = Path(config.FRONTEND_DIR) / "agent-profile.html"
        if not template_path.exists():
            return jsonify({"ok": False, "msg": "Profile template not found"}), 404

        html = template_path.read_text()
        # The HTML uses JavaScript to fetch data from /agents/{agent_id}/profile
        # and dynamically populate itself
        return Response(html, mimetype='text/html')
    except Exception as e:
        current_app.logger.error(f"View agent profile error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500
