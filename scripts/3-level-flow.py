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


def run_langgraph_engine(session_id: str = "", project_root: str = "") -> dict:
    """Execute the LangGraph 3-level flow engine.

    Args:
        session_id: Session identifier (auto-generated if empty)
        project_root: Project directory (defaults to cwd)

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

    if DEBUG:
        print(f"[DEBUG] LangGraph Engine v{VERSION}")
        print(f"[DEBUG] Session: {session_id}")
        print(f"[DEBUG] Project: {project_root}")

    # Create initial state (session_id now immutable via Annotated reducer)
    initial_state = create_initial_state(session_id, project_root)

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

        for arg in sys.argv[1:]:
            if arg.startswith("--session-id="):
                session_id = arg.split("=", 1)[1]
            elif arg.startswith("--project="):
                project_root = arg.split("=", 1)[1]
            elif arg in ("--summary", "-s"):
                DEBUG = True
            elif arg in ("--help", "-h"):
                print(f"{SCRIPT_NAME} - LangGraph 3-Level Flow Engine v{VERSION}")
                print("Usage: python 3-level-flow.py [options]")
                print("Options:")
                print("  --session-id=ID    Session identifier")
                print("  --project=PATH     Project directory")
                print("  --summary,-s       Print summary output")
                print("  --help,-h          Show this help")
                sys.exit(0)

        # Run engine
        result = run_langgraph_engine(session_id, project_root)

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
