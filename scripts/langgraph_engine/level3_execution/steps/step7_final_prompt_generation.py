"""
REMOVED (v1.15.0) -- Step 7: Final Prompt Generation

This module was removed as dead code. Removed in v1.13.0 when Steps 1, 3, 4,
5, 6, 7 were collapsed into the Step 0 orchestration template call. The
execution prompt is now written by step0_task_analysis_node (see _map_step0_result_to_state).

If you see this file being imported, that import is stale and should be removed.
"""

raise ImportError(
    "step7_final_prompt_generation is removed (v1.13.0). "
    "The execution prompt is written by Step 0 (step0_task_analysis_node)."
)
