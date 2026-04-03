"""GitHub CLI client primitives.

Provides is_gh_available(), _run_gh_cmd(), and module-level constants
GH_TIMEOUT and MAX_OPS_PER_SESSION. All other github_operations modules
import from here so the gh CLI check is centralised.
"""

import subprocess

MAX_OPS_PER_SESSION = 10
GH_TIMEOUT = 15  # seconds

# Cached per-invocation (module-level)
_gh_available = None


def is_gh_available():
    """Check if gh CLI is installed and authenticated. Cached per invocation."""
    global _gh_available
    if _gh_available is not None:
        return _gh_available

    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=GH_TIMEOUT)
        _gh_available = result.returncode == 0
    except Exception:
        _gh_available = False

    return _gh_available


def _run_gh_cmd(cmd, cwd=None, timeout=None):
    """Run a gh CLI command and return the CompletedProcess result.

    Args:
        cmd (list[str]): Full command list starting with 'gh'.
        cwd (str or None): Working directory for the command.
        timeout (int or None): Timeout in seconds. Defaults to GH_TIMEOUT.

    Returns:
        subprocess.CompletedProcess: Result object with returncode, stdout,
            stderr. On exception returns a fake result with returncode=-1.
    """
    if timeout is None:
        timeout = GH_TIMEOUT
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except Exception as exc:
        # Return a fake CompletedProcess so callers can check returncode
        class _FailResult:
            returncode = -1
            stdout = ""
            stderr = str(exc)

        return _FailResult()
