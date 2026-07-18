"""Runtime verification engine.

RuntimeVerifier checks node contracts (preconditions/postconditions) and
level-transition guards against the pipeline state when
ENABLE_RUNTIME_VERIFICATION == '1'. When disabled, get_instance() returns a
NullVerifier whose methods are no-ops (zero hot-path overhead).
"""

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
    """No-op verifier returned when ENABLE_RUNTIME_VERIFICATION != '1'.

    Every method is a no-op so the pipeline hot path pays zero overhead when
    runtime verification is disabled. Mirrors the RuntimeVerifier interface so
    callers never have to branch on whether verification is enabled.
    """

    def register(self, contract: NodeContract) -> None:
        """Ignore the contract; nothing is verified while disabled."""

    def check_preconditions(self, node_name: str, state: dict) -> List[Dict]:
        """Return no violations (verification disabled)."""
        return []

    def check_postconditions(self, node_name: str, state: dict) -> List[Dict]:
        """Return no violations (verification disabled)."""
        return []

    def check_level_transition(self, from_level: str, to_level: str, state: dict) -> List[Dict]:
        """Return no violations (verification disabled)."""
        return []

    def build_report(self) -> Optional[VerificationReport]:
        """Return None; no report is produced while verification is disabled."""
        return None

    def reset_for_tests(self) -> None:
        """Reset nothing; present only for interface parity with RuntimeVerifier."""


class RuntimeVerifier:
    """Central runtime verification engine. Singleton per process when enabled."""

    _instance: Optional["RuntimeVerifier"] = None

    def __init__(self) -> None:
        """Initialise empty registry, violation log, verified-node list, and timings.

        Violations are stored as plain dicts (via ``asdict(Violation(...))``) so the
        resulting report is trivially JSON-serialisable.
        """
        self._registry: Dict[str, NodeContract] = {}
        self._violations: List[Dict[str, Any]] = []
        self._verified_nodes: List[str] = []
        self._elapsed: Dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> Union["RuntimeVerifier", NullVerifier]:
        """Return the process-wide verifier, or a NullVerifier when disabled.

        Returns:
            A singleton RuntimeVerifier when ENABLE_RUNTIME_VERIFICATION == '1',
            otherwise a NullVerifier whose methods are no-ops.
        """
        if os.getenv("ENABLE_RUNTIME_VERIFICATION", "0") != "1":
            return NullVerifier()
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, contract: NodeContract) -> None:
        """Register a node contract, keyed by its node_name, for later checks."""
        self._registry[contract.node_name] = contract

    def _evaluate_precondition_spec(
        self, node_name: str, spec: PreconditionSpec, state: dict, check_type: str
    ) -> List[Dict]:
        """Evaluate one precondition spec against state and return any violations.

        Checks presence/non-None (when required), then type, then min/max bounds.
        Numeric bounds compare the value directly; length bounds apply to
        str/list/dict. A wrong type short-circuits the range checks.

        Args:
            node_name: Node the spec belongs to, recorded on each Violation.
            spec: The precondition specification to evaluate.
            state: The pipeline state dict being validated.
            check_type: Label recorded on violations (e.g. "precondition",
                "transition").

        Returns:
            A list of violation dicts (via asdict(Violation(...))); empty when
            the spec is satisfied.
        """
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
        """Validate all preconditions for a node before it executes.

        Args:
            node_name: Name of the node whose contract to check.
            state: The pipeline state dict.

        Returns:
            A list of violation dicts; empty when no contract is registered or
            all preconditions pass.
        """
        contract = self._registry.get(node_name)
        if contract is None:
            _LOG.warning(f"[RuntimeVerifier] no contract registered for node: {node_name}")
            return []
        violations = []
        for spec in contract.preconditions:
            violations.extend(self._evaluate_precondition_spec(node_name, spec, state, "precondition"))
        if violations:
            self._violations.extend(violations)
        return violations

    def check_postconditions(self, node_name: str, state: dict) -> List[Dict]:
        """Validate all postconditions for a node after it executes.

        Args:
            node_name: Name of the node whose contract to check.
            state: The pipeline state dict after the node ran.

        Returns:
            A list of violation dicts; empty when no contract is registered or
            all postconditions hold.
        """
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
        """Validate the guard specs for a level-to-level transition.

        Args:
            from_level: The level being left.
            to_level: The level being entered.
            state: The pipeline state dict at the transition point.

        Returns:
            A list of violation dicts; empty when no guard is defined or all
            guard specs pass.
        """
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
                f"[RuntimeVerifier] {len(violations)} transition guard violation(s) ({from_level}->{to_level})"
            )
            if os.getenv("ENABLE_METRICS", "0") == "1":
                try:
                    from langgraph_engine.metrics_exporter import inc_verification_violations  # noqa: PLC0415

                    for violation in violations:
                        inc_verification_violations(
                            level=violation.get("severity", "ERROR"),
                            node=guard_node,
                        )
                except ImportError:
                    pass
        return violations

    def build_report(self) -> VerificationReport:
        """Assemble a VerificationReport snapshot from accumulated state.

        Returns:
            A report with the verified nodes, all recorded violations, and
            per-node timings; pass_fail is True only when no violations exist.
        """
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
