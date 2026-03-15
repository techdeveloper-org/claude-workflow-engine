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
# RECURSION GUARD - Prevent infinite loop when claude CLI calls trigger hooks
# ============================================================================
if os.environ.get("CLAUDE_WORKFLOW_RUNNING") == "1":
    sys.exit(0)
os.environ["CLAUDE_WORKFLOW_RUNNING"] = "1"

# ============================================================================
# PATH SETUP - Auto-detect scripts directory (works for ANY project)
# ============================================================================

# Use this file's location to find the scripts directory (no hardcoded paths)
_this_scripts_dir = Path(__file__).resolve().parent
if str(_this_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_this_scripts_dir))

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
    # Log detailed error for debugging
    import sys
    print(f"[IMPORT ERROR] {import_error}", file=sys.stderr)
    print(f"[DEBUG] Python path:", file=sys.stderr)
    for p in sys.path[:5]:
        print(f"  {p}", file=sys.stderr)

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
    """Determine project root directory.

    Priority:
    1. CLAUDE_CWD env var (set by hook event JSON parsing)
    2. Current working directory (actual project the user is in)
    """
    # Hook event provides cwd - use it if available
    cwd_from_hook = os.environ.get("CLAUDE_CWD", "").strip()
    if cwd_from_hook and Path(cwd_from_hook).exists():
        return cwd_from_hook

    # Fallback to actual cwd (where Claude CLI was started)
    return str(Path.cwd())


def _capture_user_message() -> str:
    """Capture user message from stdin hook event.

    Hook passes JSON event via stdin: {"prompt":"...", "cwd":"...", ...}
    We extract the actual user prompt and set cwd for project detection.
    """
    import sys
    user_message = ""

    # Try reading from stdin (hook pipes JSON event here)
    if not sys.stdin.isatty():
        try:
            raw_input = sys.stdin.read().strip()
            if raw_input:
                # Try parsing as JSON (hook event format)
                try:
                    event = json.loads(raw_input)
                    # Extract actual user prompt
                    user_message = event.get("prompt", "").strip()
                    # Extract cwd so _get_project_root() uses correct project
                    cwd = event.get("cwd", "").strip()
                    if cwd:
                        os.environ["CLAUDE_CWD"] = cwd
                    if user_message:
                        return user_message
                except (json.JSONDecodeError, TypeError):
                    # Not JSON - treat as plain text prompt
                    user_message = raw_input
                    if user_message:
                        return user_message
        except Exception:
            pass

    # Fallback to environment variable
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

    # CRITICAL FIX: Store user_message in env var so Step 0 can access it
    # (LangGraph strips immutable fields between nodes due to reducer limitations)
    os.environ["CURRENT_USER_MESSAGE"] = user_message

    if DEBUG:
        print(f"[DEBUG] Initial state keys: {list(initial_state.keys())}", file=sys.stderr)
        print(f"[DEBUG] Initial state user_message: {'user_message' in initial_state}", file=sys.stderr)
        if "user_message" in initial_state:
            print(f"[DEBUG] user_message value: {initial_state['user_message'][:50] if initial_state['user_message'] else 'EMPTY'}", file=sys.stderr)

    # Create and invoke graph
    # hook_mode=True: Skip Steps 8-14 (GitHub workflow) for fast hook execution
    # This reduces hook time from ~170s to ~60s (only analysis + prompt generation)
    hook_mode = os.environ.get("CLAUDE_HOOK_MODE", "1") == "1"
    graph = create_flow_graph(hook_mode=hook_mode)

    if DEBUG:
        print("[DEBUG] Starting LangGraph execution...")

    # Invoke with proper config for multi-window multi-session support
    # LangGraph uses thread_id for session isolation
    # session_id is now immutable and won't cause duplicate update errors
    invoke_config = get_invoke_config(session_id)
    if DEBUG:
        print(f"[DEBUG] Before graph.invoke: initial_state['project_root']='{initial_state.get('project_root', 'MISSING')}'", file=sys.stderr)
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

        print(f"[DEBUG] sys.argv: {sys.argv}", file=sys.stderr)

        for arg in sys.argv[1:]:
            print(f"[DEBUG] Processing arg: {arg}", file=sys.stderr)
            if arg.startswith("--session-id="):
                session_id = arg.split("=", 1)[1]
                print(f"[DEBUG]   -> session_id={session_id}", file=sys.stderr)
            elif arg.startswith("--project="):
                project_root = arg.split("=", 1)[1]
                print(f"[DEBUG]   -> project_root={project_root}", file=sys.stderr)
            elif arg.startswith("--message="):
                user_message = arg.split("=", 1)[1]
                print(f"[DEBUG]   -> user_message=...", file=sys.stderr)
            elif arg in ("--summary", "-s"):
                DEBUG = True
                print(f"[DEBUG]   -> DEBUG=True", file=sys.stderr)
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

        print(f"[DEBUG] Before run_langgraph_engine:", file=sys.stderr)
        print(f"[DEBUG]   session_id={session_id}", file=sys.stderr)
        print(f"[DEBUG]   project_root={project_root}", file=sys.stderr)
        print(f"[DEBUG]   user_message length={len(user_message) if user_message else 0}", file=sys.stderr)

        result = run_langgraph_engine(session_id, project_root, user_message)

        # Write flow-trace.json (backward compatible format)
        trace_file = write_flow_trace_json(result)
        if DEBUG:
            print(f"[DEBUG] flow-trace.json written to: {trace_file}")

        # Print checkpoint
        print_flow_checkpoint(result, verbose=DEBUG)

        # Return status code
        # HOOK FIX: Always return 0 so Claude Code doesn't treat flow errors as hook failures
        sys.exit(0)  # Hook executed successfully, regardless of flow status

    except Exception as e:
        print(f"[ERROR] {SCRIPT_NAME}: {str(e)}", file=sys.stderr)
        if DEBUG:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
