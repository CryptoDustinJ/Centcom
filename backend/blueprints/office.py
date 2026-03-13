#!/usr/bin/env python3
"""Office Collaboration Blueprint - Agents working together to improve their office."""

import json
import os
import re
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


# Agent role definitions for context-aware proposals
# Each proposal can include custom 'furniture' to be placed in the room
_AGENT_ROLES = {
    "Rook": {
        "role": "architect", "expertise": ["rooms", "layout", "integration"],
        "proposal_pool": [
            {"type": "new_room", "room": "lab", "idea": "Add lab room for code quality analysis", "priority": 2,
             "details": "A dedicated lab for testing, linting, and code review.",
             "furniture": [{"type": "linter", "x": 0.2, "y": 0.3, "label": "Lint Results"},
                           {"type": "coverage", "x": 0.5, "y": 0.3, "label": "Test Coverage"},
                           {"type": "pr_board", "x": 0.8, "y": 0.3, "label": "PR Stats"}]},
            {"type": "new_room", "room": "archive", "idea": "Create archive room for decision history", "priority": 2,
             "details": "Store and display architectural decisions and reasoning logs.",
             "furniture": [{"type": "archive", "x": 0.2, "y": 0.3, "label": "Decision Archive"},
                           {"type": "whiteboard", "x": 0.6, "y": 0.3, "label": "Architecture Board"},
                           {"type": "filing_cabinet", "x": 0.8, "y": 0.5, "label": "Old Plans"}]},
            {"type": "new_room", "room": "comms", "idea": "Build communications center for cross-agent messaging", "priority": 2,
             "details": "Central hub for agent-to-agent messaging and status updates.",
             "furniture": [{"type": "satellite", "x": 0.3, "y": 0.2, "label": "Signal Relay"},
                           {"type": "radio", "x": 0.6, "y": 0.3, "label": "Dispatch Radio"},
                           {"type": "tv", "x": 0.5, "y": 0.6, "label": "Status Wall"}]},
            {"type": "monitoring", "room": "serverroom", "idea": "Expand server room with GPU monitoring", "priority": 1,
             "details": "Add GPU temp, VRAM usage, and Ollama model status.",
             "furniture": [{"type": "gauge", "x": 0.3, "y": 0.5, "label": "GPU Temps"},
                           {"type": "dashboard", "x": 0.7, "y": 0.5, "label": "VRAM Usage"}]},
            {"type": "monitoring", "room": "serverroom", "idea": "Add network traffic monitor to server room", "priority": 2,
             "details": "Visualize inbound/outbound network traffic and API call rates.",
             "furniture": [{"type": "globe", "x": 0.5, "y": 0.4, "label": "Traffic Map"}]},
            {"type": "new_room", "room": "war_room", "idea": "Create incident war room for emergencies", "priority": 2,
             "details": "Dedicated room for coordinating during outages and critical issues.",
             "furniture": [{"type": "alert_board", "x": 0.2, "y": 0.3, "label": "Incident Board"},
                           {"type": "phone", "x": 0.5, "y": 0.3, "label": "Hotline"},
                           {"type": "shield", "x": 0.8, "y": 0.3, "label": "Defense Status"},
                           {"type": "clock", "x": 0.5, "y": 0.6, "label": "Uptime Clock"}]},
            {"type": "new_room", "room": "garden", "idea": "Create rooftop garden for agent relaxation", "priority": 3,
             "details": "A peaceful space with plants and ambient nature sounds.",
             "furniture": [{"type": "plant", "x": 0.2, "y": 0.3, "label": "Bonsai"},
                           {"type": "plant", "x": 0.5, "y": 0.2, "label": "Fern"},
                           {"type": "water_cooler", "x": 0.8, "y": 0.4, "label": "Fountain"},
                           {"type": "couch", "x": 0.5, "y": 0.6, "label": "Hammock"}]},
        ]
    },
    "Ralph": {
        "role": "devops", "expertise": ["monitoring", "maintenance", "syscheck"],
        "proposal_pool": [
            {"type": "monitoring", "room": "serverroom", "idea": "Create system health dashboard", "priority": 1,
             "details": "Monitor CPU, memory, disk across all services.",
             "furniture": [{"type": "dashboard", "x": 0.3, "y": 0.3, "label": "CPU/RAM"},
                           {"type": "gauge", "x": 0.7, "y": 0.3, "label": "Disk Usage"}]},
            {"type": "automation", "room": "workspace", "idea": "Add deployment pipeline tracker", "priority": 1,
             "details": "Visualize the CI/CD pipeline with build/test/deploy stages.",
             "furniture": [{"type": "pipeline", "x": 0.3, "y": 0.4, "label": "Build Pipeline"},
                           {"type": "battery", "x": 0.7, "y": 0.4, "label": "Deploy Status"}]},
            {"type": "automation", "room": "workspace", "idea": "Install alert escalation board", "priority": 2,
             "details": "Track alert severity, who's on call, and escalation chains.",
             "furniture": [{"type": "alert_board", "x": 0.5, "y": 0.3, "label": "Escalations"}]},
            {"type": "monitoring", "room": "serverroom", "idea": "Add Ollama model health panel", "priority": 1,
             "details": "Show loaded models, inference speed, and context window usage.",
             "furniture": [{"type": "terminal", "x": 0.5, "y": 0.5, "label": "Model Status"}]},
            {"type": "new_room", "room": "ops_center", "idea": "Create ops center with live service dashboards", "priority": 2,
             "details": "Centralized monitoring for all services: gateway, node, ollama.",
             "furniture": [{"type": "server_rack", "x": 0.2, "y": 0.3, "label": "Gateway"},
                           {"type": "server_rack", "x": 0.5, "y": 0.3, "label": "Node Host"},
                           {"type": "terminal", "x": 0.8, "y": 0.3, "label": "Ollama"},
                           {"type": "log_stream", "x": 0.5, "y": 0.6, "label": "Log Tail"}]},
            {"type": "automation", "room": "workspace", "idea": "Add backup status indicator", "priority": 2,
             "details": "Show latest backup timestamps and verification status.",
             "furniture": [{"type": "safe", "x": 0.5, "y": 0.4, "label": "Backup Vault"}]},
            {"type": "monitoring", "room": "serverroom", "idea": "Install network latency tracker", "priority": 2,
             "details": "Ping times to key services and external APIs.",
             "furniture": [{"type": "compass", "x": 0.4, "y": 0.5, "label": "Latency Compass"},
                           {"type": "globe", "x": 0.7, "y": 0.5, "label": "Endpoint Map"}]},
        ]
    },
    "Nova": {
        "role": "artist", "expertise": ["creative_content", "visuals", "theming"],
        "proposal_pool": [
            {"type": "creative", "room": "breakroom", "idea": "Add story corner with sci-fi snippets", "priority": 2,
             "details": "Show latest generated stories and storybook database stats.",
             "furniture": [{"type": "bookshelf", "x": 0.2, "y": 0.3, "label": "Story Corner"},
                           {"type": "lamp", "x": 0.5, "y": 0.3, "label": "Reading Lamp"}]},
            {"type": "creative", "room": "breakroom", "idea": "Create art gallery wall for generated images", "priority": 2,
             "details": "Display AI-generated artwork and wallpapers.",
             "furniture": [{"type": "easel", "x": 0.3, "y": 0.3, "label": "Art Display"},
                           {"type": "palette", "x": 0.7, "y": 0.3, "label": "Color Palette"}]},
            {"type": "new_room", "room": "gallery", "idea": "Build dedicated art gallery room", "priority": 2,
             "details": "A whole room for displaying generated art, wallpapers, and creative output.",
             "furniture": [{"type": "easel", "x": 0.15, "y": 0.3, "label": "Canvas 1"},
                           {"type": "easel", "x": 0.4, "y": 0.3, "label": "Canvas 2"},
                           {"type": "easel", "x": 0.65, "y": 0.3, "label": "Canvas 3"},
                           {"type": "trophy", "x": 0.85, "y": 0.3, "label": "Best Of"},
                           {"type": "lamp", "x": 0.5, "y": 0.6, "label": "Spotlight"}]},
            {"type": "creative", "room": "breakroom", "idea": "Install jukebox with ambient sounds", "priority": 3,
             "details": "Background music and sound effects for the office.",
             "furniture": [{"type": "radio", "x": 0.5, "y": 0.4, "label": "Jukebox"}]},
            {"type": "new_room", "room": "lounge", "idea": "Create cozy lounge with coffee bar", "priority": 3,
             "details": "A relaxation space with sofas and beverages.",
             "furniture": [{"type": "couch", "x": 0.2, "y": 0.3, "label": "Sofa"},
                           {"type": "coffee", "x": 0.5, "y": 0.3, "label": "Espresso Bar"},
                           {"type": "plant", "x": 0.8, "y": 0.3, "label": "Ficus"},
                           {"type": "tv", "x": 0.5, "y": 0.6, "label": "News Feed"}]},
            {"type": "theming", "room": "workspace", "idea": "Add motivational poster wall", "priority": 3,
             "details": "Rotating inspirational quotes and team achievements.",
             "furniture": [{"type": "trophy", "x": 0.5, "y": 0.4, "label": "Wall of Fame"}]},
            {"type": "creative", "room": "breakroom", "idea": "Set up storybook reading nook", "priority": 2,
             "details": "Cozy corner to browse the storybook database.",
             "furniture": [{"type": "bookshelf", "x": 0.3, "y": 0.3, "label": "Storybooks"},
                           {"type": "lamp", "x": 0.6, "y": 0.3, "label": "Reading Light"},
                           {"type": "couch", "x": 0.5, "y": 0.6, "label": "Bean Bag"}]},
        ]
    },
    "Claude": {
        "role": "analyst", "expertise": ["reasoning", "architecture", "code_review"],
        "proposal_pool": [
            {"type": "reasoning", "room": "archive", "idea": "Create reasoning logs wall", "priority": 2,
             "details": "Display recent deep analysis threads and architectural decisions.",
             "furniture": [{"type": "whiteboard", "x": 0.3, "y": 0.3, "label": "Decision Board"},
                           {"type": "archive", "x": 0.7, "y": 0.3, "label": "Reasoning Logs"}]},
            {"type": "code_quality", "room": "lab", "idea": "Add code review dashboard", "priority": 2,
             "details": "Track code quality metrics, tech debt, and review comments.",
             "furniture": [{"type": "linter", "x": 0.3, "y": 0.3, "label": "Review Queue"},
                           {"type": "coverage", "x": 0.7, "y": 0.3, "label": "Quality Score"}]},
            {"type": "new_room", "room": "library", "idea": "Build knowledge library room", "priority": 2,
             "details": "Central repository for documentation, guides, and learned patterns.",
             "furniture": [{"type": "bookshelf", "x": 0.15, "y": 0.3, "label": "Docs"},
                           {"type": "bookshelf", "x": 0.4, "y": 0.3, "label": "Guides"},
                           {"type": "telescope", "x": 0.65, "y": 0.3, "label": "Research"},
                           {"type": "desk", "x": 0.85, "y": 0.3, "label": "Study Desk"}]},
            {"type": "reasoning", "room": "workspace", "idea": "Add architecture diagram board", "priority": 2,
             "details": "Visual system architecture with component relationships.",
             "furniture": [{"type": "map", "x": 0.5, "y": 0.4, "label": "System Map"}]},
        ]
    },
    "CodeMaster": {
        "role": "engineer", "expertise": ["code_quality", "testing", "optimization"],
        "proposal_pool": [
            {"type": "code_quality", "room": "lab", "idea": "Add code quality metrics dashboard", "priority": 1,
             "details": "Show test coverage, lint results, and recent PR stats.",
             "furniture": [{"type": "linter", "x": 0.2, "y": 0.3, "label": "Lint Results"},
                           {"type": "coverage", "x": 0.5, "y": 0.3, "label": "Test Coverage"},
                           {"type": "pr_board", "x": 0.8, "y": 0.3, "label": "PR Stats"}]},
            {"type": "automation", "room": "lab", "idea": "Create CI/CD pipeline monitor", "priority": 2,
             "details": "Track build status, deployment history, and test results.",
             "furniture": [{"type": "pipeline", "x": 0.3, "y": 0.3, "label": "CI Pipeline"},
                           {"type": "chart", "x": 0.7, "y": 0.3, "label": "Build History"}]},
            {"type": "automation", "room": "workspace", "idea": "Install automated test runner display", "priority": 2,
             "details": "Live view of test suite execution and results.",
             "furniture": [{"type": "terminal", "x": 0.3, "y": 0.4, "label": "Test Runner"},
                           {"type": "coverage", "x": 0.7, "y": 0.4, "label": "Pass Rate"}]},
            {"type": "new_room", "room": "forge", "idea": "Build code forge for build artifacts", "priority": 2,
             "details": "Where code gets compiled, packaged, and deployed.",
             "furniture": [{"type": "hammer", "x": 0.2, "y": 0.3, "label": "Compiler"},
                           {"type": "gear", "x": 0.5, "y": 0.3, "label": "Packager"},
                           {"type": "plug", "x": 0.8, "y": 0.3, "label": "Deployer"},
                           {"type": "toolbox", "x": 0.5, "y": 0.6, "label": "Build Tools"}]},
        ]
    },
}


