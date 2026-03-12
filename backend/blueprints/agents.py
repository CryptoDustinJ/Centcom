#!/usr/bin/env python3
"""Agents blueprint: multi-agent management, joins, pushes, approvals."""

from flask import Blueprint, jsonify, request, session, current_app
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
from validation import validate_agent_name, validate_state_detail, validate_invite_code, validate_agent_id, ValidationError as ValidationErrorExc
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


@bp.route("/dispatch", methods=["POST"])
@rate_limit(20, 60)
def dispatch():
    """Execute dashboard commands (restart-services, status, etc.)"""
    import subprocess

    data = request.get_json() or {}
    command = data.get("command", "").strip()
    if not command:
        return jsonify({"ok": False, "msg": "command required"}), 400

    env = os.environ.copy()
    env["PATH"] = "/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin"

    try:
        if command == "restart-services":
            result = subprocess.run(
                ["bash", "/home/dustin/rook.sh"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            ok = result.returncode == 0
            return jsonify({"ok": ok, "msg": result.stdout[:300] if ok else result.stderr[:300]})

        elif command == "status":
            result = subprocess.run(
                ["openclaw", "status"],
                capture_output=True, text=True, timeout=15, env=env,
            )
            return jsonify({"ok": True, "msg": result.stdout[:500]})

        else:
            return jsonify({"ok": False, "msg": f"Unknown command: {command}"}), 400

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "msg": f"{command} timed out"}), 504
    except Exception as e:
        current_app.logger.error(f"Dispatch error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


# === OpenClaw Dispatch Helpers ===

# Map agent names/IDs to OpenClaw agent IDs and Discord accounts
_MAIN_CHANNEL = "483749214568972290"

_OPENCLAW_AGENT_MAP = {
    "rook": {"oc_agent": "main", "discord_account": "default", "target": _MAIN_CHANNEL},
    "ralph": {"oc_agent": "ralph", "discord_account": "default", "target": "1476410277862834359"},  # DM via Rook→Ralph bot
    "nova": {"oc_agent": "nova", "discord_account": "default", "target": _MAIN_CHANNEL},
    "codemaster": {"oc_agent": "codemaster", "discord_account": "default", "target": _MAIN_CHANNEL},
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
