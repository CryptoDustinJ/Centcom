"""Pytest configuration and fixtures for Star Office tests."""

import sys
import os

# Ensure backend module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Override config paths to use temporary directory."""
    from backend import config as cfgmod
    monkeypatch.setattr(cfgmod, 'ROOT_DIR', str(tmp_path))
    monkeypatch.setattr(cfgmod, 'STATE_FILE', os.path.join(str(tmp_path), 'state.json'))
    monkeypatch.setattr(cfgmod, 'AGENTS_STATE_FILE', os.path.join(str(tmp_path), 'agents-state.json'))
    monkeypatch.setattr(cfgmod, 'JOIN_KEYS_FILE', os.path.join(str(tmp_path), 'join-keys.json'))
    monkeypatch.setattr(cfgmod, 'FRONTEND_DIR', os.path.join(str(tmp_path), 'frontend'))
    os.makedirs(cfgmod.FRONTEND_DIR, exist_ok=True)
    yield
