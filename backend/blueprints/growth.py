#!/usr/bin/env python3
"""Growth Engine Blueprint - AI learning, metrics, and collaboration tracking."""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app

from config import config as cfg
from logger import get_logger

log = get_logger(__name__)
bp = Blueprint('growth', __name__)

# Growth data directory
GROWTH_DIR = Path(cfg.ROOT_DIR) / "growth"
GROWTH_DIR.mkdir(exist_ok=True)
METRICS_FILE = GROWTH_DIR / "metrics.json"
AGENT_SCORES_FILE = GROWTH_DIR / "agent_scores.json"
CONTRIBUTIONS_FILE = GROWTH_DIR / "contributions.json"


def _load_json(path: Path, default: dict):
    """Load JSON file or return default."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception as e:
            log.warning("Failed to load JSON", extra={"_path": str(path), "_error": str(e)})
    return default


def _save_json(path: Path, data: dict):
    """Save JSON file atomically."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _calculate_file_metrics(workspace_dir: str = None) -> dict:
    """Calculate code metrics for a workspace directory."""
    if not workspace_dir:
        workspace_dir = cfg.ROOT_DIR

    metrics = {
        "total_files": 0,
        "total_lines": 0,
        "python_files": 0,
        "js_files": 0,
        "html_files": 0,
        "css_files": 0,
        "md_files": 0,
        "last_modified": None,
    }

    extensions = {'.py': 'python_files', '.js': 'js_files', '.html': 'html_files',
                  '.css': 'css_files', '.md': 'md_files'}

    workspace = Path(workspace_dir)
    if not workspace.exists():
        return metrics

    latest_mtime = None
    for file_path in workspace.rglob('*'):
        if file_path.is_file():
            metrics['total_files'] += 1
            ext = file_path.suffix.lower()
            if ext in extensions:
                metrics[extensions[ext]] += 1
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = sum(1 for _ in f)
                    metrics['total_lines'] += lines
                mtime = file_path.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
            except Exception:
                pass

    if latest_mtime:
        metrics['last_modified'] = datetime.fromtimestamp(latest_mtime).isoformat()

    return metrics


def _calculate_agent_score(agent_name: str, contributions: list) -> int:
    """Calculate an agent's total contribution score."""
    score = 0
    for contrib in contributions:
        if contrib.get('agent') != agent_name and contrib.get('agent_id') != agent_name:
            continue
        # Base points for any contribution
        score += contrib.get('points', 10)
        # Bonus for room creation
        if contrib.get('type') == 'room_created':
            score += 50
        # Bonus for automation
        if contrib.get('type') == 'automation':
            score += 30
        # Bonus for creative work
        if contrib.get('type') == 'creative':
            score += 25
        # Bonus for code quality work
        if contrib.get('type') == 'code_quality':
            score += 40
    return score


@bp.route("/growth/metrics", methods=["GET"])
def get_growth_metrics():
    """
    Get overall growth metrics for the office and agents.
    Shows files, lines, rooms, contributions, and agent scores.
    """
    # Load contributions
    contributions = _load_json(CONTRIBUTIONS_FILE, {"contributions": []}).get("contributions", [])

    # Calculate current workspace metrics
    workspace_metrics = _calculate_file_metrics()

    # Load agent scores (or compute fresh)
    agent_scores = _load_json(AGENT_SCORES_FILE, {"scores": {}}).get("scores", {})

    # Room count
    rooms_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
    room_count = 0
    if rooms_file.exists():
        try:
            rooms_data = json.loads(rooms_file.read_text())
            room_count = len(rooms_data.get("rooms", []))
        except Exception:
            pass

    # Recent contributions (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    recent_contributions = []
    for contrib in contributions:
        try:
            contrib_time = datetime.fromisoformat(contrib.get('timestamp', ''))
            if contrib_time > week_ago:
                recent_contributions.append(contrib)
        except Exception:
            pass

    # Agent breakdown
    agent_breakdown = {}
    for agent in ['Rook', 'Ralph', 'Nova', 'CodeMaster', 'Claude']:
        agent_contribs = [c for c in contributions if c.get('agent') == agent]
        agent_breakdown[agent] = {
            "contributions": len(agent_contribs),
            "score": agent_scores.get(agent, 0),
            "last_active": max([c.get('timestamp', '') for c in agent_contribs]) if agent_contribs else None
        }

    metrics = {
        "overall": {
            "total_files": workspace_metrics['total_files'],
            "total_lines": workspace_metrics['total_lines'],
            "rooms": room_count,
            "total_contributions": len(contributions),
            "recent_contributions_7d": len(recent_contributions),
            "workspace_growth_bytes": workspace_metrics.get('total_lines', 0) * 100,  # rough estimate
        },
        "by_agent": agent_breakdown,
        "generated_at": datetime.now().isoformat()
    }

    return jsonify(metrics)


