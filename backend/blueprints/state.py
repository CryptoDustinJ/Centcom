#!/usr/bin/env python3
"""State blueprint: main agent state management and memo."""

from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

from shared import (
    config,
    load_state,
    save_state,
    get_office_name_from_identity,
    normalize_agent_state,
    VALID_AGENT_STATES as _VALID_AGENT_STATES,
)
from validation import validate_state_detail, ValidationError as ValidationErrorExc
from rate_limit import rate_limit
from memo_utils import get_yesterday_date_str, sanitize_content, extract_memo_from_file
from audit import log_event as audit_log

bp = Blueprint('state', __name__)
VALID_AGENT_STATES = _VALID_AGENT_STATES


@bp.route("/status", methods=["GET"])
def get_status():
    """Get current main state (backward compatibility). Optionally include officeName from IDENTITY.md."""
    state = load_state()
    office_name = get_office_name_from_identity()
    if office_name:
        state["officeName"] = office_name
    return jsonify(state)


@bp.route("/set_state", methods=["POST"])
@rate_limit(120, 60)  # 120 requests per minute per IP
def set_state_endpoint():
    """Set main state via POST (for UI control panel)"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"status": "error", "msg": "invalid json"}), 400
        state = load_state()
        if "state" in data:
            s = data["state"]
            if s in VALID_AGENT_STATES:
                state["state"] = s
        if "detail" in data:
            try:
                state["detail"] = validate_state_detail(data["detail"])
            except ValidationErrorExc as e:
                return jsonify({"status": "error", "msg": str(e)}), 400
        state["updated_at"] = datetime.now().isoformat()
        save_state(state)
        audit_log(
            event="main_state_changed",
            actor="main",
            target="main",
            details={"state": state.get("state"), "detail": state.get("detail")},
            ip=request.remote_addr,
        )
        return jsonify({"status": "ok"})
    except Exception as e:
        current_app.logger.error(f"Set state error: {e}", exc_info=True)
        return jsonify({"status": "error", "msg": str(e)}), 500


@bp.route("/yesterday-memo", methods=["GET"])
def yesterday_memo():
    """Get yesterday's memo from memory/*.md files."""
    try:
        date_str = get_yesterday_date_str()
        memo = extract_memo_from_file(config.MEMORY_DIR, date_str)
        memo = sanitize_content(memo)
        return jsonify({"success": True, "date": date_str, "memo": memo})
    except Exception as e:
        current_app.logger.error(f"Yesterday memo error: {e}", exc_info=True)
        return jsonify({"success": False, "date": None, "memo": "", "error": str(e)}), 500


@bp.route("/soul/goals", methods=["GET"])
def get_goals():
    """Get goal/task items from OpenClaw SOUL.md."""
    try:
        from shared import get_soul_goals
        goals = get_soul_goals()
        return jsonify({"goals": goals})
    except Exception as e:
        current_app.logger.error(f"Get goals error: {e}", exc_info=True)
        return jsonify({"goals": []})
