"""
Orchestrator - Main StateGraph for 3-level flow execution.

LangGraph 1.0.10 Implementation: Flattened graph (no subgraph nesting)

This StateGraph wires together all 3 levels with conditional routing:
1. Level -1 (auto-fix) - blocking checkpoint
2. Level 1 (sync, 4 parallel context tasks)
3. Level 2 (standards, conditional Java routing)
4. Level 3 (12-step execution)
5. Output node - writes flow-trace.json

Note: LangGraph 1.0.10 doesn't support add_graph() nesting, so we flatten
all nodes into one graph. This works fine - the graph structure is still clear
via node naming (level_minus1_*, level1_*, etc.)
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Literal

try:
    from langgraph.graph import StateGraph, START, END
    # Send not available in LangGraph 0.2.0
# from langgraph.types import Send, Command
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .flow_state import FlowState

# Import all nodes from subgraphs
from .subgraphs.level_minus1 import (
    node_unicode_fix,
    node_encoding_validation,
    node_windows_path_check,
    level_minus1_merge_node,
)

from .subgraphs.level1_sync import (
    node_context_loader,
    node_session_loader,
    node_preferences_loader,
    node_patterns_detector,
    level1_merge_node,
)

from .subgraphs.level2_standards import (
    node_common_standards,
    node_java_standards,
    level2_merge_node,
    detect_project_type,
)

from .subgraphs.level3_execution import (
    step0_prompt_generation,
    step1_task_breakdown,
    step2_plan_mode_decision,
    step3_context_read_enforcement,
    step4_model_selection,
    step5_skill_agent_selection,
    step6_tool_optimization,
    step7_auto_recommendations,
    step8_progress_tracking,
    step9_git_commit_preparation,
    step10_session_save,
    step11_failure_prevention,
    level3_merge_node,
)


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================


def route_after_level_minus1(state: FlowState) -> Literal["output_node", "level1_context"]:
    """Route based on Level -1 blocking status."""
    if state.get("level_minus1_status") == "BLOCKED":
        return "output_node"
    return "level1_context"


def route_context_threshold(state: FlowState) -> Literal["emergency_archive", "level2_common_standards"]:
    """Route based on context usage threshold."""
    if state.get("context_threshold_exceeded"):
        return "emergency_archive"
    return "level2_common_standards"


def route_standards_loading(state: FlowState) -> Literal["level2_java_standards", "level2_merge"]:
    """Route based on project type (Java detection)."""
    detect_project_type(state)
    if state.get("is_java_project"):
        return "level2_java_standards"
    return "level2_merge"


# ============================================================================
# SIMPLE HELPER NODES
# ============================================================================


def emergency_archive(state: FlowState) -> dict:
    """Emergency archival when context threshold exceeded."""
    updates = {}
    existing_warnings = state.get("warnings") or []
    warnings = list(existing_warnings) + [
        f"Context usage high ({state.get('context_percentage', 0):.1f}%) - "
        "archive recommended"
    ]
    updates["warnings"] = warnings
    return updates


def output_node(state: FlowState) -> dict:
    """Final output node - determines completion status."""
    # If final_status not yet set, determine it now
    # Check for blocking conditions
    if state.get("level_minus1_status") == "BLOCKED":
        return {"final_status": "BLOCKED"}
    elif state.get("errors"):
        return {"final_status": "FAILED"}
    elif state.get("warnings"):
        return {"final_status": "PARTIAL"}
    else:
        return {"final_status": "OK"}


# ============================================================================
# GRAPH FACTORY
# ============================================================================


def create_flow_graph():
    """Create and return the main StateGraph for 3-level flow.

    LangGraph 1.0.10: All nodes flattened into single graph.
    Parallel execution: Multiple edges from START or same source
    achieve automatic parallelization.

    Returns:
        Compiled StateGraph instance

    Raises:
        RuntimeError: If LangGraph not installed
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError(
            "LangGraph not installed. Install with: "
            "pip install langgraph>=0.2.0 langchain-core>=0.3.0"
        )

    # Create graph
    graph = StateGraph(FlowState)

    # ========================================================================
    # LEVEL -1: AUTO-FIX ENFORCEMENT (3 checks, sequential)
    # ========================================================================
    graph.add_node("level_minus1_unicode", node_unicode_fix)
    graph.add_node("level_minus1_encoding", node_encoding_validation)
    graph.add_node("level_minus1_windows", node_windows_path_check)
    graph.add_node("level_minus1_merge", level_minus1_merge_node)

    # Sequential: START -> unicode -> encoding -> windows -> merge
    graph.add_edge(START, "level_minus1_unicode")
    graph.add_edge("level_minus1_unicode", "level_minus1_encoding")
    graph.add_edge("level_minus1_encoding", "level_minus1_windows")
    graph.add_edge("level_minus1_windows", "level_minus1_merge")

    # Route based on blocking status
    graph.add_conditional_edges(
        "level_minus1_merge",
        route_after_level_minus1,
        {
            "output_node": "output_node",
            "level1_context": "level1_context",
        },
    )

    # ========================================================================
    # LEVEL 1: SYNC SYSTEM (4 parallel context tasks)
    # ========================================================================
    graph.add_node("level1_context", node_context_loader)
    graph.add_node("level1_session", node_session_loader)
    graph.add_node("level1_preferences", node_preferences_loader)
    graph.add_node("level1_patterns", node_patterns_detector)
    graph.add_node("level1_merge", level1_merge_node)

    # Sequential execution: Level 1 tasks run one after another
    # (LangGraph 1.0.10 doesn't support true parallel from one source)
    # Still efficient: each node is independent, just sequential
    graph.add_edge("level1_context", "level1_session")
    graph.add_edge("level1_session", "level1_preferences")
    graph.add_edge("level1_preferences", "level1_patterns")
    graph.add_edge("level1_patterns", "level1_merge")

    # Route based on context threshold
    graph.add_conditional_edges(
        "level1_merge",
        route_context_threshold,
        {
            "emergency_archive": "emergency_archive",
            "level2_common_standards": "level2_common_standards",
        },
    )

    # ========================================================================
    # LEVEL 2: STANDARDS SYSTEM (conditional Java routing)
    # ========================================================================
    graph.add_node("emergency_archive", emergency_archive)
    graph.add_node("level2_common_standards", node_common_standards)
    graph.add_node("level2_java_standards", node_java_standards)
    graph.add_node("level2_merge", level2_merge_node)

    # Emergency archive routes to standards
    graph.add_edge("emergency_archive", "level2_common_standards")

    # Common standards check for Java
    graph.add_conditional_edges(
        "level2_common_standards",
        route_standards_loading,
        {
            "level2_java_standards": "level2_java_standards",
            "level2_merge": "level2_merge",
        },
    )

    # Java standards merge
    graph.add_edge("level2_java_standards", "level2_merge")

    # Merge to Level 3
    graph.add_edge("level2_merge", "level3_step0")

    # ========================================================================
    # LEVEL 3: EXECUTION SYSTEM (12 sequential steps)
    # ========================================================================
    graph.add_node("level3_step0", step0_prompt_generation)
    graph.add_node("level3_step1", step1_task_breakdown)
    graph.add_node("level3_step2", step2_plan_mode_decision)
    graph.add_node("level3_step3", step3_context_read_enforcement)
    graph.add_node("level3_step4", step4_model_selection)
    graph.add_node("level3_step5", step5_skill_agent_selection)
    graph.add_node("level3_step6", step6_tool_optimization)
    graph.add_node("level3_step7", step7_auto_recommendations)
    graph.add_node("level3_step8", step8_progress_tracking)
    graph.add_node("level3_step9", step9_git_commit_preparation)
    graph.add_node("level3_step10", step10_session_save)
    graph.add_node("level3_step11", step11_failure_prevention)
    graph.add_node("level3_merge", level3_merge_node)

    # Sequential edges through all 12 steps
    graph.add_edge("level3_step0", "level3_step1")
    graph.add_edge("level3_step1", "level3_step2")
    graph.add_edge("level3_step2", "level3_step3")
    graph.add_edge("level3_step3", "level3_step4")
    graph.add_edge("level3_step4", "level3_step5")
    graph.add_edge("level3_step5", "level3_step6")
    graph.add_edge("level3_step6", "level3_step7")
    graph.add_edge("level3_step7", "level3_step8")
    graph.add_edge("level3_step8", "level3_step9")
    graph.add_edge("level3_step9", "level3_step10")
    graph.add_edge("level3_step10", "level3_step11")
    graph.add_edge("level3_step11", "level3_merge")

    # ========================================================================
    # OUTPUT
    # ========================================================================
    graph.add_node("output_node", output_node)
    graph.add_edge("level3_merge", "output_node")
    graph.add_edge("output_node", END)

    # Compile graph WITHOUT checkpointer to avoid session_id conflicts
    # TODO: Add checkpointer support after fixing state merge issues
    compiled_graph = graph.compile()
    return compiled_graph


