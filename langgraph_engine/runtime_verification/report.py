from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# NOTE: violations stores plain dicts (from dataclasses.asdict(Violation(...))),
# NOT Violation dataclass objects. This keeps the field JSON-serialisable and
# consistent with FlowState TypedDict.


@dataclass
class VerificationReport:
    verified_nodes: List[str] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)  # plain dicts, NOT Violation objects
    warnings: List[str] = field(default_factory=list)
    pass_fail: bool = True  # True only when len(violations) == 0; set by caller
    elapsed_ms_per_node: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified_nodes": list(self.verified_nodes),
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "pass_fail": self.pass_fail,
            "elapsed_ms_per_node": dict(self.elapsed_ms_per_node),
        }
