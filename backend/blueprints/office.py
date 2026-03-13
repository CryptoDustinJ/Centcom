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



def _get_office_context():
    """
    Aggregate comprehensive office state for intelligent planning.
    This data is used by agents during huddles to make context-aware proposals.
    """
    context = {
        "timestamp": datetime.now().isoformat(),
        "agents": {"total": 0, "by_state": {}, "active": 0},
        "tasks": {"total": 0, "open": 0, "in_progress": 0, "completed": 0, "overdue": 0},
        "git": {"branch": None, "dirty": False, "recent_commits": 0},
        "rooms": {"total": 0, "list": []},
        "growth": {"total_contributions": 0, "top_agent": None, "leaderboard": []},
        "system": {"disk_free_gb": 0, "uptime_days": 0}
    }

    # Agent stats
    try:
        with open(cfg.AGENTS_STATE_FILE) as f:
            agents = json.load(f)
        context["agents"]["total"] = len(agents)
        for agent in agents:
            state = agent.get("state", "unknown")
            context["agents"]["by_state"][state] = context["agents"]["by_state"].get(state, 0) + 1
            if state not in ["left", "offline"]:
                context["agents"]["active"] += 1
    except Exception as e:
        log.warning("Failed to load agents for context", extra={"_error": str(e)})

    # Task stats
    try:
        tasks_file = Path(cfg.ROOT_DIR) / "growth" / "tasks.json"
        if tasks_file.exists():
            tasks_data = json.loads(tasks_file.read_text())
            tasks = tasks_data.get("tasks", [])
            context["tasks"]["total"] = len(tasks)
            for task in tasks:
                status = task.get("status", "open")
                if status == "open":
                    context["tasks"]["open"] += 1
                elif status == "in_progress":
                    context["tasks"]["in_progress"] += 1
                elif status == "completed":
                    context["tasks"]["completed"] += 1

            # Check overdue (created >7 days ago and not completed)
            now = datetime.now()
            for task in tasks:
                if task.get("status") not in ["completed", "cancelled"]:
                    created = datetime.fromisoformat(task.get("created_at", now.isoformat()))
                    if (now - created).days > 7:
                        context["tasks"]["overdue"] += 1
    except Exception as e:
        log.warning("Failed to load tasks for context", extra={"_error": str(e)})

    # Git stats
    git_info = _get_git_status()
    context["git"]["branch"] = git_info["branch"]
    context["git"]["dirty"] = git_info["dirty"]
    try:
        repo = Path(cfg.ROOT_DIR)
        recent = subprocess.check_output(
            ["git", "log", "--oneline", "-10"],
            cwd=repo, text=True, stderr=subprocess.DEVNULL
        ).strip().split('\n')
        context["git"]["recent_commits"] = len([c for c in recent if c])
    except Exception:
        pass

    # Rooms
    try:
        rooms_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
        if rooms_file.exists():
            rooms_data = json.loads(rooms_file.read_text())
            rooms = rooms_data.get("rooms", [])
            context["rooms"]["total"] = len(rooms)
            context["rooms"]["list"] = [{"id": r.get("id"), "name": r.get("name")} for r in rooms]
    except Exception as e:
        log.warning("Failed to load rooms for context", extra={"_error": str(e)})

    # Growth leaderboard
    try:
        scores_file = Path(cfg.ROOT_DIR) / "growth" / "agent_scores.json"
        if scores_file.exists():
            scores_data = json.loads(scores_file.read_text())
            scores = scores_data.get("scores", {})
            if scores:
                sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                context["growth"]["top_agent"] = sorted_agents[0][0] if sorted_agents else None
                context["growth"]["leaderboard"] = [{"name": name, "score": score} for name, score in sorted_agents[:5]]
                context["growth"]["total_contributions"] = sum(scores.values())
    except Exception as e:
        log.warning("Failed to load growth data for context", extra={"_error": str(e)})

    # System metrics (simplified)
    try:
        import shutil
        disk = shutil.disk_usage(cfg.ROOT_DIR)
        context["system"]["disk_free_gb"] = round(disk.free / (1024**3), 2)
    except Exception:
        pass

    return context


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

    # Save decision audit record (CM-9)
    try:
        decisions_dir = COLLAB_DIR / "decisions"
        decisions_dir.mkdir(exist_ok=True)
        decision_file = decisions_dir / f"{huddle_id}.json"
        decision_data = {
            "huddle_id": huddle_id,
            "timestamp": huddle["timestamp"],
            "agents": huddle["agents"],
            "context_snapshot": _get_office_context(),
            "proposals": huddle["proposals"],
            "selected_plan": huddle["selected_plan"],
            "status": huddle["status"],
            "execution_log": [],
            "completed": False
        }
        decision_file.write_text(json.dumps(decision_data, indent=2, ensure_ascii=False))
        log.info("Decision audit record saved", extra={"_file": str(decision_file)})
    except Exception as e:
        log.warning("Failed to save decision audit record", extra={"_error": str(e)})

    # Auto-create tasks from high-priority proposals (priority <= 2)
    try:
        tasks_file = Path(cfg.ROOT_DIR) / "growth" / "tasks.json"
        if tasks_file.exists():
            tasks_data = json.loads(tasks_file.read_text())
        else:
            tasks_data = {"tasks": [], "next_id": 1}

        for prop in huddle.get("proposals", []):
            if prop.get("priority", 3) <= 2:
                # Avoid duplicates (same title + assignee)
                if any(t.get("title") == prop.get("idea") and t.get("assignee") == prop.get("agent")
                       for t in tasks_data.get("tasks", [])):
                    continue
                new_task = {
                    "id": f"task_{tasks_data.get('next_id', 1):04d}",
                    "title": prop.get("idea", "Untitled task"),
                    "description": prop.get("details", ""),
                    "room": prop.get("room", "general"),
                    "type": prop.get("type", "improvement"),
                    "status": "open",
                    "points": prop.get("points", 25),
                    "assignee": prop.get("agent"),
                    "assignee_id": prop.get("agentId"),
                    "created_by": "huddle_auto",
                    "created_at": datetime.now().isoformat(),
                    "assigned_at": datetime.now().isoformat(),
                    "completed_at": None,
                    "tags": ["auto", "huddle"],
                    "dependencies": [],
                    "progress": 0,
                }
                tasks_data["tasks"].append(new_task)
                tasks_data["next_id"] = tasks_data.get("next_id", 1) + 1

        tasks_file.write_text(json.dumps(tasks_data, indent=2, ensure_ascii=False))
        log.info("Auto-created tasks from huddle", extra={"_count": len(tasks_data["tasks"])})
    except Exception as e:
        log.warning("Auto-task creation failed", extra={"_error": str(e)})

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

    # Load decision audit record if it exists
    decisions_dir = COLLAB_DIR / "decisions"
    decision_file = decisions_dir / f"{huddle_id}.json"
    decision_data = None
    if decision_file.exists():
        try:
            decision_data = json.loads(decision_file.read_text())
        except Exception:
            pass

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

        # Update decision audit record on success
        if decision_data:
            try:
                decision_data["execution_log"] = execution_log
                decision_data["completed"] = True
                decision_data["completed_at"] = datetime.now().isoformat()
                decision_file.write_text(json.dumps(decision_data, indent=2, ensure_ascii=False))
                log.info("Decision audit record updated with execution", extra={"_file": str(decision_file)})
            except Exception as e:
                log.warning("Failed to update decision audit file", extra={"_error": str(e)})

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

        # Update decision audit with failure
        if decision_data:
            try:
                decision_data["status"] = "failed"
                decision_data["error"] = str(e)
                decision_data["completed"] = True
                decision_data["completed_at"] = datetime.now().isoformat()
                decision_file.write_text(json.dumps(decision_data, indent=2, ensure_ascii=False))
            except Exception:
                pass

        return jsonify({"ok": False, "msg": f"Execution failed: {e}"}), 500


