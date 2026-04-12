"""Sentry error tracking integration for the Claude Workflow Engine pipeline.

Provides:
- init_sentry(): configure sentry_sdk with DSN, release, and environment
- capture_exception(exc, step, session_id, metadata): report an exception
- capture_message(msg, level): report a plain message

All functions degrade gracefully to no-ops when sentry_sdk is not installed
or SENTRY_DSN is not set, so callers never need to guard with try/except.

Usage::

    from langgraph_engine.error_tracking import (
        init_sentry, capture_exception, capture_message
    )

    init_sentry()  # call once at startup

    try:
        result = risky_operation()
    except ValueError as exc:
        capture_exception(exc, step="step_5", session_id=sid, metadata={"task": task})
        raise

Environment variables:
    SENTRY_DSN   Sentry Data Source Name.  When empty, tracking is disabled.
    APP_ENV      Deployment environment tag (default: "production").

ASCII-only: cp1252 safe (Windows).
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional sentry_sdk import
# ---------------------------------------------------------------------------
_HAS_SENTRY = False

try:
    import sentry_sdk as _sentry_sdk

    _HAS_SENTRY = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_sentry_initialized = False
_RELEASE = "1.6.1"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_sentry(dsn: Optional[str] = None) -> bool:
    """Initialise the Sentry SDK.

    Safe to call multiple times; subsequent calls are no-ops.

    Args:
        dsn: Sentry DSN.  When None, reads SENTRY_DSN env var.

    Returns:
        True if Sentry was successfully initialised, False otherwise.
    """
    global _sentry_initialized

    if _sentry_initialized:
        return True

    if not _HAS_SENTRY:
        logger.debug("sentry_sdk not installed; error tracking disabled. " "Install: pip install sentry-sdk")
        return False

    resolved_dsn = dsn or os.environ.get("SENTRY_DSN", "")
    if not resolved_dsn:
        logger.debug("SENTRY_DSN not set; Sentry error tracking disabled")
        return False

    environment = os.environ.get("APP_ENV", "production")

    try:
        _sentry_sdk.init(
            dsn=resolved_dsn,
            release=_RELEASE,
            environment=environment,
            # Avoid sending PII by default
            send_default_pii=False,
            # Capture 10% of transactions for performance monitoring
            traces_sample_rate=0.1,
        )
        _sentry_initialized = True
        logger.info("Sentry initialised (release=%s, environment=%s)", _RELEASE, environment)
        return True
    except Exception as exc:
        logger.warning("Failed to initialise Sentry: %s", exc)
        return False


def capture_exception(
    exc: BaseException,
    step: str = "unknown",
    session_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Capture an exception and send it to Sentry with context tags.

    Args:
        exc:        The exception to report.
        step:       Pipeline step name where the error occurred (e.g. "step_5").
        session_id: Current session identifier (used as a Sentry tag).
        metadata:   Arbitrary key/value pairs attached as extras.
                    Total serialised length is truncated to 500 characters.
    """
    if not (_HAS_SENTRY and _sentry_initialized):
        return

    try:
        with _sentry_sdk.push_scope() as scope:
            scope.set_tag("step", step)
            if session_id:
                scope.set_tag("session_id", session_id)
            scope.set_tag("release", _RELEASE)

            if metadata:
                # Truncate total extras to 500 chars to avoid oversized payloads
                extras_str = str(metadata)
                if len(extras_str) > 500:
                    metadata = {"_truncated": extras_str[:497] + "..."}
                for key, value in metadata.items():
                    scope.set_extra(key, value)

            _sentry_sdk.capture_exception(exc)
    except Exception as inner:
        logger.debug("Sentry capture_exception failed: %s", inner)


def capture_message(msg: str, level: str = "warning") -> None:
    """Send a plain message to Sentry.

    Args:
        msg:   Human-readable message string.
        level: Sentry level string: "debug", "info", "warning", "error", "fatal".
    """
    if not (_HAS_SENTRY and _sentry_initialized):
        return

    try:
        _sentry_sdk.capture_message(msg, level=level)
    except Exception as exc:
        logger.debug("Sentry capture_message failed: %s", exc)
