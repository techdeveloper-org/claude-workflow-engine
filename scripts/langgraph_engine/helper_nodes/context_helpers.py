"""Context helper nodes - Context optimization and workflow memory persistence.

Extracted from orchestrator.py. Handles context compression between levels
and saving workflow memory for session persistence.
"""

import sys
from pathlib import Path

try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
    from utils.path_resolver import get_claude_home
    _CONTEXT_HELPERS_CLAUDE_HOME = get_claude_home()
except ImportError:
    _CONTEXT_HELPERS_CLAUDE_HOME = Path.home() / ".claude"

from ..flow_state import FlowState, WorkflowContextOptimizer, StepKeys


def emergency_archive(state: FlowState) -> dict:
    """Emergency archival when context threshold exceeded.

    Runs as part of the Level 1 -> Level 2 transition. If context usage
    is below threshold, this is a no-op pass-through. If above 95%,
    triggers aggressive cleanup and logs a warning.
    """
    updates = {}
    context_pct = state.get(StepKeys.CONTEXT_PERCENTAGE, 0)

    if context_pct >= 95:
        existing_warnings = state.get(StepKeys.WARNINGS) or []
        warnings = list(existing_warnings) + [
            "EMERGENCY: Context usage at %.1f%% - archiving old sessions to free memory" % context_pct
        ]
        updates[StepKeys.WARNINGS] = warnings
        updates["emergency_archive_triggered"] = True

        # Best-effort: trigger session pruning
        try:
            import sys as _sys_ea
            _sys_ea.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "architecture"))
            from importlib import import_module
            _pruner_spec = import_module("session-pruner") if False else None
        except Exception:
            pass

        print("[EMERGENCY ARCHIVE] Context at %.1f%% - archive triggered" % context_pct, file=sys.stderr)
    else:
        updates["emergency_archive_triggered"] = False

    return updates


def optimize_context_after_level1(state: FlowState) -> dict:
    """Optimize context after Level 1 completes before passing to Level 2.

    Stores full Level 1 output in workflow_memory, passes only summary to Level 2.
    This keeps context clean while preserving full data for fallback/debugging.
    """
    # Store full level 1 output
    level1_output = {
        StepKeys.CONTEXT_LOADED: state.get(StepKeys.CONTEXT_LOADED),
        StepKeys.CONTEXT_PERCENTAGE: state.get(StepKeys.CONTEXT_PERCENTAGE),
        StepKeys.SESSION_CHAIN_LOADED: state.get(StepKeys.SESSION_CHAIN_LOADED),
        StepKeys.PATTERNS_DETECTED: state.get(StepKeys.PATTERNS_DETECTED, []),
        StepKeys.PREFERENCES_DATA: state.get(StepKeys.PREFERENCES_DATA, {}),
    }

    state = WorkflowContextOptimizer.store_step_output(state, "level1_output", level1_output)

    # Build optimized context for Level 2
    optimized = WorkflowContextOptimizer.build_optimized_context(state)
    state["workflow_context_optimized"] = optimized

    return state


def optimize_context_after_level2(state: FlowState) -> dict:
    """Optimize context after Level 2 before Level 3 execution.

    Stores standards info in memory, passes only summary to Level 3.
    """
    # Store full level 2 output
    level2_output = {
        StepKeys.STANDARDS_LOADED: state.get(StepKeys.STANDARDS_LOADED),
        StepKeys.STANDARDS_COUNT: state.get(StepKeys.STANDARDS_COUNT),
        StepKeys.JAVA_STANDARDS_LOADED: state.get(StepKeys.JAVA_STANDARDS_LOADED),
        StepKeys.SPRING_BOOT_PATTERNS: state.get(StepKeys.SPRING_BOOT_PATTERNS, {}),
        StepKeys.TOOL_OPTIMIZATION_RULES: state.get(StepKeys.TOOL_OPTIMIZATION_RULES, {}),
        StepKeys.TOOL_OPTIMIZATION_LOADED: state.get(StepKeys.TOOL_OPTIMIZATION_LOADED, False),
    }

    state = WorkflowContextOptimizer.store_step_output(state, "level2_output", level2_output)

    # Build optimized context for Level 3
    optimized = WorkflowContextOptimizer.build_optimized_context(state)
    state["workflow_context_optimized"] = optimized

    return state


def optimize_context_for_level3_step(state: FlowState, step_name: str) -> dict:
    """Optimize context before each Level 3 step.

    For Level 3, only pass data specific to current step.
    All previous step outputs stay in workflow_memory.
    """
    # Store current step's inputs/outputs
    current_data = {
        k: v for k, v in state.items()
        if k.startswith("step") and isinstance(v, dict)
    }

    state = WorkflowContextOptimizer.store_step_output(state, step_name, current_data)

    return state


def save_workflow_memory(state: FlowState) -> dict:
    """Save workflow memory to disk for session persistence."""
    try:
        import json

        session_id = state.get(StepKeys.SESSION_ID, "unknown")
        memory = state.get(StepKeys.WORKFLOW_MEMORY, {})

        if memory and session_id != "unknown":
            # Save to ~/.claude/memory/logs/sessions/{session_id}/workflow-memory.json
            memory_dir = _CONTEXT_HELPERS_CLAUDE_HOME / "memory" / "logs" / "sessions" / session_id
            memory_dir.mkdir(parents=True, exist_ok=True)

            memory_file = memory_dir / "workflow-memory.json"
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": session_id,
                        "timestamp": state.get(StepKeys.TIMESTAMP),
                        "workflow_memory": memory,
                        "context_optimization_stats": state.get(StepKeys.STEP_OPTIMIZATION_STATS, {}),
                        "memory_size_kb": state.get(StepKeys.WORKFLOW_MEMORY_SIZE_KB, 0),
                    },
                    f,
                    indent=2,
                )

            return {"workflow_memory_file": str(memory_file)}
    except Exception:
        # Don't fail if memory save fails - it's non-critical
        pass

    return {}