def _generate_proposal_for_agent(agent, context):
    """Generate a context-aware proposal for an agent based on their role and office state."""
    import random
    name = agent.get("name", "Unknown")
    role_def = _AGENT_ROLES.get(name, {
        "role": "generalist", "expertise": ["general"],
        "proposal_pool": [
            {"type": "new_room", "room": "lounge", "idea": "Suggest a general improvement", "priority": 3,
             "details": "Propose enhancements based on current needs."}
        ]
    })

    # Pick a proposal from the pool, preferring ones for rooms that don't exist yet
    existing_room_ids = set(r.get("id") for r in context.get("rooms", {}).get("list", []))
    pool = role_def["proposal_pool"]

    # Prefer proposals for rooms that don't exist yet
    new_room_proposals = [p for p in pool if p.get("room") not in existing_room_ids]
    if new_room_proposals:
        chosen = random.choice(new_room_proposals)
    else:
        chosen = random.choice(pool)

    # Build reasoning string with context
    ctx_summary = (
        f"agents={context['agents']['total']}, tasks={context['tasks']['total']}, "
        f"rooms={context['rooms']['total']}, disk={context['system']['disk_free_gb']} GB"
    )
    reasoning = (
        f"As a {role_def['role']} with expertise in {', '.join(role_def['expertise'])}, "
        f"I analyzed: {ctx_summary}. Suggested {chosen['type']}.\n\n"
        f"[Context snapshot]: {ctx_summary}, top_agent={context['growth']['top_agent']}"
    )

    proposal = {
        "agent": name,
        "type": chosen["type"],
        "room": chosen["room"],
        "idea": chosen["idea"],
        "priority": chosen["priority"],
        "details": chosen["details"],
        "reasoning": reasoning,
        "agentId": agent.get("agentId"),
        "requires": ["exec", "git"],
        "status": "pending",
    }
    # Include custom furniture from the proposal if defined
    if "furniture" in chosen:
        proposal["furniture"] = chosen["furniture"]
    return proposal


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
        "cron_board": "⏰",
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
            }
            existing_rooms["rooms"].append(new_room)
            execution_log.append(f"Room '{room_name}' created with {len(room_config['furniture'])} furniture items")

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

    # Generate context-aware proposals from each agent based on their role
    context = _get_office_context()
    for agent in collaborators:
        proposal = _generate_proposal_for_agent(agent, context)
        huddle["proposals"].append(proposal)

    # Simple voting: sum of priorities, pick highest
    selected = None
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

    response_data = {
        "ok": True,
        "huddle_id": huddle_id,
        "agents": [a["name"] for a in collaborators],
        "proposals": huddle["proposals"],
        "selected_plan": selected,
        "msg": f"Huddle started with {len(collaborators)} agents. Plan: {selected['idea'] if selected else 'No plan'}"
    }

    # AUTO-EXECUTE: If a plan was selected, execute it immediately
    log.info(f"Auto-execute check: selected={selected is not None}, huddle_id={huddle_id}")
    if selected:
        try:
            log.info("Calling _execute_plan_impl")
            success, exec_log = _execute_plan_impl(huddle_id)
            response_data["execution"] = {"success": success, "log": exec_log}
            if success:
                response_data["msg"] = f"Huddle completed and plan executed: {selected['idea']}"
            else:
                response_data["msg"] = f"Huddle plan selected but execution failed: {exec_log[0] if exec_log else 'Unknown error'}"
            log.info("Auto-execute finished", extra={"success": success, "log": exec_log})
        except Exception as e:
            log.error("Auto-execution failed", extra={"_error": str(e)})
            response_data["execution"] = {"success": False, "log": [f"Auto-execution error: {e}"]}

    return jsonify(response_data)


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
            }
            existing_rooms["rooms"].append(new_room)
            execution_log.append(f"Room '{room_name}' created with {len(room_config['furniture'])} furniture items")

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

