"""
Orchestrator - Main StateGraph for 3-level flow execution.

This is the top-level graph that wires together all three levels with
proper routing and error handling.

Flow:
1. Level -1 (auto-fix) - blocking checkpoint
2. Level 1 (sync, 4 parallel tasks) - waits for all tasks
3. Level 2 (standards, with conditional Java routing)
4. Level 3 (12-step execution)
5. Output node - writes flow-trace.json

Each level can be replaced with a nested subgraph for better modularity.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Literal

try:
    from langgraph.graph import StateGraph, START, END, Send
    from langgraph.types import Command
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from .flow_state import FlowState


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

    return FlowState(
        session_id=session_id,
        timestamp=datetime.now().isoformat(),
        project_root=project_root,
        is_java_project=False,
        is_fresh_project=False,
        level_minus1_status="pending",
        level1_status="pending",
        level2_status="pending",
        final_status="pending",
        pipeline=[],
        errors=[],
        warnings=[],
        execution_time_ms=0,
        level_durations={},
    )


def route_after_level_minus1(state: FlowState) -> Literal["output_node", "level1_subgraph"]:
    """Route based on Level -1 blocking status.

    If Level -1 encountered a BLOCKED status, exit early.
    Otherwise, proceed to Level 1.

    Args:
        state: FlowState after Level -1

    Returns:
        Next node name
    """
    if state.get("level_minus1_status") == "BLOCKED":
        state["final_status"] = "BLOCKED"
        return "output_node"
    return "level1_subgraph"


def route_context_threshold(state: FlowState) -> Literal["emergency_archive_node", "level2_subgraph"]:
    """Route based on context usage.

    If context > 85%, trigger emergency archival before Level 2.

    Args:
        state: FlowState after Level 1

    Returns:
        Next node name
    """
    if state.get("context_threshold_exceeded"):
        return "emergency_archive_node"
    return "level2_subgraph"


def route_standards_loading(state: FlowState) -> Literal["java_standards_node", "level3_subgraph"]:
    """Route based on project type.

    Java projects load Java standards; others skip.

    Args:
        state: FlowState with is_java_project set

    Returns:
        Next node name
    """
    if state.get("is_java_project"):
        return "java_standards_node"
    return "level3_subgraph"


# ============================================================================
# IMPORT SUBGRAPH FACTORIES
# ============================================================================

from .subgraphs import (
    create_level_minus1_subgraph,
    create_level1_subgraph,
    create_level2_subgraph,
    create_level3_subgraph,
)


def emergency_archive_node(state: FlowState) -> FlowState:
    """Emergency archival when context threshold exceeded."""
    if "warnings" not in state:
        state["warnings"] = []
    state["warnings"].append(
        f"Context usage high ({state.get('context_percentage', 0):.1f}%) - "
        "archive recommended"
    )
    return state


def java_standards_node(state: FlowState) -> FlowState:
    """Load Java-specific standards (Spring Boot, etc.)."""
    state["java_standards_loaded"] = True
    state["spring_boot_patterns"] = {
        "annotations": ["@Service", "@Repository", "@RestController"],
        "patterns_detected": 0,
    }
    return state


def output_node(state: FlowState) -> FlowState:
    """Final output node - writes flow-trace.json and returns state."""
    # flow-trace.json output is handled by caller, not here
    # This node just marks completion
    if state.get("final_status") == "pending":
        if state.get("errors"):
            state["final_status"] = "FAILED"
        elif state.get("warnings"):
            state["final_status"] = "PARTIAL"
        else:
            state["final_status"] = "OK"

    return state


# ============================================================================
# GRAPH FACTORY
# ============================================================================


def create_flow_graph():
    """Create and return the main StateGraph for 3-level flow.

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

    # Add subgraphs (compiled, nested execution)
    graph.add_graph("level_minus1", create_level_minus1_subgraph())
    graph.add_graph("level1_subgraph", create_level1_subgraph())
    graph.add_graph("level2_subgraph", create_level2_subgraph())
    graph.add_graph("level3_subgraph", create_level3_subgraph())

    # Add simple nodes (non-subgraph)
    graph.add_node("emergency_archive_node", emergency_archive_node)
    graph.add_node("output_node", output_node)

    # Add edges with routing
    graph.add_edge(START, "level_minus1")
    graph.add_conditional_edges(
        "level_minus1",
        route_after_level_minus1,
        {
            "output_node": "output_node",
            "level1_subgraph": "level1_subgraph",
        },
    )
    graph.add_conditional_edges(
        "level1_subgraph",
        route_context_threshold,
        {
            "emergency_archive_node": "emergency_archive_node",
            "level2_subgraph": "level2_subgraph",
        },
    )
    graph.add_edge("emergency_archive_node", "level2_subgraph")
    graph.add_conditional_edges(
        "level2_subgraph",
        route_standards_loading,
        {
            "java_standards_node": "java_standards_node",
            "level3_subgraph": "level3_subgraph",
        },
    )
    graph.add_node("java_standards_node", java_standards_node)
    graph.add_edge("java_standards_node", "level3_subgraph")
    graph.add_edge("level3_subgraph", "output_node")
    graph.add_edge("output_node", END)

    # Compile with checkpointer
    from .checkpointer import CheckpointerManager
    checkpointer = CheckpointerManager.get_default_checkpointer(use_sqlite=True)

    compiled_graph = graph.compile(checkpointer=checkpointer)
    return compiled_graph


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

    result = graph.invoke(initial_state, config=config)
    return result
