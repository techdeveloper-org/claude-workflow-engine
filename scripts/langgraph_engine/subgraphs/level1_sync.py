"""
Level 1 SubGraph - Sync System with Parallel Execution

Level 1 has 4 independent context/state tasks that can run in parallel:
1. Context Management - load context from ~/.claude/memory/
2. Session Management - load session chain and history
3. User Preferences - load user workflow preferences
4. Pattern Detection - cross-project pattern analysis

These 4 tasks are entirely independent (no shared state between them)
so they can run simultaneously using LangGraph's parallel execution.

After all 4 complete, merge_node collects results and determines
overall Level 1 status.
"""

import sys
from pathlib import Path
from typing import List, Any

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Send
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    Send = Any  # type: ignore

from ..flow_state import FlowState
from ..policy_node_adapter import (
    PolicyNodeAdapter,
    CONTEXT_READER_MAPPING,
    SESSION_LOADER_MAPPING,
    PREFERENCE_LOADER_MAPPING,
    PATTERN_DETECTOR_MAPPING,
)


# ============================================================================
# PARALLEL NODES (one per task)
# ============================================================================


def node_context_loader(state: FlowState) -> FlowState:
    """Load context from ~/.claude/memory/logs/context-monitor-*.log

    This node:
    - Reads context percentage from latest context-monitor log
    - Determines if context > 85% threshold (triggers emergency routing)
    - Loads full context metadata

    Args:
        state: FlowState

    Returns:
        Updated state with context_loaded, context_percentage, etc.
    """
    try:
        memory_logs = Path.home() / ".claude" / "memory" / "logs"
        context_logs = list(memory_logs.glob("context-monitor-*.log"))

        if not context_logs:
            # No context logs found - treat as fresh
            state["context_loaded"] = False
            state["context_percentage"] = 0.0
            state["context_threshold_exceeded"] = False
            return state

        # Parse latest context log (contains context_percentage)
        latest_log = max(context_logs)
        content = latest_log.read_text(encoding="utf-8", errors="ignore")

        # Simple parsing: look for "context_percentage: XX.X" in file
        context_pct = 0.0
        for line in content.split("\n"):
            if "context_percentage" in line or "context" in line.lower():
                # Try to extract percentage
                import re

                match = re.search(r"(\d+\.?\d*)", line)
                if match:
                    context_pct = float(match.group(1))
                    break

        state["context_loaded"] = True
        state["context_percentage"] = context_pct
        state["context_threshold_exceeded"] = context_pct > 85.0
        state["context_metadata"] = {
            "source": str(latest_log),
            "percentage": context_pct,
        }

        return state

    except Exception as e:
        state["context_loaded"] = False
        state["context_error"] = str(e)
        return state


def node_session_loader(state: FlowState) -> FlowState:
    """Load session chain and history from ~/.claude/memory/sessions/

    This node:
    - Loads session chain index
    - Reads previous session summaries
    - Builds session history list

    Args:
        state: FlowState

    Returns:
        Updated state with session_chain_loaded, session_history, etc.
    """
    try:
        memory_sessions = Path.home() / ".claude" / "memory" / "sessions"

        if not memory_sessions.exists():
            state["session_chain_loaded"] = False
            state["session_history"] = []
            state["session_state_data"] = {}
            return state

        # Try to load chain-index.json
        chain_file = memory_sessions / "chain-index.json"
        session_history = []

        if chain_file.exists():
            import json

            chain_data = json.loads(chain_file.read_text(encoding="utf-8"))
            session_history = chain_data.get("sessions", [])[:10]  # Last 10 sessions

        state["session_chain_loaded"] = True
        state["session_history"] = session_history
        state["session_state_data"] = {
            "chain_depth": len(session_history),
            "current_session_id": state.get("session_id"),
        }

        return state

    except Exception as e:
        state["session_chain_loaded"] = False
        state["session_error"] = str(e)
        return state


