"""Pipeline builder - Builder Pattern for StateGraph construction.

Extracted from orchestrator.py create_flow_graph(). Each add_level*() method
wires one level's nodes and edges. The build() method compiles and returns
the graph, optionally with a SQLite checkpointer.

Usage:
    graph = (
        PipelineBuilder()
        .add_level_minus1()
        .add_level1()
        .add_level2()
        .add_level3(hook_mode=True)
        .build()
    )
"""

try:
    from langgraph.graph import END, START, StateGraph

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .checkpointer import CheckpointerManager
from .flow_state import FlowState

# Helper nodes
from .helper_nodes import (
    emergency_archive,
    level2_select_standards_node,
    optimize_context_after_level2,
    output_node,
    step11_retry_increment_node,
)

# Standards integration hook functions
from .helper_nodes.standards_helpers import (
    apply_integration_step1,
    apply_integration_step2,
    apply_integration_step3,
    apply_integration_step4,
    apply_integration_step5,
    apply_integration_step6,
    apply_integration_step7,
    apply_integration_step10,
    apply_integration_step13,
)

# Level 1 nodes
from .level1_sync import (
    cleanup_level1_memory,
    level1_merge_node,
    node_complexity_calculation,
    node_context_loader,
    node_session_loader,
    node_toon_compression,
)

# Level 2 nodes
from .level2_standards import (
    level2_merge_node,
    node_common_standards,
    node_java_standards,
    node_mcp_plugin_discovery,
    node_tool_optimization_standards,
)

# Level 3 nodes (v2 active)
from .level3_execution.subgraph import (
    level3_init_node,
    level3_merge_node,
    orchestration_pre_analysis_node,
    route_pre_analysis,
    step0_0_project_context_node,
    step0_1_initial_callgraph_node,
    step0_task_analysis_node,
    step1_plan_mode_decision_node,
    step2_plan_execution_node,
    step3_task_breakdown_node,
    step4_toon_refinement_node,
    step5_skill_selection_node,
    step6_skill_validation_node,
    step7_final_prompt_node,
    step8_github_issue_node,
    step9_branch_creation_node,
    step10_implementation_note,
    step11_pull_request_node,
    step12_issue_closure_node,
    step13_docs_update_node,
    step14_final_summary_node,
)

# Level -1 nodes
from .level_minus1 import (
    ask_level_minus1_fix,
    fix_level_minus1_issues,
    level_minus1_merge_node,
    node_encoding_validation,
    node_unicode_fix,
    node_windows_path_check,
)

# Routing functions
from .routing import (
    route_after_level_minus1,
    route_after_level_minus1_user_choice,
    route_after_step1_decision,
    route_after_step11_review,
    route_standards_loading,
)