@bp.route("/office/decisions", methods=["GET"])
def list_decisions():
    """
    List decision audit records - full huddle reasoning and outcomes.
    Returns recent huddles with complete agent proposals and execution logs.
    """
    plans = _load_plans()
    decisions = []

    for huddle in plans.get("plans", []):
        decision = {
            "id": huddle["id"],
            "timestamp": huddle["timestamp"],
            "agents": huddle["agents"],
            "status": huddle.get("status", "planning"),
            "selected_plan": huddle.get("selected_plan"),
            "proposals_count": len(huddle.get("proposals", [])),
            "completed": huddle.get("completed", False),
            "proposals": [
                {
                    "agent": p.get("agent"),
                    "agentId": p.get("agentId"),
                    "type": p.get("type"),
                    "room": p.get("room"),
                    "idea": p.get("idea"),
                    "priority": p.get("priority"),
                    "details": p.get("details", ""),
                    "reasoning": p.get("reasoning", ""),
                    "requires": p.get("requires", [])
                }
                for p in huddle.get("proposals", [])
            ],
            "execution_log": huddle.get("execution_log", []) if huddle.get("completed") else []
        }
        decisions.append(decision)

    decisions.sort(key=lambda d: d["timestamp"], reverse=True)

    return jsonify({
        "ok": True,
        "decisions": decisions,
        "total": len(decisions),
        "last_huddle": plans.get("last_huddle")
    })



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

