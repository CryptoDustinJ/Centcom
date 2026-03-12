#!/usr/bin/env python3
"""Office Collaboration Blueprint - Agents working together to improve their office."""

import json
import os
import subprocess
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from pathlib import Path

from config import config as cfg
from logger import get_logger
# Auth not yet implemented; will use session-based asset drawer auth pattern from assets.py

log = get_logger(__name__)
bp = Blueprint('office', __name__)

# Office state file for collaboration plans
COLLAB_DIR = Path(cfg.ROOT_DIR) / "collaboration"
COLLAB_DIR.mkdir(exist_ok=True)
PLANS_FILE = COLLAB_DIR / "plans.json"
AGENT_PROFILES_FILE = COLLAB_DIR / "agent_profiles.json"


def _load_plans():
    """Load collaboration plans."""
    if PLANS_FILE.exists():
        try:
            return json.loads(PLANS_FILE.read_text())
        except Exception:
            pass
    return {"plans": [], "last_huddle": None, "version": 1}


def _save_plans(data):
    """Save collaboration plans."""
    PLANS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _load_agent_profiles():
    """Load agent personalities and contributions."""
    if AGENT_PROFILES_FILE.exists():
        try:
            return json.loads(AGENT_PROFILES_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_agent_profiles(data):
    """Save agent profiles."""
    AGENT_PROFILES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _get_git_status():
    """Get current git status of the office repo."""
    try:
        repo = Path(cfg.ROOT_DIR)
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=repo, text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo, text=True, stderr=subprocess.DEVNULL
        ).strip()
        return {"branch": branch, "dirty": bool(status), "status": status}
    except Exception as e:
        log.warning("git status failed", extra={"_error": str(e)})
        return {"branch": None, "dirty": False, "status": ""}


