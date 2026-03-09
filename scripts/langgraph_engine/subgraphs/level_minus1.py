"""
Level -1 SubGraph - Auto-Fix Enforcement

Level -1 runs three independent checks that cannot be parallelized
(unlike Level 1 which has 4 parallel tasks). All three checks run
but they are sequential.

Checks:
1. Windows Unicode fix - ensure UTF-8 output encoding
2. File encoding validation - ASCII-only Python on Windows (cp1252 safe)
3. Windows path handling - forward slashes, no drive letters in paths
"""

import sys
import platform
from pathlib import Path

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState


# ============================================================================
# AUTO-FIX NODES
# ============================================================================


def node_unicode_fix(state: FlowState) -> dict:
    """Auto-fix Windows Unicode/UTF-8 encoding issues.

    On Windows, ensures sys.stdout and sys.stderr are UTF-8 encoded
    to prevent encoding errors when printing special characters.

    Args:
        state: FlowState

    Returns:
        Updated state with unicode_check result
    """
    # NOTE: session_id is immutable (Annotated with _keep_first_value reducer)
    # Nodes should NOT return it - let LangGraph manage it
    updates = {}
    try:
        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["unicode_check"] = True
            return updates

        # Windows - apply UTF-8 reconfiguration
        import io

        applied = False

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            applied = True
        elif hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            applied = True

        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            applied = True
        elif hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
            applied = True

        updates["unicode_check"] = True
        if applied:
            existing = state.get("auto_fix_applied") or []
            updates["auto_fix_applied"] = list(existing) + ["Unicode UTF-8 encoding"]
        return updates

    except Exception as e:
        updates["unicode_check"] = False
        updates["unicode_check_error"] = str(e)
        return updates


def node_encoding_validation(state: FlowState) -> dict:
    """Validate file encoding standards for Python on Windows.

    On Windows, enforces ASCII-only Python files (cp1252 safe) to avoid
    encoding issues. Scans project Python files and records any with
    non-ASCII content.

    Args:
        state: FlowState

    Returns:
        Updated state with encoding_check result (only changed fields)
    """
    updates = {}
    try:
        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["encoding_check"] = True
            return updates

        project_root = Path(state.get("project_root", "."))
        py_files = list(project_root.glob("**/*.py"))

        non_ascii_files = []

        for py_file in py_files[:50]:  # Check first 50 Python files
            try:
                content = py_file.read_bytes()
                # Check if content is pure ASCII
                content.decode("ascii")
            except (UnicodeDecodeError, Exception):
                non_ascii_files.append(str(py_file.relative_to(project_root)))

        if non_ascii_files:
            updates["encoding_check"] = False
            updates["encoding_check_error"] = (
                f"Non-ASCII Python files found: {', '.join(non_ascii_files[:3])}"
            )
        else:
            updates["encoding_check"] = True

        return updates

    except Exception as e:
        updates["encoding_check"] = False
        updates["encoding_check_error"] = str(e)
        return updates


def node_windows_path_check(state: FlowState) -> dict:
    """Validate Windows path handling in code and configs.

    Checks that all paths use forward slashes (/) and don't contain
    Windows drive letters (C:, D:, etc.) in hardcoded paths.

    Args:
        state: FlowState

    Returns:
        Updated state with windows_path_check result (only changed fields)
    """
    updates = {}
    if "session_id" in state:
        updates["session_id"] = state["session_id"]
    try:
        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["windows_path_check"] = True
            return updates

        project_root = Path(state.get("project_root", "."))

        # Check for obvious backslash paths in .py files
        issues = []
        for py_file in list(project_root.glob("**/*.py"))[:20]:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                # Look for hardcoded Windows paths (C:\, D:\, etc.)
                if "\\" in content and ":\\" in content:
                    issues.append(str(py_file.relative_to(project_root)))
            except Exception:
                pass

        if issues:
            updates["windows_path_check"] = False
            updates["windows_path_check_error"] = (
                f"Backslash paths found: {', '.join(issues[:2])}"
            )
        else:
            updates["windows_path_check"] = True

        return updates

    except Exception as e:
        updates["windows_path_check"] = False
        updates["windows_path_check_error"] = str(e)
        return updates


# ============================================================================
# MERGE NODE
# ============================================================================


def level_minus1_merge_node(state: FlowState) -> dict:
    """Merge results from all Level -1 checks.

    Determines overall Level -1 status based on individual checks:
    - All passed: OK
    - Any failed: BLOCKED (exit early)

    Args:
        state: FlowState with all checks complete

    Returns:
        Updated state with level_minus1_status (only changed fields)
    """
    unicode_ok = state.get("unicode_check", False)
    encoding_ok = state.get("encoding_check", False)
    windows_path_ok = state.get("windows_path_check", False)

    updates = {}

    # All checks must pass for Level -1 to be OK
    if unicode_ok and encoding_ok and windows_path_ok:
        updates["level_minus1_status"] = "OK"
    else:
        updates["level_minus1_status"] = "BLOCKED"
        errors = state.get("errors") or []  # Handle None case
        if not unicode_ok:
            errors = list(errors) + [f"Unicode check failed: {state.get('unicode_check_error')}"]
        if not encoding_ok:
            errors = list(errors) + [f"Encoding check failed: {state.get('encoding_check_error')}"]
        if not windows_path_ok:
            errors = list(errors) + [f"Windows path check failed: {state.get('windows_path_check_error')}"]
        updates["errors"] = errors

    return updates


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level_minus1_subgraph():
    """Create Level -1 subgraph.

    Returns:
        Compiled StateGraph for Level -1
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add nodes (all run sequentially for now)
    graph.add_node("node_unicode", node_unicode_fix)
    graph.add_node("node_encoding", node_encoding_validation)
    graph.add_node("node_windows_path", node_windows_path_check)
    graph.add_node("merge", level_minus1_merge_node)

    # Sequential edges
    graph.add_edge(START, "node_unicode")
    graph.add_edge("node_unicode", "node_encoding")
    graph.add_edge("node_encoding", "node_windows_path")
    graph.add_edge("node_windows_path", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
