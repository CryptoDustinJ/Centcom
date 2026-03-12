#!/usr/bin/env python3
"""Input validation and output sanitization utilities.

Prevents XSS, injection, and data integrity issues by validating all external inputs
and sanitizing data before rendering in HTML context.
"""

from __future__ import annotations

import html
import os
import re
from typing import Optional

# Constants
MAX_AGENT_NAME_LENGTH = 50
MAX_DETAIL_LENGTH = 500
MAX_JOIN_KEY_LENGTH = 64

# Validation regex patterns
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-_]{1,50}$")
SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9._\-]+$")
NO_CONTROL_CHARS = re.compile(r"[\x00-\x1F\x7F]")


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def _strip_control_chars(text: str) -> str:
    """Remove any control characters (ASCII 0-31, 127)."""
    return NO_CONTROL_CHARS.sub("", text)


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags using a simple regex. For complex cases, consider bleach."""
    # This regex matches <tag> and </tag> but preserves content
    return re.sub(r"<[^>]*>", "", text)


def validate_agent_name(name: str) -> str:
    """
    Validate agent display name.

    Rules:
    - Required, non-empty after stripping
    - Max 50 characters
    - No control characters
    - Strip any HTML tags (defense in depth)
    - Basic printable character check (no unicode control)

    Args:
        name: Raw agent name from user input

    Returns:
        Sanitized agent name

    Raises:
        ValidationError: If name is invalid
    """
    if not isinstance(name, str):
        raise ValidationError("Agent name must be a string")

    # Strip leading/trailing whitespace and control chars
    name = _strip_control_chars(name.strip())

    if not name:
        raise ValidationError("Agent name cannot be empty")

    if len(name) > MAX_AGENT_NAME_LENGTH:
        raise ValidationError(f"Agent name too long (max {MAX_AGENT_NAME_LENGTH} chars)")

    # Strip HTML tags (XSS prevention)
    name = _strip_html_tags(name)

    if not name.strip():
        raise ValidationError("Agent name cannot be empty after sanitization")

    # Additional check: should not contain obvious XSS patterns
    dangerous_patterns = ["script", "javascript:", "data:", "onerror=", "onload="]
    name_lower = name.lower()
    for pattern in dangerous_patterns:
        if pattern in name_lower:
            raise ValidationError(f"Agent name contains prohibited pattern: {pattern}")

    return name


def validate_state_detail(detail: str) -> str:
    """
    Validate state detail description.

    Rules:
    - Optional (can be empty)
    - Max 500 characters
    - Strip control characters
    - Escape HTML entities (for safe rendering in HTML context)

    Args:
        detail: Raw detail from user input

    Returns:
        Sanitized detail string (with HTML entities escaped)
    """
    if not isinstance(detail, str):
        raise ValidationError("Detail must be a string")

    detail = detail.strip()
    if not detail:
        return ""

    if len(detail) > MAX_DETAIL_LENGTH:
        raise ValidationError(f"Detail too long (max {MAX_DETAIL_LENGTH} chars)")

    # Strip control chars
    detail = _strip_control_chars(detail)

    # Escape HTML entities so it's safe to put in innerHTML
    detail = html.escape(detail, quote=True)

    return detail


def validate_invite_code(code: str) -> str:
    """
    Validate join key/invite code format.

    Rules:
    - Required, non-empty
    - Max 64 chars (prevents DoS with huge strings)
    - Alphanumeric + underscores/dashes only
    - No whitespace
    """
    if not isinstance(code, str):
        raise ValidationError("Invite code must be a string")

    code = code.strip()
    if not code:
        raise ValidationError("Invite code cannot be empty")

    if len(code) > MAX_JOIN_KEY_LENGTH:
        raise ValidationError(f"Invite code too long (max {MAX_JOIN_KEY_LENGTH} chars)")

    if not re.match(r"^[a-zA-Z0-9\-_]+$", code):
        raise ValidationError("Invite code can only contain letters, numbers, hyphens, underscores")

    return code


def validate_agent_id(agent_id: str) -> str:
    """
    Validate agent ID (UUID or alphanumeric identifier).

    Rules:
    - Required
    - 1-128 chars
    - Alphanumeric + hyphens/underscores/dots only (UUID format allowed)
    """
    if not isinstance(agent_id, str):
        raise ValidationError("Agent ID must be a string")

    agent_id = agent_id.strip()
    if not agent_id:
        raise ValidationError("Agent ID cannot be empty")

    if len(agent_id) > 128:
        raise ValidationError("Agent ID too long")

    if not re.match(r"^[a-zA-Z0-9\-_\.]+$", agent_id):
        raise ValidationError("Agent ID contains invalid characters")

    return agent_id


def sanitize_filename(filename: str) -> str:
    """
    Sanitize uploaded filename to prevent directory traversal.

    Rules:
    - Only allow safe characters (alphanumeric, dash, underscore, dot)
    - Reject paths with ".." or "/" or "\\" or absolute paths
    - Return basename only
    """
    if not isinstance(filename, str):
        raise ValidationError("Filename must be a string")

    filename = filename.strip()
    if not filename:
        raise ValidationError("Filename cannot be empty")

    # Reject any path separators or parent directory references
    if any(sep in filename for sep in ["..", "/", "\\", "\x00"]):
        raise ValidationError("Filename contains prohibited characters")

    # Allow only safe characters
    if not SAFE_FILENAME_PATTERN.match(filename):
        raise ValidationError("Filename contains invalid characters")

    # Get basename (remove any path components that might have slipped through)
    filename = os.path.basename(filename)

    return filename


def validate_file_extension(filename: str, allowed_extensions: set[str]) -> str:
    """
    Validate file extension against allowed set.

    Args:
        filename: Sanitized filename (from sanitize_filename)
        allowed_extensions: Set of allowed extensions (e.g., {'.png', '.webp'})

    Returns:
        Lowercase extension (including dot) if valid

    Raises:
        ValidationError: If extension not in allowed set
    """
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        raise ValidationError("File has no extension")
    if ext not in allowed_extensions:
        raise ValidationError(f"File extension '{ext}' not allowed. Allowed: {', '.join(sorted(allowed_extensions))}")
    return ext


def validate_api_key(key: str) -> str:
    """
    Validate API key format.

    Rules:
    - Non-empty
    - Stripped
    - At least 8 characters
    - No control characters
    """
    if not isinstance(key, str):
        raise ValidationError("API key must be a string")

    key = key.strip()
    if not key:
        raise ValidationError("API key cannot be empty")

    if len(key) < 8:
        raise ValidationError("API key too short")

    key = _strip_control_chars(key)

    return key
