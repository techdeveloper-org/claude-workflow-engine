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

    # Determine project path dynamically (works for ANY project)
    # Priority: CWD (Claude Code runs from project root) > this script's parent
    _cwd = Path.cwd()
    _script_parent = Path(__file__).resolve().parent.parent  # scripts/ -> project root

    project_path = ""
    for proj in [_cwd, _script_parent]:
        if (proj / "CLAUDE.md").exists() or (proj / "README.md").exists():
            project_path = str(proj)
            break

    # **CRITICAL**: Pass project path via environment variable
    # This is more reliable than command-line arguments for nested subprocess calls
    if project_path:
        env["CLAUDE_PROJECT_ROOT"] = project_path

    # Run with summary flag
    cmd = [
        sys.executable,
        str(script_path),
        "--summary"
    ]

    # Execute the script with output capture so Claude Code can see all messages
    try:
        result = subprocess.run(
            cmd,
            env=env,
            timeout=180,  # 3 minutes - allows for Ollama processing + all 14 steps
            capture_output=True,  # CRITICAL: Capture output so we can forward to Claude Code
            text=True
        )

        # Forward captured output to Claude Code UI
        # This is critical for Level -1 error messages to reach the user
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        print("ERROR: 3-level-flow execution timed out after 180 seconds", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to execute 3-level-flow: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
