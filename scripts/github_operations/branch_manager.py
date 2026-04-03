"""Git branch creation and query helpers for GitHub issue branches.

Provides create_issue_branch(), get_session_branch(), and is_on_issue_branch().
Branch naming format: {issue_type}/{issue_number}  e.g. bugfix/42, feature/123
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .labels import _detect_issue_type
from .session_integration import _get_current_session_id, _load_issues_mapping, _save_issues_mapping


def _get_repo_root():
    """Return the absolute path to the git repository root from the current directory.

    Returns:
        str or None: Absolute repo root path, or None if not inside a git
            repository or the command fails.
    """
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _log_branch_debug(debug_log, final_msg):
    """Write comprehensive branch creation debug log to file."""
    try:
        log_dir = Path.home() / ".claude" / "memory" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "branch-creation-debug.log"

        with open(log_file, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write("\n" + ("=" * 70) + "\n")
            f.write("[" + ts + "] Branch Creation Debug Log\n")
            f.write(("=" * 70) + "\n")
            for line in debug_log:
                f.write(line + "\n")
            f.write(("=" * 70) + "\n")
            f.write("[" + ts + "] FINAL: " + final_msg + "\n\n")
    except Exception:
        pass  # Logging errors should never block


def create_issue_branch(issue_number, subject, issue_type=None):
    """Create and checkout a git branch named {label}/{issueId}.

    Examples: fix/42, feature/123, refactor/99, docs/55, enhancement/78

    IMPORTANT: Must include issue ID for auto-close policy to work!
    The branch name is used to link issues in github-issues.json and PR workflow.

    Only creates if currently on main/master.
    Stores branch name in github-issues.json under 'session_branch'.

    Logs ALL steps to branch-creation-debug.log for troubleshooting.
    Blocks with error message if critical failure (prevents silent failures).

    Args:
        issue_number: GitHub issue number (int)
        subject: Task subject (used for type detection if issue_type not provided)
        issue_type: Optional explicit type ('fix', 'feature', 'refactor', 'docs', etc.)

    Returns:
        Branch name string on success, None on failure.
    """
    debug_log = []
    branch_name = None

    try:
        repo_root = _get_repo_root()
        if not repo_root:
            error_msg = "[BRANCH-CREATE] CRITICAL ERROR: Not in a git repository"
            debug_log.append(error_msg)
            _log_branch_debug(debug_log, error_msg)
            sys.stdout.write("\n" + error_msg + "\n\n")
            sys.stdout.flush()
            return None

        # STEP 1: Determine current branch
        debug_log.append("[BRANCH-CREATE] STEP 1: Reading current branch...")
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5, cwd=repo_root
        )
        if result.returncode != 0:
            error_msg = "[BRANCH-CREATE] STEP 1 FAILED: Could not read current branch"
            debug_log.append("  Error: " + result.stderr)
            _log_branch_debug(debug_log, error_msg)
            sys.stdout.write("\n[GH ERROR] " + error_msg + "\n\n")
            sys.stdout.flush()
            return None

        current_branch = result.stdout.strip()
        debug_log.append("[BRANCH-CREATE] STEP 1 OK: Current branch = " + current_branch)

        # Check if we're already on a feature branch
        if current_branch not in ("main", "master"):
            info_msg = "[BRANCH-CREATE] INFO: Already on " + current_branch + ", skipping branch creation"
            debug_log.append(info_msg)
            _log_branch_debug(debug_log, info_msg)
            return None

        # STEP 2: Detect issue type
        debug_log.append("[BRANCH-CREATE] STEP 2: Detecting issue type from subject...")
        if not issue_type:
            issue_type = _detect_issue_type(subject)
        debug_log.append("[BRANCH-CREATE] STEP 2 OK: Issue type = " + issue_type)

        # STEP 3: Build branch name
        branch_name = issue_type + "/" + str(issue_number)
        debug_log.append("[BRANCH-CREATE] STEP 3: Branch name = " + branch_name)

        # STEP 4: Create and checkout new branch
        debug_log.append("[BRANCH-CREATE] STEP 4: Creating branch (git checkout -b " + branch_name + ")...")
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name], capture_output=True, text=True, timeout=10, cwd=repo_root
        )

        if result.returncode == 0:
            debug_log.append("[BRANCH-CREATE] STEP 4 OK: Branch created and checked out")

            # STEP 5: Verify we're on the branch
            verify_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5, cwd=repo_root
            )
            if verify_result.returncode == 0:
                verified_branch = verify_result.stdout.strip()
                debug_log.append("[BRANCH-CREATE] STEP 5 VERIFY: Confirmed on " + verified_branch)

            # STEP 6: Store branch name in mapping (with session_id for future session validation)
            debug_log.append("[BRANCH-CREATE] STEP 6: Saving to github-issues.json...")
            mapping = _load_issues_mapping()
            mapping["session_branch"] = branch_name
            mapping["session_id"] = _get_current_session_id()  # Save current session_id
            mapping["branch_created_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            mapping["branch_from_issue"] = issue_number
            mapping["branch_type"] = issue_type
            _save_issues_mapping(mapping)
            debug_log.append("[BRANCH-CREATE] STEP 6 OK: Branch info saved")

            success_msg = "[BRANCH-CREATE] [OK] SUCCESS: " + branch_name
            debug_log.append(success_msg)
            _log_branch_debug(debug_log, success_msg)
            sys.stdout.write("[GH] Branch: " + branch_name + " (created + checked out)\n")
            sys.stdout.flush()
            return branch_name

        else:
            # STEP 4b: Branch might already exist - try checkout
            debug_log.append("[BRANCH-CREATE] STEP 4 FAILED: Create failed with code " + str(result.returncode))
            debug_log.append("  stderr: " + result.stderr[:300])
            debug_log.append("[BRANCH-CREATE] STEP 4b: Attempting checkout on existing branch...")

            result = subprocess.run(
                ["git", "checkout", branch_name], capture_output=True, text=True, timeout=10, cwd=repo_root
            )
            if result.returncode == 0:
                debug_log.append("[BRANCH-CREATE] STEP 4b OK: Existing branch checked out")
                mapping = _load_issues_mapping()
                mapping["session_branch"] = branch_name
                mapping["session_id"] = _get_current_session_id()  # Save current session_id
                mapping["branch_checked_out_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                _save_issues_mapping(mapping)
                success_msg = "[BRANCH-CREATE] [OK] SUCCESS: " + branch_name + " (existing)"
                debug_log.append(success_msg)
                _log_branch_debug(debug_log, success_msg)
                sys.stdout.write("[GH] Branch: " + branch_name + " (existing, checked out)\n")
                sys.stdout.flush()
                return branch_name
            else:
                # CRITICAL: Both create AND checkout failed
                error_msg = "[BRANCH-CREATE] CRITICAL FAILURE: Cannot create or checkout " + branch_name
                debug_log.append("[BRANCH-CREATE] STEP 4b FAILED: Checkout failed with code " + str(result.returncode))
                debug_log.append("  stderr: " + result.stderr[:300])
                debug_log.append(error_msg)
                debug_log.append("[BRANCH-CREATE] ACTION REQUIRED: Fix git manually or try again")
                _log_branch_debug(debug_log, error_msg)

                # BLOCKING: Print prominent error so user sees it
                sys.stdout.write("\n" + ("=" * 70) + "\n")
                sys.stdout.write("[GH ERROR] Branch creation FAILED: " + branch_name + "\n")
                sys.stdout.write("  Cannot create new branch: " + result.stderr[:150] + "\n")
                sys.stdout.write("  Cannot checkout existing: " + result.stderr[:150] + "\n")
                sys.stdout.write("  ACTION: Check git status and fix manually\n")
                sys.stdout.write("  DEBUG: See ~/.claude/memory/logs/branch-creation-debug.log\n")
                sys.stdout.write(("=" * 70) + "\n\n")
                sys.stdout.flush()
                return None

    except subprocess.TimeoutExpired:
        error_msg = "[BRANCH-CREATE] TIMEOUT: git command exceeded timeout (repo_root=" + str(repo_root) + ")"
        debug_log.append(error_msg)
        _log_branch_debug(debug_log, error_msg)
        sys.stdout.write("\n[GH ERROR] Branch creation timeout: " + str(branch_name) + "\n\n")
        sys.stdout.flush()
        return None

    except Exception as e:
        error_msg = "[BRANCH-CREATE] EXCEPTION: " + type(e).__name__ + ": " + str(e)
        debug_log.append(error_msg)
        _log_branch_debug(debug_log, error_msg)
        sys.stdout.write("\n[GH ERROR] Branch creation exception: " + str(e)[:150] + "\n\n")
        sys.stdout.flush()
        return None


def get_session_branch():
    """Get the branch name stored for the CURRENT SESSION ONLY.

    Returns branch name string only if:
    1. A session_branch exists in github-issues.json, AND
    2. It was created in the current session (session_id matches)

    Returns None if:
    - No branch stored, or
    - Branch is from a PREVIOUS session (stale)
    """
    try:
        # Get current session ID by finding latest session folder
        current_session_id = _get_current_session_id()

        # Load github-issues.json mapping
        mapping = _load_issues_mapping()

        # Check if stored branch matches current session
        stored_session_id = mapping.get("session_id", "")
        stored_branch = mapping.get("session_branch")

        # Only return branch if it's from CURRENT session
        if stored_branch and stored_session_id and stored_session_id == current_session_id:
            return stored_branch

        # Branch is stale or from different session - return None
        if stored_branch and stored_session_id != current_session_id:
            # Log this for debugging
            try:
                import logging as _logging

                _logging.debug("[SESSION] Ignoring stale branch from previous session: %s", stored_branch)
            except Exception:
                pass

        return None
    except Exception as e:
        # If anything fails, return None to prevent blocking
        try:
            import logging as _logging

            _logging.debug("[SESSION] get_session_branch() exception: %s: %s", type(e).__name__, str(e)[:150])
        except Exception:
            pass
        return None


def is_on_issue_branch():
    """Check if the current git branch matches the {label}/{id} pattern.

    Valid prefixes: fix/, feature/, refactor/, docs/, enhancement/, test/, task/
    Also supports legacy issue-{N} format for backwards compatibility.

    Returns:
        bool: True if on an issue branch, False otherwise.
    """
    valid_prefixes = ("fix/", "feature/", "refactor/", "docs/", "enhancement/", "test/", "task/", "issue-")
    try:
        repo_root = _get_repo_root()
        if not repo_root:
            return False

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5, cwd=repo_root
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return any(branch.startswith(p) for p in valid_prefixes)
    except Exception:
        pass
    return False
