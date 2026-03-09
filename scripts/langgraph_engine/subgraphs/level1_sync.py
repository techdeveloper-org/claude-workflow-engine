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
    import sys
    import os

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"

    try:
        # Find script in architecture directories
        scripts_dir = Path(__file__).parent.parent.parent

        if DEBUG:
            print(f"[L1-DEBUG] Finding script: {script_name}", file=sys.stderr)

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
            if DEBUG:
                print(f"[L1-DEBUG] Script not found: {script_name}", file=sys.stderr)
            return {"error": f"Script not found: {script_name}", "status": "NOT_FOUND"}

        # Build command
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        if DEBUG:
            print(f"[L1-DEBUG] Running: {script_name} (timeout={timeout}s)", file=sys.stderr)

        # Execute with UTF-8 encoding for Windows compatibility
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            cwd=scripts_dir
        )

        if DEBUG:
            print(f"[L1-DEBUG] {script_name} returned: {result.returncode}", file=sys.stderr)

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


def node_context_loader(state: FlowState) -> dict:
    """Load context using context-monitor-v2.py script."""
    import os
    import sys

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L1] → node_context_loader START", file=sys.stderr)

    updates = {}
    try:
        # Call actual context-monitor-v2.py
        output = run_policy_script("context-monitor-v2", ["--current-status"])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            # Fallback to basic implementation
            updates["context_loaded"] = False
            updates["context_percentage"] = 0.0
            return updates

        # Extract context percentage from script output
        context_pct = output.get("percentage", 0.0)

        updates["context_loaded"] = True
        updates["context_percentage"] = float(context_pct)
        updates["context_threshold_exceeded"] = context_pct > 85.0
        updates["context_metadata"] = {
            "source": "context-monitor-v2.py",
            "percentage": context_pct,
            "script_output": output
        }

        if DEBUG:
            print(f"[L1] → node_context_loader END", file=sys.stderr)
        return updates

    except Exception as e:
        if DEBUG:
            print(f"[L1] → node_context_loader ERROR: {str(e)}", file=sys.stderr)
        updates["context_loaded"] = False
        updates["context_error"] = str(e)
        return updates


def node_session_loader(state: FlowState) -> dict:
    """Load session using session-loader.py script."""
    updates = {}
    try:
        # Call actual session-loader.py
        output = run_policy_script("session-loader", ["--current"])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            updates["session_chain_loaded"] = False
            updates["session_history"] = []
            updates["session_state_data"] = {}
            return updates

        # Extract session data
        session_id = output.get("session_id", state.get("session_id"))
        session_history = output.get("session_history", [])

        updates["session_chain_loaded"] = True
        updates["session_history"] = session_history
        updates["session_state_data"] = {
            "session_id": session_id,
            "chain_depth": len(session_history),
            "script_output": output
        }

        return updates

    except Exception as e:
        updates["session_chain_loaded"] = False
        updates["session_error"] = str(e)
        return updates


def node_preferences_loader(state: FlowState) -> dict:
    """Load preferences using load-preferences.py script."""
    updates = {}
    try:
        # Call actual load-preferences.py
        output = run_policy_script("load-preferences", [])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            updates["preferences_loaded"] = False
            updates["preferences_data"] = {}
            return updates

        # Extract preferences
        prefs = output.get("preferences", output)

        updates["preferences_loaded"] = True
        updates["preferences_data"] = {
            "default_model": prefs.get("default_model", "haiku"),
            "use_plan_mode": prefs.get("use_plan_mode", False),
            "parallel_execution": prefs.get("parallel_execution", True),
            "script_output": output
        }

        return updates

    except Exception as e:
        updates["preferences_loaded"] = False
        updates["preferences_error"] = str(e)
        return updates


def node_patterns_detector(state: FlowState) -> dict:
    """Detect patterns using detect-patterns.py script."""
    updates = {}
    try:
        # Call actual detect-patterns.py
        project_root = state.get("project_root", ".")
        output = run_policy_script("detect-patterns", [f"--project={project_root}"])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            updates["patterns_detected"] = []
            updates["pattern_metadata"] = {}
            return updates

        # Extract patterns
        patterns = output.get("patterns", [])

        updates["patterns_detected"] = patterns
        updates["pattern_metadata"] = {
            "total_patterns": len(patterns),
            "script_output": output
        }

        return updates

    except Exception as e:
        updates["patterns_detected"] = []
        updates["patterns_error"] = str(e)
        return updates


# ============================================================================
# MERGE NODE
# ============================================================================


def level1_merge_node(state: FlowState) -> dict:
    """Merge results from all 4 Level 1 tasks."""
    loaded_count = sum([
        state.get("context_loaded", False),
        state.get("session_chain_loaded", False),
        state.get("preferences_loaded", False),
        1,  # patterns always counted
    ])

    updates = {}
    if loaded_count == 4:
        updates["level1_status"] = "OK"
    elif loaded_count >= 2:
        updates["level1_status"] = "PARTIAL"
    else:
        updates["level1_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + ["Level 1: Policy script execution failed"]

    # Check context threshold
    if state.get("context_percentage", 0) > 85:
        updates["context_threshold_exceeded"] = True

    return updates


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
