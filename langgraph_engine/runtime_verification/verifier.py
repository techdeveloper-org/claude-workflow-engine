from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Union

from langgraph_engine.core.logger_factory import get_logger
from langgraph_engine.runtime_verification.contracts import NodeContract, PreconditionSpec, Violation
from langgraph_engine.runtime_verification.invariants import get_transition_guard
from langgraph_engine.runtime_verification.report import VerificationReport

_LOG = get_logger(__name__)


class NullVerifier:
    """Returned by RuntimeVerifier.get_instance() when ENABLE_RUNTIME_VERIFICATION != '1'.
    All methods are no-ops -- zero overhead on the pipeline hot path."""

    def register(self, contract: NodeContract) -> None:
        pass

    def check_preconditions(self, node_name: str, state: dict) -> List[Dict]:
        return []

    def check_postconditions(self, node_name: str, state: dict) -> List[Dict]:
        return []

    def check_level_transition(self, from_level: str, to_level: str, state: dict) -> List[Dict]:
        return []

    def build_report(self) -> Optional[VerificationReport]:
        return None

    def reset_for_tests(self) -> None:
        pass


class RuntimeVerifier:
    """Central runtime verification engine. Singleton per process when enabled."""

    _instance: Optional["RuntimeVerifier"] = None

    def __init__(self) -> None:
        self._registry: Dict[str, NodeContract] = {}
        self._violations: List[Dict[str, Any]] = []  # plain dicts via asdict(Violation(...))
        self._verified_nodes: List[str] = []
        self._elapsed: Dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> Union["RuntimeVerifier", NullVerifier]:
        if os.getenv("ENABLE_RUNTIME_VERIFICATION", "0") != "1":
            return NullVerifier()
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, contract: NodeContract) -> None:
        self._registry[contract.node_name] = contract

    def _evaluate_precondition_spec(
        self, node_name: str, spec: PreconditionSpec, state: dict, check_type: str
    ) -> List[Dict]:
        violations = []
        if spec.key not in state or state[spec.key] is None:
            if spec.required:
                v = Violation(
                    node_name=node_name,
                    check_type=check_type,
                    key=spec.key,
                    message="required key '%s' missing or None in state" % spec.key,
                    severity="CRITICAL",
                )
                violations.append(asdict(v))
            return violations

        val = state[spec.key]

        # Type check
        if not isinstance(val, spec.expected_type):
            v = Violation(
                node_name=node_name,
                check_type=check_type,
                key=spec.key,
                message="key '%s' expected type %s, got %s" % (spec.key, spec.expected_type, type(val).__name__),
                severity="ERROR",
            )
            violations.append(asdict(v))
            return violations  # skip range checks if type is wrong

        # Range / length check
        if spec.min_val is not None:
            actual = len(val) if isinstance(val, (str, list, dict)) else val
            if actual < spec.min_val:
                v = Violation(
                    node_name=node_name,
                    check_type=check_type,
                    key=spec.key,
                    message="key '%s' value %r below minimum %s" % (spec.key, actual, spec.min_val),
                    severity="ERROR",
                )
                violations.append(asdict(v))

        if spec.max_val is not None:
            actual = len(val) if isinstance(val, (str, list, dict)) else val
            if actual > spec.max_val:
                v = Violation(
                    node_name=node_name,
                    check_type=check_type,
                    key=spec.key,
                    message="key '%s' value %r above maximum %s" % (spec.key, actual, spec.max_val),
                    severity="ERROR",
                )
                violations.append(asdict(v))

        return violations

    def check_preconditions(self, node_name: str, state: dict) -> List[Dict]:
        contract = self._registry.get(node_name)
        if contract is None:
            _LOG.warning("[RuntimeVerifier] no contract registered for node: %s", node_name)
            return []
        violations = []
        for spec in contract.preconditions:
            violations.extend(self._evaluate_precondition_spec(node_name, spec, state, "precondition"))
        if violations:
            self._violations.extend(violations)
        return violations

    def check_postconditions(self, node_name: str, state: dict) -> List[Dict]:
        contract = self._registry.get(node_name)
        if contract is None:
            return []
        violations = []
        for spec in contract.postconditions:
            val = state.get(spec.key)
            if spec.non_null and (val is None):
                v = Violation(
                    node_name=node_name,
                    check_type="postcondition",
                    key=spec.key,
                    message="postcondition failed: key '%s' is None after node execution" % spec.key,
                    severity="ERROR",
                )
                violations.append(asdict(v))
                continue
            if val is not None and spec.min_length > 0:
                actual_len = len(val) if isinstance(val, (str, list, dict)) else 0
                if actual_len < spec.min_length:
                    v = Violation(
                        node_name=node_name,
                        check_type="postcondition",
                        key=spec.key,
                        message="postcondition failed: key '%s' length %d below minimum %d"
                        % (spec.key, actual_len, spec.min_length),
                        severity="ERROR",
                    )
                    violations.append(asdict(v))
        if violations:
            self._violations.extend(violations)
        return violations

    def check_level_transition(self, from_level: str, to_level: str, state: dict) -> List[Dict]:
        specs = get_transition_guard(from_level, to_level)
        if not specs:
            return []
        guard_node = "transition:%s->%s" % (from_level, to_level)
        violations = []
        for spec in specs:
            violations.extend(self._evaluate_precondition_spec(guard_node, spec, state, "transition"))
        if violations:
            self._violations.extend(violations)
            _LOG.warning(
                "[RuntimeVerifier] %d transition guard violation(s) (%s->%s)",
                len(violations),
                from_level,
                to_level,
            )
        return violations

    def build_report(self) -> VerificationReport:
        return VerificationReport(
            verified_nodes=list(self._verified_nodes),
            violations=list(self._violations),
            warnings=[],
            pass_fail=len(self._violations) == 0,
            elapsed_ms_per_node=dict(self._elapsed),
        )

    @classmethod
    def reset_for_tests(cls) -> None:
        """Reset singleton for test isolation. Call in pytest fixtures."""
        cls._instance = None
