from __future__ import annotations

from typing import Dict, List, Tuple

from langgraph_engine.runtime_verification.contracts import PreconditionSpec

# Level transition guards: keyed by (from_level, to_level)
# For str expected_type: min_val = minimum string length
# IMPORTANT: combined_complexity_score is 1-25 scale (NOT 1-10)
LEVEL_TRANSITION_GUARDS: Dict[Tuple[str, str], List[PreconditionSpec]] = {
    ("level_minus1", "level1"): [
        PreconditionSpec(
            key="auto_fix_complete",
            expected_type=bool,
            required=True,
        ),
    ],
    ("level1", "level3"): [
        PreconditionSpec(
            key="combined_complexity_score",
            expected_type=(int, float),
            required=True,
            min_val=1,
            max_val=25,  # 1-25 scale: simple*0.3 + graph*0.7
        ),
        PreconditionSpec(
            key="session_synced",
            expected_type=bool,
            required=True,
        ),
    ],
    ("pre_analysis", "step0"): [
        PreconditionSpec(
            key="pre_analysis_result",
            expected_type=dict,
            required=True,
        ),
        PreconditionSpec(
            key="call_graph_metrics",
            expected_type=dict,
            required=True,
        ),
    ],
    ("step0", "step8"): [
        PreconditionSpec(
            key="orchestration_prompt",
            expected_type=str,
            required=True,
            min_val=200,  # min length for str
        ),
        PreconditionSpec(
            key="orchestrator_result",
            expected_type=str,
            required=True,
            min_val=50,  # min length for str
        ),
    ],
}


def get_transition_guard(from_level: str, to_level: str) -> List[PreconditionSpec]:
    """Return the list of PreconditionSpec for the given level transition, or [] if not guarded."""
    return LEVEL_TRANSITION_GUARDS.get((from_level, to_level), [])
