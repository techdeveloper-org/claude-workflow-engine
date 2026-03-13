#!/usr/bin/env python3
"""
Wrapper script for UserPromptSubmit hook.

This script properly handles stdin/environment setup for the 3-level-flow.py
script when called via Claude Code hooks.

Hooks pass the user message via stdin, but we need to handle it properly.
"""

import sys
import os
import subprocess
from pathlib import Path

def main():
    """Execute 3-level-flow with proper hook setup."""

    # Get the script location
    script_path = Path.home() / ".claude" / "scripts" / "3-level-flow.py"

    if not script_path.exists():
        print(f"ERROR: 3-level-flow.py not found at {script_path}", file=sys.stderr)
        sys.exit(1)

    # Read user message from stdin if available
    user_message = ""
    if not sys.stdin.isatty():
        try:
            user_message = sys.stdin.read().strip()
        except Exception:
            pass

    # Build environment
    env = os.environ.copy()

    # Pass user message via environment variable (safer than stdin redirection in subprocess)
    if user_message:
        env["CLAUDE_USER_MESSAGE"] = user_message

    # Run with summary flag (doesn't need user message if not available)
    cmd = [
        sys.executable,
        str(script_path),
        "--summary"
    ]

    # Execute the script
    try:
        result = subprocess.run(
            cmd,
            env=env,
            timeout=75
        )
        sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        print("ERROR: 3-level-flow execution timed out after 75 seconds", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to execute 3-level-flow: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