@bp.route("/office/vitals", methods=["GET"])
def office_vitals():
    """
    Return system resource vitals (CPU, RAM, Disk, Network).
    Displayed on floor tiles in the office for at-a-glance monitoring.
    """
    vitals = {
        "cpu_percent": 0,
        "ram_percent": 0,
        "disk_free_gb": 0,
        "network_sent_mb": 0,
        "network_recv_mb": 0,
        "timestamp": datetime.now().isoformat()
    }
    # CPU and RAM - try psutil if available
    try:
        import psutil
        vitals["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        vitals["ram_percent"] = psutil.virtual_memory().percent
    except ImportError:
        # estimate from /proc if Linux
        try:
            with open('/proc/stat', 'r') as f:
                cpu_line = f.readline()
                parts = cpu_line.split()
                idle = int(parts[4])
                total = sum(map(int, parts[1:5]))
                vitals["cpu_percent"] = max(0, 100 - (idle / total * 100)) if total > 0 else 0
        except Exception:
            vitals["cpu_percent"] = 0
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemAvailable:'):
                        avail = int(line.split()[1]) / 1024
                    if line.startswith('MemTotal:'):
                        total = int(line.split()[1]) / 1024
                if 'total' in locals() and 'avail' in locals():
                    vitals["ram_percent"] = round((1 - avail / total) * 100, 1)
        except Exception:
            vitals["ram_percent"] = 0

    # Disk usage
    try:
        import shutil
        disk = shutil.disk_usage(cfg.ROOT_DIR)
        vitals["disk_free_gb"] = round(disk.free / (1024**3), 2)
        vitals["disk_percent"] = round(disk.used / disk.total * 100, 1)
    except Exception:
        vitals["disk_free_gb"] = 0
        vitals["disk_percent"] = 0

    # Network stats
    try:
        net_stats = {}
        with open('/proc/net/dev', 'r') as f:
            for line in f:
                if ':' in line:
                    iface, stats = line.split(':')
                    iface = iface.strip()
                    stats = stats.split()
                    if iface not in ('lo',):
                        net_stats[iface] = {
                            'rx': int(stats[0]),
                            'tx': int(stats[8])
                        }
        total_rx = sum(n['rx'] for n in net_stats.values()) if net_stats else 0
        total_tx = sum(n['tx'] for n in net_stats.values()) if net_stats else 0
        vitals["network_rx_mb"] = round(total_rx / (1024*1024), 2)
        vitals["network_tx_mb"] = round(total_tx / (1024*1024), 2)
    except Exception:
        vitals["network_rx_mb"] = 0
        vitals["network_tx_mb"] = 0

    # Health status
    vitals["status"] = "healthy"
    if vitals["cpu_percent"] > 80 or vitals["ram_percent"] > 85 or vitals.get("disk_percent", 0) > 90:
        vitals["status"] = "warning"
    if vitals["cpu_percent"] > 95 or vitals["ram_percent"] > 95 or vitals.get("disk_percent", 0) > 98:
        vitals["status"] = "critical"

    return jsonify({"ok": True, "vitals": vitals})


@bp.route("/office/incidents", methods=["GET"])
def office_incidents():
    """
    Return current incident status based on recent audit log entries.
    Used to trigger visual alarms in the office.
    """
    incidents = {
        "status": "healthy",
        "level": 0,
        "recent_failures": 0,
        "rate_limit_hits": 0,
        "details": [],
        "timestamp": datetime.now().isoformat()
    }

    try:
        audit_log_path = Path(cfg.ROOT_DIR) / "audit.log"
        if not audit_log_path.exists():
            return jsonify({"ok": True, "incidents": incidents})

        import time
        now = time.time()
        recent_window = 300
        failure_count = 0
        rate_limit_count = 0
        details = []

        with open(audit_log_path, 'r') as f:
            lines = f.readlines()[-100:]

        for line in lines:
            try:
                import json as js
                entry = js.loads(line)
                ts = entry.get('timestamp')
                if not ts:
                    continue
                log_time = datetime.fromisoformat(ts).timestamp()
                if now - log_time > recent_window:
                    continue

                event = entry.get('event', '')
                details.append(f"{event} at {ts}")

                if 'error' in event or 'failed' in event:
                    failure_count += 1
                if 'rate_limit' in event or '429' in event:
                    rate_limit_count += 1
            except Exception:
                continue

        incidents["recent_failures"] = failure_count
        incidents["rate_limit_hits"] = rate_limit_count
        incidents["details"] = details[:10]

        if rate_limit_count > 0 or failure_count >= 5:
            incidents["status"] = "critical"
            incidents["level"] = 2
        elif failure_count >= 2:
            incidents["status"] = "warning"
            incidents["level"] = 1

    except Exception as e:
        log.warning("Incident check failed", extra={"_error": str(e)})

    return jsonify({"ok": True, "incidents": incidents})


@bp.route("/office/briefing-status", methods=["GET"])
def briefing_status():
    """Check if a fresh briefing is available for the podium."""
    briefing_file = Path(cfg.ROOT_DIR) / "growth" / "latest_briefing.json"
    if not briefing_file.exists():
        return jsonify({"ok": True, "fresh": False})

    try:
        data = json.loads(briefing_file.read_text())
        gen_date = datetime.fromisoformat(data.get("generated_at", "2000-01-01")).date()
        today = datetime.now().date()
        fresh = gen_date == today
        return jsonify({"ok": True, "fresh": fresh, "generated_at": data.get("generated_at")})
    except Exception:
        return jsonify({"ok": True, "fresh": False})


@bp.route("/office/latest-briefing", methods=["GET"])
def latest_briefing():
    """Return the latest board meeting briefing text for the podium."""
    briefing_file = Path(cfg.ROOT_DIR) / "growth" / "latest_briefing.json"
    default_briefing = {
        "text": "Good morning! The office is operational. No new updates.",
        "generated_at": datetime.now().isoformat()
    }

    if briefing_file.exists():
        try:
            data = json.loads(briefing_file.read_text())
            return jsonify({"ok": True, "briefing": data})
        except Exception:
            pass

    return jsonify({"ok": True, "briefing": default_briefing})


@bp.route("/office/generate-briefing", methods=["POST"])
def generate_briefing():
    """Generate a new board meeting briefing using office context."""
    context = _get_office_context()
    lines = [
        "Board Meeting Briefing",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Active agents: {context['agents']['active']} total, {context['agents']['total']} registered",
        f"Tasks: {context['tasks']['open']} open, {context['tasks']['overdue']} overdue",
        f"Git: On branch '{context['git']['branch']}' with {context['git']['recent_commits']} recent commits",
        f"Disk space: {context['system']['disk_free_gb']} GB free",
        f"Top agent: {context['growth']['top_agent'] or 'none'}",
        "Let's make today productive!"
    ]
    text = "\n".join(lines)

    briefing = {
        "text": text,
        "generated_at": datetime.now().isoformat(),
        "context": context
    }

    briefing_file = Path(cfg.ROOT_DIR) / "growth" / "latest_briefing.json"
    briefing_file.write_text(json.dumps(briefing, indent=2, ensure_ascii=False))

    log.info("Board briefing generated")
    return jsonify({"ok": True, "briefing": briefing})


@bp.route("/office/huddle/emergency", methods=["POST"])
def emergency_huddle():
    """Trigger an immediate huddle (bypass any normal scheduling)."""
    return start_huddle()


@bp.route("/office/data/context.json", methods=["GET"])
def get_context_data():
    """Return full office context snapshot for agent planning."""
    context = _get_office_context()
    return jsonify({"ok": True, "context": context})


# === CM-12: Context Pressure Data ===

@bp.route("/office/context-pressure", methods=["GET"])
def context_pressure():
    """
    Return context usage estimates per agent.
    In future, this will pull real context window stats from OpenClaw.
    For now, estimates based on agent state and recent activity.
    """
    try:
        with open(cfg.AGENTS_STATE_FILE) as f:
            agents = json.load(f)
    except Exception:
        return jsonify({"ok": True, "agents": []})

    pressure_data = []
    for agent in agents:
        if agent.get("state") == "left":
            continue
        state = agent.get("state", "idle")
        # Estimate context usage by state
        base_usage = {
            "executing": 85, "researching": 80, "writing": 65,
            "syncing": 40, "idle": 15, "error": 50
        }
        usage = base_usage.get(state, 20)
        pressure_data.append({
            "agentId": agent.get("agentId"),
            "name": agent.get("name"),
            "state": state,
            "context_usage_pct": usage,
        })

    return jsonify({"ok": True, "agents": pressure_data})


# === CM-13: Data Conduit Zones ===

CONDUIT_ZONES = {
    "library": {"label": "Knowledge Base", "color": "#3498db", "tools": ["kb_search", "kb_research"]},
    "mailroom": {"label": "Communications", "color": "#e67e22", "tools": ["sessions_send", "discord"]},
    "cloud": {"label": "External APIs", "color": "#9b59b6", "tools": ["web_fetch", "web_search", "openrouter"]},
    "forge": {"label": "Execution", "color": "#e74c3c", "tools": ["exec", "git"]},
}

@bp.route("/office/conduits", methods=["GET"])
def get_conduits():
    """Return data conduit zone definitions for frontend visualization."""
    return jsonify({"ok": True, "conduits": CONDUIT_ZONES})


@bp.route("/office/conduits/activity", methods=["GET"])
def conduit_activity():
    """
    Return recent tool call activity mapped to conduit zones.
    Reads audit log to find recent tool invocations.
    """
    activity = {zone: {"calls": 0, "last_call": None} for zone in CONDUIT_ZONES}

    try:
        audit_log_path = Path(cfg.ROOT_DIR) / "audit.log"
        if audit_log_path.exists():
            import time as _time
            now = _time.time()
            window = 300  # 5 minutes

            with open(audit_log_path, 'r') as f:
                lines = f.readlines()[-200:]

            for line in lines:
                try:
                    entry = json.loads(line)
                    ts = entry.get('timestamp')
                    if not ts:
                        continue
                    log_time = datetime.fromisoformat(ts).timestamp()
                    if now - log_time > window:
                        continue

                    event = entry.get('event', '')
                    details = entry.get('details', {})
                    tool = details.get('tool', '') or event

                    # Map to conduit zone
                    for zone_id, zone_def in CONDUIT_ZONES.items():
                        if any(t in tool.lower() for t in zone_def["tools"]):
                            activity[zone_id]["calls"] += 1
                            activity[zone_id]["last_call"] = ts
                            break
                except Exception:
                    continue
    except Exception as e:
        log.warning("Conduit activity scan failed", extra={"_error": str(e)})

    return jsonify({"ok": True, "activity": activity})


# === CM-17: Skill Supply Closet ===

@bp.route("/skills/list", methods=["GET"])
def list_skills():
    """
    List available skills from OpenClaw workspace skills directory.
    Each skill is a directory with a run script or manifest.
    """
    skills = []
    skills_dirs = [
        Path("/home/dustin/.openclaw/workspace/skills"),
        Path("/home/dustin/.openclaw/workspace-ralph/skills"),
        Path("/home/dustin/.openclaw/workspace-nova/skills"),
    ]

    for skills_dir in skills_dirs:
        if not skills_dir.exists():
            continue
        agent_name = "Rook"
        if "ralph" in str(skills_dir):
            agent_name = "Ralph"
        elif "nova" in str(skills_dir):
            agent_name = "Nova"

        for item in skills_dir.iterdir():
            if item.is_dir():
                skill_info = {
                    "id": item.name,
                    "name": item.name.replace("-", " ").replace("_", " ").title(),
                    "agent": agent_name,
                    "path": str(item),
                    "has_run_script": (item / "run.sh").exists() or (item / "run_wallpaper.sh").exists(),
                    "has_manifest": (item / "manifest.json").exists() or (item / "skill.json").exists(),
                }
                # Try to read manifest for description
                for mf in ["manifest.json", "skill.json"]:
                    manifest_path = item / mf
                    if manifest_path.exists():
                        try:
                            manifest = json.loads(manifest_path.read_text())
                            skill_info["description"] = manifest.get("description", "")
                            skill_info["version"] = manifest.get("version", "")
                            break
                        except Exception:
                            pass
                skills.append(skill_info)

    return jsonify({"ok": True, "skills": skills, "total": len(skills)})


# === CM-15: Ghost Replay Data Capture ===

@bp.route("/office/replay/sessions", methods=["GET"])
def replay_sessions():
    """
    List available session replays with timestamps.
    Returns metadata about recorded agent sessions for the time machine.
    """
    sessions = []
    openclaw_agents_dir = Path("/home/dustin/.openclaw/agents")
    if not openclaw_agents_dir.exists():
        return jsonify({"ok": True, "sessions": []})

    agent_names = {"main": "Rook", "ralph": "Ralph", "nova": "Nova"}

    for agent_id, display_name in agent_names.items():
        sessions_dir = openclaw_agents_dir / agent_id / "sessions"
        if not sessions_dir.exists():
            continue
        for session_file in sorted(sessions_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:5]:
            stat = session_file.stat()
            sessions.append({
                "agent": display_name,
                "agent_id": agent_id,
                "filename": session_file.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            })

    sessions.sort(key=lambda s: s["modified"], reverse=True)
    return jsonify({"ok": True, "sessions": sessions[:15]})

