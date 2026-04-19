"""Level -1 Auto-Fix recovery and interactive fix functions.

Extracted from subgraphs/level_minus1.py for modularity.
Windows-safe: ASCII only, no Unicode characters.

Contains:
- _load_failure_kb: Load Failure Prevention KB from policy file
- ask_level_minus1_fix: Interactive user prompt for fix decisions
- fix_level_minus1_issues: Auto-fix Level -1 issues with backup & validation
"""

import logging
import sys
from pathlib import Path

from ..backup_manager import BackupManager
from ..error_logger import ErrorLogger
from ..flow_state import FlowState
from .merge import MAX_LEVEL_MINUS1_ATTEMPTS

_logger = logging.getLogger(__name__)


# ============================================================================
# FAILURE PREVENTION KB
# ============================================================================


def _load_failure_kb(project_root_str="."):
    """Load Failure Prevention KB from common-failures-prevention.md.

    Parses Signature -> Prevention Strategy pairs from the KB policy file.
    Returns list of dicts: [{signature, prevention, category}].

    Fail-open: returns empty list on any error.
    """
    try:
        import re

        # Try new level-based location first, fall back to legacy path
        kb_path = (
            Path(__file__).parent.parent
            / "level3_execution"
            / "policies"
            / "failure-prevention"
            / "common-failures-prevention.md"
        )
        if not kb_path.is_file():
            kb_path = (
                Path(project_root_str)
                / "policies"
                / "03-execution-system"
                / "failure-prevention"
                / "common-failures-prevention.md"
            )
        if not kb_path.is_file():
            return []

        content = kb_path.read_text(encoding="utf-8", errors="replace")

        entries = []
        # Parse markdown sections: look for Signature/Prevention pairs
        # Pattern: **Signature:** ... **Prevention Strategy:** ...
        sig_pattern = re.compile(
            r"\*\*Signature[:\s]*\*\*\s*(.+?)(?:\n|\r)",
            re.IGNORECASE,
        )
        prev_pattern = re.compile(
            r"\*\*Prevention\s*(?:Strategy)?[:\s]*\*\*\s*(.+?)(?:\n|\r)",
            re.IGNORECASE,
        )

        signatures = sig_pattern.findall(content)
        preventions = prev_pattern.findall(content)

        # Pair up signatures with their prevention strategies
        for i, sig in enumerate(signatures):
            prevention = preventions[i].strip() if i < len(preventions) else ""
            entries.append(
                {
                    "signature": sig.strip(),
                    "prevention": prevention,
                    "category": "auto-fix",
                }
            )

        return entries
    except Exception as exc:
        _logger.warning("[LEVEL -1 KB] Failed to load failure KB: %s", exc)
        return []


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
    # Track attempt count FIRST
    attempt = state.get("level_minus1_retry_count", 0) + 1

    # Check if we've exceeded max attempts
    if attempt > MAX_LEVEL_MINUS1_ATTEMPTS:
        session_id = state.get("session_id")
        logger = ErrorLogger(session_id) if session_id else None

        print("\n[LEVEL -1] [ERROR] FATAL: MAX ATTEMPTS REACHED (3/3)")
        print("[LEVEL -1] Continuing to Level 1 despite unresolved checks...")

        # Log FATAL_FAILURE state
        logger and logger.log_error(
            "Level -1",
            f"Max {MAX_LEVEL_MINUS1_ATTEMPTS} retry attempts exceeded",
            severity="CRITICAL",
            error_type="FatalError",
            recovery_action="Force continue to Level 1",
        )
        logger and logger.save_audit_trail()

        return {
            "level_minus1_user_choice": "force_continue",
            "level_minus1_retry_count": attempt,
            "level_minus1_max_attempts_reached": True,
            "level_minus1_fatal_failure": True,
        }

    # Build list of specific failures
    failed_checks = []
    if not state.get("unicode_check"):
        failed_checks.append("  [FAIL] Unicode UTF-8 encoding: " + state.get("unicode_check_error", "Failed"))
    else:
        failed_checks.append("  [PASS] Unicode UTF-8 encoding: PASS")

    if not state.get("encoding_check"):
        failed_checks.append("  [FAIL] ASCII-only Python files: " + state.get("encoding_check_error", "Failed"))
    else:
        failed_checks.append("  [PASS] ASCII-only Python files: PASS")

    if not state.get("windows_path_check"):
        failed_checks.append("  [FAIL] Windows path handling: " + state.get("windows_path_check_error", "Failed"))
    else:
        failed_checks.append("  [PASS] Windows path handling: PASS")

    # Failure Prevention KB lookup (best-effort, never blocks)
    kb_suggestions = []
    kb_loaded = False
    try:
        project_root = state.get("project_root", ".")
        kb_entries = _load_failure_kb(project_root)
        kb_loaded = len(kb_entries) > 0
        if kb_entries:
            for check_msg in failed_checks:
                if "PASS" in check_msg:
                    continue
                for entry in kb_entries:
                    # Match KB signature keywords against failure message
                    sig_words = entry["signature"].lower().split()
                    if any(w in check_msg.lower() for w in sig_words if len(w) > 3):
                        kb_suggestions.append(entry)
    except Exception:
        pass  # Fail-open

    # Show message to user (including KB suggestions if available)
    message = f"\n[LEVEL -1] VALIDATION CHECKS ({attempt}/{MAX_LEVEL_MINUS1_ATTEMPTS}):\n"
    message += "\n".join(failed_checks)

    if kb_suggestions:
        message += "\n\n  KB SUGGESTIONS:/n"
        seen = set()
        for kb in kb_suggestions:
            sig = kb.get("signature", "")
            if sig not in seen:
                seen.add(sig)
                message += "    -> %s: %s\n" % (sig, kb.get("prevention", ""))

    message += "\n\nOPTIONS:/n"
    message += "  1. auto-fix   -> Attempt repair + retry\n"
    message += "  2. skip       -> Continue anyway (NOT RECOMMENDED)\n"

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
        "level_minus1_retry_count": attempt,
        "level_minus1_failed_checks": failed_checks,
        "failure_kb_loaded": kb_loaded,
        "failure_kb_suggestions": kb_suggestions,
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
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            elif hasattr(sys.stderr, "buffer"):
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

            fixed_issues.append("[FIXED] Unicode UTF-8 encoding reconfigured")
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True)
        except Exception as e:
            error_msg = f"Could not fix Unicode: {e}"
            fix_errors.append(error_msg)
            logger and logger.log_error("Level -1", str(e), severity="ERROR", error_type="UnicodeError")

    # Fix 2: Non-ASCII Python files - REPORT ONLY (per encoding-validation-policy.md)
    # Policy: "Cannot auto-fix. Non-ASCII content requires human judgment."
    # Action: Report non-ASCII files and flag for manual review.
    if not state.get("encoding_check"):
        try:
            nonascii_files = state.get("encoding_nonascii_files") or []
            if nonascii_files:
                fix_errors.append(
                    "Non-ASCII files need MANUAL review (%d files): %s%s"
                    % (
                        len(nonascii_files),
                        ", ".join(nonascii_files[:5]),
                        " ... and %d more" % (len(nonascii_files) - 5) if len(nonascii_files) > 5 else "",
                    )
                )
                fixed_issues.append(
                    ">> Encoding: %d non-ASCII files reported (auto-fix disabled per policy)" % len(nonascii_files)
                )
                logger and logger.log_decision(
                    "Level -1",
                    "Encoding fix skipped",
                    "Policy requires manual review for non-ASCII content",
                    chosen_option="report-only",
                )
            else:
                fixed_issues.append(">> All Python files are ASCII-safe")
        except Exception as e:
            fix_errors.append("Could not check encoding: %s" % e)

    # Fix 3: Windows path handling (convert backslashes to forward slashes)
    if not state.get("windows_path_check") and sys.platform == "win32":
        try:
            import re as _re_fix

            # Only replace backslashes that are part of a Windows drive path (X:\something).
            # Negative lookbehind (?<![A-Za-z0-9_]) ensures the drive letter is not preceded
            # by another word character, preventing false matches on escape sequences like
            # "Either:\n" (where 'r' would be mistaken for a drive letter).
            _DRIVE_PATH_RE = _re_fix.compile(r"(?<![A-Za-z0-9_])([A-Za-z]):\\([\w\\. \-]+)")

            def _fix_drive_path(m):
                drive = m.group(1)
                rest = m.group(2).replace("\\", "/")
                return drive + ":/" + rest

            project_root = Path(state.get("project_root", "."))
            fixed_files = []
            issues = []

            _fix_files = list(project_root.glob("**/*.py"))
            if len(_fix_files) > 500:
                _logger.warning("project_root has %d Python files (>500), capping path fix at 500", len(_fix_files))
                _fix_files = _fix_files[:500]
            for py_file in _fix_files:
                try:
                    # Step 1: Backup file before modification
                    backup and backup.backup_file(str(py_file), "Level -1", "Before path fix")

                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    if "\\" in content and ":\\" in content:
                        # Original content to compare
                        original_content = content

                        # Replace only matched Windows drive paths (e.g. C:/foo/bar -> C:/foo/bar).
                        # Backslashes outside a drive-path match are left untouched.
                        content = _DRIVE_PATH_RE.sub(_fix_drive_path, content)

                        # Only write back if content changed
                        if content != original_content:
                            py_file.write_text(content, encoding="utf-8")

                            # Step 2: Validate file integrity after modification
                            if backup and backup.validate_file_integrity(str(py_file), "Level -1"):
                                fixed_files.append(str(py_file.relative_to(project_root)))
                                logger and logger.log_validation_result("Level -1", f"Path fix: {py_file.name}", True)

                                # Step 3: Generate diff for audit trail
                                diff_path = backup.generate_diff(str(py_file), "Level -1", "path_fix")
                                logger and logger.log_decision(
                                    "Level -1",
                                    "File modified and validated",
                                    f"Path fix applied to {py_file.name}",
                                    chosen_option=f"Diff saved: {diff_path}",
                                )
                            else:
                                # Restore file if validation failed
                                backup and backup.restore_file(str(py_file), "Level -1")
                                fix_errors.append(f"Validation failed for {py_file.name}, file restored")
                                logger and logger.log_error(
                                    "Level -1",
                                    f"Validation failed for {py_file.name}",
                                    severity="ERROR",
                                    recovery_action="File restored from backup",
                                )
                        else:
                            # File had backslashes but they were all escape sequences
                            issues.append(str(py_file.relative_to(project_root)))
                except Exception as e:
                    # Restore file on any error
                    backup and backup.restore_file(str(py_file), "Level -1")
                    error_msg = f"Could not fix {py_file.name}: {e}"
                    fix_errors.append(error_msg)
                    logger and logger.log_error(
                        "Level -1", str(e), severity="ERROR", recovery_action=f"File restored: {py_file.name}"
                    )

            if fixed_files:
                fixed_issues.append(
                    f"[FIXED] Fixed backslash paths in {len(fixed_files)} files: {', '.join(fixed_files[:3])}"
                )

            if issues:
                fix_errors.append(f"Files with escape sequences only (not path separators): {', '.join(issues[:2])}")

            if not fixed_files and not issues:
                fixed_issues.append("[FIXED] All paths already use forward slashes")

        except Exception as e:
            error_msg = f"Could not fix paths: {e}"
            fix_errors.append(error_msg)
            logger and logger.log_error("Level -1", str(e), severity="ERROR", error_type="PathFixError")

    return {
        "level_minus1_fixes_applied": fixed_issues,
        "level_minus1_fix_errors": fix_errors,
        "level_minus1_ready_to_retry": True,
    }