@bp.route("/growth/contribute", methods=["POST"])
def record_contribution():
    """
    Record an agent's contribution to the office growth.
    Called by agents after they complete an improvement task.
    """
    data = request.get_json()
    if not data or 'agent' not in data or 'type' not in data:
        return jsonify({"ok": False, "msg": "Missing agent or type"}), 400

    agent = data['agent']
    contrib_type = data['type']
    description = data.get('description', '')
    room = data.get('room', 'general')
    points = data.get('points', 10)

    # Load existing contributions
    contributions = _load_json(CONTRIBUTIONS_FILE, {"contributions": []})
    contrib_list = contributions.get("contributions", [])

    # Add new contribution
    new_contrib = {
        "id": f"contrib_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "agent": agent,
        "agent_id": data.get('agentId'),
        "type": contrib_type,
        "room": room,
        "description": description,
        "points": points,
        "timestamp": datetime.now().isoformat(),
        "git_commit": data.get('gitCommit'),
        "files_changed": data.get('filesChanged', []),
    }
    contrib_list.append(new_contrib)
    contributions["contributions"] = contrib_list
    _save_json(CONTRIBUTIONS_FILE, contributions)

    # Update agent scores
    agent_scores = _load_json(AGENT_SCORES_FILE, {"scores": {}})
    scores = agent_scores.get("scores", {})
    scores[agent] = scores.get(agent, 0) + points
    agent_scores["scores"] = scores
    agent_scores["updated_at"] = datetime.now().isoformat()
    _save_json(AGENT_SCORES_FILE, agent_scores)

    log.info("Contribution recorded", extra={"_agent": agent, "_type": contrib_type, "_points": points})

    return jsonify({
        "ok": True,
        "contribution": new_contrib,
        "agent_score": scores[agent],
        "msg": f"Recorded {points} points for {agent}"
    })


@bp.route("/growth/leaderboard", methods=["GET"])
def get_leaderboard():
    """Get agent leaderboard sorted by total score."""
    agent_scores = _load_json(AGENT_SCORES_FILE, {"scores": {}}).get("scores", {})
    contributions = _load_json(CONTRIBUTIONS_FILE, {"contributions": []}).get("contributions", [])

    # Build agent stats
    agents = {}
    for agent_name in set(list(agent_scores.keys()) + [c['agent'] for c in contributions if 'agent' in c]):
        agents[agent_name] = {
            "name": agent_name,
            "score": agent_scores.get(agent_name, 0),
            "contributions": len([c for c in contributions if c.get('agent') == agent_name]),
            "types": {}
        }

    # Count contribution types per agent
    for contrib in contributions:
        agent = contrib.get('agent')
        if agent in agents:
            ctype = contrib.get('type', 'unknown')
            agents[agent]['types'][ctype] = agents[agent]['types'].get(ctype, 0) + 1

    # Sort by score descending
    leaderboard = sorted(
        list(agents.values()),
        key=lambda a: a['score'],
        reverse=True
    )

    return jsonify({
        "leaderboard": leaderboard,
        "generated_at": datetime.now().isoformat()
    })


