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
    import sys
    print(f"[L-1 UNICODE FIX] state['project_root'] at entry: '{state.get('project_root', 'MISSING')}'", file=sys.stderr)
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
        print(f"[L-1 UNICODE FIX] Returning: {list(updates.keys())}", file=sys.stderr)
        return updates

    except Exception as e:
        updates["unicode_check"] = False
        updates["unicode_check_error"] = str(e)
        print(f"[L-1 UNICODE FIX] Returning (exception): {list(updates.keys())}", file=sys.stderr)
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
# INTERACTIVE RECOVERY NODES
# ============================================================================


def ask_level_minus1_fix(state: FlowState) -> dict:
    """Ask user what to do when Level -1 checks fail.

    Shows specific PASS/FAIL for each check and offers:
    - "auto-fix": Attempt to fix issues, retry (max 3 times)
    - "skip": Continue anyway (not recommended)

    Args:
        state: FlowState with failed checks

    Returns:
        Updated state with user choice and attempt tracking
    """
    import sys

    # Build list of specific failures
    failed_checks = []
    if not state.get("unicode_check"):
        failed_checks.append("  ❌ Unicode UTF-8 encoding: " + state.get("unicode_check_error", "Failed"))
    else:
        failed_checks.append("  ✅ Unicode UTF-8 encoding: PASS")

    if not state.get("encoding_check"):
        failed_checks.append("  ❌ ASCII-only Python files: " + state.get("encoding_check_error", "Failed"))
    else:
        failed_checks.append("  ✅ ASCII-only Python files: PASS")

    if not state.get("windows_path_check"):
        failed_checks.append("  ❌ Windows path handling: " + state.get("windows_path_check_error", "Failed"))
    else:
        failed_checks.append("  ✅ Windows path handling: PASS")

    # Show message to user
    message = "\n[LEVEL -1] VALIDATION CHECKS:\n"
    message += "\n".join(failed_checks)
    message += "\n\nOPTIONS:\n"
    message += "  1. auto-fix   → Attempt repair + retry (max 3 times)\n"
    message += "  2. skip       → Continue anyway (⚠️  NOT RECOMMENDED)\n"

    # Get user choice
    print(message, file=sys.stderr)
    user_choice = input("\nYour choice [auto-fix/skip]: ").strip().lower()

    # Validate choice
    if user_choice not in ["auto-fix", "skip"]:
        user_choice = "auto-fix"  # Default to auto-fix

    # Track attempt count
    attempt = state.get("level_minus1_attempt", 0) + 1

    return {
        "level_minus1_user_choice": user_choice,
        "level_minus1_attempt": attempt,
        "level_minus1_failed_checks": failed_checks,
    }


