"""Structured JSON logger for Docker/K8s compatible log ingestion.

Wraps loguru (when available) with a JSON sink so every log record is emitted
as a single-line JSON object.  Falls back gracefully to the stdlib logger
returned by logger_factory.get_logger() when loguru is not installed.

Usage::

    from langgraph_engine.core.structured_logger import get_structured_logger, set_log_context

    logger = get_structured_logger(__name__)

    # Inject per-session context (written into every subsequent log record)
    set_log_context(session_id="sess-abc123", step="step_5")

    logger.info("skill selected", skill="langgraph-core", confidence=0.91)

Environment variables:
    LOG_FORMAT   Set to "json" to activate the JSON sink (default: plain text).
    LOG_LEVEL    Minimum log level, e.g. "DEBUG", "INFO" (default: "INFO").

ASCII-only: cp1252 safe (Windows).
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# ContextVars for per-request / per-session context injection
# ---------------------------------------------------------------------------
_session_id_var: ContextVar[str] = ContextVar("session_id", default="")
_step_var: ContextVar[str] = ContextVar("step", default="")


def set_log_context(session_id: str = "", step: str = "") -> None:
    """Inject session_id and step into all subsequent log records on this thread/task."""
    _session_id_var.set(session_id)
    _step_var.set(step)


# ---------------------------------------------------------------------------
# JSON sink installation (loguru)
# ---------------------------------------------------------------------------
_json_sink_installed = False


def _install_json_sink() -> bool:
    """Install the loguru JSON sink once; return True on success."""
    global _json_sink_installed
    if _json_sink_installed:
        return True
    try:
        from loguru import logger as _loguru_logger  # noqa: F401
    except ImportError:
        return False

    try:
        from loguru import logger as _lg

        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

        def _json_sink(message: Any) -> None:
            record = message.record
            payload = {
                "ts": record["time"].astimezone(timezone.utc).isoformat(),
                "level": record["level"].name,
                "logger": record["name"],
                "message": record["message"],
                "session_id": _session_id_var.get(),
                "step": _step_var.get(),
                "file": record["file"].name,
                "line": record["line"],
                "function": record["function"],
            }
            # Merge any extra key=value pairs passed by the caller
            extra = record.get("extra", {})
            if extra:
                payload.update(extra)
            # exception info
            if record["exception"] is not None:
                exc = record["exception"]
                payload["exception"] = {
                    "type": str(exc.type.__name__) if exc.type else None,
                    "value": str(exc.value) if exc.value else None,
                }
            sys.stdout.write(json.dumps(payload) + "\n")
            sys.stdout.flush()

        # Remove default sink and replace with JSON sink
        _lg.remove()
        _lg.add(_json_sink, level=log_level, colorize=False, backtrace=False)
        _json_sink_installed = True
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def get_structured_logger(name: Optional[str] = None) -> Any:
    """Return a logger that emits JSON when LOG_FORMAT=json, plain text otherwise.

    Args:
        name: Module name for the stdlib fallback logger.

    Returns:
        loguru Logger (singleton) when LOG_FORMAT=json and loguru is installed,
        otherwise the logger returned by logger_factory.get_logger().
    """
    log_format = os.environ.get("LOG_FORMAT", "").lower()
    if log_format == "json":
        if _install_json_sink():
            try:
                from loguru import logger as _lg

                return _lg
            except ImportError:
                pass

    # Fallback: use logger_factory (loguru plain or stdlib)
    try:
        from langgraph_engine.core.logger_factory import get_logger

        return get_logger(name)
    except ImportError:
        pass

    # Last resort: stdlib
    return logging.getLogger(name or __name__)
