"""Level -1 merge node and constants.

Extracted from subgraphs/level_minus1.py for modularity.
Windows-safe: ASCII only, no Unicode characters.

Contains:
- MAX_LEVEL_MINUS1_ATTEMPTS: Maximum retry attempts for Level -1 checks
- level_minus1_merge_node: Merge results from all Level -1 checks
"""

import logging
import time

from ..error_logger import ErrorLogger
from ..flow_state import FlowState
from ..step_logger import write_level_log

_logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_LEVEL_MINUS1_ATTEMPTS = 3


# ============================================================================
# MERGE NODE
# ============================================================================


def level_minus1_merge_node(state: FlowState) -> dict:
    """Merge results from all Level -1 checks with comprehensive logging.

    Determines overall Level -1 status based on individual checks:
    - All passed: OK (GO TO LEVEL 1)
    - Any failed: Check if user chose auto-fix
      -- If auto-fix: GO TO RETRY (with max 3 attempts)
      -- If skip: GO TO LEVEL 1 anyway (not recommended)
    - Fatal failure: Exceeded max attempts, force continue with warning

    Args:
        state: FlowState with all checks complete

    Returns:
        Updated state with level_minus1_status
    """
    _step_start = time.time()
    session_id = state.get("session_id")
    logger = ErrorLogger(session_id) if session_id else None

    _logger.debug("[L-1 MERGE] state['project_root'] at entry: '%s'", state.get("project_root", "MISSING"))

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

        # Return only NEW errors for this merge pass.
        # The FlowState 'errors' field uses a _merge_lists reducer that appends
        # incoming lists onto the accumulated state list.  If we read the existing
        # state["errors"] here and re-return them we would double-count every entry
        # on each retry cycle.  Always return only the freshly generated entries.
        new_errors = []

        # Log individual failures
        if not unicode_ok:
            error_msg = state.get("unicode_check_error", "Unknown error")
            new_errors.append(f"Unicode check failed: {error_msg}")
            logger and logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", False, error_msg)

        if not encoding_ok:
            error_msg = state.get("encoding_check_error", "Unknown error")
            new_errors.append(f"Encoding check failed: {error_msg}")
            logger and logger.log_validation_result("Level -1", "ASCII-only Python files", False, error_msg)

        if not windows_path_ok:
            error_msg = state.get("windows_path_check_error", "Unknown error")
            new_errors.append(f"Windows path check failed: {error_msg}")
            logger and logger.log_validation_result("Level -1", "Windows path handling", False, error_msg)

        if new_errors:
            updates["errors"] = new_errors

    _logger.debug("[L-1 MERGE] Returning: %s", list(updates.keys()))
    write_level_log(
        state, "level-minus1", "merge", updates.get("level_minus1_status", "FAILED"), time.time() - _step_start, updates
    )
    return updates
