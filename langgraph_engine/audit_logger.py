"""Append-only audit log for sensitive pipeline operations.

Writes one JSON line per audited event to AUDIT_LOG_PATH (env var, default:
./audit.log). Uses Python's logging.handlers.TimedRotatingFileHandler for
daily rotation.

Usage:
    from langgraph_engine.audit_logger import audit_log
    audit_log("pipeline_start", session_id, "pipeline", "success", {"task": "..."})
"""

import json
import logging
import logging.handlers
import os
import threading
from datetime import datetime
from pathlib import Path

# Set of operation names that are accepted by audit_log.
# Calls with operations not in this set are dropped with a WARNING.
AUDITABLE_OPERATIONS = {
    "pipeline_start",
    "llm_call_made",
    "github_issue_created",
    "branch_created",
    "pr_merged",
    "secrets_validated",
    "rate_limit_hit",
}

# Keys whose values are replaced with "[REDACTED]" in metadata dicts.
# Matching is case-insensitive substring.
_SENSITIVE_KEY_SUBSTRINGS = ("key", "token", "secret", "password")

# Module-level state for lazy init
_audit_logger = None  # type: logging.Logger
_init_lock = threading.Lock()


def _redact_metadata(metadata):
    # type: (dict) -> dict
    """Return a copy of metadata with sensitive values replaced by [REDACTED].

    A key is considered sensitive if it contains any of the strings in
    _SENSITIVE_KEY_SUBSTRINGS (case-insensitive).

    Args:
        metadata: Original metadata dict. Values may be any JSON-serialisable
                  type; only string values are replaced (non-strings are kept).

    Returns:
        New dict with sensitive values redacted. The original dict is not
        modified.
    """
    redacted = {}
    for k, v in metadata.items():
        lower_key = k.lower() if isinstance(k, str) else ""
        if any(sub in lower_key for sub in _SENSITIVE_KEY_SUBSTRINGS):
            redacted[k] = "[REDACTED]"
        else:
            redacted[k] = v
    return redacted


def _get_audit_logger():
    # type: () -> logging.Logger
    """Return the audit logger, initialising it lazily on the first call.

    Thread-safe via _init_lock. Uses TimedRotatingFileHandler rotating at
    midnight with 30 backup files retained.
    """
    global _audit_logger

    if _audit_logger is not None:
        return _audit_logger

    with _init_lock:
        # Double-checked locking
        if _audit_logger is not None:
            return _audit_logger

        log_path = Path(os.environ.get("AUDIT_LOG_PATH", "./audit.log"))

        # Ensure parent directory exists
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # Fall back to current dir; handler will fail loudly if needed

        handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_path),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
            delay=True,  # do not open file until first emit
        )
        # Raw format: write the message as-is (we pre-build JSON)
        handler.setFormatter(logging.Formatter("%(message)s"))

        audit_log_instance = logging.getLogger("claude_workflow_engine.audit")
        audit_log_instance.setLevel(logging.INFO)
        # Prevent propagation to the root logger to avoid duplicate output
        audit_log_instance.propagate = False

        if not audit_log_instance.handlers:
            audit_log_instance.addHandler(handler)

        _audit_logger = audit_log_instance

    return _audit_logger


def audit_log(operation, actor, resource, outcome, metadata=None):
    # type: (str, str, str, str, dict) -> None
    """Write a single audit event as a JSON line to the audit log file.

    Args:
        operation: Operation name. Must be in AUDITABLE_OPERATIONS; if not,
                   a WARNING is logged and the call is silently dropped.
        actor: Identity performing the operation (e.g. session_id, user name).
        resource: Resource being acted upon (e.g. "pipeline", "github_issue").
        outcome: Outcome of the operation (e.g. "success", "failure").
        metadata: Optional dict of additional context. Values whose keys
                  contain "key", "token", "secret", or "password" are
                  automatically redacted before writing.
    """
    if operation not in AUDITABLE_OPERATIONS:
        logging.getLogger(__name__).warning(
            "audit_log called with unrecognised operation '%s'; dropping event.",
            operation,
        )
        return

    safe_metadata = _redact_metadata(metadata) if metadata else {}

    record = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
        "operation": operation,
        "actor": actor,
        "resource": resource,
        "outcome": outcome,
        "metadata": safe_metadata,
    }

    try:
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        logging.getLogger(__name__).error(
            "Failed to serialise audit record for operation '%s': %s",
            operation,
            exc,
        )
        return

    _get_audit_logger().info(line)
