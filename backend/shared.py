#!/usr/bin/env python3
"""Shared constants, state management, and utility functions used across blueprints.

Centralizes logic that was previously in app.py module scope to avoid circular imports
and enable clean blueprint separation.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from config import config as cfg

# Logger convenience
def get_logger(name: str | None = None):
    from logger import get_logger as _get_logger
    return _get_logger(name)

# Re-export config reference for convenience
config = cfg

# === State Constants ===
VALID_AGENT_STATES = frozenset({"idle", "writing", "researching", "executing", "syncing", "error"})
WORKING_STATES = frozenset({"writing", "researching", "executing"})  # subset used for auto-idle TTL
STATE_TO_AREA_MAP = {
    "idle": "breakroom",
    "writing": "writing",
    "researching": "researching",
    "executing": "writing",
    "syncing": "command",
    "error": "error",
    "sleeping": "breakroom",
}

DEFAULT_STATE = {
    "state": "idle",
    "detail": "等待任务中...",
    "progress": 0,
    "updated_at": datetime.now().isoformat()
}


# === Agent State Management ===

def normalize_agent_state(state: str) -> str:
    """Normalize agent state to canonical form (syncing -> syncing, etc)."""
    s = (state or "").strip().lower()
    if s in VALID_AGENT_STATES:
        return s
    # Map synonyms
    if s in {"busy", "working", "coding", "debugging"}:
        return "writing"
    if s in {"training", "building", "running"}:
        return "executing"
    if s in {"research", "searching", "reading"}:
        return "researching"
    if s in {"sync", "upload", "download"}:
        return "syncing"
    if s in {"error", "failed", "exception", "crash"}:
        return "error"
    if s in {"idle", "waiting", "pending"}:
        return "idle"
    # Default fallback
    return "idle"


def state_to_area(state: str) -> str:
    """Map agent state to office area."""
    return STATE_TO_AREA_MAP.get(normalize_agent_state(state), "breakroom")


# === File-based State Persistence ===

def load_state() -> dict[str, Any]:
    """Load main state from file, with auto-idle fallback."""
    state = None
    if os.path.exists(cfg.STATE_FILE):
        try:
            with open(cfg.STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = None

    if not isinstance(state, dict):
        state = dict(DEFAULT_STATE)

    # Auto-idle: if working state and too old, revert to idle
    try:
        ttl = int(state.get("ttl_seconds", cfg.AUTO_IDLE_TTL))
        updated_at = state.get("updated_at")
        s = state.get("state", "idle")
        if updated_at and s in WORKING_STATES:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if dt.tzinfo:
                from datetime import timezone
                age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            else:
                age = (datetime.now() - dt).total_seconds()
            if age > ttl:
                state["state"] = "idle"
                state["detail"] = "待命中（自动回到休息区）"
                state["progress"] = 0
                state["updated_at"] = datetime.now().isoformat()
                try:
                    from store_utils import save_state as _store_save_state
                    _store_save_state(cfg.STATE_FILE, state)
                except Exception:
                    pass
    except Exception:
        pass

    return state


def save_state(state: dict) -> None:
    """Save main state to file."""
    from store_utils import _save_json
    _save_json(cfg.STATE_FILE, state)


def load_agents_state() -> list[dict[str, Any]]:
    """Load agents list from file."""
    from store_utils import load_agents_state
    default_agents = []
    return load_agents_state(cfg.AGENTS_STATE_FILE, default_agents)


def save_agents_state(agents: list[dict[str, Any]]) -> None:
    """Save agents list to file."""
    from store_utils import _save_json
    _save_json(cfg.AGENTS_STATE_FILE, agents, lock=True)


def load_join_keys() -> dict[str, Any]:
    """Load join keys structure."""
    from store_utils import load_join_keys
    return load_join_keys(cfg.JOIN_KEYS_FILE)


def save_join_keys(keys_data: dict[str, Any]) -> None:
    """Save join keys to file."""
    from store_utils import _save_json
    _save_json(cfg.JOIN_KEYS_FILE, keys_data, lock=True)


def load_asset_positions() -> dict[str, Any]:
    """Load asset positions map."""
    from store_utils import load_asset_positions
    return load_asset_positions(cfg.ASSET_POSITIONS_FILE)


def save_asset_positions(data: dict[str, Any]) -> None:
    """Save asset positions."""
    from store_utils import _save_json
    _save_json(cfg.ASSET_POSITIONS_FILE, data, lock=True)


def load_asset_defaults() -> dict[str, Any]:
    """Load asset defaults map."""
    from store_utils import load_asset_defaults
    return load_asset_defaults(cfg.ASSET_DEFAULTS_FILE)


def save_asset_defaults(data: dict[str, Any]) -> None:
    """Save asset defaults."""
    from store_utils import _save_json
    _save_json(cfg.ASSET_DEFAULTS_FILE, data, lock=True)


def load_runtime_config() -> dict[str, Any]:
    """Load runtime config (gemini settings)."""
    from store_utils import load_runtime_config
    return load_runtime_config(cfg.RUNTIME_CONFIG_FILE)


def save_runtime_config(data: dict[str, Any]) -> None:
    """Save runtime config."""
    from store_utils import _save_json
    _save_json(cfg.RUNTIME_CONFIG_FILE, data, lock=True)


# === OpenClaw Integration ===

def get_office_name_from_identity() -> str | None:
    """Read office display name from OpenClaw workspace IDENTITY.md."""
    if not os.path.isfile(cfg.IDENTITY_FILE):
        return None
    try:
        with open(cfg.IDENTITY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"-\s*\*\*Name:\*\*\s*(.+)", content)
        if m:
            name = m.group(1).strip().replace("\r", "").split("\n")[0].strip()
            return f"{name}'s Office" if name else None
    except Exception:
        pass
    return None


# === File Operations ===

def ensure_electron_standalone_snapshot() -> None:
    """Create Electron standalone snapshot if missing."""
    target = cfg.FRONTEND_ELECTRON_STANDALONE_FILE
    if os.path.exists(target):
        return
    try:
        shutil.copy2(cfg.FRONTEND_INDEX_FILE, target)
        logger = get_logger(__name__)
        logger.info("Electron standalone snapshot created", extra={"_path": target})
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning("Failed to create Electron standalone snapshot", exc_info=True, extra={"_error": str(e)})


def _maybe_apply_random_home_favorite():
    """If AUTO_ROTATE_HOME_ON_PAGE_OPEN is enabled, randomly select a home favorite background."""
    if not cfg.AUTO_ROTATE_HOME_ON_PAGE_OPEN:
        return
    # Throttle: only rotate if at least AUTO_ROTATE_MIN_INTERVAL_SECONDS since last rotation
    # Use a file mtime as simple marker; or we can store in memory. For multi-process, file-based lock needed.
    # Simpler: skip for now, keep original behavior minimal.
    try:
        fav_dir = cfg.HOME_FAVORITES_DIR
        if not os.path.isdir(fav_dir):
            return
        images = [f for f in os.listdir(fav_dir) if f.lower().endswith(('.webp', '.png', '.jpg', '.jpeg'))]
        if not images:
            return
        chosen = random.choice(images)
        dest = os.path.join(cfg.FRONTEND_DIR, "background-home.webp")
        shutil.copy2(os.path.join(fav_dir, chosen), dest)
        logger = get_logger(__name__)
        logger.info("Auto-rotated home background", extra={"_chosen": chosen})
    except Exception:
        pass


def get_agent_memory_entries(agent_name: str, date_str: str | None = None) -> list[dict[str, Any]]:
    """
    Read memory entries for a given agent from memory/*.md files.
    Returns list of entries with 'date', 'content', 'filename'.
    """
    entries = []
    try:
        memory_dir = cfg.MEMORY_DIR
        if not os.path.isdir(memory_dir):
            return entries
        # Determine which files to read
        if date_str:
            filenames = [f"{date_str}.md"]
        else:
            # Read all .md files (sorted by date descending)
            filenames = sorted([f for f in os.listdir(memory_dir) if f.endswith(".md")], reverse=True)
        for fn in filenames[:10]:  # limit to recent 10 files
            filepath = os.path.join(memory_dir, fn)
            if not os.path.isfile(filepath):
                continue
            date_part = fn.replace(".md", "")
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            # Parse entries by agent sections (simple: look for "## Agent Name" headers)
            # This is a simplified parser; actual format may vary
            sections = re.split(r'^##\s+(.+?)$', content, flags=re.MULTILINE)
            # sections: ['', 'Agent1', 'content for agent1', 'Agent2', 'content for agent2', ...]
            for i in range(1, len(sections), 2):
                agent_header = sections[i].strip()
                agent_content = sections[i+1].strip() if i+1 < len(sections) else ""
                # Match agent name (case-insensitive, allow partial)
                if agent_name.lower() in agent_header.lower():
                    entries.append({
                        "date": date_part,
                        "agent": agent_header,
                        "content": agent_content[:500],  # truncate
                        "filename": fn,
                    })
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Memory read error for {agent_name}: {e}", exc_info=True)
    return entries


def get_soul_goals() -> list[str]:
    """
    Parse the main OpenClaw SOUL.md to extract goals/tasks.
    Returns list of task strings (from bullet points or numbered lists).
    """
    goals = []
    try:
        soul_path = os.path.join(cfg.OPENCLAW_WORKSPACE, "SOUL.md")
        if not os.path.isfile(soul_path):
            return goals
        with open(soul_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Simple extraction: lines starting with - or * or 1. 2. etc that look like tasks
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ", "9. ")):
                task = stripped[2:] if stripped[1] == ' ' else stripped[3:]
                goals.append(task)
            # Also look for "## Goals" section
        return goals[:20]  # limit to 20
    except Exception:
        return []


def _probe_animated_frame_size(upload_path: str) -> tuple[int, int] | None:
    """Probe the frame size of an animated image (webp/gif) for auto-spritesheet generation."""
    try:
        from PIL import Image as PILImage
        with PILImage.open(upload_path) as img:
            # For animated images, get the first frame size
            try:
                img.seek(0)
            except Exception:
                pass
            return img.size  # (width, height)
    except Exception:
        return None


def _ensure_magick_or_ffmpeg_available() -> str | None:
    """Check if ImageMagick (magick) or ffmpeg is available."""
    if shutil.which("magick"):
        return "magick"
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    return None


def _animated_to_spritesheet(
    upload_path: str,
    frame_w: int,
    frame_h: int,
    out_ext: str = ".webp",
    preserve_original: bool = True,
    pixel_art: bool = True,
    cols: int | None = None,
    rows: int | None = None,
) -> tuple[str, int, int, int, int, int]:
    """Convert animated GIF/WEBP to spritesheet.

    Returns:
        (output_path, columns, rows, total_frames, out_frame_w, out_frame_h)
    """
    backend = _ensure_magick_or_ffmpeg_available()
    if not backend:
        raise RuntimeError("未检测到 ImageMagick/ffmpeg，无法自动转换动图")

    ext = (out_ext or ".webp").lower()
    if ext not in {".webp", ".png"}:
        ext = ".webp"

    out_fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(out_fd)

    try:
        with tempfile.TemporaryDirectory() as td:
            frames = 0
            out_fw, out_fh = int(frame_w), int(frame_h)

            # Try using Pillow to split frames
            try:
                from PIL import Image as PILImage
                with PILImage.open(upload_path) as im:
                    n = getattr(im, "n_frames", 1)
                    if preserve_original:
                        out_fw, out_fh = im.size
                    for i in range(n):
                        im.seek(i)
                        fr = im.convert("RGBA")
                        if not preserve_original and (fr.size != (out_fw, out_fh)):
                            resample = PILImage.Resampling.NEAREST if pixel_art else PILImage.Resampling.LANCZOS
                            fr = fr.resize((out_fw, out_fh), resample)
                        fr.save(os.path.join(td, f"f_{i:04d}.png"), "PNG")
                    frames = n
            except Exception:
                frames = 0

            # Fallback to ffmpeg for frame extraction
            if frames <= 0:
                cmd1 = f"ffmpeg -y -i '{upload_path}' '{td}/f_%04d.png' >/dev/null 2>&1"
                if os.system(cmd1) != 0:
                    raise RuntimeError("动图抽帧失败（Pillow/ffmpeg 都失败）")
                files = sorted([x for x in os.listdir(td) if x.startswith("f_") and x.endswith(".png")])
                frames = len(files)
                if frames <= 0:
                    raise RuntimeError("动图无有效帧")

            # Combine frames into spritesheet
            if backend == "magick":
                quality_flag = "-define webp:lossless=true -define webp:method=6 -quality 100" if ext == ".webp" else ""
                if cols is None or cols <= 0:
                    cols_eff = frames
                else:
                    cols_eff = max(1, int(cols))
                rows_eff = max(1, int(rows)) if (rows is not None and rows > 0) else max(1, math.ceil(frames / cols_eff))

                prep = ""
                if not preserve_original:
                    magick_filter = "-filter point" if pixel_art else ""
                    prep = f" {magick_filter} -resize {out_fw}x{out_fh}^ -gravity center -background none -extent {out_fw}x{out_fh}"

                cmd = (
                    f"magick '{td}/f_*.png'{prep} "
                    f"-tile {cols_eff}x{rows_eff} -background none -geometry +0+0 {quality_flag} '{out_path}'"
                )
                rc = os.system(cmd)
                if rc != 0:
                    raise RuntimeError("ImageMagick 拼图失败")
                return out_path, cols_eff, rows_eff, frames, out_fw, out_fh

            # ffmpeg path
            ffmpeg_quality = "-lossless 1 -compression_level 6 -q:v 100" if ext == ".webp" else ""
            cols_eff = max(1, int(cols)) if (cols is not None and cols > 0) else frames
            rows_eff = max(1, int(rows)) if (rows is not None and rows > 0) else max(1, math.ceil(frames / cols_eff))
            if preserve_original:
                vf = f"tile={cols_eff}x{rows_eff}"
            else:
                scale_algo = "neighbor" if pixel_art else "lanczos"
                vf = (
                    f"scale={out_fw}:{out_fh}:force_original_aspect_ratio=decrease:flags={scale_algo},"
                    f"pad={out_fw}:{out_fh}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
                    f"tile={cols_eff}x{rows_eff}"
                )
            cmd2 = (
                f"ffmpeg -y -pattern_type glob -i '{td}/f_*.png' "
                f"-vf '{vf}' "
                f"{ffmpeg_quality} '{out_path}' >/dev/null 2>&1"
            )
            if os.system(cmd2) != 0:
                raise RuntimeError("ffmpeg 拼图失败")
            return out_path, cols_eff, rows_eff, frames, out_fw, out_fh
    except Exception:
        # Cleanup partially created file
        try:
            os.unlink(out_path)
        except Exception:
            pass
        raise
