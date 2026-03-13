#!/usr/bin/env python3
"""Badge & Achievement System for Growth Engine.

Tracks agent achievements and awards badges based on contribution history.
"""

import json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app

from config import config as cfg
from logger import get_logger

log = get_logger(__name__)
bp = Blueprint('badges', __name__)

# Directories
ROOT = Path(cfg.ROOT_DIR)
GROWTH_DIR = ROOT / "growth"
BADGES_FILE = GROWTH_DIR / "badges.json"
AGENT_BADGES_FILE = GROWTH_DIR / "agent_badges.json"

# In-memory caches (reloaded on each request for simplicity)
_badges_cache = None
_agent_badges_cache = None


def _load_badges():
    """Load badge definitions."""
    global _badges_cache
    if _badges_cache is not None:
        return _badges_cache

    if BADGES_FILE.exists():
        try:
            data = json.loads(BADGES_FILE.read_text())
            _badges_cache = {b["id"]: b for b in data.get("badges", [])}
            return _badges_cache
        except Exception as e:
            log.error("Failed to load badges", extra={"_error": str(e)})

    _badges_cache = {}
    return _badges_cache


def _load_agent_badges():
    """Load agent badge awards."""
    global _agent_badges_cache
    if _agent_badges_cache is not None:
        return _agent_badges_cache

    if AGENT_BADGES_FILE.exists():
        try:
            data = json.loads(AGENT_BADGES_FILE.read_text())
            _agent_badges_cache = data.get("agents", {})
            return _agent_badges_cache
        except Exception as e:
            log.error("Failed to load agent badges", extra={"_error": str(e)})

    _agent_badges_cache = {}
    return _agent_badges_cache


def _save_agent_badges(agent_badges):
    """Save agent badge awards."""
    try:
        data = {"agents": agent_badges, "updated_at": datetime.now().isoformat()}
        AGENT_BADGES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        global _agent_badges_cache
        _agent_badges_cache = agent_badges
    except Exception as e:
        log.error("Failed to save agent badges", extra={"_error": str(e)})


def _invalidate_caches():
    """Clear cached data (call after data changes)."""
    global _badges_cache, _agent_badges_cache
    _badges_cache = None
    _agent_badges_cache = None


def award_badge(agent_name: str, badge_id: str, reason: str = ""):
    """
    Award a badge to an agent if not already owned.
    Returns: badge definition if newly awarded, None if already owned or invalid.
    """
    badges = _load_badges()
    if badge_id not in badges:
        log.warning("Unknown badge ID", extra={"_badge_id": badge_id})
        return None

    agent_badges = _load_agent_badges()
    if agent_name not in agent_badges:
        agent_badges[agent_name] = []

    # Check if already awarded
    if any(b.get("id") == badge_id for b in agent_badges[agent_name]):
        return None  # Already has it

    # Award the badge
    badge_def = badges[badge_id]
    award = {
        "id": badge_id,
        "name": badge_def["name"],
        "icon": badge_def["icon"],
        "awarded_at": datetime.now().isoformat(),
        "reason": reason
    }
    agent_badges[agent_name].append(award)
    _save_agent_badges(agent_badges)

    log.info("Badge awarded", extra={
        "_agent": agent_name,
        "_badge_id": badge_id,
        "_badge_name": badge_def["name"],
        "_reason": reason
    })
    return badge_def


def get_agent_badges(agent_name: str):
    """Return list of badges earned by an agent."""
    agent_badges = _load_agent_badges()
    return agent_badges.get(agent_name, [])


