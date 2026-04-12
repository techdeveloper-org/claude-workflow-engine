"""Pipeline builder - Builder Pattern for StateGraph construction.

Extracted from orchestrator.py create_flow_graph(). Each add_level*() method
wires one level's nodes and edges. The build() method compiles and returns
the graph, optionally with a SQLite checkpointer.

Usage:
    graph = (
        PipelineBuilder()
        .add_level_minus1()
        .add_level1()
        .add_level3(hook_mode=True)
        .build()
    )

CHANGE LOG (v1.15.0):
  node_toon_compression removed from level1_sync import.
  add_level1() TOON node + edges replaced with direct parallel merge:
    level1_complexity -> level1_merge
    level1_context -> level1_merge

CHANGE LOG (v1.15.2):
  level3_merge_node removed from import and add_level3().
  level3_merge was a comment stub in subgraph.py, never implemented.
  Hook mode: level3_step9 -> level3_output (direct edge).
  Full mode: level3_step14 -> level3_output (direct edge).

CHANGE LOG (v1.16.0):
  Level 2 (standards system) removed from pipeline.
  add_level2() method deleted.
  add_level3() bridge edge changed: level1_cleanup -> level3_init.
  Required levels set updated: level2 removed.
  Default build chain: add_level_minus1().add_level1().add_level3(...).
"""

try:
    from langgraph.graph import END, START, StateGraph

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .checkpointer import CheckpointerManager
from .flow_state import FlowState

# Helper nodes
from .helper_nodes import output_node, step11_retry_increment_node

# Standards integration hook functions
from .helper_nodes.standards_helpers import apply_integration_step10, apply_integration_step13

# Level 1 nodes
from .level1_sync import (
    cleanup_level1_memory,
    level1_merge_node,
    node_complexity_calculation,
    node_context_loader,
    node_session_loader,
)

# Level 3 nodes (v2 active)
from .level3_execution.subgraph import (
    level3_init_node,
    orchestration_pre_analysis_node,
    route_pre_analysis,
    step0_0_project_context_node,
    step0_1_initial_callgraph_node,
    step0_task_analysis_node,
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
from .routing import route_after_level_minus1, route_after_level_minus1_user_choice, route_after_step11_review


class PipelineBuilder:
    """Builder for the 3-level LangGraph StateGraph pipeline.

    Each add_level*() method wires one level's nodes and edges into the graph.
    Call build() to compile and return the runnable graph.

    Methods are chainable:
        graph = PipelineBuilder().add_level_minus1().add_level1().add_level3().build()

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

        Flow: session -> parallel(complexity, context) -> merge -> cleanup
        Both complexity and context feed directly into merge (v1.15.0).
        """
        g = self._graph

        # Nodes
        g.add_node("level1_session", node_session_loader)
        g.add_node("level1_complexity", node_complexity_calculation)
        g.add_node("level1_context", node_context_loader)
        g.add_node("level1_merge", level1_merge_node)
        g.add_node("level1_cleanup", cleanup_level1_memory)

        # Session first, then parallel complexity + context
        g.add_edge("level1_session", "level1_complexity")
        g.add_edge("level1_session", "level1_context")

        # Both feed directly into merge (no TOON intermediate step)
        g.add_edge("level1_complexity", "level1_merge")
        g.add_edge("level1_context", "level1_merge")

        # merge -> cleanup
        g.add_edge("level1_merge", "level1_cleanup")

        self._levels_added.append("level1")
        return self

    # =========================================================================
    # LEVEL 3: EXECUTION PIPELINE (v1.14.0: Pre-0, Step 0, Steps 8-14)
    # =========================================================================

    def add_level3(self, hook_mode: bool = False) -> "PipelineBuilder":
        """Wire Level 3 execution pipeline nodes and edges.

        v1.14.0 active steps:
            Pre-0 -> Step 0.0 -> Step 0.1 -> Step 0 -> Step 8 -> Step 9 -> [Steps 10-14]

        Steps 1-7 were removed in v1.13.0 (collapsed into Step 0 orchestration template).

        Hook mode (hook_mode=True):
            Steps 0-9 execute: analysis + prompt + GitHub issue + branch
            Steps 10-14 skipped: user implements, then full mode runs PR/closure

        Full mode (hook_mode=False):
            Steps 0-14 execute sequentially with retry loop at Step 11.

        Standards hooks run at Steps 10 and 13 for compliance context injection.

        v1.15.2: level3_merge node removed (was a comment stub, never implemented).
          Hook mode: level3_step9 -> level3_output (direct edge).
          Full mode: level3_step14 -> level3_output (direct edge).

        v1.16.0: Level 2 removed. Bridge edge changed to level1_cleanup -> level3_init.
        """
        self._hook_mode = hook_mode
        g = self._graph

        # Bridge node: level1_cleanup -> level3_init (v1.16.0: Level 2 removed)
        g.add_node("level3_init", level3_init_node)
        g.add_edge("level1_cleanup", "level3_init")

        # Pre-analysis gate: call graph scan
        # Template fast-path (--orchestration-template): jumps directly to level3_step8
        # Normal path: falls through to level3_step0_0 (pre-flight flow)
        g.add_node("level3_pre_analysis", orchestration_pre_analysis_node)
        g.add_edge("level3_init", "level3_pre_analysis")
        g.add_conditional_edges(
            "level3_pre_analysis",
            route_pre_analysis,
            {
                "level3_step0_0": "level3_step0_0",
                "level3_step8": "level3_step8",
            },
        )

        # Step 0.0: Pre-flight - Project Context (README, CHANGELOG, etc.)
        g.add_node("level3_step0_0", step0_0_project_context_node)

        # Step 0.1: Pre-flight - Initial CallGraph Snapshot (baseline for Step 11 diff)
        g.add_node("level3_step0_1", step0_1_initial_callgraph_node)
        g.add_edge("level3_step0_0", "level3_step0_1")

        # Step 0: Task Analysis (prompt_gen_expert + orchestrator_agent chain)
        # Produces all step5/6/7 migration fields so Steps 8-14 work correctly.
        g.add_node("level3_step0", step0_task_analysis_node)
        g.add_edge("level3_step0_1", "level3_step0")

        # Step 8: GitHub Issue Creation (runs in both modes)
        g.add_node("level3_step8", step8_github_issue_node)
        g.add_edge("level3_step0", "level3_step8")

        # Step 9: Branch Creation (runs in both modes)
        g.add_node("level3_step9", step9_branch_creation_node)
        g.add_edge("level3_step8", "level3_step9")

        if hook_mode:
            # HOOK MODE: After Steps 8-9, skip to output
            # Claude Code itself is Step 10 (LLM reading the prompt and working)
            # v1.15.2: direct edge to output (no merge node)
            g.add_node("level3_output", output_node)
            g.add_edge("level3_step9", "level3_output")
            g.add_edge("level3_output", END)
        else:
            # FULL MODE: Steps 10-14 (implementation + PR + merge + close)

            # Step 10: Implementation (in full mode)
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

            # v1.15.2: direct edge to output (no merge node)
            g.add_node("level3_output", output_node)
            g.add_edge("level3_step14", "level3_output")
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
        required = {"level_minus1", "level1", "level3"}
        missing = required - set(self._levels_added)
        if missing:
            raise RuntimeError(
                f"Cannot build pipeline: missing levels {sorted(missing)}. "
                "Call add_level_minus1(), add_level1(), add_level3() first."
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
    return PipelineBuilder().add_level_minus1().add_level1().add_level3(hook_mode=hook_mode).build()