class PipelineBuilder:
    """Builder for the 3-level LangGraph StateGraph pipeline.

    Each add_level*() method wires one level's nodes and edges into the graph.
    Call build() to compile and return the runnable graph.

    Methods are chainable:
        graph = PipelineBuilder().add_level_minus1().add_level1().add_level2().add_level3().build()

    Raises:
        RuntimeError: If LangGraph is not installed when build() is called.
        RuntimeError: If build() is called before all required levels are added.
    """

    def __init__(self) -> None:
        if not _LANGGRAPH_AVAILABLE:
            raise RuntimeError(
                "LangGraph not installed. Install with: " "pip install langgraph>=0.2.0 langchain-core>=0.3.0"
            )
        self._graph: StateGraph = StateGraph(FlowState)
        self._hook_mode: bool = False
        self._levels_added: list = []

    # =========================================================================
    # LEVEL -1: AUTO-FIX ENFORCEMENT
    # =========================================================================

    def add_level_minus1(self) -> "PipelineBuilder":
        """Wire Level -1 auto-fix enforcement nodes and edges.

        Sequential: START -> unicode -> encoding -> windows -> merge
        Conditional: merge -> ask_fix | level1_session
        Retry loop: ask_fix -> fix -> retry(unicode) | skip(level1_session)
        """
        g = self._graph

        # Nodes
        g.add_node("level_minus1_unicode", node_unicode_fix)
        g.add_node("level_minus1_encoding", node_encoding_validation)
        g.add_node("level_minus1_windows", node_windows_path_check)
        g.add_node("level_minus1_merge", level_minus1_merge_node)
        g.add_node("ask_level_minus1_fix", ask_level_minus1_fix)
        g.add_node("fix_level_minus1", fix_level_minus1_issues)

        # Sequential edges: START -> checks -> merge
        g.add_edge(START, "level_minus1_unicode")
        g.add_edge("level_minus1_unicode", "level_minus1_encoding")
        g.add_edge("level_minus1_encoding", "level_minus1_windows")
        g.add_edge("level_minus1_windows", "level_minus1_merge")

        # Conditional: merge -> ask_fix | level1_session
        g.add_conditional_edges(
            "level_minus1_merge",
            route_after_level_minus1,
            {
                "ask_level_minus1_fix": "ask_level_minus1_fix",
                "level1_session": "level1_session",
            },
        )

        # Conditional: ask_fix -> fix_level_minus1 | level1_session
        g.add_conditional_edges(
            "ask_level_minus1_fix",
            route_after_level_minus1_user_choice,
            {
                "fix_level_minus1": "fix_level_minus1",
                "level1_session": "level1_session",
            },
        )

        # After fix, always retry Level -1 checks from start
        g.add_edge("fix_level_minus1", "level_minus1_unicode")

        self._levels_added.append("level_minus1")
        return self

    # =========================================================================
    # LEVEL 1: CONTEXT SYNC
    # =========================================================================

    def add_level1(self) -> "PipelineBuilder":
        """Wire Level 1 context sync nodes and edges.

        Flow: session -> parallel(complexity, context) -> toon -> merge -> cleanup
        """
        g = self._graph

        # Nodes
        g.add_node("level1_session", node_session_loader)
        g.add_node("level1_complexity", node_complexity_calculation)
        g.add_node("level1_context", node_context_loader)
        g.add_node("level1_toon_compression", node_toon_compression)
        g.add_node("level1_merge", level1_merge_node)
        g.add_node("level1_cleanup", cleanup_level1_memory)

        # Session first, then parallel complexity + context
        g.add_edge("level1_session", "level1_complexity")
        g.add_edge("level1_session", "level1_context")

        # Both join at toon
        g.add_edge("level1_complexity", "level1_toon_compression")
        g.add_edge("level1_context", "level1_toon_compression")

        # toon -> merge -> cleanup
        g.add_edge("level1_toon_compression", "level1_merge")
        g.add_edge("level1_merge", "level1_cleanup")

        self._levels_added.append("level1")
        return self

    # =========================================================================
    # LEVEL 2: STANDARDS SYSTEM
    # =========================================================================

    def add_level2(self) -> "PipelineBuilder":
        """Wire Level 2 standards loading nodes and edges.

        From level1_cleanup: three parallel paths (emergency_archive, tool_opt, mcp_discovery)
        then conditional Java routing, merge, standards selector, context optimize.
        """
        g = self._graph

        # Nodes
        g.add_node("level2_emergency_archive", emergency_archive)
        g.add_node("level2_common_standards", node_common_standards)
        g.add_node("level2_java_standards", node_java_standards)
        g.add_node("level2_tool_optimization", node_tool_optimization_standards)
        g.add_node("level2_mcp_discovery", node_mcp_plugin_discovery)
        g.add_node("level2_merge", level2_merge_node)
        g.add_node("level2_select_standards", level2_select_standards_node)
        g.add_node("level2_optimize_context", optimize_context_after_level2)

        # From Level 1 cleanup: three parallel entry points
        g.add_edge("level1_cleanup", "level2_emergency_archive")
        g.add_edge("level1_cleanup", "level2_tool_optimization")
        g.add_edge("level1_cleanup", "level2_mcp_discovery")

        # Emergency archive is a no-op pass-through when context < 95%
        g.add_edge("level2_emergency_archive", "level2_common_standards")

        # Conditional: common_standards -> java_standards | merge
        g.add_conditional_edges(
            "level2_common_standards",
            route_standards_loading,
            {
                "level2_java_standards": "level2_java_standards",
                "level2_merge": "level2_merge",
            },
        )

        # All three parallel paths converge at merge
        g.add_edge("level2_java_standards", "level2_merge")
        g.add_edge("level2_tool_optimization", "level2_merge")
        g.add_edge("level2_mcp_discovery", "level2_merge")

        # merge -> standards selector -> context optimize
        g.add_edge("level2_merge", "level2_select_standards")
        g.add_edge("level2_select_standards", "level2_optimize_context")

        self._levels_added.append("level2")
        return self

    # =========================================================================
    # LEVEL 3: EXECUTION PIPELINE (15-step: Step 0-14)
    # =========================================================================

    def add_level3(self, hook_mode: bool = False) -> "PipelineBuilder":
        """Wire Level 3 execution pipeline nodes and edges.

        Hook mode (hook_mode=True):
            Steps 0-9 execute: analysis + prompt + GitHub issue + branch
            Steps 10-14 skipped: user implements, then full mode runs PR/closure

        Full mode (hook_mode=False):
            Steps 0-14 execute sequentially with retry loop at Step 11.

        Standards hooks run between each step to inject compliance context.
        """
        self._hook_mode = hook_mode
        g = self._graph

        # Bridge node: session_path -> session_dir
        g.add_node("level3_init", level3_init_node)
        g.add_edge("level2_optimize_context", "level3_init")

        # Pre-analysis gate: call graph scan + RAG orchestration lookup
        # On RAG hit (confidence >= 0.85): jumps to level3_step5, skipping steps 0-4
        # On miss: falls through to level3_step0_0 (normal pre-flight flow)
        g.add_node("level3_pre_analysis", orchestration_pre_analysis_node)
        g.add_edge("level3_init", "level3_pre_analysis")
        g.add_conditional_edges(
            "level3_pre_analysis",
            route_pre_analysis,
            {
                "level3_step0_0": "level3_step0_0",
                "level3_step5": "level3_step5",
            },
        )

        # Step 0.0: Pre-flight - Project Context (README, CHANGELOG, etc.)
        g.add_node("level3_step0_0", step0_0_project_context_node)

        # Step 0.1: Pre-flight - Initial CallGraph Snapshot (baseline for Step 11 diff)
        g.add_node("level3_step0_1", step0_1_initial_callgraph_node)
        g.add_edge("level3_step0_0", "level3_step0_1")

        # Step 0: Task Analysis (provides task_type, complexity, tasks for Step 1)
        g.add_node("level3_step0", step0_task_analysis_node)
        g.add_edge("level3_step0_1", "level3_step0")

        # Standards hook: Step 1 (before plan mode decision)
        g.add_node("level3_standards_hook_step1", apply_integration_step1)
        g.add_edge("level3_step0", "level3_standards_hook_step1")

        # Step 1: Plan Mode Decision
        g.add_node("level3_step1", step1_plan_mode_decision_node)
        g.add_edge("level3_standards_hook_step1", "level3_step1")

        # Conditional: plan_required -> step2 | step3
        g.add_conditional_edges(
            "level3_step1",
            route_after_step1_decision,
            {
                "level3_step2": "level3_step2",
                "level3_step3": "level3_step3",
            },
        )

        # Standards hook: Step 2 (during plan execution)
        g.add_node("level3_standards_hook_step2", apply_integration_step2)

        # Step 2: Plan Execution (only when plan_required=True)
        g.add_node("level3_step2", step2_plan_execution_node)
        g.add_edge("level3_step2", "level3_standards_hook_step2")
        g.add_edge("level3_standards_hook_step2", "level3_step3")

        # Step 3: Task Breakdown
        g.add_node("level3_step3", step3_task_breakdown_node)

        # Standards hook: Step 3
        g.add_node("level3_standards_hook_step3", apply_integration_step3)
        g.add_edge("level3_step3", "level3_standards_hook_step3")

        # Step 4: TOON Refinement
        g.add_node("level3_step4", step4_toon_refinement_node)
        g.add_edge("level3_standards_hook_step3", "level3_step4")

        # Standards hook: Step 4
        g.add_node("level3_standards_hook_step4", apply_integration_step4)
        g.add_edge("level3_step4", "level3_standards_hook_step4")

        # Step 5: Skill & Agent Selection
        g.add_node("level3_step5", step5_skill_selection_node)
        g.add_edge("level3_standards_hook_step4", "level3_step5")

        # Standards hook: Step 5
        g.add_node("level3_standards_hook_step5", apply_integration_step5)
        g.add_edge("level3_step5", "level3_standards_hook_step5")

        # Step 6: Skill Validation & Download
        g.add_node("level3_step6", step6_skill_validation_node)
        g.add_edge("level3_standards_hook_step5", "level3_step6")

        # Standards hook: Step 6
        g.add_node("level3_standards_hook_step6", apply_integration_step6)
        g.add_edge("level3_step6", "level3_standards_hook_step6")

        # Step 7: Final Prompt Generation
        g.add_node("level3_step7", step7_final_prompt_node)
        g.add_edge("level3_standards_hook_step6", "level3_step7")

        # Standards hook: Step 7
        g.add_node("level3_standards_hook_step7", apply_integration_step7)
        g.add_edge("level3_step7", "level3_standards_hook_step7")

        # Step 8: GitHub Issue Creation (runs in both modes)
        g.add_node("level3_step8", step8_github_issue_node)
        g.add_edge("level3_standards_hook_step7", "level3_step8")

        # Step 9: Branch Creation (runs in both modes)
        g.add_node("level3_step9", step9_branch_creation_node)
        g.add_edge("level3_step8", "level3_step9")

        if hook_mode:
            # HOOK MODE: After Steps 8-9, skip to output
            # Claude Code itself is Step 10 (LLM reading the prompt and working)
            g.add_node("level3_merge", level3_merge_node)
            g.add_edge("level3_step9", "level3_merge")

            g.add_node("level3_output", output_node)
            g.add_edge("level3_merge", "level3_output")
            g.add_edge("level3_output", END)
        else:
            # FULL MODE: Steps 10-14 (implementation + PR + merge + close)

            # Step 10: Implementation (calls hybrid_inference in full mode)
            g.add_node("level3_step10", step10_implementation_note)
            g.add_edge("level3_step9", "level3_step10")

            # Standards hook: Step 10 (code review compliance checklist)
            g.add_node("level3_standards_hook_step10", apply_integration_step10)
            g.add_edge("level3_step10", "level3_standards_hook_step10")

            # Step 11: PR Creation & Merge
            g.add_node("level3_step11", step11_pull_request_node)
            g.add_edge("level3_standards_hook_step10", "level3_step11")

            # Step 11 retry loop: retry node increments counter, re-routes to step10
            g.add_node("level3_step11_retry", step11_retry_increment_node)
            g.add_edge("level3_step11_retry", "level3_step10")

            # Conditional: review passed or max retries -> step12 | failed -> retry
            g.add_conditional_edges(
                "level3_step11",
                route_after_step11_review,
                {
                    "level3_step12": "level3_step12",
                    "level3_step11_retry": "level3_step11_retry",
                },
            )

            # Step 12: Issue Closure
            g.add_node("level3_step12", step12_issue_closure_node)

            # Step 13: Documentation Update
            g.add_node("level3_step13", step13_docs_update_node)
            g.add_edge("level3_step12", "level3_step13")

            # Standards hook: Step 13 (documentation requirements)
            g.add_node("level3_standards_hook_step13", apply_integration_step13)
            g.add_edge("level3_step13", "level3_standards_hook_step13")

            # Step 14: Final Summary + Voice Notification
            g.add_node("level3_step14", step14_final_summary_node)
            g.add_edge("level3_standards_hook_step13", "level3_step14")

            # Merge -> output -> END
            g.add_node("level3_merge", level3_merge_node)
            g.add_edge("level3_step14", "level3_merge")

            g.add_node("level3_output", output_node)
            g.add_edge("level3_merge", "level3_output")
            g.add_edge("level3_output", END)

        self._levels_added.append("level3")
        return self

    # =========================================================================
    # BUILD
    # =========================================================================

    def build(self):
        """Compile and return the StateGraph.

        Attempts to attach a SQLite checkpointer for state persistence.
        Falls back to no checkpointer if SQLite setup fails.

        Returns:
            Compiled LangGraph runnable (CompiledStateGraph).

        Raises:
            RuntimeError: If not all required levels were added before build().
        """
        required = {"level_minus1", "level1", "level2", "level3"}
        missing = required - set(self._levels_added)
        if missing:
            raise RuntimeError(
                f"Cannot build pipeline: missing levels {sorted(missing)}. "
                "Call add_level_minus1(), add_level1(), add_level2(), add_level3() first."
            )

        try:
            checkpointer = CheckpointerManager.get_default_checkpointer(use_sqlite=True)
            return self._graph.compile(checkpointer=checkpointer)
        except Exception:
            # Fallback to no checkpointer if SQLite setup fails
            return self._graph.compile()


# ============================================================================
# CONVENIENCE FACTORY - backward compatible with orchestrator.create_flow_graph
# ============================================================================


def create_flow_graph(hook_mode: bool = False):
    """Create the compiled pipeline graph.

    Convenience wrapper around PipelineBuilder that matches the original
    orchestrator.create_flow_graph() signature for backward compatibility.

    Args:
        hook_mode: If True, only Steps 0-9 are wired (analysis + prompt gen).
                   Steps 10-14 require full mode (CLAUDE_HOOK_MODE=0).

    Returns:
        Compiled LangGraph runnable (CompiledStateGraph).
    """
    return PipelineBuilder().add_level_minus1().add_level1().add_level2().add_level3(hook_mode=hook_mode).build()
