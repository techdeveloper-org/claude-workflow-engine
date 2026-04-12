"""
post_tool_tracker/policies/post_merge_update.py - Level 3.10+ non-blocking policy.

Auto-updates VERSION, README, SRS after PR merge.
Policy: version-release-policy.md
"""

import json
import sys
from pathlib import Path


def run_post_merge_version_update(tool_name, tool_input, is_error):
    """Level 3.10+: Auto-update VERSION, README, SRS after PR merge (non-blocking).

    Policy: version-release-policy.md
    Rule: After PR merge to main, automatically bump VERSION and update docs.

    Detects: 'gh pr merge', 'git push' with merge in recent commits
    Calls: post-merge-version-updater.py

    Args:
        tool_name (str):   Current tool being invoked.
        tool_input (dict): Bash tool input dict.
        is_error (bool):   Whether the tool call errored.

    Returns:
        (bool, str): Always (False, '') - this check is non-blocking.
    """
    if tool_name != "Bash" or is_error:
        return False, ""

    cmd = (tool_input or {}).get("command", "").lower()
    is_merge_cmd = "gh pr merge" in cmd or ("git push" in cmd and "main" in cmd)

    if not is_merge_cmd:
        return False, ""

    try:
        import subprocess as _sp_merge

        # __file__ is scripts/post_tool_tracker/policies/post_merge_update.py
        # post-merge-version-updater.py lives in scripts/
        updater_script = Path(__file__).parent.parent.parent / "post-merge-version-updater.py"
        if updater_script.exists():
            result = _sp_merge.run([sys.executable, str(updater_script)], capture_output=True, timeout=120)

            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout.decode())
                    if output.get("status") == "OK":
                        new_version = output.get("new_version", "unknown")
                        sys.stderr.write(
                            "[POST-MERGE] Version auto-updated to " + str(new_version) + "\n"
                            "  - VERSION file updated\n"
                            "  - README.md updated\n"
                            "  - SYSTEM_REQUIREMENTS_SPECIFICATION.md updated\n"
                            "  - Auto-commit created\n"
                        )
                        sys.stderr.flush()
                except Exception:
                    pass
    except Exception:
        pass  # Non-blocking: version update errors never fail the hook

    return False, ""
