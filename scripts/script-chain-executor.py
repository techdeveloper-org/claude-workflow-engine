#!/usr/bin/env python3
"""
script-chain-executor.py - Nested/Chained Script Execution Orchestrator

Implements nested/chained execution model where:
- Each script receives output from previous script as input
- Sequential execution (NOT parallel/concurrent)
- Data flows between consecutive scripts
- Policy blocking preserved (exit code 2 on enforcement violations)
- Claude Code hook stdin (prompt, cwd) is preserved and passed to all scripts
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

def chain_execute(scripts, initial_context=None, mode="pre-tool"):
    """Execute scripts in sequence with data flow.

    Child script stderr is forwarded to parent stderr so the user can
    see progress/debug messages.  For pre-tool mode, the last script's
    raw text output (e.g. 3-level-flow checkpoint table) is printed to
    stdout so Claude Code displays it to the user.
    """

    if not scripts:
        return (0, {})

    context = initial_context or {
        "mode": mode,
        "session_id": os.environ.get("CLAUDE_SESSION_ID", ""),
        "timestamp": datetime.now().isoformat(),
        "chain_results": []
    }

    accumulated_output = {}
    # Store the last script's raw text output for display to the user
    last_raw_text = ""

    for i, script in enumerate(scripts):
        if not os.path.exists(script):
            sys.stderr.write(f"[CHAIN] Error: Script not found: {script}\n")
            return (1, accumulated_output)

        sys.stderr.write(f"[CHAIN] Step {i+1}/{len(scripts)}: {Path(script).name}\n")

        stdin_data = json.dumps(context)

        try:
            result = subprocess.run(
                ["python", script],
                input=stdin_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=90
            )

            stdout = result.stdout.strip() if result.stdout else ""
            stderr = result.stderr.strip() if result.stderr else ""
            exit_code = result.returncode

            # Forward child stderr to parent stderr (visible to user)
            if stderr:
                sys.stderr.write(stderr + "\n")

            script_output = {}
            is_raw_text = False
            if stdout:
                try:
                    script_output = json.loads(stdout)
                except (json.JSONDecodeError, ValueError):
                    # Non-JSON output: store FULL text (no truncation)
                    script_output = {"raw_output": stdout}
                    is_raw_text = True

            # Track the last raw text output for final display
            if is_raw_text and stdout:
                last_raw_text = stdout

            step_result = {
                "script": Path(script).name,
                "exit_code": exit_code,
                "output": script_output,
            }

            context["chain_results"].append(step_result)
            accumulated_output[Path(script).stem] = script_output

            # BLOCKING enforcement
            if exit_code == 2:
                sys.stderr.write(f"[CHAIN] BLOCKED: {Path(script).name}\n")
                # Print any checkpoint output before blocking
                if last_raw_text:
                    print(last_raw_text)
                return (2, accumulated_output)

            if exit_code != 0:
                sys.stderr.write(f"[CHAIN] Error in {Path(script).name}: {stderr[:200]}\n")
                return (1, accumulated_output)

            if isinstance(script_output, dict):
                context.update(script_output)

            sys.stderr.write(f"[CHAIN] OK: {Path(script).name}\n")

        except subprocess.TimeoutExpired:
            sys.stderr.write(f"[CHAIN] Timeout: {Path(script).name}\n")
            return (1, accumulated_output)
        except Exception as e:
            sys.stderr.write(f"[CHAIN] Exception in {Path(script).name}: {str(e)[:200]}\n")
            return (1, accumulated_output)

    sys.stderr.write(f"[CHAIN] All {len(scripts)} scripts completed successfully\n")

    # For pre-tool mode: print 3-level-flow checkpoint table (human-readable)
    # For post-tool mode: print JSON summary (machine-readable)
    if mode == "pre-tool" and last_raw_text:
        print(last_raw_text)
    else:
        print(json.dumps({
            "status": "success",
            "mode": mode
        }, default=str))

    return (0, accumulated_output)


def get_pretool_chain():
    """Scripts for pre-tool chain."""
    scripts_dir = Path.home() / '.claude' / 'scripts'
    return [
        str(scripts_dir / 'auto-fix-enforcer.py'),
        str(scripts_dir / 'clear-session-handler.py'),
        str(scripts_dir / 'pre-tool-enforcer.py'),
        str(scripts_dir / '3-level-flow.py'),
    ]


def get_posttool_chain():
    """Scripts for post-tool chain."""
    scripts_dir = Path.home() / '.claude' / 'scripts'
    return [
        str(scripts_dir / 'post-tool-tracker.py'),
        str(scripts_dir / 'session-summary-manager.py'),
    ]


def read_claude_stdin():
    """Read Claude Code hook stdin and extract prompt + cwd.

    Claude Code pipes JSON to UserPromptSubmit hooks:
      {"prompt": "user message", "cwd": "/path/to/project", ...}

    Returns:
        dict: The parsed stdin JSON, or empty dict if unavailable.
    """
    try:
        if sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        if raw and raw.strip():
            return json.loads(raw.strip())
    except Exception:
        pass
    return {}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nested/chained script execution orchestrator")
    parser.add_argument("--mode", choices=["pre-tool", "post-tool"], default="pre-tool")
    parser.add_argument("--scripts", nargs="+", help="Explicit list of scripts to chain")

    args = parser.parse_args()

    # Read Claude Code's stdin FIRST (before any script consumes it)
    hook_input = read_claude_stdin()

    # Build initial context WITH all Claude Code hook fields preserved
    # CRITICAL: PostToolUse hooks receive tool_name, tool_input, tool_response
    # These MUST be at the top level for post-tool-tracker.py to read them.
    # UserPromptSubmit hooks receive prompt, cwd.
    initial_context = {
        "mode": args.mode,
        "session_id": os.environ.get("CLAUDE_SESSION_ID", ""),
        "timestamp": datetime.now().isoformat(),
        "chain_results": [],
        # Preserve ALL Claude Code hook fields at top level
        "prompt": hook_input.get("prompt", ""),
        "message": hook_input.get("prompt", ""),
        "cwd": hook_input.get("cwd", ""),
        # PostToolUse fields (critical for flag clearing in post-tool-tracker.py)
        "tool_name": hook_input.get("tool_name", ""),
        "tool_input": hook_input.get("tool_input", {}),
        "tool_response": hook_input.get("tool_response", {}),
        # Full original hook input for any script that needs it
        "hook_input": hook_input,
    }

    if args.scripts:
        scripts = args.scripts
    elif args.mode == "pre-tool":
        scripts = get_pretool_chain()
    else:
        scripts = get_posttool_chain()

    exit_code, output = chain_execute(scripts, initial_context=initial_context, mode=args.mode)
    sys.exit(exit_code)