def _git_commit(message: str):
    """Create a git commit with the given message."""
    try:
        repo = Path(cfg.ROOT_DIR)
        subprocess.check_call(["git", "add", "-A"], cwd=repo)
        subprocess.check_call(
            ["git", "commit", "-m", message],
            cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError as e:
        log.warning("git commit failed", extra={"_error": str(e)})
        return False


@bp.route("/office/huddle/start", methods=["POST"])
def start_huddle():
    """
    Trigger a daily collaboration huddle.
    Agents will propose improvements and plan the next changes.
    """
    # Check admin auth (optional for now, can be enabled)
    # require_auth()

    plans = _load_plans()
    agent_profiles = _load_agent_profiles()

    # Get all active agents from agents-state.json
    try:
        with open(cfg.AGENTS_STATE_FILE) as f:
            agents = json.load(f)
    except Exception as e:
        log.error("Failed to load agents state", extra={"_error": str(e)})
        return jsonify({"ok": False, "msg": "Cannot load agents"}), 500

    # Filter to connected, non-main agents (they're the collaborators)
    collaborators = [
        a for a in agents
        if not a.get("isMain") and a.get("state") != "left"
    ]

    huddle_id = f"huddle_{datetime.now().strftime('%Y%m%d_%H%M')}"
    huddle = {
        "id": huddle_id,
        "timestamp": datetime.now().isoformat(),
        "agents": [a["name"] for a in collaborators],
        "status": "planning",
        "proposals": [],
        "selected_plan": None,
        "execution_log": [],
        "completed": False
    }

    # For now, generate placeholder proposals based on agent personalities
    # In a full implementation, we'd query each agent via sessions_send
    for agent in collaborators:
        # Read agent's workspace to understand their capabilities
        agent_workspace = Path(f"/home/dustin/.openclaw/workspace-{agent['name'].lower()}")
        proposal = {
            "agent": agent["name"],
            "agentId": agent["agentId"],
            "type": "room_improvement",
            "room": "workspace",  # Default - could be determined by agent state
            "idea": f"{agent['name']} suggests improving the office environment",
            "priority": 2,
            "requires": ["exec", "git"],
            "status": "pending"
        }

        # Simple personality-based proposals (can be expanded)
        if agent["name"] == "Rook":
            proposal.update({
                "type": "new_room",
                "room": "serverroom",
                "idea": "Add a server room with live system metrics dashboard",
                "priority": 1,
                "details": "Create a new room displaying gateway/node status, GPU usage, disk space"
            })
        elif agent["name"] == "Ralph":
            proposal.update({
                "type": "automation",
                "room": "workspace",
                "idea": "Add automated syscheck pipeline visualization",
                "priority": 1,
                "details": "Display recent syscheck runs, alerts, and system health trends"
            })
        elif agent["name"] == "Nova":
            proposal.update({
                "type": "creative",
                "room": "breakroom",
                "idea": "Add story corner with generated sci-fi snippets",
                "priority": 2,
                "details": "Show latest sci-fi story and storybook database stats"
            })
        elif agent["name"] == "Claude":
            proposal.update({
                "type": "reasoning",
                "room": "archive",
                "idea": "Create reasoning logs wall for complex decisions",
                "priority": 2,
                "details": "Display recent deep analysis threads and architectural decisions"
            })
        elif agent["name"] == "CodeMaster":
            proposal.update({
                "type": "code_quality",
                "room": "lab",
                "idea": "Add code quality metrics dashboard",
                "priority": 1,
                "details": "Show test coverage, lint results, and recent PR stats"
            })

        huddle["proposals"].append(proposal)

    # Simple voting: sum of priorities, pick highest
    if huddle["proposals"]:
        # Sort by priority (lower = higher priority)
        sorted_proposals = sorted(huddle["proposals"], key=lambda p: p["priority"])
        selected = sorted_proposals[0]
        huddle["selected_plan"] = selected
        huddle["status"] = "approved"

    plans["plans"].append(huddle)
    plans["last_huddle"] = huddle["timestamp"]
    _save_plans(plans)

    log.info("Office huddle started", extra={"_huddle_id": huddle_id, "_agents": len(collaborators)})

    return jsonify({
        "ok": True,
        "huddle_id": huddle_id,
        "agents": [a["name"] for a in collaborators],
        "proposals": huddle["proposals"],
        "selected_plan": selected,
        "msg": f"Huddle started with {len(collaborators)} agents. Plan: {selected['idea']}"
    })


@bp.route("/office/plans", methods=["GET"])
def list_plans():
    """List all collaboration plans."""
    plans = _load_plans()
    return jsonify(plans)


@bp.route("/office/plans/<huddle_id>/execute", methods=["POST"])
def execute_plan(huddle_id):
    """
    Execute the selected plan from a huddle.
    This applies the changes to the office (create rooms, commit files, etc.)
    """
    plans = _load_plans()
    huddle = next((p for p in plans["plans"] if p["id"] == huddle_id), None)

    if not huddle:
        return jsonify({"ok": False, "msg": "Huddle not found"}), 404

    if huddle["completed"]:
        return jsonify({"ok": False, "msg": "Huddle already completed"}), 400

    if not huddle.get("selected_plan"):
        return jsonify({"ok": False, "msg": "No plan selected"}), 400

    plan = huddle["selected_plan"]
    execution_log = []

    try:
        # Execute based on plan type
        if plan["type"] == "new_room":
            # Create a new room definition in the frontend assets
            room_name = plan["room"]
            execution_log.append(f"Creating new room: {room_name}")

            # Load or create rooms.json
            room_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
            existing_rooms = {"rooms": []}
            if room_file.exists():
                try:
                    existing_rooms = json.loads(room_file.read_text())
                except Exception:
                    pass

            # Check if room already exists
            if any(r.get("id") == room_name for r in existing_rooms.get("rooms", [])):
                execution_log.append(f"Room '{room_name}' already exists, skipping creation")
            else:
                # Define the new room with appropriate color and properties
                room_colors = {
                    "serverroom": "#e74c3c",  # Red for server
                    "lab": "#9b59b6",         # Purple for lab
                    "knowledge": "#3498db",   # Blue for knowledge
                    "archive": "#7f8c8d",     # Gray for archive
                    "dashboard": "#2ecc71",   # Green for dashboard
                }
                new_room = {
                    "id": room_name,
                    "name": plan.get("room_name", room_name.title()),
                    "color": room_colors.get(room_name, "#95a5a6"),
                    "states": plan.get("states", ["idle"]),
                    "background": plan.get("background"),
                    "furniture": plan.get("furniture", []),
                    "created_by": plan["agent"],
                    "created_at": datetime.now().isoformat(),
                    "description": plan["idea"]
                }
                existing_rooms["rooms"].append(new_room)
                room_file.write_text(json.dumps(existing_rooms, indent=2, ensure_ascii=False))
                execution_log.append(f"Room '{room_name}' added to rooms.json")

        elif plan["type"] == "automation":
            execution_log.append("Adding automation improvement")
            # Could create new scripts, update monitoring, etc.

        elif plan["type"] == "creative":
            execution_log.append("Adding creative content")
            # Could generate assets, update memos, etc.

        elif plan["type"] == "reasoning":
            execution_log.append("Adding reasoning content")

        elif plan["type"] == "code_quality":
            execution_log.append("Adding code quality metrics")

        # Commit changes if any git modifications exist
        git_status = _get_git_status()
        if git_status["dirty"]:
            commit_msg = f"Office collaboration: {plan['idea']} (by {plan['agent']})"
            if _git_commit(commit_msg):
                execution_log.append(f"Comitted changes: {commit_msg}")
            else:
                execution_log.append("No changes to commit")
        else:
            execution_log.append("No file changes detected")

        huddle["status"] = "completed"
        huddle["execution_log"] = execution_log
        huddle["completed"] = True
        huddle["completed_at"] = datetime.now().isoformat()
        _save_plans(plans)

        log.info("Office plan executed", extra={"_huddle_id": huddle_id, "_plan_type": plan["type"]})

        return jsonify({
            "ok": True,
            "huddle_id": huddle_id,
            "execution_log": execution_log,
            "msg": f"Plan executed: {plan['idea']}"
        })

    except Exception as e:
        log.error("Plan execution failed", extra={"_error": str(e), "_huddle_id": huddle_id})
        huddle["status"] = "failed"
        huddle["error"] = str(e)
        _save_plans(plans)
        return jsonify({"ok": False, "msg": f"Execution failed: {e}"}), 500


@bp.route("/office/rooms", methods=["GET"])
def list_rooms():
    """
    List available rooms in the office.
    Currently defined rooms map to zones in the frontend.
    """
    rooms = [
        {"id": "workspace", "name": "Work Zone", "color": "#4a90d9", "states": ["writing", "researching", "executing", "syncing"]},
        {"id": "breakroom", "name": "Break Room", "color": "#2ecc71", "states": ["idle"]},
        {"id": "bugarea", "name": "Bug Isolation", "color": "#e74c3c", "states": ["error"]},
    ]

    # Check for additional room configs in assets
    # Could load from a rooms.json if it exists
    extra_rooms_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
    if extra_rooms_file.exists():
        try:
            extra = json.loads(extra_rooms_file.read_text())
            rooms.extend(extra.get("rooms", []))
        except Exception:
            pass

    return jsonify({"rooms": rooms})


@bp.route("/office/rooms", methods=["POST"])
def create_room():
    """
    Create a new room definition.
    TODO: Add session-based auth like assets.py: _require_asset_editor_auth()
    """
    # if _require_asset_editor_auth():
    #     return _require_asset_editor_auth()

    data = request.get_json()
    if not data or "room_id" not in data or "name" not in data:
        return jsonify({"ok": False, "msg": "Missing room_id or name"}), 400

    room_id = data["room_id"]
    room_def = {
        "id": room_id,
        "name": data["name"],
        "color": data.get("color", "#9b59b6"),
        "states": data.get("states", ["idle"]),
        "background": data.get("background"),
        "furniture": data.get("furniture", []),
        "created_by": data.get("created_by", "collaboration")
    }

    # Save to rooms.json in frontend dir
    rooms_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
    existing = {"rooms": []}
    if rooms_file.exists():
        try:
            existing = json.loads(rooms_file.read_text())
        except Exception:
            pass

    # Avoid duplicates
    if any(r["id"] == room_id for r in existing["rooms"]):
        return jsonify({"ok": False, "msg": f"Room {room_id} already exists"}), 409

    existing["rooms"].append(room_def)
    rooms_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

    log.info("New room created", extra={"_room_id": room_id, "_room_name": room_def["name"]})

    return jsonify({"ok": True, "room": room_def, "msg": f"Room '{room_id}' created"})


@bp.route("/office/status", methods=["GET"])
def office_status():
    """Get current office collaboration status."""
    plans = _load_plans()
    last_huddle = plans.get("last_huddle")

    # Count active collaborators
    try:
        with open(cfg.AGENTS_STATE_FILE) as f:
            agents = json.load(f)
        active_collaborators = [
            a for a in agents
            if not a.get("isMain") and a.get("state") != "left"
        ]
    except Exception:
        active_collaborators = []

    return jsonify({
        "ok": True,
        "last_huddle": last_huddle,
        "total_huddles": len(plans["plans"]),
        "active_collaborators": len(active_collaborators),
        "collaborator_names": [a["name"] for a in active_collaborators]
    })
