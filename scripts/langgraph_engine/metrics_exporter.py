"""Prometheus metrics exporter for the Claude Workflow Engine pipeline.

Exposes 8 metrics covering pipeline execution, step durations,
LLM inference, MCP tool calls, call graph rebuilds, and active pipeline count.

The HTTP metrics server is started automatically when ENABLE_METRICS=1 is set
in the environment.  All metric functions degrade gracefully to no-ops when
prometheus_client is not installed.

Usage::

    from scripts.langgraph_engine.metrics_exporter import (
        inc_pipeline_executions,
        observe_pipeline_duration,
        observe_step_duration,
        inc_llm_calls,
        inc_llm_tokens,
        inc_mcp_tool_calls,
        inc_call_graph_rebuild,
        set_active_pipelines,
        start_metrics_server,
    )

    inc_pipeline_executions(status="success")
    observe_pipeline_duration(seconds=42.3, task_type="feature")

Environment variables:
    ENABLE_METRICS   Set to "1" to start the Prometheus HTTP server on import.
    METRICS_PORT     Port for the HTTP server (default: 9090).

ASCII-only: cp1252 safe (Windows).
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional prometheus_client import
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Gauge, Histogram
    from prometheus_client import start_http_server as _prom_start_http

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------
if _HAS_PROMETHEUS:
    pipeline_executions_total = Counter(
        "pipeline_executions_total",
        "Total number of pipeline executions",
        ["status"],  # success | failure | cancelled
    )

    pipeline_duration_seconds = Histogram(
        "pipeline_duration_seconds",
        "End-to-end pipeline execution time in seconds",
        ["task_type"],  # feature | bugfix | refactor | unknown
        buckets=[30, 60, 120, 300, 600],
    )

    step_duration_seconds = Histogram(
        "step_duration_seconds",
        "Duration of each pipeline step in seconds",
        ["step_name"],  # step_0 .. step_14
        buckets=[1, 5, 10, 30, 60, 120],
    )

    llm_calls_total = Counter(
        "llm_calls_total",
        "Total LLM inference calls",
        ["provider", "model"],  # anthropic/claude-sonnet-4-6, claude_cli/sonnet, etc.
    )

    llm_tokens_total = Counter(
        "llm_tokens_total",
        "Total tokens consumed across all LLM calls",
        ["provider", "direction"],  # direction: input | output
    )

    mcp_tool_calls_total = Counter(
        "mcp_tool_calls_total",
        "Total MCP tool invocations",
        ["server", "tool"],
    )

    call_graph_rebuild_total = Counter(
        "call_graph_rebuild_total",
        "Number of call graph rebuild operations triggered",
        ["reason"],  # stale | forced | initial
    )

    active_pipelines = Gauge(
        "active_pipelines",
        "Number of pipeline instances currently executing",
    )
else:
    # Sentinel objects so callers never need to guard with _HAS_PROMETHEUS checks
    pipeline_executions_total = None  # type: ignore[assignment]
    pipeline_duration_seconds = None  # type: ignore[assignment]
    step_duration_seconds = None  # type: ignore[assignment]
    llm_calls_total = None  # type: ignore[assignment]
    llm_tokens_total = None  # type: ignore[assignment]
    mcp_tool_calls_total = None  # type: ignore[assignment]
    call_graph_rebuild_total = None  # type: ignore[assignment]
    active_pipelines = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Public convenience functions (always safe to call)
# ---------------------------------------------------------------------------


def inc_pipeline_executions(status: str = "success") -> None:
    """Increment the pipeline execution counter."""
    if _HAS_PROMETHEUS and pipeline_executions_total is not None:
        pipeline_executions_total.labels(status=status).inc()


def observe_pipeline_duration(seconds: float, task_type: str = "unknown") -> None:
    """Record end-to-end pipeline duration."""
    if _HAS_PROMETHEUS and pipeline_duration_seconds is not None:
        pipeline_duration_seconds.labels(task_type=task_type).observe(seconds)


def observe_step_duration(step_name: str, seconds: float) -> None:
    """Record the duration of a named pipeline step."""
    if _HAS_PROMETHEUS and step_duration_seconds is not None:
        step_duration_seconds.labels(step_name=step_name).observe(seconds)


def inc_llm_calls(provider: str = "unknown", model: str = "unknown") -> None:
    """Increment the LLM call counter."""
    if _HAS_PROMETHEUS and llm_calls_total is not None:
        llm_calls_total.labels(provider=provider, model=model).inc()


def inc_llm_tokens(
    count: int,
    provider: str = "unknown",
    direction: str = "input",
) -> None:
    """Add token count to the LLM tokens counter."""
    if _HAS_PROMETHEUS and llm_tokens_total is not None:
        llm_tokens_total.labels(provider=provider, direction=direction).inc(count)


def inc_mcp_tool_calls(server: str = "unknown", tool: str = "unknown") -> None:
    """Increment the MCP tool call counter."""
    if _HAS_PROMETHEUS and mcp_tool_calls_total is not None:
        mcp_tool_calls_total.labels(server=server, tool=tool).inc()


def inc_call_graph_rebuild(reason: str = "stale") -> None:
    """Increment the call graph rebuild counter."""
    if _HAS_PROMETHEUS and call_graph_rebuild_total is not None:
        call_graph_rebuild_total.labels(reason=reason).inc()


def set_active_pipelines(count: int) -> None:
    """Set the gauge for active pipeline instances."""
    if _HAS_PROMETHEUS and active_pipelines is not None:
        active_pipelines.set(count)


# ---------------------------------------------------------------------------
# HTTP server startup
# ---------------------------------------------------------------------------

_server_started = False


def start_metrics_server(port: Optional[int] = None) -> bool:
    """Start the Prometheus HTTP metrics server.

    Args:
        port: TCP port to listen on.  Defaults to METRICS_PORT env var or 9090.

    Returns:
        True if the server started successfully, False otherwise.
    """
    global _server_started
    if _server_started:
        return True
    if not _HAS_PROMETHEUS:
        logger.warning("prometheus_client not installed; metrics server not started")
        return False

    if os.environ.get("ENABLE_METRICS", "0") != "1":
        return False

    if port is None:
        port = int(os.environ.get("METRICS_PORT", "9090"))

    try:
        _prom_start_http(port)
        _server_started = True
        logger.info("Prometheus metrics server started on port %d", port)
        return True
    except Exception as exc:
        logger.warning("Failed to start metrics server on port %d: %s", port, exc)
        return False
