"""
Level 1 SubGraph - Sync System with REAL Policy Script Integration

This version calls ACTUAL policy scripts instead of stubbing.
Uses subprocess to invoke:
- context-monitor-v2.py
- session-loader.py
- load-preferences.py
- detect-patterns.py
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import List, Any

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState


# ============================================================================
# POLICY SCRIPT RUNNERS (call ACTUAL scripts)
# ============================================================================


def run_policy_script(script_name: str, args: list = None, timeout: int = 30) -> dict:
    """Run a policy script and return JSON output.

    Args:
        script_name: Name of script in scripts/architecture/
        args: Command line arguments
        timeout: Execution timeout in seconds

    Returns:
        Parsed JSON output from script
    """
    try:
        # Find script in architecture directories
        scripts_dir = Path(__file__).parent.parent.parent

        # Search Level 1, 2, 3 directories
        search_paths = [
            scripts_dir / "architecture" / "01-sync-system",
            scripts_dir / "architecture" / "02-standards-system",
            scripts_dir / "architecture" / "03-execution-system",
        ]

        script_path = None
        for search_dir in search_paths:
            found = list(search_dir.glob(f"**/{script_name}.py"))
            if found:
                script_path = found[0]
                break

        if not script_path:
            return {"error": f"Script not found: {script_name}", "status": "NOT_FOUND"}

        # Build command
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        # Execute
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=scripts_dir
        )

        # Parse JSON output
        if result.stdout:
            try:
                output = json.loads(result.stdout)
                return output
            except json.JSONDecodeError:
                # Script returned non-JSON, return as message
                return {
                    "status": "SUCCESS",
                    "message": result.stdout[:500],
                    "exit_code": result.returncode
                }

        return {
            "status": "SUCCESS" if result.returncode == 0 else "FAILED",
            "exit_code": result.returncode,
            "stderr": result.stderr[:500] if result.stderr else None
        }

    except subprocess.TimeoutExpired:
        return {"error": f"Script timeout: {script_name}", "status": "TIMEOUT"}
    except Exception as e:
        return {"error": str(e), "status": "ERROR"}


# ============================================================================
# LEVEL 1 NODES (calling ACTUAL scripts)
# ============================================================================


def node_context_loader(state: FlowState) -> FlowState:
    """Load context using context-monitor-v2.py script."""
    try:
        # Call actual context-monitor-v2.py
        output = run_policy_script("context-monitor-v2", ["--current-status"])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            # Fallback to basic implementation
            state["context_loaded"] = False
            state["context_percentage"] = 0.0
            return state

        # Extract context percentage from script output
        context_pct = output.get("percentage", 0.0)

        state["context_loaded"] = True
        state["context_percentage"] = float(context_pct)
        state["context_threshold_exceeded"] = context_pct > 85.0
        state["context_metadata"] = {
            "source": "context-monitor-v2.py",
            "percentage": context_pct,
            "script_output": output
        }

        return state

    except Exception as e:
        state["context_loaded"] = False
        state["context_error"] = str(e)
        return state


def node_session_loader(state: FlowState) -> FlowState:
    """Load session using session-loader.py script."""
    try:
        # Call actual session-loader.py
        output = run_policy_script("session-loader", ["--current"])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            state["session_chain_loaded"] = False
            state["session_history"] = []
            state["session_state_data"] = {}
            return state

        # Extract session data
        session_id = output.get("session_id", state.get("session_id"))
        session_history = output.get("session_history", [])

        state["session_chain_loaded"] = True
        state["session_history"] = session_history
        state["session_state_data"] = {
            "session_id": session_id,
            "chain_depth": len(session_history),
            "script_output": output
        }

        return state

    except Exception as e:
        state["session_chain_loaded"] = False
        state["session_error"] = str(e)
        return state


def node_preferences_loader(state: FlowState) -> FlowState:
    """Load preferences using load-preferences.py script."""
    try:
        # Call actual load-preferences.py
        output = run_policy_script("load-preferences", [])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            state["preferences_loaded"] = False
            state["preferences_data"] = {}
            return state

        # Extract preferences
        prefs = output.get("preferences", output)

        state["preferences_loaded"] = True
        state["preferences_data"] = {
            "default_model": prefs.get("default_model", "haiku"),
            "use_plan_mode": prefs.get("use_plan_mode", False),
            "parallel_execution": prefs.get("parallel_execution", True),
            "script_output": output
        }

        return state

    except Exception as e:
        state["preferences_loaded"] = False
        state["preferences_error"] = str(e)
        return state


def node_patterns_detector(state: FlowState) -> FlowState:
    """Detect patterns using detect-patterns.py script."""
    try:
        # Call actual detect-patterns.py
        project_root = state.get("project_root", ".")
        output = run_policy_script("detect-patterns", [f"--project={project_root}"])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            state["patterns_detected"] = []
            state["pattern_metadata"] = {}
            return state

        # Extract patterns
        patterns = output.get("patterns", [])

        state["patterns_detected"] = patterns
        state["pattern_metadata"] = {
            "total_patterns": len(patterns),
            "script_output": output
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
    """Merge results from all 4 Level 1 tasks."""
    loaded_count = sum([
        state.get("context_loaded", False),
        state.get("session_chain_loaded", False),
        state.get("preferences_loaded", False),
        1,  # patterns always counted
    ])

    if loaded_count == 4:
        state["level1_status"] = "OK"
    elif loaded_count >= 2:
        state["level1_status"] = "PARTIAL"
    else:
        state["level1_status"] = "FAILED"
        if "errors" not in state:
            state["errors"] = []
        state["errors"].append("Level 1: Policy script execution failed")

    # Check context threshold
    if state.get("context_percentage", 0) > 85:
        state["context_threshold_exceeded"] = True

    return state


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level1_subgraph():
    """Create Level 1 subgraph (sequential execution)."""
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add nodes
    graph.add_node("level1_context", node_context_loader)
    graph.add_node("level1_session", node_session_loader)
    graph.add_node("level1_preferences", node_preferences_loader)
    graph.add_node("level1_patterns", node_patterns_detector)
    graph.add_node("level1_merge", level1_merge_node)

    # Sequential edges
    graph.add_edge(START, "level1_context")
    graph.add_edge("level1_context", "level1_session")
    graph.add_edge("level1_session", "level1_preferences")
    graph.add_edge("level1_preferences", "level1_patterns")
    graph.add_edge("level1_patterns", "level1_merge")
    graph.add_edge("level1_merge", END)

    return graph.compile()
