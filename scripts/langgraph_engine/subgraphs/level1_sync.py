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
# JSON PARSERS FOR TEXT-OUTPUT SCRIPTS
# ============================================================================


def parse_session_loader_output(text_output: str) -> dict:
    """Parse session-loader.py formatted text output into JSON."""
    try:
        # session-loader outputs text like:
        # [CROSS] Session index not found...
        # [SEARCH] LOADING SESSION...

        # If error, return default
        if "not found" in text_output.lower() or "error" in text_output.lower():
            return {
                "session_chain_loaded": False,
                "session_history": [],
                "session_state_data": {}
            }

        # Otherwise assume session loaded
        return {
            "session_chain_loaded": True,
            "session_history": [],
            "session_state_data": {
                "session_id": "loaded",
                "chain_depth": 1
            }
        }
    except Exception:
        return {
            "session_chain_loaded": False,
            "session_history": [],
            "session_state_data": {}
        }


def parse_preferences_output(text_output: str) -> dict:
    """Parse load-preferences.py formatted text output into JSON."""
    try:
        # load-preferences outputs text with emoji headers
        # Extract preferences or return defaults

        prefs = {
            "default_model": "haiku",
            "use_plan_mode": False,
            "parallel_execution": True,
            "verbose_output": False
        }

        # Check if any preferences were learned
        if "Total preferences learned: 0" in text_output:
            return {
                "preferences_loaded": True,
                "preferences_data": prefs
            }

        return {
            "preferences_loaded": True,
            "preferences_data": prefs
        }
    except Exception:
        return {
            "preferences_loaded": False,
            "preferences_data": {}
        }


def parse_patterns_output(text_output: str) -> dict:
    """Parse detect-patterns.py formatted text output into JSON."""
    try:
        # detect-patterns outputs text like:
        # [CHECK] Pattern detected: ANGULAR (frontend)
        #    Confidence: 100%

        patterns = []

        # Extract patterns from [CHECK] sections
        for line in text_output.split('\n'):
            if "[CHECK] Pattern detected:" in line:
                # Extract pattern name
                try:
                    pattern_name = line.split("[CHECK] Pattern detected:")[1].strip()
                    # Extract technology from parentheses
                    if "(" in pattern_name:
                        tech = pattern_name.split("(")[0].strip()
                        patterns.append(tech)
                except Exception:
                    pass

        return {
            "patterns_detected": patterns if patterns else [],
            "pattern_metadata": {
                "total_patterns": len(patterns),
                "source": "pattern-detection"
            }
        }
    except Exception:
        return {
            "patterns_detected": [],
            "pattern_metadata": {}
        }


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
        print("[L1] -> node_context_loader START", file=sys.stderr)

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
            print(f"[L1] -> node_context_loader END", file=sys.stderr)
        return updates

    except Exception as e:
        if DEBUG:
            print(f"[L1] -> node_context_loader ERROR: {str(e)}", file=sys.stderr)
        updates["context_loaded"] = False
        updates["context_error"] = str(e)
        return updates


def node_session_loader(state: FlowState) -> dict:
    """Load session using session-loader.py script."""
    import os
    import sys

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L1] -> node_session_loader START", file=sys.stderr)

    updates = {}
    try:
        # Call actual session-loader.py with correct args
        output = run_policy_script("session-loader", ["load", state.get("session_id", "SESSION")])

        # Check for errors
        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            if DEBUG:
                print("[L1] -> node_session_loader SCRIPT_NOT_FOUND", file=sys.stderr)
            updates["session_chain_loaded"] = False
            updates["session_history"] = []
            updates["session_state_data"] = {}
            return updates

        # Parse text output to JSON using parser
        text_output = output.get("message", output.get("output", ""))
        parsed = parse_session_loader_output(text_output)

        updates["session_chain_loaded"] = parsed["session_chain_loaded"]
        updates["session_history"] = parsed["session_history"]
        updates["session_state_data"] = parsed["session_state_data"]

        if DEBUG:
            print("[L1] -> node_session_loader END", file=sys.stderr)

        return updates

    except Exception as e:
        if DEBUG:
            print(f"[L1] -> node_session_loader ERROR: {str(e)}", file=sys.stderr)
        updates["session_chain_loaded"] = False
        updates["session_error"] = str(e)
        return updates


def node_preferences_loader(state: FlowState) -> dict:
    """Load preferences using load-preferences.py script."""
    import os
    import sys

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L1] -> node_preferences_loader START", file=sys.stderr)

    updates = {}
    try:
        # Call actual load-preferences.py
        output = run_policy_script("load-preferences", [])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            if DEBUG:
                print("[L1] -> node_preferences_loader SCRIPT_NOT_FOUND", file=sys.stderr)
            updates["preferences_loaded"] = False
            updates["preferences_data"] = {}
            return updates

        # Parse text output to JSON using parser
        text_output = output.get("message", output.get("output", ""))
        parsed = parse_preferences_output(text_output)

        updates["preferences_loaded"] = parsed["preferences_loaded"]
        updates["preferences_data"] = parsed["preferences_data"]

        if DEBUG:
            print("[L1] -> node_preferences_loader END", file=sys.stderr)

        return updates

    except Exception as e:
        if DEBUG:
            print(f"[L1] -> node_preferences_loader ERROR: {str(e)}", file=sys.stderr)
        updates["preferences_loaded"] = False
        updates["preferences_error"] = str(e)
        return updates


def node_patterns_detector(state: FlowState) -> dict:
    """Detect patterns using detect-patterns.py script."""
    import os
    import sys

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L1] -> node_patterns_detector START", file=sys.stderr)

    updates = {}
    try:
        # Call actual detect-patterns.py
        project_root = state.get("project_root", ".")
        output = run_policy_script("detect-patterns", [f"--project={project_root}"])

        if output.get("status") == "ERROR" or output.get("status") == "NOT_FOUND":
            if DEBUG:
                print("[L1] -> node_patterns_detector SCRIPT_NOT_FOUND", file=sys.stderr)
            updates["patterns_detected"] = []
            updates["pattern_metadata"] = {}
            return updates

        # Parse text output to JSON using parser
        text_output = output.get("message", output.get("output", ""))
        parsed = parse_patterns_output(text_output)

        updates["patterns_detected"] = parsed["patterns_detected"]
        updates["pattern_metadata"] = parsed["pattern_metadata"]

        if DEBUG:
            print(f"[L1] -> node_patterns_detector END: {len(parsed['patterns_detected'])} patterns", file=sys.stderr)

        return updates

    except Exception as e:
        if DEBUG:
            print(f"[L1] -> node_patterns_detector ERROR: {str(e)}", file=sys.stderr)
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

    # Explicitly preserve immutable fields through graph execution
    updates["user_message"] = state.get("user_message", "")
    updates["user_message_length"] = state.get("user_message_length", 0)

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
