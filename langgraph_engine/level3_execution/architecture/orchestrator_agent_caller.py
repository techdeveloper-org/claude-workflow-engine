#!/usr/bin/env python3
"""
Level 3 - Orchestrator Agent Caller

Reads a pre-built prompt from a temp file path (--orchestration-prompt-file),
calls the claude CLI subprocess with stderr streamed live to the terminal,
and writes JSON to stdout.

Invoked by: call_streaming_script("orchestrator_agent_caller", args)
Output: JSON with keys: status, agent_output, llm_response, error (on failure)

Environment:
  STEP0_ORCHESTRATOR_TIMEOUT  max seconds to wait for claude CLI (default: 300)
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
_TIMEOUT = int(os.getenv("STEP0_ORCHESTRATOR_TIMEOUT", "300"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_args(argv):
    """Parse CLI arguments into a dict.

    Supported flags:
      --orchestration-prompt-file <path>   path to file containing full prompt text
      --task-description <str>             fallback if no prompt file provided
      --complexity-score <int>
    """
    args = {
        "orchestration_prompt_file": "",
        "task_description": "",
        "complexity_score": 5,
    }

    i = 1
    while i < len(argv):
        token = argv[i]
        if token == "--orchestration-prompt-file" and i + 1 < len(argv):
            args["orchestration_prompt_file"] = argv[i + 1]
            i += 2
        elif token == "--task-description" and i + 1 < len(argv):
            args["task_description"] = argv[i + 1]
            i += 2
        elif token == "--complexity-score" and i + 1 < len(argv):
            try:
                args["complexity_score"] = int(argv[i + 1])
            except ValueError:
                args["complexity_score"] = 5
            i += 2
        else:
            i += 1

    return args


def _load_prompt(args):
    """Load prompt text from file or fall back to task_description.

    Returns (prompt_text, error).
    """
    prompt_file = args.get("orchestration_prompt_file", "")
    if prompt_file:
        path = Path(prompt_file)
        if not path.exists():
            return None, "Prompt file not found: " + prompt_file
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return text.strip(), None
        except Exception as exc:
            return None, "Failed to read prompt file: " + str(exc)

    # Fallback: use task_description as bare prompt
    task = args.get("task_description", "").strip()
    if task:
        return task, None

    return None, "No --orchestration-prompt-file and no --task-description provided"


def _call_claude_cli(prompt):
    """Call claude CLI as subprocess with stderr inherited (live streaming).

    Returns (response_text, error).
    """
    temp_file = None
    try:
        # Write prompt to temp file (avoids shell escaping issues)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as tf:
            tf.write(prompt)
            temp_file = tf.name

        cmd = [
            "claude",
            "--json",
            "--no-stream",
            "@" + temp_file,
        ]

        if DEBUG:
            print("[orchestrator_agent_caller] Running: claude CLI", file=sys.stderr, flush=True)

        # stderr=None inherits parent stderr -- user sees real-time progress
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=None,  # Inherit: live output visible in terminal
            text=True,
            timeout=_TIMEOUT,
        )

        if result.returncode != 0 and not result.stdout:
            return None, "claude CLI non-zero exit (%d)" % result.returncode

        # Parse JSON output from claude CLI
        response_text = result.stdout or ""
        try:
            json_out = json.loads(response_text)
            # claude --json returns {"type":"result","result":"..."}
            if isinstance(json_out, dict) and "result" in json_out:
                return json_out["result"], None
            return response_text, None
        except (json.JSONDecodeError, ValueError):
            if response_text.strip():
                return response_text.strip(), None
            return None, "claude CLI returned empty response"

    except subprocess.TimeoutExpired:
        return None, "claude CLI timed out after %ds" % _TIMEOUT
    except FileNotFoundError:
        return None, "claude CLI binary not found in PATH"
    except Exception as exc:
        return None, "claude CLI call failed: " + str(exc)
    finally:
        if temp_file:
            try:
                Path(temp_file).unlink(missing_ok=True)
            except Exception:
                pass


def _parse_agent_output(llm_response):
    """Attempt to parse structured JSON from the response."""
    if not llm_response:
        return None
    try:
        if "{" in llm_response:
            json_start = llm_response.index("{")
            json_end = llm_response.rindex("}") + 1
            return json.loads(llm_response[json_start:json_end])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[orchestrator_agent_caller] Starting", file=sys.stderr, flush=True)

    args = _parse_args(sys.argv)

    # Load prompt
    print("[orchestrator_agent_caller] Loading prompt", file=sys.stderr, flush=True)
    prompt, err = _load_prompt(args)
    if err:
        print(json.dumps({"status": "ERROR", "error": err}))
        return

    prompt_len = len(prompt)
    print(
        "[orchestrator_agent_caller] Prompt ready (" + str(prompt_len) + " chars)",
        file=sys.stderr,
        flush=True,
    )

    if DEBUG:
        preview = prompt[:200].replace("\n", " ")
        print("[orchestrator_agent_caller] Preview: " + preview, file=sys.stderr, flush=True)

    # Call claude CLI subprocess (stderr streamed live to terminal)
    print("[orchestrator_agent_caller] Calling claude CLI", file=sys.stderr, flush=True)

    llm_response, err = _call_claude_cli(prompt)

    if err:
        print("[orchestrator_agent_caller] claude CLI failed: " + str(err), file=sys.stderr, flush=True)
        print(json.dumps({"status": "ERROR", "error": err}))
        return

    response_len = len(llm_response) if llm_response else 0
    print(
        "[orchestrator_agent_caller] claude CLI responded (" + str(response_len) + " chars)",
        file=sys.stderr,
        flush=True,
    )

    # Parse structured output
    agent_output = _parse_agent_output(llm_response)
    if agent_output:
        print("[orchestrator_agent_caller] Parsed agent output OK", file=sys.stderr, flush=True)
    else:
        print("[orchestrator_agent_caller] No structured JSON in response", file=sys.stderr, flush=True)

    result = {
        "status": "SUCCESS",
        "agent_output": agent_output,
        "llm_response": llm_response,
        "complexity_score": args["complexity_score"],
        "prompt_chars": prompt_len,
    }

    print(json.dumps(result, ensure_ascii=True))

    print("[orchestrator_agent_caller] Done", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