def fix_level_minus1_issues(state: FlowState) -> dict:
    """Auto-fix Level -1 issues.

    Attempts to fix:
    1. Unicode UTF-8 encoding (Windows)
    2. Non-ASCII Python files (convert or report)
    3. Windows path handling (convert backslashes)

    Args:
        state: FlowState with failed checks

    Returns:
        Updated state with fixes applied
    """
    import io

    fixed_issues = []
    fix_errors = []

    # Fix 1: Unicode UTF-8 encoding
    if not state.get("unicode_check") and sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            elif hasattr(sys.stdout, "buffer"):
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer, encoding="utf-8", errors="replace"
                )

            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            elif hasattr(sys.stderr, "buffer"):
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.buffer, encoding="utf-8", errors="replace"
                )

            fixed_issues.append("✓ Unicode UTF-8 encoding reconfigured")
        except Exception as e:
            fix_errors.append(f"Could not fix Unicode: {e}")

    # Fix 2: Non-ASCII Python files (report for user to fix)
    if not state.get("encoding_check"):
        try:
            project_root = Path(state.get("project_root", "."))
            py_files = list(project_root.glob("**/*.py"))

            non_ascii_files = []
            for py_file in py_files[:50]:
                try:
                    content = py_file.read_bytes()
                    content.decode("ascii")
                except UnicodeDecodeError:
                    non_ascii_files.append(str(py_file.relative_to(project_root)))

            if non_ascii_files:
                # Note: We can't auto-fix this without knowing the intent
                fix_errors.append(
                    f"Non-ASCII files need manual fix: {', '.join(non_ascii_files[:3])}"
                )
            else:
                fixed_issues.append("✓ All Python files are ASCII-safe")
        except Exception as e:
            fix_errors.append(f"Could not check encoding: {e}")

    # Fix 3: Windows path handling (convert backslashes to forward slashes)
    if not state.get("windows_path_check") and sys.platform == "win32":
        try:
            import re
            project_root = Path(state.get("project_root", "."))
            fixed_files = []
            issues = []

            for py_file in list(project_root.glob("**/*.py"))[:50]:
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    if "\\" in content and ":\\" in content:
                        # Original content to compare
                        original_content = content

                        # Pattern 1: Replace Windows drive paths (C:\, D:\, etc.)
                        # Matches: C:\path\to\file or "C:\\path\\to\\file"
                        content = re.sub(r'([A-Z]):\\([\\]*)', r'\1:/\2', content)
                        content = re.sub(r'\\\\([\\]*)', r'/', content)

                        # Pattern 2: Replace standalone backslash paths in strings
                        # Matches paths that look like Windows paths
                        lines = content.split('\n')
                        new_lines = []
                        for line in lines:
                            # Replace backslashes with forward slashes in path-like strings
                            # But be careful not to break escape sequences
                            if '\\' in line and not line.strip().startswith('#'):
                                # Replace double backslashes with single forward slash
                                line = line.replace('\\\\', '/')
                                # Replace single backslashes that look like path separators
                                # (but not escape sequences like \n, \t, \r, etc.)
                                line = re.sub(r'(?<!\\)\\(?![\\ntrv"\'])', '/', line)
                            new_lines.append(line)

                        content = '\n'.join(new_lines)

                        # Only write back if content changed
                        if content != original_content:
                            py_file.write_text(content, encoding="utf-8")
                            fixed_files.append(str(py_file.relative_to(project_root)))
                        else:
                            # File had backslashes but they were all escape sequences
                            issues.append(str(py_file.relative_to(project_root)))
                except Exception as e:
                    fix_errors.append(f"Could not fix {py_file.name}: {e}")

            if fixed_files:
                fixed_issues.append(
                    f"✓ Fixed backslash paths in {len(fixed_files)} files: {', '.join(fixed_files[:3])}"
                )

            if issues:
                fix_errors.append(
                    f"Files with escape sequences only (not path separators): {', '.join(issues[:2])}"
                )

            if not fixed_files and not issues:
                fixed_issues.append("✓ All paths already use forward slashes")

        except Exception as e:
            fix_errors.append(f"Could not fix paths: {e}")

    return {
        "level_minus1_fixes_applied": fixed_issues,
        "level_minus1_fix_errors": fix_errors,
        "level_minus1_ready_to_retry": True,
    }


# ============================================================================
# MERGE NODE
# ============================================================================


def level_minus1_merge_node(state: FlowState) -> dict:
    """Merge results from all Level -1 checks.

    Determines overall Level -1 status based on individual checks:
    - All passed: OK (GO TO LEVEL 1)
    - Any failed: Check if user chose auto-fix
      ├─ If auto-fix: GO TO RETRY (with max 3 attempts)
      └─ If skip: GO TO LEVEL 1 anyway (⚠️ not recommended)

    Args:
        state: FlowState with all checks complete

    Returns:
        Updated state with level_minus1_status
    """
    import sys
    print(f"[L-1 MERGE] state['project_root'] at entry: '{state.get('project_root', 'MISSING')}'", file=sys.stderr)
    unicode_ok = state.get("unicode_check", False)
    encoding_ok = state.get("encoding_check", False)
    windows_path_ok = state.get("windows_path_check", False)

    updates = {}

    # All checks must pass for Level -1 to be OK
    if unicode_ok and encoding_ok and windows_path_ok:
        updates["level_minus1_status"] = "OK"
    else:
        # Any check failed - need recovery
        updates["level_minus1_status"] = "FAILED"
        errors = state.get("errors") or []  # Handle None case
        if not unicode_ok:
            errors = list(errors) + [f"Unicode check failed: {state.get('unicode_check_error')}"]
        if not encoding_ok:
            errors = list(errors) + [f"Encoding check failed: {state.get('encoding_check_error')}"]
        if not windows_path_ok:
            errors = list(errors) + [f"Windows path check failed: {state.get('windows_path_check_error')}"]
        updates["errors"] = errors

    print(f"[L-1 MERGE] Returning: {list(updates.keys())}", file=sys.stderr)
    return updates


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def route_after_level_minus1_merge(state: FlowState) -> str:
    """Route after merge node: OK vs FAILED.

    - If OK: exit to Level 1
    - If FAILED: ask user (interactive recovery)
    """
    status = state.get("level_minus1_status", "FAILED")
    if status == "OK":
        return END  # Go to Level 1
    else:
        return "ask_fix"  # Ask user for auto-fix or skip


