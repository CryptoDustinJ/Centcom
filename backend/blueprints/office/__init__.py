#!/usr/bin/env python3
"""Office Collaboration Blueprint package.

Registers all sub-routes from huddles, collaboration, and forge modules.
Maintains backward compatibility: `from blueprints.office import bp` still works.
"""

import json
import os
import re
import subprocess
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app, send_from_directory
from pathlib import Path

from config import config as cfg
from logger import get_logger

log = get_logger(__name__)
bp = Blueprint('office', __name__)

# ── Shared state ──────────────────────────────────────────────────────────────

COLLAB_DIR = Path(cfg.ROOT_DIR) / "collaboration"
COLLAB_DIR.mkdir(exist_ok=True)
PLANS_FILE = COLLAB_DIR / "plans.json"
AGENT_PROFILES_FILE = COLLAB_DIR / "agent_profiles.json"


# ── Shared helpers ────────────────────────────────────────────────────────────

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


def _furniture_icon(item_type):
    """Map furniture/plan type to emoji icon."""
    icons = {
        "server_rack": "🖥️", "monitor": "📊", "terminal": "💻", "pipeline": "⚙️",
        "chart": "📈", "alert_board": "🚨", "dashboard": "📊", "gauge": "🎯",
        "log_stream": "📜", "bookshelf": "📚", "easel": "🎨", "speaker": "🔊",
        "palette": "🎨", "preview": "👁️", "whiteboard": "📝", "archive": "🗄️",
        "linter": "🔍", "coverage": "✅", "pr_board": "📋",
        "new_room": "🏠", "automation": "⚙️", "monitoring": "📊", "creative": "🎨",
        "theming": "🎨", "reasoning": "🧠", "code_quality": "🔍",
        "cron_board": "⏰", "coffee": "☕", "plant": "🌿", "trophy": "🏆",
        "clock": "🕐", "lamp": "💡", "printer": "🖨️", "phone": "📞",
        "calendar": "📅", "tv": "📺", "radio": "📻", "globe": "🌐",
        "toolbox": "🧰", "shield": "🛡️", "telescope": "🔭", "microscope": "🔬",
        "beaker": "🧪", "satellite": "📡", "battery": "🔋", "plug": "🔌",
        "wrench": "🔧", "hammer": "🔨", "gear": "⚙️", "magnet": "🧲",
        "bulb": "💡", "podium": "🎤", "water_cooler": "🚰", "couch": "🛋️",
        "desk": "🪑", "filing_cabinet": "🗃️", "safe": "🔐", "map": "🗺️",
        "compass": "🧭",
        "anvil": "🔨", "deploy_pipe": "🚀", "artifact_shelf": "📦",
    }
    return icons.get(item_type, "📦")


def _generate_furniture_card(item, color):
    """Generate a single furniture card HTML."""
    icon = _furniture_icon(item.get("type", ""))
    label = item.get("label", "Unknown")
    item_type = item.get("type", "")

    # Custom data panel based on furniture type
    if item_type == "cron_board":
        data_panel = """<div class="data-panel">
          <span class="cron-running">--</span> running |
          <span class="cron-failed">--</span> failed |
          <span class="cron-last">--</span>
        </div>"""
    elif item_type == "anvil":
        data_panel = """<div class="data-panel">
          <span class="forge-build-status">--</span> |
          <span class="forge-build-duration">--</span>
        </div>"""
    elif item_type == "deploy_pipe":
        data_panel = """<div class="data-panel">
          <span class="forge-deploy-target">--</span> |
          <span class="forge-deploy-status">--</span>
        </div>"""
    elif item_type == "artifact_shelf":
        data_panel = """<div class="data-panel">
          <span class="forge-artifact-count">--</span> artifacts |
          <span class="forge-artifact-size">--</span>
        </div>"""
    else:
        data_panel = """<div class="data-panel">
          <span class="data-value-cpu">--</span> CPU |
          <span class="data-value-ram">--</span> RAM |
          <span class="data-value-disk">--</span> Disk
        </div>"""

    return f"""<div class="furniture-card">
      <div class="icon">{icon}</div>
      <h3>{label}</h3>
      {data_panel}
    </div>"""