def check_conditions_for_contribution(contribution: dict):
    """
    Check if a new contribution triggers any badges.
    Called after a contribution is logged.
    """
    agent = contribution.get("agent")
    if not agent:
        return []

    agent_badges = _load_agent_badges()
    already_owned = {b["id"] for b in agent_badges.get(agent, [])}

    # Load all contributions to count across history
    contributions = []
    try:
        cont_path = GROWTH_DIR / "contributions.json"
        if cont_path.exists():
            data = json.loads(cont_path.read_text())
            contributions = data.get("contributions", [])
    except Exception:
        pass

    # Count agent's contributions by type
    agent_contribs = [c for c in contributions if c.get("agent") == agent]
    room_created_count = sum(1 for c in agent_contribs if c.get("type") == "room_created")
    dashboard_created_count = sum(1 for c in agent_contribs if c.get("type") in ["dashboard_created", "room_dashboard"])
    automation_dashboard_count = sum(1 for c in agent_contribs if c.get("type") == "automation")
    creative_contribution_count = sum(1 for c in agent_contribs if c.get("type") in ["creative", "room_dashboard", "theming", "content"])
    huddles_started_count = sum(1 for c in agent_contribs if c.get("type") == "huddle_started")
    # Multi-agent tasks: count tasks where assignee contains multiple agent names
    multi_agent_count = 0
    for c in agent_contribs:
        if c.get("type") == "task_completed":
            task_id = c.get("task_id")
            # Look up task to check assignees
            try:
                tasks_file = GROWTH_DIR / "tasks.json"
                if tasks_file.exists():
                    tasks_data = json.loads(tasks_file.read_text())
                    task = next((t for t in tasks_data.get("tasks", []) if t.get("id") == task_id), None)
                    if task:
                        assignee = task.get("assignee", "")
                        # Check if task had multiple assignees (Ralph, Rook, Nova all present)
                        if any(name in assignee for name in ["Ralph", "Rook", "Nova"]) and "Ralph" in assignee and "Nova" in assignee:
                            multi_agent_count += 1
            except Exception:
                pass

    badges = _load_badges()
    earned = []

    for badge_id, badge in badges.items():
        if badge_id in already_owned:
            continue

        condition = badge.get("condition", {})
        cond_type = condition.get("type")

        triggered = False
        reason = ""

        if cond_type == "first_contribution":
            # First contribution ever: if this is the first contribution for agent
            if len(agent_contribs) <= 1:  # This one is the first (or only)
                triggered = True
                reason = "First contribution to office"

        elif cond_type == "room_created":
            count_needed = condition.get("count", 1)
            if room_created_count >= count_needed:
                triggered = True
                reason = f"Created {count_needed}+ rooms ({room_created_count})"

        elif cond_type == "dashboard_created":
            count_needed = condition.get("count", 5)
            if dashboard_created_count >= count_needed:
                triggered = True
                reason = f"Created {count_needed}+ dashboards ({dashboard_created_count})"

        elif cond_type == "multi_agent_tasks":
            count_needed = condition.get("count", 3)
            if multi_agent_count >= count_needed:
                triggered = True
                reason = f"Completed {count_needed}+ multi-agent tasks ({multi_agent_count})"

        elif cond_type == "contribution_by_type":
            type_filters = condition.get("type_filter", [])
            if isinstance(type_filters, str):
                type_filters = [type_filters]
            count_needed = condition.get("count", 3)
            actual_count = sum(1 for c in agent_contribs if c.get("type") in type_filters)
            if actual_count >= count_needed:
                triggered = True
                reason = f"Achieved {count_needed}+ contributions of type {type_filters} ({actual_count})"

        elif cond_type == "dashboard_created_by_type":
            type_filter = condition.get("type_filter", "automation")
            count_needed = condition.get("count", 5)
            # Count dashboards of this specific type
            actual_count = sum(1 for c in agent_contribs if c.get("type") == type_filter)
            if actual_count >= count_needed:
                triggered = True
                reason = f"Created {count_needed}+ {type_filter} dashboards ({actual_count})"

        elif cond_type == "huddles_started":
            count_needed = condition.get("count", 10)
            if huddles_started_count >= count_needed:
                triggered = True
                reason = f"Started {count_needed}+ huddles ({huddles_started_count})"

        elif cond_type == "usage_views":
            # Requires usage tracking data - not implemented yet
            pass

        elif cond_type == "tasks_completed_no_rework":
            # Requires rework tracking - not implemented yet
            pass

        if triggered:
            award = award_badge(agent, badge_id, reason)
            if award:
                earned.append(award)

    return earned


