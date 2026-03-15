"""Plans, proposals, voting, execution, rooms, and general office routes."""

import json
import os
import re
import subprocess
from datetime import datetime
from flask import jsonify, request, send_from_directory
from pathlib import Path

from config import config as cfg
from logger import get_logger

from . import (
    bp,
    COLLAB_DIR,
    _load_plans,
    _save_plans,
    _get_git_status,
    _git_commit,
    _get_office_context,
    _generate_room_dashboard,
    _generate_furniture_card,
)

log = get_logger(__name__)

# === CM-13: Data Conduit Zones ===

CONDUIT_ZONES = {
    "library": {"label": "Knowledge Base", "color": "#3498db", "tools": ["kb_search", "kb_research"]},
    "mailroom": {"label": "Communications", "color": "#e67e22", "tools": ["sessions_send", "discord"]},
    "cloud": {"label": "External APIs", "color": "#9b59b6", "tools": ["web_fetch", "web_search", "openrouter"]},
    "forge": {"label": "Execution", "color": "#e74c3c", "tools": ["exec", "git"]},
}

_CLAUDE_SESSION_ID = None  # Persistent session for conversation continuity
_CLAUDE_PROJECT_DIR = str(cfg.ROOT_DIR)

_NEWSSITE_DIR = os.path.expanduser("~/.openclaw/newssite")


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
        room_name = plan.get("room", "workspace")

        # Execute based on plan type - ALL types create/update rooms with content
        execution_log.append(f"Executing plan type '{plan['type']}' for room '{room_name}'")

        # Load or create rooms.json
        room_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
        existing_rooms = {"rooms": []}
        if room_file.exists():
            try:
                existing_rooms = json.loads(room_file.read_text())
            except Exception:
                pass

        # Color defaults by plan type
        TYPE_COLORS = {
            "new_room": "#e74c3c", "automation": "#27ae60", "monitoring": "#2980b9",
            "creative": "#8e44ad", "theming": "#e67e22", "reasoning": "#7f8c8d",
            "code_quality": "#9b59b6",
        }

        # Fallback furniture if proposal doesn't include any
        FALLBACK_FURNITURE = {
            "new_room": [{"type": "desk", "x": 0.3, "y": 0.3, "label": "Workstation"},
                         {"type": "lamp", "x": 0.7, "y": 0.3, "label": "Lamp"}],
            "automation": [{"type": "pipeline", "x": 0.3, "y": 0.3, "label": "Pipeline"},
                           {"type": "gear", "x": 0.7, "y": 0.3, "label": "Automation"}],
            "monitoring": [{"type": "dashboard", "x": 0.3, "y": 0.3, "label": "Monitor"},
                           {"type": "gauge", "x": 0.7, "y": 0.3, "label": "Gauge"}],
            "creative": [{"type": "easel", "x": 0.3, "y": 0.3, "label": "Canvas"},
                         {"type": "palette", "x": 0.7, "y": 0.3, "label": "Palette"}],
        }

        plan_type = plan.get("type", "new_room")

        # Use furniture from proposal if available, otherwise use fallback
        plan_furniture = plan.get("furniture")
        if plan_furniture:
            room_config = {"color": TYPE_COLORS.get(plan_type, "#95a5a6"), "furniture": plan_furniture}
        else:
            fallback = FALLBACK_FURNITURE.get(plan_type, FALLBACK_FURNITURE["new_room"])
            room_config = {"color": TYPE_COLORS.get(plan_type, "#95a5a6"), "furniture": fallback}

        # Ensure room exists in rooms.json
        existing_room = next((r for r in existing_rooms.get("rooms", []) if r.get("id") == room_name), None)
        if existing_room:
            # Update existing room with new furniture from this plan
            old_furniture = existing_room.get("furniture", [])
            for item in room_config["furniture"]:
                if not any(f.get("label") == item["label"] for f in old_furniture):
                    old_furniture.append(item)
            existing_room["furniture"] = old_furniture
            existing_room["last_updated_by"] = plan["agent"]
            existing_room["last_updated_at"] = datetime.now().isoformat()
            execution_log.append(f"Room '{room_name}' updated with new furniture")
        else:
            # Create new room
            room_colors = {
                "serverroom": "#e74c3c", "lab": "#9b59b6", "knowledge": "#3498db",
                "archive": "#7f8c8d", "dashboard": "#2ecc71", "breakroom": "#27ae60",
            }
            new_room = {
                "id": room_name,
                "name": plan.get("room_name", room_name.replace("_", " ").replace("-", " ").title()),
                "color": room_colors.get(room_name, room_config.get("color", "#95a5a6")),
                "states": ["idle", "active"],
                "furniture": room_config["furniture"],
                "created_by": plan["agent"],
                "created_at": datetime.now().isoformat(),
                "description": plan["idea"],
                "plan_type": plan_type,
                "connections": ["lobby"],
            }
            existing_rooms["rooms"].append(new_room)
            execution_log.append(f"Room '{room_name}' created with {len(room_config['furniture'])} furniture items")

            # Add bidirectional connection: lobby -> new room
            lobby = next((r for r in existing_rooms["rooms"] if r.get("id") == "lobby"), None)
            if lobby:
                if "connections" not in lobby:
                    lobby["connections"] = []
                if room_name not in lobby["connections"]:
                    lobby["connections"].append(room_name)

        room_file.write_text(json.dumps(existing_rooms, indent=2, ensure_ascii=False))

        # Create room-specific dashboard HTML if it doesn't exist
        rooms_dir = Path(cfg.FRONTEND_DIR) / "rooms" / room_name
        rooms_dir.mkdir(parents=True, exist_ok=True)
        dashboard_file = rooms_dir / "dashboard.html"
        if not dashboard_file.exists():
            dashboard_html = _generate_room_dashboard(room_name, plan, room_config)
            dashboard_file.write_text(dashboard_html)
            execution_log.append(f"Dashboard created: rooms/{room_name}/dashboard.html")

        # Update agents-state to reflect the agent is working on this
        try:
            with open(cfg.AGENTS_STATE_FILE) as f:
                agents_data = json.load(f)
            for agent in agents_data:
                if agent.get("name") == plan.get("agent"):
                    agent["state"] = "writing"
                    agent["detail"] = f"Building: {plan['idea'][:60]}"
                    agent["area"] = "writing"
                    agent["updated_at"] = datetime.now().isoformat()
                    break
            with open(cfg.AGENTS_STATE_FILE, 'w') as f:
                json.dump(agents_data, f, indent=2)
            execution_log.append(f"Agent '{plan['agent']}' state updated to 'writing'")
        except Exception as e:
            execution_log.append(f"Could not update agent state: {e}")

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
    Merges base rooms with dynamic rooms from rooms.json (no duplicates).
    """
    base_rooms = [
        {"id": "workspace", "name": "Work Zone", "color": "#4a90d9", "states": ["writing", "researching", "executing", "syncing"]},
        {"id": "breakroom", "name": "Break Room", "color": "#2ecc71", "states": ["idle"]},
        {"id": "bugarea", "name": "Bug Isolation", "color": "#e74c3c", "states": ["error"]},
    ]

    # Load dynamic rooms from rooms.json
    extra_rooms_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
    if extra_rooms_file.exists():
        try:
            extra = json.loads(extra_rooms_file.read_text())
            extra_list = extra.get("rooms", [])
            # Dynamic rooms override base rooms with same id (they have more data)
            extra_ids = {r["id"] for r in extra_list}
            rooms = [r for r in base_rooms if r["id"] not in extra_ids]
            rooms.extend(extra_list)
        except Exception:
            rooms = base_rooms
    else:
        rooms = base_rooms

    return jsonify({"rooms": rooms})


@bp.route("/office/rooms", methods=["POST"])
def create_room():
    """
    Create a new room definition.
    TODO: Add session-based auth like assets.py: _require_asset_editor_auth()
    """
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


@bp.route("/office/cron-status", methods=["GET"])
def office_cron_status():
    """
    Return cron job status for monitoring.
    Shows configured cron jobs, whether they're currently running,
    and their last execution times.
    """
    cron_jobs = []

    try:
        # Get user crontab entries
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(None, 5)
                    if len(parts) >= 6:
                        schedule = ' '.join(parts[:5])
                        command = parts[5].strip()
                        # Extract script path (before any redirection)
                        script_part = command.split('>>')[0].split('>')[0].strip()
                        # Get job name from script path
                        job_name = script_part.split('/')[-1].split()[0]
                        # Check if currently running
                        running = False
                        try:
                            ps = subprocess.run(['pgrep', '-f', job_name], capture_output=True)
                            running = ps.returncode == 0
                        except:
                            pass

                        # Estimate last run from log file if exists
                        last_run = None
                        status = "unknown"
                        # Try to find the actual log file from the redirection
                        log_file = None
                        if '>>' in command:
                            log_file = command.split('>>')[1].strip().split()[0]
                        elif '>' in command:
                            log_file = command.split('>')[1].strip().split()[0]
                        if log_file:
                            log_path = Path(log_file)
                        else:
                            log_path = Path(cfg.ROOT_DIR) / "logs" / f"{job_name}.log"

                        if log_path.exists():
                            try:
                                mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
                                last_run = mtime.isoformat()
                                # If log modified within last minute and job not running, assume success
                                if (datetime.now() - mtime).total_seconds() < 60:
                                    status = "recent"
                            except:
                                pass

                        cron_jobs.append({
                            "name": job_name,
                            "schedule": schedule,
                            "running": running,
                            "last_run": last_run,
                            "status": status,
                            "command": command[:80] + ("..." if len(command) > 80 else "")
                        })
    except Exception as e:
        log.warning("Cron status check failed", extra={"_error": str(e)})

    return jsonify({"ok": True, "cron_jobs": cron_jobs})


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


@bp.route("/office/replay/session/<agent_id>/<filename>", methods=["GET"])
def replay_session_data(agent_id, filename):
    """
    Read a specific session JSONL file and return parsed events.
    Used by the Ghost Replays time machine UI.
    """
    # Validate agent_id
    if agent_id not in ['main', 'ralph', 'nova']:
        return jsonify({"ok": False, "msg": "Invalid agent ID"}), 400

    # Sanitize filename: prevent path traversal
    if not re.match(r'^[\w\-\.]+\.jsonl$', filename):
        return jsonify({"ok": False, "msg": "Invalid filename"}), 400

    # Construct full path (must reside within agent's sessions directory)
    base_sessions_dir = Path("/home/dustin/.openclaw/agents") / agent_id / "sessions"
    session_path = base_sessions_dir / filename

    # Additional check: ensure resolved path is within base_sessions_dir
    try:
        resolved = session_path.resolve()
        if not str(resolved).startswith(str(base_sessions_dir.resolve())):
            return jsonify({"ok": False, "msg": "Invalid path"}), 400
    except Exception:
        return jsonify({"ok": False, "msg": "Invalid path"}), 400

    if not session_path.exists() or not session_path.is_file():
        return jsonify({"ok": False, "msg": "Session file not found"}), 404

    try:
        # Read entire file (session files are small, < few MB)
        content = session_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.strip().splitlines()

        events = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                continue

        log.info("Session data served", extra={"_agent": agent_id, "_file": filename, "_events": len(events)})
        return jsonify({"ok": True, "events": events, "count": len(events)})
    except Exception as e:
        log.error("Failed to read session", extra={"_error": str(e)})
        return jsonify({"ok": False, "msg": str(e)}), 500


# ── Claude Code terminal ──────────────────────────────────────────────
# Runs the real `claude` CLI (Claude Code) with Opus 4.6 in the project dir.
# Each request runs a single turn via `claude -p` and returns the response.
# Uses --continue to maintain conversation history across turns.

@bp.route("/office/claude-code", methods=["POST"])
def claude_code_endpoint():
    """Run a Claude Code turn with Opus 4.6 in the project directory."""
    global _CLAUDE_SESSION_ID

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({"ok": False, "msg": "invalid json"}), 400

    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "msg": "message required"}), 400

    env = os.environ.copy()
    env["PATH"] = "/home/linuxbrew/.linuxbrew/bin:/home/dustin/.local/bin:" + env.get("PATH", "")
    # Ensure Anthropic API key is available
    if "ANTHROPIC_API_KEY" not in env:
        # Check common locations
        for keyfile in [
            os.path.expanduser("~/.anthropic/api_key"),
            os.path.expanduser("~/.config/anthropic/api_key"),
        ]:
            if os.path.exists(keyfile):
                with open(keyfile) as f:
                    env["ANTHROPIC_API_KEY"] = f.read().strip()
                break

    system_context = (
        "You are Claude Code running inside the OpenClaw Office (CentCom) project. "
        "The project is at ~/openclaw-office. It is a Phaser 3 pixel-art dashboard for AI agents. "
        "Frontend: frontend/index.html (single-page inline Phaser game, ~8000 lines). "
        "Backend: Flask server in backend/ with blueprints (core.py, agents.py, office.py). "
        "Agent sprites in frontend/sprites/. Dashboards in frontend/rooms/. "
        "You can freely read, edit, and create files. The server runs on port 19000. "
        "Keep changes focused and test-aware. This is a live production app."
    )

    cmd = [
        "claude",
        "-p", message,
        "--model", "claude-opus-4-6",
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--append-system-prompt", system_context,
    ]

    # Continue existing session if we have one
    if _CLAUDE_SESSION_ID:
        cmd.extend(["--resume", _CLAUDE_SESSION_ID])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=_CLAUDE_PROJECT_DIR,
            env=env,
        )

        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else ""
            log.warning("Claude Code error", extra={"_stderr": stderr})
            return jsonify({"ok": False, "msg": f"Claude Code error: {stderr}"})

        try:
            output = json.loads(result.stdout)
            reply = output.get("result", "")
            session_id = output.get("session_id", "")
            cost = output.get("total_cost_usd", 0)
            duration = output.get("duration_ms", 0)

            # Save session ID for conversation continuity
            if session_id:
                _CLAUDE_SESSION_ID = session_id

            return jsonify({
                "ok": True,
                "reply": reply,
                "session_id": session_id,
                "cost_usd": round(cost, 4) if cost else 0,
                "duration_ms": duration,
            })
        except json.JSONDecodeError:
            # If JSON parse fails, return raw stdout
            return jsonify({"ok": True, "reply": result.stdout[:2000]})

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "msg": "Claude Code timed out (5 min limit)"}), 504
    except FileNotFoundError:
        return jsonify({"ok": False, "msg": "claude CLI not found — install Claude Code first"}), 500
    except Exception as e:
        log.error("Claude Code error", extra={"_error": str(e)})
        return jsonify({"ok": False, "msg": str(e)}), 500


@bp.route("/office/claude-code/reset", methods=["POST"])
def claude_code_reset():
    """Reset the Claude Code session (start fresh conversation)."""
    global _CLAUDE_SESSION_ID
    _CLAUDE_SESSION_ID = None
    return jsonify({"ok": True, "msg": "Session reset"})


# === News site proxy ===

@bp.route("/office/newssite/")
@bp.route("/office/newssite/<path:filename>")
def newssite(filename="index.html"):
    """Serve the OpenClaw News site files."""
    return send_from_directory(_NEWSSITE_DIR, filename)


# === Hive Mind Context Stream ===

HIVE_MIND_FILE = os.path.join(cfg.ROOT_DIR, "growth", "swarm_context_stream.json")


def log_memory_packet(packet: dict) -> None:
    """Append a new event to the swarm context stream.

    Each packet should contain at minimum a 'type' and 'data' key.
    A timestamp is added automatically.
    """
    packet.setdefault("timestamp", datetime.now().isoformat())

    try:
        if os.path.isfile(HIVE_MIND_FILE):
            with open(HIVE_MIND_FILE, "r") as f:
                stream = json.load(f)
        else:
            stream = {"events": []}

        stream.setdefault("events", []).append(packet)
        stream["last_updated"] = datetime.now().isoformat()

        os.makedirs(os.path.dirname(HIVE_MIND_FILE), exist_ok=True)
        with open(HIVE_MIND_FILE, "w") as f:
            json.dump(stream, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error("Failed to log memory packet", extra={"_error": str(e)})
        raise


@bp.route("/office/log-memory-packet", methods=["POST"])
def http_log_memory_packet():
    """HTTP endpoint for agents to log a memory packet to the Hive-Mind ledger."""
    data = request.get_json(silent=True)
    if not data or "type" not in data or "data" not in data:
        return jsonify({"error": "packet must include 'type' and 'data'"}), 400
    try:
        log_memory_packet(data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/office/get-hive-mind-context", methods=["GET"])
def get_hive_mind_context():
    """Return the swarm context stream JSON."""
    if not os.path.isfile(HIVE_MIND_FILE):
        return jsonify({"events": [], "last_updated": None})
    try:
        with open(HIVE_MIND_FILE, "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        log.error("Failed to read hive mind context", extra={"_error": str(e)})
        return jsonify({"error": str(e)}), 500


# === Hive Mind: Memory Paging (Archive) ===

HIVE_MIND_ARCHIVE_FILE = os.path.join(cfg.ROOT_DIR, "growth", "swarm_context_archive.json")
MEMORY_PAGE_TTL_HOURS = 24


def archive_old_memory() -> dict:
    """Move events older than 24 hours from the context stream to the archive.

    Returns a summary: {"archived": N, "remaining": M}.
    """
    if not os.path.isfile(HIVE_MIND_FILE):
        return {"archived": 0, "remaining": 0}

    try:
        with open(HIVE_MIND_FILE, "r") as f:
            stream = json.load(f)
    except Exception:
        return {"archived": 0, "remaining": 0}

    events = stream.get("events", [])
    if not events:
        return {"archived": 0, "remaining": 0}

    now = datetime.now()
    keep = []
    to_archive = []

    for event in events:
        ts_str = event.get("timestamp")
        if not ts_str:
            keep.append(event)
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            if (now - ts).total_seconds() > MEMORY_PAGE_TTL_HOURS * 3600:
                to_archive.append(event)
            else:
                keep.append(event)
        except (ValueError, TypeError):
            keep.append(event)

    if not to_archive:
        return {"archived": 0, "remaining": len(keep)}

    # Load or create archive
    archive = {"events": [], "last_updated": None}
    if os.path.isfile(HIVE_MIND_ARCHIVE_FILE):
        try:
            with open(HIVE_MIND_ARCHIVE_FILE, "r") as f:
                archive = json.load(f)
        except Exception:
            pass

    archive.setdefault("events", []).extend(to_archive)
    archive["last_updated"] = now.isoformat()

    # Write archive
    os.makedirs(os.path.dirname(HIVE_MIND_ARCHIVE_FILE), exist_ok=True)
    with open(HIVE_MIND_ARCHIVE_FILE, "w") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    # Update stream with only recent events
    stream["events"] = keep
    stream["last_updated"] = now.isoformat()
    with open(HIVE_MIND_FILE, "w") as f:
        json.dump(stream, f, indent=2, ensure_ascii=False)

    log.info("Memory paging: archived %d events, %d remaining", len(to_archive), len(keep))
    return {"archived": len(to_archive), "remaining": len(keep)}


@bp.route("/office/archive-memory", methods=["POST"])
def trigger_archive_memory():
    """HTTP trigger for memory paging — used by the archivist dispatcher."""
    result = archive_old_memory()
    return jsonify(result)
