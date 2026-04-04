#!/usr/bin/env python3
"""One-time script to apply v1.14 edits to orchestrator.py."""
from pathlib import Path

f = Path(__file__).parent / "langgraph_engine" / "orchestrator.py"
content = f.read_text(encoding="utf-8")
original = content

replacements = [
    # 1. Update docstring: remove Step 2 references
    (
        "  Step 2 (plan execution) retained as optional branch post-step0.\n"
        "  Direct edge: level3_step0 -> level3_step2 -> level3_step8 (plan mode)\n"
        "             OR level3_step0 -> level3_step8 (no-plan mode, new default).\n"
        "  New step count: Pre-0, 0.0, 0.1, 0, [2], 8, 9, [10-14] = 9 active steps.",
        "  Step 2 (plan execution) removed -- orchestrator subprocess already produces\n"
        "  comprehensive plan, making separate plan execution redundant.\n"
        "  Direct edge: level3_step0 -> level3_step8.\n"
        "  New step count: Pre-0, 0.0, 0.1, 0, 8, 9, [10-14] = 8 active steps.\n"
        "\n"
        "CHANGE LOG (v1.14.0):\n"
        "  Step 0 caller scripts now use claude CLI subprocess (not direct llm_call API).\n"
        "  Step 2 (plan execution) removed from graph -- never triggered in practice.\n"
        "  route_after_step0_to_step2_or_step8 replaced with direct edge to step8.",
    ),
    # 2. Remove step2_plan_execution_node from imports
    (
        "    step0_task_analysis_node,\n" "    step2_plan_execution_node,\n" "    step8_github_issue_node,",
        "    step0_task_analysis_node,\n" "    step8_github_issue_node,",
    ),
    # 3. Replace route_after_step0_to_step2_or_step8 function
    (
        'def route_after_step0_to_step2_or_step8(state: FlowState) -> Literal["level3_step2", "level3_step8"]:\n'
        '    """Conditional routing after Step 0: if plan required, execute Step 2; else skip to Step 8."""\n'
        "    if state.get(StepKeys.PLAN_REQUIRED, False):\n"
        '        return "level3_step2"\n'
        '    return "level3_step8"',
        "# REMOVED (v1.14.0): route_after_step0_to_step2_or_step8 -- Step 2 removed from graph.\n"
        "# Step 0 now always routes directly to Step 8.",
    ),
    # 4. Remove Step 2 from step_info table
    (
        '            (0, "Task Analysis + Template", "step0_task_type", "step0_complexity"),\n'
        '            (2, "Plan Execution (optional)", "step2_plan_status", "step2_phases"),\n'
        '            (8, "GitHub Issue Creation", "step8_status", "step8_issue_url"),',
        '            (0, "Task Analysis + Template", "step0_task_type", "step0_complexity"),\n'
        '            (8, "GitHub Issue Creation", "step8_status", "step8_issue_url"),',
    ),
    # 5. Update Level 3 log header comment
    (
        "# Level 3 Steps (v1.13.0: Steps 1,3,4,5,6,7 removed; Step 2 is optional)",
        "# Level 3 Steps (v1.14.0: Steps 1-7 removed; Step 0 -> Step 8 direct)",
    ),
    # 6. Replace Step 2 conditional routing with direct edge
    (
        "    # CONDITIONAL: plan_required -> step2 (plan execution) | step8 (direct to GitHub issue)\n"
        "    graph.add_conditional_edges(\n"
        '        "level3_step0",\n'
        "        route_after_step0_to_step2_or_step8,\n"
        "        {\n"
        '            "level3_step2": "level3_step2",\n'
        '            "level3_step8": "level3_step8",\n'
        "        },\n"
        "    )\n"
        "\n"
        "    # Step 2: Plan Execution (optional - only when step0 sets plan_required=True)\n"
        '    graph.add_node("level3_step2", step2_plan_execution_node)\n'
        '    graph.add_edge("level3_step2", "level3_step8")',
        "    # Direct edge: Step 0 -> Step 8 (Step 2 removed in v1.14.0)\n"
        '    graph.add_edge("level3_step0", "level3_step8")',
    ),
    # 7. Update graph section header
    (
        "    # Active steps: Pre-0, 0.0, 0.1, 0, [2 optional], 8, 9, [10-14 full mode]\n"
        "    # Steps 1, 3, 4, 5, 6, 7 removed -- outputs merged into Step 0 template call.",
        "    # Active steps: Pre-0, 0.0, 0.1, 0, 8, 9, [10-14 full mode]\n"
        "    # Steps 1-7 removed -- outputs merged into Step 0 subprocess calls (v1.14.0).",
    ),
    # 8. Update create_flow_graph CHANGE LOG
    (
        "    CHANGE LOG (v1.13.0):\n"
        "        Steps 1, 3, 4, 5, 6, 7 removed from graph.\n"
        "        Step 0 now does consolidated LLM call (orchestration template) and\n"
        "        populates all migration fields previously written by steps 1-7.\n"
        "        Step 2 (plan execution) retained as optional conditional branch.\n"
        '        route_pre_analysis targets updated to "level3_step8" for both fast paths.\n'
        "        Standards hooks for removed steps are no longer registered.",
        "    CHANGE LOG (v1.13.0):\n"
        "        Steps 1, 3, 4, 5, 6, 7 removed from graph.\n"
        "        Step 0 now does consolidated template call and populates all migration\n"
        "        fields previously written by steps 1-7.\n"
        '        route_pre_analysis targets updated to "level3_step8" for both fast paths.\n'
        "        Standards hooks for removed steps are no longer registered.\n"
        "\n"
        "    CHANGE LOG (v1.14.0):\n"
        "        Step 2 (plan execution) removed -- orchestrator subprocess produces full plan.\n"
        "        Step 0 caller scripts use claude CLI subprocess (not direct llm_call API).\n"
        "        route_after_step0_to_step2_or_step8 replaced with direct edge.",
    ),
    # 9. Update hook_mode docstring
    (
        "and Steps 0/2/8/9 (analysis + prompt generation + issue + branch).",
        "and Steps 0/8/9 (analysis + prompt generation + issue + branch).",
    ),
    # 10. Update removed comments
    (
        "# REMOVED (v1.13.0): apply_integration_step2 -- Step 2 standards hook removed (step2 is now optional, no hook)",
        "# REMOVED (v1.14.0): apply_integration_step2 -- Step 2 removed from pipeline",
    ),
    # 11. Update top-level description
    ("4. Level 3 (9-step execution)", "4. Level 3 (8-step execution)"),
    # 12. Fix Step 0 comment
    (
        "    # Step 0: Task Analysis + Orchestration Template (consolidated LLM call).",
        "    # Step 0: Task Analysis + Orchestration (2 claude CLI subprocess calls).",
    ),
]

applied = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)
        applied += 1
    else:
        # Show first 80 chars for debugging
        print(f"WARNING: replacement {applied+1} not found: {repr(old[:80])}")

f.write_text(content, encoding="utf-8")
print(f"Applied {applied}/{len(replacements)} replacements to orchestrator.py")
