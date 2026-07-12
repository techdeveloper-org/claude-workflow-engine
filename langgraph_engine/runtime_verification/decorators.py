"""verify_node decorator -- wraps pipeline node functions with runtime contract checks.

When ENABLE_RUNTIME_VERIFICATION != '1' the decorator returns the original function
unchanged (zero overhead). Otherwise it registers the node's NodeContract with the
singleton RuntimeVerifier and checks preconditions/postconditions around each call.
"""

from __future__ import annotations

import functools
import os
import time
from typing import Any, Callable

from langgraph_engine.core.logger_factory import get_logger
from langgraph_engine.engine_logging.tracing import create_span
from langgraph_engine.runtime_verification.contracts import NodeContract
from langgraph_engine.runtime_verification.verifier import RuntimeVerifier

_LOG = get_logger(__name__)

# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"WARNING": 0, "ERROR": 1, "CRITICAL": 2}


def _max_severity(violations):
    # type: (list) -> str
    """Return the highest severity string from a list of violation dicts."""
    return max(
        violations,
        key=lambda v: _SEVERITY_RANK.get(v.get("severity", "ERROR"), 1),
    )["severity"]


def verify_node(contract: NodeContract) -> Callable:
    """Decorator factory: wrap a pipeline node function with pre/post contract checks.

    When ENABLE_RUNTIME_VERIFICATION != '1', returns the original function unchanged
    (literal zero overhead -- no wrapper created, no closure allocated).

    Usage:
        contract = NodeContract(
            node_name="my_node",
            preconditions=[PreconditionSpec("task_description", str, required=True)],
            postconditions=[PostconditionSpec("result", non_null=True)],
        )

        @verify_node(contract)
        def my_node(state: dict) -> dict:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        # Fast path: disabled at import time -- return original function, zero overhead
        if os.getenv("ENABLE_RUNTIME_VERIFICATION", "0") != "1":
            return fn

        # Register contract with the singleton verifier
        verifier = RuntimeVerifier.get_instance()
        verifier.register(contract)

        @functools.wraps(fn)
        def wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
            node_name = contract.node_name
            t0 = time.monotonic()

            with create_span("runtime_verification.verify_node") as span:
                span.set_attribute("node.name", node_name)

                # Pre-condition check
                pre_violations = verifier.check_preconditions(node_name, state)

                # Always call original -- never skipped regardless of violations
                result = fn(state, *args, **kwargs)

                # Post-condition check (only when result is a dict)
                post_violations = []
                if isinstance(result, dict):
                    post_violations = verifier.check_postconditions(node_name, result)

                # Log summary if any violations found
                all_violations = pre_violations + post_violations

                span.set_attribute("verification.result", "fail" if all_violations else "pass")
                span.set_attribute("violation.count", len(all_violations))

                if all_violations:
                    span.set_attribute("violation.level", _max_severity(all_violations))
                    _LOG.warning(
                        "[RuntimeVerifier] {} violation(s) in node '{}'",
                        len(all_violations),
                        node_name,
                    )
                    # Append violation messages to result state (list of strings)
                    if isinstance(result, dict):
                        existing = result.get("verification_violations") or []
                        result["verification_violations"] = existing + [v["message"] for v in all_violations]
                    # Emit metrics when enabled (lazy import to avoid circular deps)
                    if os.getenv("ENABLE_METRICS", "0") == "1":
                        try:
                            from langgraph_engine.metrics_exporter import inc_verification_violations  # noqa: PLC0415

                            node_name_str = getattr(contract, "node_name", "unknown")
                            for v in all_violations:
                                inc_verification_violations(
                                    level=v.get("severity", "ERROR"),
                                    node=node_name_str,
                                )
                        except ImportError:
                            pass

            # Track timing and verified node list (outside span -- not instrumentation)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            verifier._elapsed[node_name] = elapsed_ms
            if node_name not in verifier._verified_nodes:
                verifier._verified_nodes.append(node_name)

            return result

        # Marker for test assertions: confirms this is an RV-wrapped function
        wrapper.__rv_wrapped__ = True  # type: ignore[attr-defined]
        return wrapper

    return decorator
