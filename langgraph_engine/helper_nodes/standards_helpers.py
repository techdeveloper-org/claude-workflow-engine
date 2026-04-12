"""Standards helper nodes - Level 2 standards selection and integration hooks.

Extracted from orchestrator.py. Handles auto-detection of project type/framework
and loading all applicable standards with priority-based conflict resolution.
Also contains standards integration hook functions for Level 3 steps.

CHANGE LOG (v1.15.2):
  Removed apply_integration_step1 through apply_integration_step7
  (Steps 1-7 removed from the pipeline in v1.13.0; these hooks had zero
  live callers in the graph).
"""

from ..flow_state import FlowState
from ..standards_integration import apply_standards_at_step


def apply_integration_step10(state: FlowState) -> dict:
    """Apply standards integration point at Step 10 (code review)."""
    updated = apply_standards_at_step(10, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}


def apply_integration_step13(state: FlowState) -> dict:
    """Apply standards integration point at Step 13 (documentation)."""
    updated = apply_standards_at_step(13, dict(state))
    return {k: updated[k] for k in updated if k not in state or updated[k] != state.get(k)}