def route_after_user_choice(state: FlowState) -> str:
    """Route after user choice: auto-fix vs skip.

    - If "auto-fix": execute fixes and retry
    - If "skip": exit to Level 1 anyway
    """
    choice = state.get("level_minus1_user_choice", "auto-fix").lower()
    attempt = state.get("level_minus1_attempt", 0)

    if choice == "auto-fix":
        if attempt >= 3:
            # Max attempts reached, ask again or give up
            return "ask_fix_again"
        return "fix_issues"
    else:
        # User chose skip, go to Level 1
        return "end_skip"


def route_after_fix_attempt(state: FlowState) -> str:
    """Route after fix attempt: retry checks or ask again.

    - After fixing, always retry the checks
    """
    return "node_unicode"  # Retry checks from start


def create_level_minus1_subgraph():
    """Create Level -1 subgraph with interactive recovery.

    Flow:
    START
      ↓
    [Check 1: Unicode]
      ↓
    [Check 2: Encoding]
      ↓
    [Check 3: Path]
      ↓
    [Merge: Status check]
      ├─ OK → END (Level 1)
      └─ FAILED → ask_fix (interactive)
         ├─ "auto-fix" → fix_issues → retry checks (max 3x)
         │              ├─ All pass → END (Level 1)
         │              └─ Any fail → ask_fix_again
         │
         └─ "skip" → END (Level 1, not recommended)

    Returns:
        Compiled StateGraph for Level -1
    """
    from typing import Literal

    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # ===== CHECK NODES =====
    graph.add_node("node_unicode", node_unicode_fix)
    graph.add_node("node_encoding", node_encoding_validation)
    graph.add_node("node_windows_path", node_windows_path_check)

    # ===== MERGE & ROUTING =====
    graph.add_node("merge", level_minus1_merge_node)

    # ===== RECOVERY NODES =====
    graph.add_node("ask_fix", ask_level_minus1_fix)
    graph.add_node("fix_issues", fix_level_minus1_issues)
    graph.add_node("ask_fix_again", ask_level_minus1_fix)  # Ask again after max attempts

    # ===== EDGES =====

    # Initial sequence: checks → merge
    graph.add_edge(START, "node_unicode")
    graph.add_edge("node_unicode", "node_encoding")
    graph.add_edge("node_encoding", "node_windows_path")
    graph.add_edge("node_windows_path", "merge")

    # After merge: conditional routing
    graph.add_conditional_edges(
        "merge",
        route_after_level_minus1_merge,
        {
            END: END,           # All checks passed
            "ask_fix": "ask_fix"  # User needs to choose
        }
    )

    # After user choice: auto-fix or skip
    graph.add_conditional_edges(
        "ask_fix",
        route_after_user_choice,
        {
            "fix_issues": "fix_issues",    # Execute fixes
            "ask_fix_again": "ask_fix_again",  # Ask again (max attempts)
            "end_skip": END,                   # Skip to Level 1
        }
    )

    # After asking again: auto-fix or skip (2nd+ attempt)
    graph.add_conditional_edges(
        "ask_fix_again",
        route_after_user_choice,
        {
            "fix_issues": "fix_issues",
            "ask_fix_again": "ask_fix_again",  # Can ask multiple times
            "end_skip": END,
        }
    )

    # After fix attempt: retry checks
    graph.add_edge("fix_issues", "node_unicode")  # Go back to check 1 (retry)

    return graph.compile()