def node_preferences_loader(state: FlowState) -> FlowState:
    """Load user preferences from ~/.claude/memory/preferences/

    This node:
    - Loads user workflow preferences
    - Loads model preferences
    - Loads tool usage preferences

    Args:
        state: FlowState

    Returns:
        Updated state with preferences_loaded, preferences_data
    """
    try:
        pref_file = Path.home() / ".claude" / "memory" / "preferences.json"

        if not pref_file.exists():
            state["preferences_loaded"] = False
            state["preferences_data"] = {}
            return state

        import json

        prefs = json.loads(pref_file.read_text(encoding="utf-8"))

        state["preferences_loaded"] = True
        state["preferences_data"] = {
            "default_model": prefs.get("default_model", "haiku"),
            "use_plan_mode": prefs.get("use_plan_mode", False),
            "parallel_execution": prefs.get("parallel_execution", True),
        }

        return state

    except Exception as e:
        state["preferences_loaded"] = False
        state["preferences_error"] = str(e)
        return state


def node_patterns_detector(state: FlowState) -> FlowState:
    """Detect cross-project patterns from ~/.claude/memory/patterns/

    This node:
    - Loads detected patterns from previous sessions
    - Analyzes project for similar patterns
    - Returns list of applicable patterns

    Args:
        state: FlowState

    Returns:
        Updated state with patterns_detected, pattern_metadata
    """
    try:
        patterns_file = Path.home() / ".claude" / "memory" / "patterns.json"

        if not patterns_file.exists():
            state["patterns_detected"] = []
            state["pattern_metadata"] = {}
            return state

        import json

        patterns_data = json.loads(patterns_file.read_text(encoding="utf-8"))

        # Get patterns applicable to current project type
        all_patterns = patterns_data.get("patterns", [])
        applicable_patterns = [
            p.get("name", "") for p in all_patterns if p.get("applicable", True)
        ]

        state["patterns_detected"] = applicable_patterns
        state["pattern_metadata"] = {
            "total_patterns": len(all_patterns),
            "applicable_patterns": len(applicable_patterns),
        }

        return state

    except Exception as e:
        state["patterns_detected"] = []
        state["patterns_error"] = str(e)
        return state


# ============================================================================
# MERGE NODE
# ============================================================================


def level1_merge_node(state: FlowState) -> FlowState:
    """Merge results from all 4 parallel tasks.

    Determines overall Level 1 status:
    - All 4 loaded: OK
    - Some loaded: PARTIAL
    - None loaded: FAILED

    Args:
        state: FlowState with results from all 4 parallel tasks

    Returns:
        Updated state with level1_status
    """
    loaded_count = sum([
        state.get("context_loaded", False),
        state.get("session_chain_loaded", False),
        state.get("preferences_loaded", False),
        1,  # patterns always considered loaded if no error
    ])

    if loaded_count == 4:
        state["level1_status"] = "OK"
    elif loaded_count >= 2:
        state["level1_status"] = "PARTIAL"
    else:
        state["level1_status"] = "FAILED"
        if "errors" not in state:
            state["errors"] = []
        state["errors"].append("Level 1: Most context sources unavailable")

    # Check context threshold (triggers routing to emergency archival)
    if state.get("context_percentage", 0) > 85:
        state["context_threshold_exceeded"] = True

    return state


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level1_subgraph():
    """Create Level 1 subgraph with parallel execution.

    Note: LangGraph 1.0.10 requires individual add_edge() calls
    for multiple destinations. Multiple edges from one node
    achieve parallel execution automatically.

    Returns:
        Compiled StateGraph for Level 1
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add nodes
    graph.add_node("node_context", node_context_loader)
    graph.add_node("node_session", node_session_loader)
    graph.add_node("node_preferences", node_preferences_loader)
    graph.add_node("node_patterns", node_patterns_detector)
    graph.add_node("merge", level1_merge_node)

    # Parallel execution: START -> all 4 nodes simultaneously
    # In LangGraph, multiple edges from START run those nodes in parallel
    graph.add_edge(START, "node_context")
    graph.add_edge(START, "node_session")
    graph.add_edge(START, "node_preferences")
    graph.add_edge(START, "node_patterns")

    # All 4 nodes converge to merge
    graph.add_edge("node_context", "merge")
    graph.add_edge("node_session", "merge")
    graph.add_edge("node_preferences", "merge")
    graph.add_edge("node_patterns", "merge")

    graph.add_edge("merge", END)

    return graph.compile()
