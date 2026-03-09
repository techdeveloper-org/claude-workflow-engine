#!/usr/bin/env python3
"""
3-Level Flow Engine - LangGraph Orchestration

Version: 5.0.0-langgraph
Status: LangGraph-based orchestration replacing sequential execution

This is the entry point script for the 3-level architecture enforcement.
It now uses LangGraph StateGraph for:
- Parallel execution (Level 1: 4 context tasks in parallel)
- Conditional routing (Level 2: Java-only standards)
- Proper state transitions (Level 3: 12-step execution)
- Session checkpointing (MemorySaver for recovery)

Backward Compatible:
- Outputs identical flow-trace.json format
- pre-tool-enforcer.py reads same format (no changes needed)
- Incremental migration: policies can work as-is via PolicyNodeAdapter
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# ============================================================================
# IMPORTS & SETUP
# ============================================================================

try:
    # Try importing LangGraph engine
    from langgraph_engine.orchestrator import create_flow_graph, create_initial_state
    from langgraph_engine.flow_trace_converter import (
        write_flow_trace_json,
        print_flow_checkpoint,
    )
    from langgraph_engine.checkpointer import get_invoke_config
    _LANGGRAPH_AVAILABLE = True
except ImportError as e:
    _LANGGRAPH_AVAILABLE = False
    import_error = str(e)

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

VERSION = "5.0.0-langgraph"
SCRIPT_NAME = "3-level-flow.py"
DEBUG = os.getenv("CLAUDE_DEBUG", "").lower() == "1"


def _generate_session_id() -> str:
    """Generate a unique session ID."""
    import uuid
    return f"SESSION-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"


def _get_project_root() -> str:
    """Determine project root directory."""
    return str(Path.cwd())


def _capture_user_message() -> str:
    """Capture user message from stdin or environment.

    Hook passes user message via stdin when script is executed.
    Fallback to CLAUDE_USER_MESSAGE environment variable.
    """
    import sys
    user_message = ""

    # Try reading from stdin (hook typically pipes it here)
    if not sys.stdin.isatty():
        try:
            user_message = sys.stdin.read().strip()
            if user_message:
                return user_message
        except Exception:
            pass

    # Fallback to environment variable (for testing or alternative invocation)
    user_message = os.environ.get("CLAUDE_USER_MESSAGE", "").strip()
    return user_message


def run_langgraph_engine(session_id: str = "", project_root: str = "", user_message: str = "") -> dict:
    """Execute the LangGraph 3-level flow engine.

    Args:
        session_id: Session identifier (auto-generated if empty)
        project_root: Project directory (defaults to cwd)
        user_message: User's actual task/request (auto-captured if empty)

    Returns:
        Final FlowState as dict
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError(
            f"LangGraph engine not available: {import_error}\n"
            "Install with: pip install langgraph>=0.2.0 langchain-core>=0.3.0"
        )

    # Initialize
    if not session_id:
        session_id = _generate_session_id()
    if not project_root:
        project_root = _get_project_root()
    if not user_message:
        user_message = _capture_user_message()

    if DEBUG:
        print(f"[DEBUG] LangGraph Engine v{VERSION}")
        print(f"[DEBUG] Session: {session_id}")
        print(f"[DEBUG] Project: {project_root}")
        if user_message:
            print(f"[DEBUG] Message: {user_message[:100]}..." if len(user_message) > 100 else f"[DEBUG] Message: {user_message}")
        else:
            print(f"[DEBUG] WARNING: No user message captured!")

    # Create initial state (session_id now immutable via Annotated reducer)
    initial_state = create_initial_state(session_id, project_root, user_message)

    if DEBUG:
        print(f"[DEBUG] Initial state keys: {list(initial_state.keys())}", file=sys.stderr)
        print(f"[DEBUG] Initial state user_message: {'user_message' in initial_state}", file=sys.stderr)
        if "user_message" in initial_state:
            print(f"[DEBUG] user_message value: {initial_state['user_message'][:50] if initial_state['user_message'] else 'EMPTY'}", file=sys.stderr)

    # Create and invoke graph
    graph = create_flow_graph()

    if DEBUG:
        print("[DEBUG] Starting LangGraph execution...")

    # Invoke with proper config for multi-window multi-session support
    # LangGraph uses thread_id for session isolation
    # session_id is now immutable and won't cause duplicate update errors
    invoke_config = get_invoke_config(session_id)
    result = graph.invoke(initial_state, config=invoke_config)

    if DEBUG:
        print(f"[DEBUG] Execution complete. Status: {result.get('final_status')}")

    return result


def main():
    """Main entry point."""
    global DEBUG  # Allow modifying global DEBUG variable

    try:
        # Check if LangGraph is available
        if not _LANGGRAPH_AVAILABLE:
            print(
                f"[ERROR] LangGraph not installed.\n"
                f"Install with: pip install langgraph>=0.2.0 langchain-core>=0.3.0\n"
                f"Error details: {import_error}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Parse arguments
        session_id = ""
        project_root = ""
        user_message = ""

        for arg in sys.argv[1:]:
            if arg.startswith("--session-id="):
                session_id = arg.split("=", 1)[1]
            elif arg.startswith("--project="):
                project_root = arg.split("=", 1)[1]
            elif arg.startswith("--message="):
                user_message = arg.split("=", 1)[1]
            elif arg in ("--summary", "-s"):
                DEBUG = True
            elif arg in ("--help", "-h"):
                print(f"{SCRIPT_NAME} - LangGraph 3-Level Flow Engine v{VERSION}")
                print("Usage: python 3-level-flow.py [options]")
                print("Options:")
                print("  --session-id=ID    Session identifier")
                print("  --project=PATH     Project directory")
                print("  --message=MSG      User message/task")
                print("  --summary,-s       Print summary output")
                print("  --help,-h          Show this help")
                sys.exit(0)

        # Run engine (user_message auto-captured from stdin if not provided)
        if not user_message:
            user_message = _capture_user_message()
        result = run_langgraph_engine(session_id, project_root, user_message)

        # Write flow-trace.json (backward compatible format)
        trace_file = write_flow_trace_json(result)
        if DEBUG:
            print(f"[DEBUG] flow-trace.json written to: {trace_file}")

        # Print checkpoint
        print_flow_checkpoint(result, verbose=DEBUG)

        # Return status code
        status = result.get("final_status", "UNKNOWN")
        if status == "BLOCKED":
            sys.exit(1)  # Failed
        elif status == "FAILED":
            sys.exit(1)
        elif status == "PARTIAL":
            sys.exit(0)  # Success but with warnings
        else:
            sys.exit(0)  # OK

    except Exception as e:
        print(f"[ERROR] {SCRIPT_NAME}: {str(e)}", file=sys.stderr)
        if DEBUG:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
