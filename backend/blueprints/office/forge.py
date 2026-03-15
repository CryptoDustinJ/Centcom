"""Code Forge endpoints: build status, artifacts, deployment info."""

import subprocess
from datetime import datetime
from flask import jsonify
from pathlib import Path

from config import config as cfg
from logger import get_logger

from . import bp

log = get_logger(__name__)


@bp.route("/office/forge-status", methods=["GET"])
def office_forge_status():
    """
    Return build artifact and deployment status for the Code Forge room.
    Scans git history, build outputs, and deployment markers.
    """
    forge = {
        "build": {
            "status": "idle",
            "duration": "--",
            "last_commit": None,
            "last_commit_msg": None,
            "branch": "master",
        },
        "deploy": {
            "target": "local",
            "status": "stable",
            "last_deploy": None,
        },
        "artifacts": [],
        "artifact_summary": {
            "count": 0,
            "total_size_kb": 0,
        },
        "timestamp": datetime.now().isoformat(),
    }

    # --- Git / build info ---
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3, cwd=cfg.ROOT_DIR
        )
        if branch.returncode == 0:
            forge["build"]["branch"] = branch.stdout.strip()

        log_result = subprocess.run(
            ["git", "log", "-1", "--format=%H|%s|%ci"],
            capture_output=True, text=True, timeout=3, cwd=cfg.ROOT_DIR
        )
        if log_result.returncode == 0 and log_result.stdout.strip():
            parts = log_result.stdout.strip().split("|", 2)
            if len(parts) == 3:
                forge["build"]["last_commit"] = parts[0][:8]
                forge["build"]["last_commit_msg"] = parts[1][:80]
                forge["build"]["duration"] = parts[2].strip()

        # Detect if a build is running (look for common build tools)
        for proc_name in ["npm", "python", "make", "cargo", "go"]:
            try:
                ps = subprocess.run(
                    ["pgrep", "-f", proc_name], capture_output=True, timeout=2
                )
                if ps.returncode == 0:
                    forge["build"]["status"] = "building"
                    break
            except Exception:
                pass

        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=3, cwd=cfg.ROOT_DIR
        )
        if dirty.returncode == 0 and dirty.stdout.strip():
            forge["build"]["status"] = "dirty"
    except Exception as e:
        log.warning("Forge git check failed", extra={"_error": str(e)})

    # --- Deployment markers ---
    try:
        deploy_marker = Path(cfg.ROOT_DIR) / "deploy.json"
        if deploy_marker.exists():
            import json
            with open(deploy_marker, "r") as f:
                deploy_data = json.load(f)
            forge["deploy"]["target"] = deploy_data.get("target", "local")
            forge["deploy"]["status"] = deploy_data.get("status", "stable")
            forge["deploy"]["last_deploy"] = deploy_data.get("timestamp")
        else:
            # Infer from service status
            try:
                svc = subprocess.run(
                    ["systemctl", "--user", "is-active", "openclaw-gateway"],
                    capture_output=True, text=True, timeout=3
                )
                if svc.returncode == 0 and "active" in svc.stdout:
                    forge["deploy"]["status"] = "running"
                else:
                    forge["deploy"]["status"] = "stopped"
            except Exception:
                forge["deploy"]["status"] = "unknown"
    except Exception as e:
        log.warning("Forge deploy check failed", extra={"_error": str(e)})

    # --- Build artifacts (scan for common output files) ---
    try:
        artifact_dirs = [
            Path(cfg.ROOT_DIR) / "dist",
            Path(cfg.ROOT_DIR) / "build",
            Path(cfg.ROOT_DIR) / "frontend" / "rooms",
        ]
        total_size = 0
        for artifact_dir in artifact_dirs:
            if artifact_dir.exists() and artifact_dir.is_dir():
                for fp in list(artifact_dir.rglob("*"))[:50]:
                    if fp.is_file():
                        size_kb = fp.stat().st_size / 1024
                        total_size += size_kb
                        forge["artifacts"].append({
                            "name": fp.name,
                            "path": str(fp.relative_to(cfg.ROOT_DIR)),
                            "size_kb": round(size_kb, 1),
                            "modified": datetime.fromtimestamp(
                                fp.stat().st_mtime
                            ).isoformat(),
                        })
        # Sort by most recent, keep top 20
        forge["artifacts"].sort(key=lambda a: a["modified"], reverse=True)
        forge["artifacts"] = forge["artifacts"][:20]
        forge["artifact_summary"]["count"] = len(forge["artifacts"])
        forge["artifact_summary"]["total_size_kb"] = round(total_size, 1)
    except Exception as e:
        log.warning("Forge artifact scan failed", extra={"_error": str(e)})

    return jsonify({"ok": True, "forge": forge})
