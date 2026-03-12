#!/usr/bin/env python3
"""Rate limiting utilities for protecting API endpoints.

Uses the 'limits' library with pluggable storage: Redis if available, otherwise in-memory.
Provides a decorator to apply limits per route with configurable strategies.
"""

from __future__ import annotations

import functools
import os
import time
from typing import Any, Callable, Optional

# Optional dependency: limits library may not be available in some environments
try:
    import limits
    import limits.strategies
    import limits.storage
    HAS_LIMITS = True
except ImportError:
    HAS_LIMITS = False

from flask import request, jsonify, current_app, g

# Default limits (can be overridden by decorator)
DEFAULT_LIMITS = {
    # format: (max_requests, window_seconds)
    "global": (100, 60),  # 100 req/min globally
    "join_agent": (10, 300),  # 10 req/5min
    "agent_push": (60, 60),  # 60 req/min
    "assets_upload": (30, 60),  # 30 req/min
    "set_state": (120, 60),  # 120 req/min
    "agents": (60, 60),  # 60 req/min
}

# Redis connection URL from env
REDIS_URL = os.getenv("REDIS_URL")

if HAS_LIMITS:
    # Global storage instance (initialized lazily)
    _storage: Optional[limits.storage.Storage] = None
    def _get_storage() -> limits.storage.Storage:
        """Get or initialize rate limit storage backend."""
        global _storage
        if _storage is None:
            if REDIS_URL:
                try:
                    import redis
                    _storage = limits.storage.RedisStorage(REDIS_URL)
                except Exception as e:
                    current_app.logger.warning(f"Redis storage init failed, falling back to memory: {e}")
                    _storage = limits.storage.MemoryStorage()
            else:
                current_app.logger.info("REDIS_URL not set, using in-memory rate limiter (not shared across workers)")
                _storage = limits.storage.MemoryStorage()
        return _storage

    def _make_limiter(max_requests: int, window_seconds: int):
        """Create a rate limiter with sliding window strategy."""
        return limits.Limit(
            f"{max_requests}/{window_seconds}",
            strategy=limits.strategies.MovingWindowRateLimiter,
        )
else:
    # Dummy implementations when limits is not available
    _storage = None
    def _get_storage():
        return None
    def _make_limiter(max_requests: int, window_seconds: int):
        class DummyLimiter:
            def get_meta_key(self, key):
                return key
            def hit(self, key, window):
                return True, max_requests, 0
        return DummyLimiter()

def rate_limit(max_requests: int, window_seconds: int, key_func: Optional[Callable[[], str]] = None):
    """
    Decorator to apply rate limiting to a Flask route.

    Args:
        max_requests: Maximum requests allowed in the window
        window_seconds: Time window in seconds
        key_func: Function that returns a string key for the limit (default: per-IP)
                  Use None for global (same for everyone), or pass custom function

    Example:
        @app.route("/api")
        @rate_limit(10, 60)  # 10/min per IP
        def my_endpoint():
            return "OK"
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            limiter = _make_limiter(max_requests, window_seconds)

            # Determine the key
            if key_func is None:
                # Default: per-IP with optional agent_id override
                ip = request.remote_addr or "unknown"
                # Check if we have an agent_id in the request that could be used for finer limit
                # We'll use IP:agent_id if agent_id present, else just IP
                agent_id = None
                if request.method == "POST":
                    try:
                        data = request.get_json(silent=True) or {}
                        agent_id = data.get("agentId")
                    except Exception:
                        pass
                key = f"ip:{ip}" + (f":agent:{agent_id}" if agent_id else "")
            else:
                key = key_func()

            storage = _get_storage()
            try:
                is_allowed, remaining, reset = limiter.hit(limiter.get_meta_key(key), window_seconds)
            except Exception as e:
                # If rate limiter storage fails, log and allow (fail open)
                current_app.logger.error(f"Rate limiter error: {e}")
                return func(*args, **kwargs)

            if not is_allowed:
                current_app.logger.warning(f"Rate limit exceeded: {key} ({max_requests}/{window_seconds}s)")
                response = jsonify({
                    "ok": False,
                    "msg": "Rate limit exceeded",
                    "retry_after": reset,
                })
                response.status_code = 429
                # Add standard retry-after header (seconds)
                response.headers["Retry-After"] = str(reset)
                return response

            # Attach rate limit info to response headers ( informational )
            response = func(*args, **kwargs)
            if isinstance(response, tuple):
                resp_obj, status = response
                if hasattr(resp_obj, 'headers'):
                    resp_obj.headers["X-RateLimit-Limit"] = str(max_requests)
                    resp_obj.headers["X-RateLimit-Remaining"] = str(remaining)
                    resp_obj.headers["X-RateLimit-Reset"] = str(reset)
            elif hasattr(response, 'headers'):
                response.headers["X-RateLimit-Limit"] = str(max_requests)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(reset)

            return response

        # Attach metadata for debugging
        wrapper._rate_limit = (max_requests, window_seconds)  # type: ignore
        return wrapper

    return decorator


# Convenience functions for common limiters
def limit_per_ip(max_requests: int, window_seconds: int):
    """Rate limit per IP address."""
    return rate_limit(max_requests, window_seconds)

def limit_global(max_requests: int, window_seconds: int):
    """Global rate limit (same for all)."""
    return rate_limit(max_requests, window_seconds, key_func=lambda: "global")