@bp.route("/growth/room/upgrade", methods=["POST"])
def upgrade_room():
    """
    Upgrade a room's capabilities (add furniture, backgrounds, etc.).
    This is how agents add features to rooms they've created.
    """
    data = request.get_json()
    if not data or 'room_id' not in data or 'upgrade' not in data:
        return jsonify({"ok": False, "msg": "Missing room_id or upgrade"}), 400

    room_id = data['room_id']
    upgrade = data['upgrade']
    agent = data.get('agent', 'unknown')
    description = data.get('description', '')

    # Load rooms
    rooms_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
    if not rooms_file.exists():
        return jsonify({"ok": False, "msg": "No rooms defined yet"}), 404

    try:
        rooms_data = json.loads(rooms_file.read_text())
        rooms = rooms_data.get("rooms", [])
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Failed to read rooms: {e}"}), 500

    # Find the room
    room = next((r for r in rooms if r.get('id') == room_id), None)
    if not room:
        return jsonify({"ok": False, "msg": f"Room '{room_id}' not found"}), 404

    # Apply upgrade
    upgrade_type = upgrade.get('type')
    if upgrade_type == 'add_furniture':
        furniture = upgrade.get('furniture', {})
        if 'furniture' not in room:
            room['furniture'] = []
        room['furniture'].append(furniture)
    elif upgrade_type == 'set_background':
        room['background'] = upgrade.get('background')
    elif upgrade_type == 'add_states':
        new_states = upgrade.get('states', [])
        room['states'] = list(set(room.get('states', []) + new_states))
    else:
        return jsonify({"ok": False, "msg": f"Unknown upgrade type: {upgrade_type}"}), 400

    # Add upgrade metadata
    if 'upgrades' not in room:
        room['upgrades'] = []
    room['upgrades'].append({
        "type": upgrade_type,
        "description": description,
        "agent": agent,
        "timestamp": datetime.now().isoformat()
    })

    # Save rooms
    try:
        rooms_file.write_text(json.dumps(rooms_data, indent=2, ensure_ascii=False))
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Failed to save rooms: {e}"}), 500

    # Record contribution
    contrib_data = {
        "agent": agent,
        "agentId": data.get('agentId'),
        "type": "room_upgraded",
        "room": room_id,
        "description": f"Room upgrade: {description}",
        "points": data.get('points', 25),
    }
    # Call record_contribution logic inline to avoid circular import
    contributions = _load_json(CONTRIBUTIONS_FILE, {"contributions": []})
    contrib_list = contributions.get("contributions", [])
    contrib_list.append({
        "id": f"contrib_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        **contrib_data,
        "timestamp": datetime.now().isoformat()
    })
    contributions["contributions"] = contrib_list
    _save_json(CONTRIBUTIONS_FILE, contributions)

    agent_scores = _load_json(AGENT_SCORES_FILE, {"scores": {}})
    scores = agent_scores.get("scores", {})
    scores[agent] = scores.get(agent, 0) + contrib_data['points']
    agent_scores["scores"] = scores
    agent_scores["updated_at"] = datetime.now().isoformat()
    _save_json(AGENT_SCORES_FILE, agent_scores)

    log.info("Room upgraded", extra={"_room": room_id, "_upgrade": upgrade_type, "_agent": agent})

    return jsonify({
        "ok": True,
        "room": room,
        "contribution_points": contrib_data['points'],
        "msg": f"Room '{room_id}' upgraded with {upgrade_type}"
    })