def _generate_room_dashboard(room_name, plan, room_config):
    """Generate a room-specific dashboard HTML page."""
    furniture_html = ""
    for item in room_config.get("furniture", []):
        furniture_html += f'<div class="furniture-item" style="left:{item["x"]*100}%;top:{item["y"]*100}%">'
        furniture_html += f'<span class="furniture-icon">{_furniture_icon(item["type"])}</span>'
        furniture_html += f'<span class="furniture-label">{item["label"]}</span>'
        furniture_html += '</div>\n'

    color = room_config.get("color", "#666")
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{room_name.title()} - Star Office</title>
<style>
  body {{ font-family: 'ArkPixel', monospace; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }}
  .room-header {{ background: {color}22; border: 2px solid {color}; border-radius: 12px; padding: 16px 24px; margin-bottom: 20px; }}
  .room-header h1 {{ margin: 0; color: {color}; font-size: 24px; }}
  .room-header .meta {{ color: #999; font-size: 12px; margin-top: 4px; }}
  .furniture-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
  .furniture-card {{ background: #16213e; border: 1px solid {color}44; border-radius: 8px; padding: 16px; }}
  .furniture-card h3 {{ margin: 0 0 8px 0; color: {color}; }}
  .furniture-card .icon {{ font-size: 32px; margin-bottom: 8px; }}
  .data-panel {{ background: #0f3460; border-radius: 6px; padding: 12px; margin-top: 8px; font-size: 13px; }}
  .data-panel .loading {{ color: #666; }}
  .status-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
  .status-ok {{ background: #27ae6033; color: #2ecc71; }}
  .status-warn {{ background: #f39c1233; color: #f1c40f; }}
  .back-link {{ color: {color}; text-decoration: none; font-size: 14px; }}
  .back-link:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <a href="/" class="back-link">← Back to Office</a>
  <div class="room-header">
    <h1>{_furniture_icon(plan.get("type", ""))} {plan.get("idea", room_name.title())}</h1>
    <div class="meta">Created by {plan.get("agent", "Unknown")} | Room: {room_name}</div>
  </div>
  <div class="furniture-grid" id="furniture-grid">
    {"".join(_generate_furniture_card(item, color) for item in room_config.get("furniture", []))}
  </div>
  <script>
    // Auto-refresh data panels
    async function refreshData() {{
      try {{
        const resp = await fetch('/office/vitals');
        if (resp.ok) {{
          const data = await resp.json();
          const v = data.vitals || {{}};
          document.querySelectorAll('.data-value-cpu').forEach(el => el.textContent = (v.cpu_percent || 0) + '%');
          document.querySelectorAll('.data-value-ram').forEach(el => el.textContent = (v.ram_percent || 0) + '%');
          document.querySelectorAll('.data-value-disk').forEach(el => el.textContent = (v.disk_free_gb || 0) + ' GB free');
        }}
      }} catch(e) {{ console.warn('Vitals refresh failed:', e); }}

      // Cron board refresh
      try {{
        const cronResp = await fetch('/office/cron-status');
        if (cronResp.ok) {{
          const cronData = await cronResp.json();
          const cronJobs = cronData.cron_jobs || [];
          const runningCount = cronJobs.filter(j => j.running).length;
          const failedCount = cronJobs.filter(j => j.status === 'failed' || (j.last_run && j.status !== 'recent')).length;
          document.querySelectorAll('.cron-running').forEach(el => el.textContent = runningCount);
          document.querySelectorAll('.cron-failed').forEach(el => el.textContent = failedCount);
          document.querySelectorAll('.cron-last').forEach(el => {{
            if (cronJobs.length > 0) {{
              const last = cronJobs[0].last_run ? new Date(cronJobs[0].last_run).toLocaleTimeString() : 'Never';
              el.textContent = `last: ${{last}}`;
            }} else {{
              el.textContent = 'No jobs';
            }}
          }});
        }}
      }} catch(e) {{ console.warn('Cron refresh failed:', e); }}
    }}
    refreshData();
    setInterval(refreshData, 10000);
  </script>
</body>
</html>"""


def _execute_plan_impl(huddle_id: str):
    """
    Internal: Execute the selected plan from a huddle.
    Returns (success, execution_log).
    """
    plans = _load_plans()
    huddle = next((p for p in plans["plans"] if p["id"] == huddle_id), None)

    if not huddle:
        return False, ["Huddle not found"]

    if huddle["completed"]:
        return False, ["Huddle already completed"]

    if not huddle.get("selected_plan"):
        return False, ["No plan selected"]

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
            with open(cfg.AGENTS_STATE_FILE, 'r') as f:
                agents_state = json.load(f)
            for agent in agents_state:
                if agent.get("name") == plan["agent"] or agent.get("agentId") == plan.get("agentId"):
                    agent["state"] = "executing"
                    agent["detail"] = f"Building: {plan['idea']}"
                    agent["updated_at"] = datetime.now().isoformat()
                    break
            with open(cfg.AGENTS_STATE_FILE, 'w') as f:
                json.dump(agents_state, f, indent=2, ensure_ascii=False)
            execution_log.append(f"Agent {plan['agent']} status updated to 'executing'")
        except Exception as e:
            execution_log.append(f"Warning: could not update agent state: {e}")

        # Optional: git commit the changes
        try:
            import subprocess
            subprocess.check_call(["git", "add", "-A"], cwd=cfg.ROOT_DIR)
            commit_msg = f"🤖 Huddle: {plan['idea']} (room: {room_name}, type: {plan_type})"
            subprocess.check_call(["git", "commit", "-m", commit_msg], cwd=cfg.ROOT_DIR)
            execution_log.append("Git commit created")
        except Exception as e:
            execution_log.append(f"Git commit skipped: {e}")

        # Mark huddle as completed
        huddle["status"] = "completed"
        huddle["completed"] = True
        huddle["execution_log"] = execution_log
        plans["plans"] = [p if p["id"] != huddle_id else huddle for p in plans["plans"]]
        _save_plans(plans)

        # Update decision audit record with execution results
        if decision_data:
            decision_data["execution_log"] = execution_log
            decision_data["status"] = "completed"
            decision_file.write_text(json.dumps(decision_data, indent=2, ensure_ascii=False))

        return True, execution_log

    except Exception as e:
        log.error("Huddle execution failed", extra={"_error": str(e)})
        return False, [f"Execution error: {e}"]


# ── Swarm status endpoint ─────────────────────────────────────────────────────

SWARM_STATUS_FILE = Path(cfg.ROOT_DIR) / "swarm" / "swarm-status.json"

@bp.route("/office/swarm-status", methods=["GET"])
def swarm_status():
    """Return current status of all domain agent dispatchers."""
    if SWARM_STATUS_FILE.exists():
        try:
            data = json.loads(SWARM_STATUS_FILE.read_text())
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": f"Failed to read swarm status: {e}"}), 500
    return jsonify({
        "updated_at": None,
        "agents": {},
        "detail": "Swarm dispatcher has not run yet"
    })


# ── Register sub-module routes onto bp ───────────────────────────────────────
# Must come after all shared definitions above (sub-modules import from here).

from . import huddles, collaboration, forge  # noqa: E402
