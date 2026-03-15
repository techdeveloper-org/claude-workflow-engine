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
import time
import platform
from pathlib import Path

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState
from ..error_logger import ErrorLogger
from ..backup_manager import BackupManager
from ..step_logger import write_level_log


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_LEVEL_MINUS1_ATTEMPTS = 3


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

    _step_start = time.time()
    session_id = state.get("session_id")
    logger = ErrorLogger(session_id) if session_id else None

    print(f"[L-1 UNICODE FIX] state['project_root'] at entry: '{state.get('project_root', 'MISSING')}'", file=sys.stderr)
    updates = {}
    try:
        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["unicode_check"] = True
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True, "Not Windows platform")
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
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True, "UTF-8 encoding applied")
        else:
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True, "Already UTF-8 configured")
        print(f"[L-1 UNICODE FIX] Returning: {list(updates.keys())}", file=sys.stderr)
        write_level_log(state, "level-minus1", "unicode-fix", "OK", time.time() - _step_start, updates)
        return updates

    except Exception as e:
        updates["unicode_check"] = False
        updates["unicode_check_error"] = str(e)
        logger and logger.log_error("Level -1", str(e), severity="ERROR", error_type="UnicodeError", recovery_action="Will retry with auto-fix")
        print(f"[L-1 UNICODE FIX] Returning (exception): {list(updates.keys())}", file=sys.stderr)
        write_level_log(state, "level-minus1", "unicode-fix", "FAILED", time.time() - _step_start, None, str(e))
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
    _step_start = time.time()
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

        write_level_log(state, "level-minus1", "encoding-validation",
                        "OK" if updates.get("encoding_check") else "FAILED",
                        time.time() - _step_start, updates)
        return updates

    except Exception as e:
        updates["encoding_check"] = False
        updates["encoding_check_error"] = str(e)
        write_level_log(state, "level-minus1", "encoding-validation", "FAILED", time.time() - _step_start, None, str(e))
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
    _step_start = time.time()
    updates = {}
    if "session_id" in state:
        updates["session_id"] = state["session_id"]
    try:
        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["windows_path_check"] = True
            write_level_log(state, "level-minus1", "windows-path-check", "OK", time.time() - _step_start, updates)
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

        write_level_log(state, "level-minus1", "windows-path-check",
                        "OK" if updates.get("windows_path_check") else "FAILED",
                        time.time() - _step_start, updates)
        return updates

    except Exception as e:
        updates["windows_path_check"] = False
        updates["windows_path_check_error"] = str(e)
        write_level_log(state, "level-minus1", "windows-path-check", "FAILED", time.time() - _step_start, None, str(e))
        return updates


# ============================================================================
# INTERACTIVE RECOVERY NODES
# ============================================================================


def ask_level_minus1_fix(state: FlowState) -> dict:
    """Ask user what to do when Level -1 checks fail.

    Shows specific PASS/FAIL for each check and offers:
    - "auto-fix": Attempt to fix issues, retry (max 3 times)
    - "skip": Continue anyway (not recommended)

    IMPORTANT: After 3 attempts, automatically continues to Level 1 with warnings,
    regardless of check status. This prevents infinite retry loops.

    IMPORTANT: When running in hook context (no stdin), automatically defaults
    to "auto-fix" for a seamless experience without hanging.

    Args:
        state: FlowState with failed checks

    Returns:
        Updated state with user choice and attempt tracking
    """
    import sys

    # Track attempt count FIRST
    attempt = state.get("level_minus1_attempt", 0) + 1

    # Check if we've exceeded max attempts
    if attempt > MAX_LEVEL_MINUS1_ATTEMPTS:
        session_id = state.get("session_id")
        logger = ErrorLogger(session_id) if session_id else None

        print("\n[LEVEL -1] 🔴 FATAL: MAX ATTEMPTS REACHED (3/3)")
        print("[LEVEL -1] Continuing to Level 1 despite unresolved checks...")

        # Log FATAL_FAILURE state
        logger and logger.log_error(
            "Level -1",
            f"Max {MAX_LEVEL_MINUS1_ATTEMPTS} retry attempts exceeded",
            severity="CRITICAL",
            error_type="FatalError",
            recovery_action="Force continue to Level 1"
        )
        logger and logger.save_audit_trail()

        return {
            "level_minus1_user_choice": "force_continue",
            "level_minus1_attempt": attempt,
            "level_minus1_max_attempts_reached": True,
            "level_minus1_fatal_failure": True,
        }

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
    message = f"\n[LEVEL -1] VALIDATION CHECKS ({attempt}/{MAX_LEVEL_MINUS1_ATTEMPTS}):\n"
    message += "\n".join(failed_checks)
    message += "\n\nOPTIONS:\n"
    message += "  1. auto-fix   → Attempt repair + retry\n"
    message += "  2. skip       → Continue anyway (⚠️  NOT RECOMMENDED)\n"

    # Print message to stdout so it reaches user through hook
    print(message)

    # Get user choice - with fallback for hook environment
    user_choice = "auto-fix"  # Default
    try:
        # Try to get input only if stdin is a TTY (interactive terminal)
        if sys.stdin.isatty():
            user_choice = input("\nYour choice [auto-fix/skip]: ").strip().lower()
        else:
            # Hook context: stdin not available, auto-default to auto-fix
            print("\n[LEVEL -1] Running in hook context (non-interactive)")
            print("[LEVEL -1] Automatically attempting auto-fix...")
            user_choice = "auto-fix"
    except (EOFError, KeyboardInterrupt):
        # stdin closed or interrupted, use default
        print("\n[LEVEL -1] No input available, using auto-fix")
        user_choice = "auto-fix"
    except Exception as e:
        # Any other error, use default
        print(f"\n[LEVEL -1] Could not read input ({e}), using auto-fix")
        user_choice = "auto-fix"

    # Validate choice
    if user_choice not in ["auto-fix", "skip"]:
        user_choice = "auto-fix"  # Default to auto-fix

    return {
        "level_minus1_user_choice": user_choice,
        "level_minus1_attempt": attempt,
        "level_minus1_failed_checks": failed_checks,
    }