@bp.route("/growth/dashboard", methods=["GET"])
def get_dashboard():
    """
    Get a comprehensive dashboard view for the current office.
    Combines metrics, recent activity, and room status.
    """
    # Workspace file metrics
    metrics = _calculate_file_metrics()

    # Agent scores
    agent_scores = _load_json(AGENT_SCORES_FILE, {"scores": {}}).get("scores", {})

    # Room info
    rooms_file = Path(cfg.FRONTEND_DIR) / "rooms.json"
    rooms = []
    if rooms_file.exists():
        try:
            rooms_data = json.loads(rooms_file.read_text())
            rooms = rooms_data.get("rooms", [])
        except Exception:
            pass

    # Recent contributions
    contributions = _load_json(CONTRIBUTIONS_FILE, {"contributions": []}).get("contributions", [])
    recent = sorted(
        contributions,
        key=lambda c: c.get('timestamp', ''),
        reverse=True
    )[:10]

    dashboard = {
        "summary": {
            "total_rooms": len(rooms),
            "total_agents": len(agent_scores),
            "total_contributions": len(contributions),
            "workspace_lines": metrics['total_lines'],
            "workspace_files": metrics['total_files'],
        },
        "rooms": [
            {
                "id": r.get('id'),
                "name": r.get('name'),
                "color": r.get('color'),
                "created_by": r.get('created_by'),
                "has_background": bool(r.get('background')),
                "furniture_count": len(r.get('furniture', [])),
                "upgrade_count": len(r.get('upgrades', [])),
            }
            for r in rooms
        ],
        "agent_scores": agent_scores,
        "recent_activity": recent[:5],
        "generated_at": datetime.now().isoformat()
    }

    return jsonify(dashboard)


# === TASK BOARD SYSTEM ===
# Tasks that agents can claim and work on collaboratively

TASKS_FILE = GROWTH_DIR / "tasks.json"


def _load_tasks():
    """Load task board."""
    return _load_json(TASKS_FILE, {"tasks": [], "next_id": 1})


def _save_tasks(data):
    """Save task board."""
    _save_json(TASKS_FILE, data)


@bp.route("/growth/tasks", methods=["GET"])
def list_tasks():
    """List all tasks with filtering options."""
    tasks_data = _load_tasks()
    tasks = tasks_data.get("tasks", [])

    # Query params
    status = request.args.get("status")
    assignee = request.args.get("assignee")
    room = request.args.get("room")
    limit = request.args.get("limit", type=int)

    if status:
        tasks = [t for t in tasks if t.get('status') == status]
    if assignee:
        tasks = [t for t in tasks if t.get('assignee') == assignee]
    if room:
        tasks = [t for t in tasks if t.get('room') == room]

    if limit:
        tasks = tasks[:limit]

    return jsonify({
        "tasks": tasks,
        "total": len(tasks),
        "generated_at": datetime.now().isoformat()
    })


@bp.route("/growth/tasks", methods=["POST"])
def create_task():
    """Create a new task (usually by huddle or human)."""
    data = request.get_json()
    if not data or 'title' not in data or 'description' not in data:
        return jsonify({"ok": False, "msg": "Missing title or description"}), 400

    tasks_data = _load_tasks()
    tasks = tasks_data.get("tasks", [])
    next_id = tasks_data.get("next_id", 1)

    new_task = {
        "id": f"task_{next_id:04d}",
        "title": data['title'],
        "description": data['description'],
        "room": data.get('room', 'general'),
        "type": data.get('type', 'improvement'),
        "status": "open",
        "points": data.get('points', 25),
        "assignee": None,
        "assignee_id": None,
        "created_by": data.get('created_by', 'huddle'),
        "created_at": datetime.now().isoformat(),
        "assigned_at": None,
        "completed_at": None,
        "tags": data.get('tags', []),
        "dependencies": data.get('dependencies', []),
        "progress": 0,  # 0-100
    }

    tasks.append(new_task)
    tasks_data["tasks"] = tasks
    tasks_data["next_id"] = next_id + 1
    _save_tasks(tasks_data)

    log.info("Task created", extra={"_task_id": new_task['id'], "_title": new_task['title']})

    return jsonify({"ok": True, "task": new_task, "msg": f"Task {new_task['id']} created"})


