"""Error handling decorators and result builders for pipeline nodes and functions.

This module extracts the try/except-with-timing pattern that is repeated 50+
times across 30 pipeline files and replaces it with two focused decorators plus
a fluent result builder.

Design patterns used
--------------------
Decorator Pattern (GoF): node_error_handler and safe_execute wrap functions
with cross-cutting concerns (timing, logging, fallback) without modifying the
wrapped function itself.

Builder Pattern (GoF): NodeResult provides a fluent API for constructing the
state-update dicts that LangGraph node functions must return, avoiding ad-hoc
dict literals scattered throughout node implementations.
"""

import functools
import sys
import time
from typing import Any, Callable, Dict, Optional

from .logger_factory import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# node_error_handler
# ---------------------------------------------------------------------------


def node_error_handler(
    node_name: str,
    fallback_result: Optional[Dict[str, Any]] = None,
    log_to_stderr: bool = True,
) -> Callable:
    """Decorator for LangGraph node functions with standardised error handling.

    Wraps a node function (state -> dict) with:
    - try/except with graceful degradation
    - wall-clock execution timing
    - consistent log format: [node_name] OK/FAILED (Xms)
    - fallback result dict on failure

    Args:
        node_name:       Human-readable name used in log messages.
        fallback_result: Dict to merge with {"error": str} on failure.
                         When None only {"error": str} is returned.
        log_to_stderr:   Also print failures to stderr for visibility in
                         environments where the logger output is redirected.

    Returns:
        A decorator that wraps a node function.

    Usage::

        @node_error_handler("level1_session", fallback_result={"session_loaded": False})
        def node_session_loader(state: FlowState) -> dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
            start = time.time()
            try:
                result = func(state, *args, **kwargs)
                duration = time.time() - start
                logger.debug("[%s] OK (%.0fms)" % (node_name, duration * 1000))
                return result if result is not None else {}
            except Exception as exc:
                duration = time.time() - start
                error_msg = "%s: %s" % (type(exc).__name__, str(exc))
                logger.error("[%s] FAILED (%.0fms): %s" % (node_name, duration * 1000, error_msg))
                if log_to_stderr:
                    print("[%s] FAILED: %s" % (node_name, error_msg), file=sys.stderr)
                if fallback_result is not None:
                    return dict(fallback_result, error=error_msg)
                return {"error": error_msg}

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# safe_execute
# ---------------------------------------------------------------------------


def safe_execute(operation_name: str, default: Any = None) -> Callable:
    """Decorator for non-critical operations that must never crash the pipeline.

    Silently catches all exceptions and returns the default value.  Intended
    for side-effect-only operations where a failure is acceptable: telemetry
    writes, session memory saves, audit log appends.

    A DEBUG-level message is still emitted so failures are visible when
    debug logging is enabled.

    Args:
        operation_name: Name used in the debug log message.
        default:        Value returned when the wrapped function raises.

    Returns:
        A decorator that wraps a function.

    Usage::

        @safe_execute("telemetry_write")
        def write_telemetry(data: dict) -> None:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                logger.debug("[%s] Non-fatal error: %s" % (operation_name, exc))
                return default

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# NodeResult
# ---------------------------------------------------------------------------


class NodeResult:
    """Fluent builder for LangGraph node return dicts.

    LangGraph node functions must return a plain dict whose keys are FlowState
    field names to update.  NodeResult provides a readable, chainable API for
    constructing those dicts without scattered ad-hoc dict literals.

    Design pattern: Builder (GoF) - accumulates updates through method chaining
    and materialises them only when build() is called.

    Usage::

        return (
            NodeResult()
            .set("step0_task_type", "Bug Fix")
            .set("step0_complexity", 7)
            .add_pipeline_entry("step0_analysis", {"type": "Bug Fix"})
            .build()
        )
    """

    def __init__(self) -> None:
        self._updates: Dict[str, Any] = {}
        self._pipeline_entries: list = []

    def set(self, key: str, value: Any) -> "NodeResult":
        """Set a single FlowState field.

        Args:
            key:   FlowState field name.
            value: New value for the field.

        Returns:
            self, for method chaining.
        """
        self._updates[key] = value
        return self

    def set_if(self, condition: bool, key: str, value: Any) -> "NodeResult":
        """Conditionally set a FlowState field.

        The field is only added to the update dict when condition is True.
        Useful for optional enrichment that depends on runtime state.

        Args:
            condition: When False the field is not updated.
            key:       FlowState field name.
            value:     New value for the field.

        Returns:
            self, for method chaining.
        """
        if condition:
            self._updates[key] = value
        return self

    def merge(self, data: Dict[str, Any]) -> "NodeResult":
        """Merge an existing dict into the accumulated updates.

        Existing keys in data overwrite previously set values for the same
        key.  Useful for incorporating the output of a sub-call or a helper
        function that already returns a partial update dict.

        Args:
            data: Dict of FlowState updates to merge.

        Returns:
            self, for method chaining.
        """
        self._updates.update(data)
        return self

    def add_pipeline_entry(self, node_name: str, data: Dict[str, Any]) -> "NodeResult":
        """Append an entry to the pipeline trace list.

        The "pipeline" key in FlowState holds a list of dicts describing what
        each node did.  This method appends one such entry, injecting the
        node_name automatically.

        Args:
            node_name: Identifying name for the pipeline entry.
            data:      Additional fields for the entry.

        Returns:
            self, for method chaining.
        """
        entry = dict(data)
        entry["node"] = node_name
        self._pipeline_entries.append(entry)
        return self

    def add_error(self, error: str) -> "NodeResult":
        """Append an error string to the FlowState errors list.

        Args:
            error: Human-readable error description.

        Returns:
            self, for method chaining.
        """
        errors = self._updates.get("errors", [])
        if not isinstance(errors, list):
            errors = []
        errors.append(error)
        self._updates["errors"] = errors
        return self

    def add_warning(self, warning: str) -> "NodeResult":
        """Append a warning string to the FlowState warnings list.

        Args:
            warning: Human-readable warning description.

        Returns:
            self, for method chaining.
        """
        warnings = self._updates.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
        warnings.append(warning)
        self._updates["warnings"] = warnings
        return self

    def build(self) -> Dict[str, Any]:
        """Materialise and return the final state update dict.

        When pipeline entries have been accumulated they are stored under the
        "pipeline" key before the dict is returned.

        Returns:
            A plain dict suitable for return from a LangGraph node function.
        """
        if self._pipeline_entries:
            self._updates["pipeline"] = self._pipeline_entries
        return self._updates
