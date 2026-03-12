#!/usr/bin/env python3
"""Config blueprint: Gemini API configuration management."""

from flask import Blueprint, jsonify, request, current_app

from shared import load_runtime_config, save_runtime_config
from validation import validate_api_key, ValidationError as ValidationErrorExc
from rate_limit import rate_limit

bp = Blueprint('config', __name__)


@bp.route("/config/gemini", methods=["GET"])
def config_gemini_get():
    """Get Gemini configuration (mask API key)"""
    cfg = load_runtime_config()
    # Mask API key: show first 4 chars only
    api_key = cfg.get("gemini_api_key", "")
    if api_key and len(api_key) > 4:
        masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else api_key[:2] + "****"
    else:
        masked = "" if not api_key else "****"
    return jsonify({
        "gemini_api_key": masked,
        "gemini_model": cfg.get("gemini_model", "nanobanana-pro"),
    })


@bp.route("/config/gemini", methods=["POST"])
@rate_limit(10, 60)  # lower limit for config changes
def config_gemini_post():
    """Set Gemini API configuration"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "msg": "invalid json"}), 400

        api_key = (data.get("gemini_api_key") or "").strip()
        model = (data.get("gemini_model") or "").strip()

        payload = {}
        if api_key:
            try:
                payload["gemini_api_key"] = validate_api_key(api_key)
            except ValidationErrorExc as e:
                return jsonify({"ok": False, "msg": f"Invalid API key: {e}"}), 400

        if model:
            # Normalize model name (reuse from store_utils)
            from store_utils import _normalize_user_model
            payload["gemini_model"] = _normalize_user_model(model)

        if not payload:
            return jsonify({"ok": False, "msg": "no changes provided"}), 400

        save_runtime_config(payload)
        current_app.logger.info("Gemini config updated", extra={"_model": payload.get("gemini_model")})
        return jsonify({"ok": True, "msg": "Gemini 配置已保存"})
    except Exception as e:
        current_app.logger.error(f"Config gemini error: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500
