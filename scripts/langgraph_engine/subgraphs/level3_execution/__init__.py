"""
Level 3 Execution sub-package.

Backward-compat shim: re-exports all public symbols so existing imports still work.
Active pipeline: level3_execution_v2.py (use that for new work).
This package is the modular refactor of the DEPRECATED level3_execution.py monolith.
"""

from .helpers import (  # noqa: F401
    _LANGGRAPH_AVAILABLE,
    _LEVEL3_AGENTS_DIR,
    _LEVEL3_SKILLS_DIR,
    _detect_project_type_from_files,
    _extract_modified_files,
    _read_project_context_snippets,
    call_execution_script,
)
from .routing import level3_merge_node, route_after_step1_plan_decision, route_after_step11_review  # noqa: F401
from .steps import (  # noqa: F401
    step0_task_analysis,
    step1_plan_mode_decision,
    step2_plan_execution,
    step3_task_breakdown_validation,
    step4_toon_refinement,
    step5_skill_agent_selection,
    step6_skill_validation_download,
    step7_final_prompt_generation,
    step8_github_issue_creation,
    step9_branch_creation,
    step10_implementation_execution,
    step11_pull_request_review,
    step12_issue_closure,
    step13_project_documentation_update,
    step14_final_summary_generation,
)


def create_level3_subgraph():
    """Create Level 3 subgraph (WORKFLOW.md compliant - 15 steps (Step 0-14)).

    Implements complete WORKFLOW.md-compliant execution pipeline:

    Flow:
    START
      |
    Step 0: Task Analysis (pre-step for context)
      |
    Step 1: Plan Decision
      +-- If plan_required=true  -> Step 2: Plan Execution
      |                               |
      +-- If plan_required=false -> Step 3: Task Breakdown
      |
    Step 3: Task Breakdown Validation
      |
    Step 4: TOON Refinement
      |
    Step 5: Skill & Agent Selection
      |
    Step 6: Skill Validation & Download
      |
    Step 7: Final Prompt Generation
      |
    Step 8: GitHub Issue Creation
      |
    Step 9: Branch Creation
      |
    Step 10: Implementation Execution
      |
    Step 11: Pull Request & Code Review
      +-- If review_passed OR retry_count >= 3 -> Step 12: Issue Closure
      |                                               |
      +-- If review failed AND retry_count < 3 -> Back to Step 10 (retry)
      |
    Step 12: Issue Closure
      |
    Step 13: Project Documentation
      |
    Step 14: Final Summary
      |
    Merge & END
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    from langgraph.graph import END, START, StateGraph

    from ...flow_state import FlowState

    graph = StateGraph(FlowState)

    # Add all steps + merge
    graph.add_node("step0_analysis", step0_task_analysis)
    graph.add_node("step1_decision", step1_plan_mode_decision)
    graph.add_node("step2_execution", step2_plan_execution)
    graph.add_node("step3_breakdown", step3_task_breakdown_validation)
    graph.add_node("step4_toon", step4_toon_refinement)
    graph.add_node("step5_selection", step5_skill_agent_selection)
    graph.add_node("step6_validation", step6_skill_validation_download)
    graph.add_node("step7_prompt", step7_final_prompt_generation)
    graph.add_node("step8_issue", step8_github_issue_creation)
    graph.add_node("step9_branch", step9_branch_creation)
    graph.add_node("step10_implementation", step10_implementation_execution)
    graph.add_node("step11_review", step11_pull_request_review)
    graph.add_node("step12_closure", step12_issue_closure)
    graph.add_node("step13_docs", step13_project_documentation_update)
    graph.add_node("step14_summary", step14_final_summary_generation)
    graph.add_node("merge", level3_merge_node)

    # Define edges
    # START -> Step 0 (Task Analysis)
    graph.add_edge(START, "step0_analysis")

    # Step 0 -> Step 1 (Plan Decision)
    graph.add_edge("step0_analysis", "step1_decision")

    # Step 1 -> [Conditional Routing]
    #   - plan_required=true  -> Step 2
    #   - plan_required=false -> Step 3
    graph.add_conditional_edges(
        "step1_decision",
        route_after_step1_plan_decision,
        {"step2_execution": "step2_execution", "step3_breakdown": "step3_breakdown"},
    )

    # Step 2 -> Step 3 (Plan Execution leads to Task Breakdown)
    graph.add_edge("step2_execution", "step3_breakdown")

    # Sequential path: Step 3 -> 4 -> 5 -> 6 -> 7
    graph.add_edge("step3_breakdown", "step4_toon")
    graph.add_edge("step4_toon", "step5_selection")
    graph.add_edge("step5_selection", "step6_validation")
    graph.add_edge("step6_validation", "step7_prompt")

    # GitHub Workflow: Step 7 -> 8 -> 9 -> 10 -> 11
    graph.add_edge("step7_prompt", "step8_issue")
    graph.add_edge("step8_issue", "step9_branch")
    graph.add_edge("step9_branch", "step10_implementation")
    graph.add_edge("step10_implementation", "step11_review")

    # Step 11 -> [Conditional Routing]
    #   - review_passed OR retry_count >= 3 -> Step 12
    #   - review_failed AND retry_count < 3 -> Step 10 (retry)
    graph.add_conditional_edges(
        "step11_review",
        route_after_step11_review,
        {"step12_closure": "step12_closure", "step10_implementation": "step10_implementation"},
    )

    # Sequential path: Step 12 -> 13 -> 14
    graph.add_edge("step12_closure", "step13_docs")
    graph.add_edge("step13_docs", "step14_summary")

    # Final -> Merge -> END
    graph.add_edge("step14_summary", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
