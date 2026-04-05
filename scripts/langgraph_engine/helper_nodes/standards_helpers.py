"""Standards helper nodes - Level 2 standards selection and integration hooks.

Extracted from orchestrator.py. Handles auto-detection of project type/framework
and loading all applicable standards with priority-based conflict resolution.
Also contains standards integration hook functions for Level 3 steps.

CHANGE LOG (v1.15.2):
  Removed apply_integration_step1 through apply_integration_step7
  (Steps 1-7 removed from the pipeline in v1.13.0; these hooks had zero
  live callers in the graph).
"""

from ..flow_state import FlowState, StepKeys
from ..standard_selector import select_standards
from ..standards_integration import apply_standards_at_step


def level2_select_standards_node(state: FlowState) -> dict:
    """Level 2 node: auto-select and load all applicable project standards.

    Runs select_standards() which detects project type/framework and loads
    standards from all sources in priority order (custom=4 > team=3 > framework=2
    > language=1), resolving conflicts so the highest-priority source wins.

    Outputs written to FlowState:
      standards_selection       - full selection result including traceability
      standards_merged_rules    - conflict-resolved merged rules dict
      detected_framework        - framework name for downstream routing
      standards_selection_error - error string (non-fatal, execution continues)

    Integration hooks (apply_integration_step10/13) consume the standards_selection
    data to inject step-specific context/constraints/checklists.
    """
    updates: dict = {}

    try:
        project_root = state.get(StepKeys.PROJECT_ROOT, ".")
        session_id = state.get(StepKeys.SESSION_ID, "unknown")

        # select_standards() internally calls detect_project_type() + detect_framework()
        # and loads all sources with conflict resolution
        full_selection = select_standards(project_root, session_id)

        updates["standards_selection"] = {
            "project_type": full_selection["project_type"],
            "framework": full_selection["framework"],
            "total_loaded": full_selection["total_loaded"],
            "conflicts_detected": len(full_selection["conflicts"]),
            "merged_rules": full_selection["merged_rules"],
            "traceability": full_selection.get("traceability", {}),
            "priority_chain": "custom(4) > team(3) > framework(2) > language(1)",
        }

        # Make merged rules available at top-level for quick access by integration hooks
        merged = full_selection.get("merged_rules", {})
        if merged:
            updates["standards_merged_rules"] = merged

        # Expose detected framework for downstream nodes
        updates["detected_framework"] = full_selection["framework"]

        existing_pipeline = state.get(StepKeys.PIPELINE) or []
        updates[StepKeys.PIPELINE] = list(existing_pipeline) + [
            {
                "node": "level2_select_standards",
                "project_type": full_selection["project_type"],
                "framework": full_selection["framework"],
                "standards_loaded": full_selection["total_loaded"],
                "conflicts": len(full_selection["conflicts"]),
                "priority_chain": "custom(4) > team(3) > framework(2) > language(1)",
                "traceability_keys": list(full_selection.get("traceability", {}).keys()),
            }
        ]

    except Exception as exc:
        updates["standards_selection_error"] = str(exc)
        existing_pipeline = state.get(StepKeys.PIPELINE) or []
        updates[StepKeys.PIPELINE] = list(existing_pipeline) + [
            {
                "node": "level2_select_standards",
                "error": str(exc),
            }
        ]

    return updates


def apply_integration_step10(state: FlowState) -> dict:
    """Apply standards integration point at Step 10 (code review)."""
    updated = apply_standards_at_step(10, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step13(state: FlowState) -> dict:
    """Apply standards integration point at Step 13 (documentation)."""
    updated = apply_standards_at_step(13, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}
