#!/usr/bin/env python3
"""File-based locking utilities for safe concurrent access to JSON data files.

Provides a simple wrapper around filelock.FileLock with sensible defaults
for Star Office UI use cases.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from filelock import FileLock, Timeout

# Default lock timeout: 60 seconds (waits for lock before raising Timeout)
DEFAULT_LOCK_TIMEOUT = 60

# Default lock age safety check: if lock file is older than this, consider it stale
# (in case a process died without cleanup). Set to 2x typical operation time.
DEFAULT_LOCK_MAX_AGE = 120


class LockError(Exception):
    """Raised when file lock cannot be acquired within timeout or is stale."""

    pass


def _lock_path(path: str) -> str:
    """Generate lock file path for a given data file."""
    p = Path(path)
    return str(p.parent / f".{p.name}.lock")


def safe_write_lock(path: str, timeout: float = DEFAULT_LOCK_TIMEOUT) -> FileLock:
    """
    Acquire an exclusive write lock on the given file path.

    Args:
        path: Path to the file to lock
        timeout: Maximum seconds to wait for lock (default 60)

    Returns:
        FileLock object (use as context manager)

    Raises:
        LockError: If lock cannot be acquired within timeout or is stale
    """
    lock_path = _lock_path(path)
    lock = FileLock(lock_path, timeout=timeout)

    try:
        lock.acquire()
        # After acquiring, check if the lock file is too old (stale lock from dead process)
        if os.path.exists(lock_path):
            lock_age = time.time() - os.path.getmtime(lock_path)
            if lock_age > DEFAULT_LOCK_MAX_AGE:
                lock.release()
                raise LockError(f"Stale lock file detected (age: {lock_age:.1f}s). "
                                f"Path: {path}")
        return lock
    except Timeout as e:
        raise LockError(f"Lock timeout after {timeout}s for {path}") from e


def safe_read_lock(path: str, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Optional[FileLock]:
    """
    Acquire a shared read lock. For JSON loads, we typically don't need locking
    since reads are concurrent-safe. However, if you want to ensure the file
    isn't being written during a read (for atomic replace scenarios), use this.

    Args:
        path: Path to the file to lock
        timeout: Maximum seconds to wait for lock

    Returns:
        FileLock object or None if file doesn't exist (no lock needed)
    """
    if not os.path.exists(path):
        return None

    lock_path = _lock_path(path)
    lock = FileLock(lock_path, timeout=timeout)

    try:
        lock.acquire()
        if os.path.exists(lock_path):
            lock_age = time.time() - os.path.getmtime(lock_path)
            if lock_age > DEFAULT_LOCK_MAX_AGE:
                lock.release()
                raise LockError(f"Stale lock file detected (age: {lock_age:.1f}s). "
                                f"Path: {path}")
        return lock
    except Timeout as e:
        raise LockError(f"Lock timeout after {timeout}s for {path}") from e


def cleanup_stale_locks(directory: str, max_age: float = DEFAULT_LOCK_MAX_AGE) -> int:
    """
    Remove stale lock files in the given directory.
    Called periodically by cleanup thread if needed.

    Args:
        directory: Directory to scan for .*.lock files
        max_age: Maximum age in seconds before considering lock stale

    Returns:
        Number of stale locks removed
    """
    removed = 0
    now = time.time()
    try:
        for entry in Path(directory).glob(".*.lock"):
            if entry.is_file():
                age = now - entry.stat().st_mtime
                if age > max_age:
                    entry.unlink(missing_ok=True)
                    removed += 1
    except Exception:
        pass  # Best effort
    return removed