def create_initial_state(session_id: str = "", project_root: str = "") -> FlowState:
    """Create initial FlowState for a new execution.

    Args:
        session_id: Session identifier (auto-generated if empty)
        project_root: Project directory path

    Returns:
        Initialized FlowState
    """
    if not session_id:
        import uuid

        session_id = f"flow-{uuid.uuid4().hex[:8]}"

    if not project_root:
        project_root = str(Path.cwd())

    # ONLY initialize immutable fields (with _keep_first_value reducer)
    # All other fields will be created/updated by nodes
    return FlowState(
        # Immutable session info only
        session_id=session_id,
        timestamp=datetime.now().isoformat(),
        project_root=project_root,
        # Other fields will be added by nodes as needed
    )


def invoke_flow(
    session_id: str = "",
    project_root: str = "",
) -> FlowState:
    """Convenience function to create and invoke flow in one call.

    Args:
        session_id: Session identifier
        project_root: Project directory

    Returns:
        Final FlowState after execution
    """
    initial_state = create_initial_state(session_id, project_root)
    graph = create_flow_graph()

    from .checkpointer import get_invoke_config

    config = get_invoke_config(initial_state["session_id"])
    # Set very high recursion limit to debug infinite loops
    config["recursion_limit"] = 1000

    result = graph.invoke(initial_state, config=config)
    return result