def fix_level_minus1_issues(state: FlowState) -> dict:
    """Auto-fix Level -1 issues with backup & validation.

    Attempts to fix:
    1. Unicode UTF-8 encoding (Windows)
    2. Non-ASCII Python files (convert or report)
    3. Windows path handling (convert backslashes)

    All fixes are backed up before modification and validated after.

    Args:
        state: FlowState with failed checks

    Returns:
        Updated state with fixes applied
    """
    import io

    session_id = state.get("session_id")
    logger = ErrorLogger(session_id) if session_id else None
    backup = BackupManager(session_id) if session_id else None

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
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True)
        except Exception as e:
            error_msg = f"Could not fix Unicode: {e}"
            fix_errors.append(error_msg)
            logger and logger.log_error("Level -1", str(e), severity="ERROR", error_type="UnicodeError")

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
                    # Step 1: Backup file before modification
                    backup and backup.backup_file(str(py_file), "Level -1", "Before path fix")

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

                            # Step 2: Validate file integrity after modification
                            if backup and backup.validate_file_integrity(str(py_file), "Level -1"):
                                fixed_files.append(str(py_file.relative_to(project_root)))
                                logger and logger.log_validation_result("Level -1", f"Path fix: {py_file.name}", True)

                                # Step 3: Generate diff for audit trail
                                diff_path = backup.generate_diff(str(py_file), "Level -1", "path_fix")
                                logger and logger.log_decision("Level -1", "File modified and validated", f"Path fix applied to {py_file.name}", chosen_option=f"Diff saved: {diff_path}")
                            else:
                                # Restore file if validation failed
                                backup and backup.restore_file(str(py_file), "Level -1")
                                fix_errors.append(f"Validation failed for {py_file.name}, file restored")
                                logger and logger.log_error("Level -1", f"Validation failed for {py_file.name}", severity="ERROR", recovery_action="File restored from backup")
                        else:
                            # File had backslashes but they were all escape sequences
                            issues.append(str(py_file.relative_to(project_root)))
                except Exception as e:
                    # Restore file on any error
                    backup and backup.restore_file(str(py_file), "Level -1")
                    error_msg = f"Could not fix {py_file.name}: {e}"
                    fix_errors.append(error_msg)
                    logger and logger.log_error("Level -1", str(e), severity="ERROR", recovery_action=f"File restored: {py_file.name}")

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
            error_msg = f"Could not fix paths: {e}"
            fix_errors.append(error_msg)
            logger and logger.log_error("Level -1", str(e), severity="ERROR", error_type="PathFixError")

    return {
        "level_minus1_fixes_applied": fixed_issues,
        "level_minus1_fix_errors": fix_errors,
        "level_minus1_ready_to_retry": True,
    }


