"""Level -1 Auto-Fix check node functions.

Extracted from subgraphs/level_minus1.py for modularity.
Windows-safe: ASCII only, no Unicode characters.

Contains:
- node_unicode_fix: Ensure UTF-8 output encoding on Windows
- node_encoding_validation: ASCII-only Python files on Windows (cp1252 safe)
- node_windows_path_check: Forward slashes, no drive letters in paths
"""

import logging
import sys
import time
from pathlib import Path

from ..error_logger import ErrorLogger
from ..flow_state import FlowState
from ..step_logger import write_level_log

_logger = logging.getLogger(__name__)


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
    _step_start = time.time()
    session_id = state.get("session_id")
    logger = ErrorLogger(session_id) if session_id else None

    _logger.debug("[L-1 UNICODE FIX] state['project_root'] at entry: '%s'", state.get("project_root", "MISSING"))
    updates = {}
    try:
        project_root_raw = state.get("project_root", ".")
        _pr = Path(project_root_raw)
        if not _pr.exists() or not _pr.is_dir():
            _logger.warning("project_root '%s' does not exist, skipping unicode check", _pr)
            updates["unicode_check"] = True
            updates["unicode_check_error"] = None
            write_level_log(state, "level-minus1", "unicode-fix", "SKIP", time.time() - _step_start, updates)
            return updates

        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["unicode_check"] = True
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True, "Not Windows platform")
            write_level_log(state, "level-minus1", "unicode-fix", "SKIP", time.time() - _step_start, updates)
            return updates

        # Windows - apply UTF-8 reconfiguration
        import io

        applied = False

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            applied = True
        elif hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            applied = True

        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            applied = True
        elif hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
            applied = True

        updates["unicode_check"] = True
        if applied:
            existing = state.get("auto_fix_applied") or []
            updates["auto_fix_applied"] = list(existing) + ["Unicode UTF-8 encoding"]
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True, "UTF-8 encoding applied")
        else:
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True, "Already UTF-8 configured")
        _logger.debug("[L-1 UNICODE FIX] Returning: %s", list(updates.keys()))
        write_level_log(state, "level-minus1", "unicode-fix", "OK", time.time() - _step_start, updates)
        return updates

    except Exception as e:
        updates["unicode_check"] = False
        updates["unicode_check_error"] = str(e)
        logger and logger.log_error(
            "Level -1", str(e), severity="ERROR", error_type="UnicodeError", recovery_action="Will retry with auto-fix"
        )
        _logger.debug("[L-1 UNICODE FIX] Returning (exception): %s", list(updates.keys()))
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
    session_id = state.get("session_id")
    logger = ErrorLogger(session_id) if session_id else None
    updates = {}
    try:
        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["encoding_check"] = True
            logger and logger.log_validation_result("Level -1", "ASCII-only Python files", True, "Not Windows platform")
            write_level_log(state, "level-minus1", "encoding-validation", "SKIP", time.time() - _step_start, updates)
            return updates

        project_root = Path(state.get("project_root", "."))
        if not project_root.exists() or not project_root.is_dir():
            _logger.warning("project_root '%s' does not exist, skipping encoding check", project_root)
            updates["encoding_check"] = True
            updates["encoding_check_error"] = None
            write_level_log(state, "level-minus1", "encoding-validation", "SKIP", time.time() - _step_start, updates)
            return updates

        py_files = list(project_root.glob("**/*.py"))
        if len(py_files) > 500:
            _logger.warning("project_root has %d Python files (>500), capping scan at 500", len(py_files))
            py_files = py_files[:500]

        non_ascii_files = []

        for py_file in py_files:  # Scan all Python files (capped at 500)
            try:
                content = py_file.read_bytes()
                # Check if content is pure ASCII
                content.decode("ascii")
            except (UnicodeDecodeError, Exception):
                non_ascii_files.append(str(py_file.relative_to(project_root)))

        # Store full file list in state for downstream visibility
        updates["encoding_nonascii_files"] = non_ascii_files

        if non_ascii_files:
            updates["encoding_check"] = False
            updates["encoding_check_error"] = (
                f"Non-ASCII Python files found ({len(non_ascii_files)} total): "
                f"{', '.join(non_ascii_files[:5])}"
                + (f" ... and {len(non_ascii_files) - 5} more" if len(non_ascii_files) > 5 else "")
            )
            logger and logger.log_validation_result(
                "Level -1", "ASCII-only Python files", False, updates["encoding_check_error"]
            )
        else:
            updates["encoding_check"] = True
            logger and logger.log_validation_result("Level -1", "ASCII-only Python files", True, "All files ASCII-safe")

        write_level_log(
            state,
            "level-minus1",
            "encoding-validation",
            "OK" if updates.get("encoding_check") else "FAILED",
            time.time() - _step_start,
            updates,
        )
        return updates

    except Exception as e:
        updates["encoding_check"] = False
        updates["encoding_check_error"] = str(e)
        logger and logger.log_error(
            "Level -1",
            str(e),
            severity="ERROR",
            error_type="EncodingValidationError",
            recovery_action="Will retry with auto-fix",
        )
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
    session_id = state.get("session_id")
    logger = ErrorLogger(session_id) if session_id else None
    updates = {}
    try:
        if sys.platform != "win32":
            # Non-Windows - skip check
            updates["windows_path_check"] = True
            logger and logger.log_validation_result("Level -1", "Windows path handling", True, "Not Windows platform")
            write_level_log(state, "level-minus1", "windows-path-check", "SKIP", time.time() - _step_start, updates)
            return updates

        project_root = Path(state.get("project_root", "."))
        if not project_root.exists() or not project_root.is_dir():
            _logger.warning("project_root '%s' does not exist, skipping path check", project_root)
            updates["windows_path_check"] = True
            updates["windows_path_check_error"] = None
            write_level_log(state, "level-minus1", "windows-path-check", "SKIP", time.time() - _step_start, updates)
            return updates

        # Check for hardcoded Windows drive paths (C:\, D:\, etc.)
        # Uses negative lookbehind to avoid false-positives on escape sequences
        # like \n, \s, \t that happen to follow a colon (e.g. "Either:\n").
        import re as _re_detect

        _DRIVE_DETECT_RE = _re_detect.compile(r"(?<![A-Za-z0-9_])([A-Za-z]):\\(?:[A-Za-z0-9_\-\. \\]+)")
        _path_files = list(project_root.glob("**/*.py"))
        if len(_path_files) > 500:
            _logger.warning("project_root has %d Python files (>500), capping scan at 500", len(_path_files))
            _path_files = _path_files[:500]
        issues = []
        for py_file in _path_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if _DRIVE_DETECT_RE.search(content):
                    issues.append(str(py_file.relative_to(project_root)))
            except Exception:
                pass

        if issues:
            updates["windows_path_check"] = False
            updates["windows_path_check_error"] = f"Backslash paths found: {', '.join(issues[:2])}"
            logger and logger.log_validation_result(
                "Level -1", "Windows path handling", False, updates["windows_path_check_error"]
            )
        else:
            updates["windows_path_check"] = True
            logger and logger.log_validation_result(
                "Level -1", "Windows path handling", True, "No backslash paths found"
            )

        write_level_log(
            state,
            "level-minus1",
            "windows-path-check",
            "OK" if updates.get("windows_path_check") else "FAILED",
            time.time() - _step_start,
            updates,
        )
        return updates

    except Exception as e:
        updates["windows_path_check"] = False
        updates["windows_path_check_error"] = str(e)
        logger and logger.log_error(
            "Level -1",
            str(e),
            severity="ERROR",
            error_type="WindowsPathCheckError",
            recovery_action="Will retry with auto-fix",
        )
        write_level_log(state, "level-minus1", "windows-path-check", "FAILED", time.time() - _step_start, None, str(e))
        return updates
