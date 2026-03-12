#!/usr/bin/env python3
"""Prometheus metrics collection for Star Office backend.

Provides counters, gauges, and histograms to monitor application performance
and operational health. The /metrics endpoint is served by the core blueprint.
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Define metrics
# HTTP metrics
http_requests_total = Counter(
    "staroffice_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
) if PROMETHEUS_AVAILABLE else None

http_request_duration_seconds = Histogram(
    "staroffice_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
) if PROMETHEUS_AVAILABLE else None

# Agent metrics
agent_count = Gauge(
    "staroffice_agents_total",
    "Total number of agents",
    ["state"],
) if PROMETHEUS_AVAILABLE else None

stale_agents_count = Gauge(
    "staroffice_stale_agents_total",
    "Number of stale (unresponsive) agents",
) if PROMETHEUS_AVAILABLE else None

# Storage metrics
json_write_duration_seconds = Histogram(
    "staroffice_json_write_duration_seconds",
    "Duration of JSON write operations (with lock)",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
) if PROMETHEUS_AVAILABLE else None

# Asset upload metrics
asset_upload_total = Counter(
    "staroffice_asset_uploads_total",
    "Total number of asset uploads",
    ["extension"],
) if PROMETHEUS_AVAILABLE else None

# Gemini generation metrics
gemini_generation_total = Counter(
    "staroffice_gemini_generation_total",
    "Total number of Gemini image generation requests",
    ["status"],
) if PROMETHEUS_AVAILABLE else None


def record_http_request(method: str, endpoint: str, status: int, duration_seconds: float) -> None:
    """Record an HTTP request for metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
    try:
        http_requests_total.labels(method=method, endpoint=endpoint, status=str(status)).inc()
        if duration_seconds >= 0:
            http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration_seconds)
    except Exception:
        pass  # Never fail the app because of metrics


def update_agent_metrics(agents: list[dict[str, Any]]) -> None:
    """Update agent-related gauges based on current agents list."""
    if not PROMETHEUS_AVAILABLE:
        return
    try:
        # Reset counts
        for state in ["idle", "writing", "researching", "executing", "syncing", "error"]:
            agent_count.labels(state=state).set(0)
        # Count agents by state
        state_counts: dict[str, int] = {}
        stale = 0
        now = __import__('datetime').datetime.now()
        for a in agents:
            if a.get("isMain"):
                continue
            s = a.get("state", "idle")
            state_counts[s] = state_counts.get(s, 0) + 1
            # Check staleness
            last = a.get("lastPushAt") or a.get("updated_at")
            if last:
                try:
                    dt = __import__('datetime').datetime.fromisoformat(last.replace("Z", "+00:00"))
                    age = (now - dt).total_seconds()
                    if age > 600 and s != "idle":
                        stale += 1
                except Exception:
                    pass
        for s, c in state_counts.items():
            agent_count.labels(state=s).set(c)
        stale_agents_count.set(stale)
    except Exception:
        pass


def record_json_write(operation: str, duration_seconds: float) -> None:
    """Record duration of a JSON write operation."""
    if not PROMETHEUS_AVAILABLE:
        return
    try:
        json_write_duration_seconds.labels(operation=operation).observe(duration_seconds)
    except Exception:
        pass


def record_asset_upload(extension: str) -> None:
    """Record an asset upload."""
    if not PROMETHEUS_AVAILABLE:
        return
    try:
        asset_upload_total.labels(extension=extension).inc()
    except Exception:
        pass


def record_gemini_generation(status: str) -> None:
    """Record a Gemini image generation request outcome."""
    if not PROMETHEUS_AVAILABLE:
        return
    try:
        gemini_generation_total.labels(status=status).inc()
    except Exception:
        pass


def get_metrics() -> bytes:
    """Return Prometheus-formatted metrics data."""
    if not PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not available\n"
    return generate_latest(REGISTRY)
