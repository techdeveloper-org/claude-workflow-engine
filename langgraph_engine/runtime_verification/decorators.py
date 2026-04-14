from __future__ import annotations

import functools
import os
import time
from typing import Any, Callable

from langgraph_engine.core.logger_factory import get_logger
from langgraph_engine.runtime_verification.contracts import NodeContract
from langgraph_engine.runtime_verification.verifier import RuntimeVerifier

_LOG = get_logger(__name__)


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
            if all_violations:
                _LOG.warning(
                    "[RuntimeVerifier] %d violation(s) in node '%s'",
                    len(all_violations),
                    node_name,
                )
                # Append violation messages to result state (list of strings)
                if isinstance(result, dict):
                    existing = result.get("verification_violations") or []
                    result["verification_violations"] = existing + [v["message"] for v in all_violations]

            # Track timing and verified node list
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            verifier._elapsed[node_name] = elapsed_ms
            if node_name not in verifier._verified_nodes:
                verifier._verified_nodes.append(node_name)

            return result

        # Marker for test assertions: confirms this is an RV-wrapped function
        wrapper.__rv_wrapped__ = True  # type: ignore[attr-defined]
        return wrapper

    return decorator
