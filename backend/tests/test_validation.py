"""Tests for validation module."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from validation import (
    validate_agent_name,
    validate_state_detail,
    validate_invite_code,
    validate_agent_id,
    sanitize_filename,
    ValidationError,
)

def test_validate_agent_name_accepts_valid():
    assert validate_agent_name("Alice") == "Alice"
    assert validate_agent_name("Bob-123_Test") == "Bob-123_Test"

def test_validate_agent_name_rejects_empty():
    try:
        validate_agent_name("")
        assert False, "Should raise"
    except ValidationError as e:
        assert "empty" in str(e).lower()

def test_validate_agent_name_rejects_too_long():
    long_name = "a" * 51
    try:
        validate_agent_name(long_name)
        assert False, "Should raise"
    except ValidationError:
        pass

def test_validate_state_detail_accepts_valid():
    assert validate_state_detail("Working on feature") == "Working on feature"
    # HTML escaping
    assert validate_state_detail("<script>") == "&lt;script&gt;"

def test_validate_state_detail_rejects_too_long():
    long_detail = "a" * 501
    try:
        validate_state_detail(long_detail)
        assert False, "Should raise"
    except ValidationError:
        pass

def test_validate_invite_code_accepts_valid():
    assert validate_invite_code("ocj_team_01") == "ocj_team_01"

def test_validate_invite_code_rejects_with_slash():
    try:
        validate_invite_code("abc/def")
        assert False, "Should raise"
    except ValidationError:
        pass

def test_sanitize_filename_rejects_path_traversal():
    try:
        sanitize_filename("../../etc/passwd")
        assert False, "Should raise"
    except ValidationError:
        pass

def test_sanitize_filename_accepts_simple():
    assert sanitize_filename("image.webp") == "image.webp"

def test_validate_agent_id_accepts_valid():
    assert validate_agent_id("abc123def456") == "abc123def456"

def test_validate_agent_id_rejects_too_long():
    long_id = "a" * 129
    try:
        validate_agent_id(long_id)
        assert False
    except ValidationError:
        pass