@bp.route("/growth/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    """Get a specific task."""
    tasks_data = _load_tasks()
    task = next((t for t in tasks_data.get("tasks", []) if t.get('id') == task_id), None)
    if not task:
        return jsonify({"ok": False, "msg": "Task not found"}), 404
    return jsonify({"ok": True, "task": task})


@bp.route("/growth/tasks/<task_id>/claim", methods=["POST"])
def claim_task(task_id):
    """Agent claims a task."""
    data = request.get_json() or {}
    agent = data.get('agent')
    agent_id = data.get('agentId')

    if not agent:
        return jsonify({"ok": False, "msg": "Missing agent name"}), 400

    tasks_data = _load_tasks()
    tasks = tasks_data.get("tasks", [])
    task = next((t for t in tasks if t.get('id') == task_id), None)

    if not task:
        return jsonify({"ok": False, "msg": "Task not found"}), 404

    if task.get('status') != 'open':
        return jsonify({"ok": False, "msg": f"Task is {task.get('status')}, cannot claim"}), 400

    if task.get('assignee') is not None:
        return jsonify({"ok": False, "msg": f"Task already assigned to {task.get('assignee')}"}), 400

    # Claim the task
    task['assignee'] = agent
    task['assignee_id'] = agent_id
    task['assigned_at'] = datetime.now().isoformat()
    task['status'] = 'in_progress'
    tasks_data["tasks"] = tasks
    _save_tasks(tasks_data)

    log.info("Task claimed", extra={"_task_id": task_id, "_agent": agent})

    return jsonify({
        "ok": True,
        "task": task,
        "msg": f"{agent} claimed task {task_id}"
    })


@bp.route("/growth/tasks/<task_id>/complete", methods=["POST"])
def complete_task(task_id):
    """Mark a task as complete and record contribution."""
    data = request.get_json() or {}
    agent = data.get('agent')
    agent_id = data.get('agentId')
    notes = data.get('notes', '')

    if not agent:
        return jsonify({"ok": False, "msg": "Missing agent name"}), 400

    tasks_data = _load_tasks()
    tasks = tasks_data.get("tasks", [])
    task = next((t for t in tasks if t.get('id') == task_id), None)

    if not task:
        return jsonify({"ok": False, "msg": "Task not found"}), 404

    if task.get('assignee') != agent:
        return jsonify({"ok": False, "msg": f"Task assigned to {task.get('assignee')}, not {agent}"}), 403

    if task.get('status') == 'completed':
        return jsonify({"ok": False, "msg": "Task already completed"}), 400

    # Complete the task
    task['status'] = 'completed'
    task['completed_at'] = datetime.now().isoformat()
    task['notes'] = notes
    task['progress'] = 100
    tasks_data["tasks"] = tasks
    _save_tasks(tasks_data)

    # Record contribution automatically
    contrib_data = {
        "agent": agent,
        "agentId": agent_id,
        "type": "task_completed",
        "room": task.get('room', 'general'),
        "description": f"Completed task: {task['title']}",
        "points": task.get('points', 25),
        "task_id": task_id,
    }
    contributions = _load_json(CONTRIBUTIONS_FILE, {"contributions": []})
    contrib_list = contributions.get("contributions", [])
    contrib_list.append({
        "id": f"contrib_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        **contrib_data,
        "timestamp": datetime.now().isoformat()
    })
    contributions["contributions"] = contrib_list
    _save_json(CONTRIBUTIONS_FILE, contributions)

    # Update agent score
    agent_scores = _load_json(AGENT_SCORES_FILE, {"scores": {}})
    scores = agent_scores.get("scores", {})
    scores[agent] = scores.get(agent, 0) + contrib_data['points']
    agent_scores["scores"] = scores
    agent_scores["updated_at"] = datetime.now().isoformat()
    _save_json(AGENT_SCORES_FILE, agent_scores)

    log.info("Task completed", extra={"_task_id": task_id, "_agent": agent, "_points": contrib_data["points"]})

    return jsonify({
        "ok": True,
        "task": task,
        "points_earned": contrib_data['points'],
        "new_score": scores[agent],
        "msg": f"Task {task_id} completed by {agent}, earned {contrib_data['points']} points"
    })