# ========== API ENDPOINTS ==========

@bp.route("/growth/badges", methods=["GET"])
def list_badges():
    """List all badges with description and criteria."""
    badges = _load_badges()
    agent_badges = _load_agent_badges()

    # Include stats: how many agents have each badge
    badge_stats = {}
    for agent, badges_list in agent_badges.items():
        for badge in badges_list:
            bid = badge["id"]
            badge_stats[bid] = badge_stats.get(bid, 0) + 1

    result = []
    for bid, bdef in badges.items():
        result.append({
            "id": bid,
            "name": bdef["name"],
            "description": bdef["description"],
            "icon": bdef["icon"],
            "points": bdef.get("points", 0),
            "agents_earned": badge_stats.get(bid, 0)
        })

    return jsonify({"ok": True, "badges": result})


@bp.route("/agents/<agent_id>/badges", methods=["GET"])
def agent_badges(agent_id: str):
    """
    Get badges for a specific agent.
    Accepts either agent name or agentId.
    Handles mapping between agents-state names and growth contribution names.
    """
    # Mapping: agents-state name -> growth agent name
    name_mapping = {
        "star": "Rook",      # Main agent's state name is "Star", but growth credits go to "Rook"
        "Rook": "Rook",
        "Nova": "Nova",
        "Ralph": "Ralph",
    }

    # If agent_id looks like an internal ID (agent_...), try to map via agents-state
    growth_agent_name = None

    if agent_id in name_mapping:
        growth_agent_name = name_mapping[agent_id]
    else:
        # Try to find by matching agentId
        try:
            with open(cfg.AGENTS_STATE_FILE) as f:
                agents = json.load(f)
            agent = next((a for a in agents if a.get("agentId") == agent_id), None)
            if agent:
                state_name = agent.get("name", "")
                growth_agent_name = name_mapping.get(state_name, state_name)
        except Exception:
            pass

    if not growth_agent_name:
        # Fallback: treat as growth name directly (e.g., "CodeMaster")
        # Even if agent not in agents-state, they might have badges from contributions
        growth_agent_name = agent_id

    badges = get_agent_badges(growth_agent_name)

    # Even if no badges yet, return success (empty list)
    return jsonify({
        "ok": True,
        "agent": growth_agent_name,
        "badges": badges,
        "total_points": sum(b.get("points", 0) for b in badges)
    })


@bp.route("/growth/badges/award", methods=["POST"])
def manual_award():
    """
    Admin endpoint to manually award a badge.
    Requires session auth (not yet implemented).
    """
    data = request.get_json()
    if not data or "agent" not in data or "badge_id" not in data:
        return jsonify({"ok": False, "msg": "Missing agent or badge_id"}), 400

    agent = data["agent"]
    badge_id = data["badge_id"]
    reason = data.get("reason", "Manual award")

    badge = award_badge(agent, badge_id, reason)
    if badge:
        return jsonify({"ok": True, "badge": badge, "msg": f"Badge awarded to {agent}"})
    else:
        return jsonify({"ok": False, "msg": "Badge already owned or invalid"}), 409


@bp.route("/growth/badges/check", methods=["POST"])
def check_badges():
    """
    Check and award badges for a specific contribution.
    Called by growth engine after logging a contribution.
    """
    data = request.get_json()
    if not data or "contribution" not in data:
        return jsonify({"ok": False, "msg": "Missing contribution data"}), 400

    contribution = data["contribution"]
    earned = check_conditions_for_contribution(contribution)

    return jsonify({
        "ok": True,
        "earned": earned,
        "count": len(earned)
    })


# Helper for non-request context (called from other blueprints)
def check_and_award_badges(contribution: dict):
    """
    Check badge conditions and award if triggered.
    Call this after logging a contribution.
    Returns list of newly awarded badges.
    """
    return check_conditions_for_contribution(contribution)