# ============================================================================
# MERGE NODE
# ============================================================================


def level_minus1_merge_node(state: FlowState) -> dict:
    """Merge results from all Level -1 checks with comprehensive logging.

    Determines overall Level -1 status based on individual checks:
    - All passed: OK (GO TO LEVEL 1)
    - Any failed: Check if user chose auto-fix
      ├─ If auto-fix: GO TO RETRY (with max 3 attempts)
      └─ If skip: GO TO LEVEL 1 anyway (⚠️ not recommended)
    - Fatal failure: Exceeded max attempts, force continue with warning

    Args:
        state: FlowState with all checks complete

    Returns:
        Updated state with level_minus1_status
    """
    import sys

    _step_start = time.time()
    session_id = state.get("session_id")
    logger = ErrorLogger(session_id) if session_id else None

    print(f"[L-1 MERGE] state['project_root'] at entry: '{state.get('project_root', 'MISSING')}'", file=sys.stderr)

    unicode_ok = state.get("unicode_check", False)
    encoding_ok = state.get("encoding_check", False)
    windows_path_ok = state.get("windows_path_check", False)

    updates = {}

    # All checks must pass for Level -1 to be OK
    if unicode_ok and encoding_ok and windows_path_ok:
        updates["level_minus1_status"] = "OK"
        logger and logger.log_validation_result("Level -1", "All checks passed", True)
    else:
        # Any check failed - need recovery
        updates["level_minus1_status"] = "FAILED"
        errors = state.get("errors") or []  # Handle None case

        # Log individual failures
        if not unicode_ok:
            error_msg = state.get('unicode_check_error', 'Unknown error')
            errors = list(errors) + [f"Unicode check failed: {error_msg}"]
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", False, error_msg)

        if not encoding_ok:
            error_msg = state.get('encoding_check_error', 'Unknown error')
            errors = list(errors) + [f"Encoding check failed: {error_msg}"]
            logger and logger.log_validation_result("Level -1", "ASCII-only Python files", False, error_msg)

        if not windows_path_ok:
            error_msg = state.get('windows_path_check_error', 'Unknown error')
            errors = list(errors) + [f"Windows path check failed: {error_msg}"]
            logger and logger.log_validation_result("Level -1", "Windows path handling", False, error_msg)

        updates["errors"] = errors

    print(f"[L-1 MERGE] Returning: {list(updates.keys())}", file=sys.stderr)
    write_level_log(state, "level-minus1", "merge",
                    updates.get("level_minus1_status", "FAILED"),
                    time.time() - _step_start, updates)
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
    """Route after user choice: auto-fix vs skip vs force_continue.

    - If "auto-fix": execute fixes and retry
    - If "skip": exit to Level 1 anyway
    - If "force_continue": max attempts reached, exit to Level 1
    """
    choice = state.get("level_minus1_user_choice", "auto-fix").lower()
    attempt = state.get("level_minus1_attempt", 0)

    if choice == "force_continue":
        # Max attempts reached, forced progression to Level 1
        return "end_skip"
    elif choice == "auto-fix":
        if attempt > MAX_LEVEL_MINUS1_ATTEMPTS:
            # This shouldn't happen (ask_fix should have returned force_continue)
            # but as a safety check, progress to Level 1
            return "end_skip"
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
    """Create Level -1 subgraph with interactive recovery and max 3 attempts enforcement.

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
      └─ FAILED → ask_fix (interactive, max 3 attempts total)
         ├─ "auto-fix" (attempt ≤ 3) → fix_issues → retry checks
         │                             ├─ All pass → END (Level 1)
         │                             └─ Any fail → ask_fix (increments attempt)
         │
         ├─ "auto-fix" (attempt > 3) → force_continue → END (Level 1, with warning)
         │
         └─ "skip" → END (Level 1, not recommended)

    MAX_LEVEL_MINUS1_ATTEMPTS = 3
    After 3 failed attempts, automatically continues to Level 1 regardless of checks.

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

    # After user choice: auto-fix, skip, or force_continue (max attempts)
    graph.add_conditional_edges(
        "ask_fix",
        route_after_user_choice,
        {
            "fix_issues": "fix_issues",    # Execute fixes and retry
            "end_skip": END,               # Skip to Level 1 (user chose skip or max attempts reached)
        }
    )

    # After fix attempt: retry all checks from start
    graph.add_edge("fix_issues", "node_unicode")  # Go back to check 1 (retry)

    return graph.compile()
