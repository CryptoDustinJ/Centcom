"""Huddle lifecycle routes: start, active check, emergency."""

import json
import threading
from datetime import datetime
from flask import jsonify
from pathlib import Path

from config import config as cfg
from logger import get_logger

from . import (
    bp,
    COLLAB_DIR,
    _load_plans,
    _save_plans,
    _load_agent_profiles,
    _get_office_context,
    _execute_plan_impl,
)

log = get_logger(__name__)


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


@bp.route("/office/huddle/start", methods=["POST"])
def start_huddle():
    """
    Trigger a daily collaboration huddle.
    Agents will propose improvements and plan the next changes.
    """
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

    # Signal the frontend that a huddle is active (agents gather at coffee table)
    try:
        huddle_state_file = Path(cfg.ROOT_DIR) / "huddle-active.json"
        huddle_state_file.write_text(json.dumps({
            "active": True,
            "huddle_id": huddle_id,
            "started_at": datetime.now().isoformat(),
            "agents": [a["name"] for a in collaborators]
        }, indent=2))
    except Exception as e:
        log.warning("Failed to write huddle-active state", extra={"_error": str(e)})

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

    # Clear huddle-active state after execution (agents return to positions)
    # Keep it active for 3 minutes so frontend can show the gathering animation
    def _clear_huddle_state():
        import time as _time
        _time.sleep(180)  # 3 minutes
        try:
            huddle_state_file = Path(cfg.ROOT_DIR) / "huddle-active.json"
            huddle_state_file.write_text(json.dumps({"active": False}, indent=2))
        except Exception:
            pass
    threading.Thread(target=_clear_huddle_state, daemon=True).start()

    return jsonify(response_data)


@bp.route("/office/huddle/active", methods=["GET"])
def huddle_active():
    """Check if a huddle is currently active (agents gathering at coffee table)."""
    try:
        huddle_state_file = Path(cfg.ROOT_DIR) / "huddle-active.json"
        if huddle_state_file.exists():
            data = json.loads(huddle_state_file.read_text())
            # Auto-expire stale huddles (>5 minutes old)
            if data.get("active") and data.get("started_at"):
                started = datetime.fromisoformat(data["started_at"])
                if (datetime.now() - started).total_seconds() > 300:
                    data["active"] = False
                    huddle_state_file.write_text(json.dumps(data, indent=2))
            return jsonify(data)
    except Exception:
        pass
    return jsonify({"active": False})


@bp.route("/office/huddle/emergency", methods=["POST"])
def emergency_huddle():
    """Trigger an immediate huddle (bypass any normal scheduling)."""
    return start_huddle()
