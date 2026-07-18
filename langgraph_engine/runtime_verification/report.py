"""VerificationReport -- the JSON-serialisable summary a RuntimeVerifier run produces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class VerificationReport:
    """Aggregated result of a runtime-verification run.

    ``violations`` holds plain dicts (from ``dataclasses.asdict(Violation(...))``), NOT
    Violation objects, so the report stays JSON-serialisable and consistent with the
    FlowState TypedDict. ``pass_fail`` is True only when there are no violations.
    """

    verified_nodes: List[str] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)  # plain dicts, NOT Violation objects
    warnings: List[str] = field(default_factory=list)
    pass_fail: bool = True  # True only when len(violations) == 0; set by caller
    elapsed_ms_per_node: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a shallow-copied plain-dict form of the report (safe to JSON-dump)."""
        return {
            "verified_nodes": list(self.verified_nodes),
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "pass_fail": self.pass_fail,
            "elapsed_ms_per_node": dict(self.elapsed_ms_per_node),
        }
