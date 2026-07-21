#!/usr/bin/env python3
"""
Level 3 - TODO Decomposer

Reads a pre-built orchestration prompt from --orchestration-prompt-file,
asks claude CLI to decompose it into a structured TODO list, and writes
JSON to stdout.

Invoked by: call_execution_script("todo_decomposer", args)
Output: JSON with keys: status, todo_list, error

Environment:
  STEP0_TODO_DECOMPOSER_TIMEOUT  max seconds for claude CLI (default: 90)
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
_TIMEOUT = int(os.getenv("STEP0_TODO_DECOMPOSER_TIMEOUT", "90"))

_DECOMPOSE_TEMPLATE = (
    "You are a TODO decomposer. Below is an orchestration prompt for a "
    "software development task.\n\n"
    "Break it down into an ordered list of discrete TODOs that can be "
    "executed by separate agents.\n\n"
    "RULES:\n"
    "1. Each TODO must be self-contained with its full context.\n"
    "2. Mark todos that can run in parallel with the same phase letter "
    "(A, B, C...).\n"
    "3. Sequential dependencies: specify depends_on as list of todo IDs.\n"
    "4. Each todo must name a specific agent from the orchestration plan.\n\n"
    "COMPLEXITY SCORE: {complexity}/25\n\n"
    "OUTPUT FORMAT (JSON only, no other text):\n"
    "{{\n"
    '  "todo_list": [\n'
    "    {{\n"
    '      "id": "todo_001",\n'
    '      "title": "short title",\n'
    '      "agent": "agent-name",\n'
    '      "prompt": "full self-contained prompt for this agent",\n'
    '      "depends_on": [],\n'
    '      "phase": "A"\n'
    "    }}\n"
    "  ]\n"
    "}}\n\n"
    "ORCHESTRATION PROMPT:\n"
    "{orchestration_prompt}"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_args(argv):
    """Parse CLI arguments into a dict.

    Supported flags:
      --orchestration-prompt-file <path>
      --complexity-score <int>
      --complexity-score=<int>
    """
    args = {
        "orchestration_prompt_file": "",
        "complexity_score": 5,
    }

    i = 1
    while i < len(argv):
        token = argv[i]
        if token == "--orchestration-prompt-file" and i + 1 < len(argv):
            args["orchestration_prompt_file"] = argv[i + 1]
            i += 2
        elif token == "--complexity-score" and i + 1 < len(argv):
            try:
                args["complexity_score"] = int(argv[i + 1])
            except ValueError:
                args["complexity_score"] = 5
            i += 2
        elif token.startswith("--complexity-score="):
            try:
                args["complexity_score"] = int(token.split("=", 1)[1])
            except ValueError:
                args["complexity_score"] = 5
            i += 1
        else:
            i += 1

    return args


def _load_prompt_file(prompt_file):
    """Read orchestration prompt from file. Returns (text, error)."""
    if not prompt_file:
        return None, "No --orchestration-prompt-file provided"
    path = Path(prompt_file)
    if not path.exists():
        return None, "Prompt file not found: " + prompt_file
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.strip(), None
    except Exception as exc:
        return None, "Failed to read prompt file: " + str(exc)


def _build_decompose_prompt(orchestration_prompt, complexity_score):
    """Build the decomposition request prompt from the template."""
    return _DECOMPOSE_TEMPLATE.format(
        complexity=complexity_score,
        orchestration_prompt=orchestration_prompt,
    )


def _call_claude_cli(prompt):
    """Call claude CLI in headless print mode via stdin. Returns (response_text, error)."""
    claude_path = shutil.which("claude")
    if not claude_path:
        return None, "claude CLI binary not found in PATH"

    if DEBUG:
        print("[todo_decomposer] Running: claude CLI -p", file=sys.stderr, flush=True)

    try:
        result = subprocess.run(
            [claude_path, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0 and not result.stdout:
            stderr_preview = (result.stderr or "")[:300]
            return None, "claude CLI non-zero exit (%d): %s" % (result.returncode, stderr_preview)

        response_text = (result.stdout or "").strip()
        if response_text:
            return response_text, None
        return None, "claude CLI returned empty response"

    except subprocess.TimeoutExpired:
        return None, "claude CLI timed out after %ds" % _TIMEOUT
    except Exception as exc:
        return None, "claude CLI call failed: " + str(exc)


def _extract_todo_list(llm_response):
    """Extract todo_list array from claude response JSON. Returns (list, error)."""
    if not llm_response:
        return [], "Empty LLM response"
    try:
        if "{" in llm_response:
            json_start = llm_response.index("{")
            json_end = llm_response.rindex("}") + 1
            parsed = json.loads(llm_response[json_start:json_end])
            todo_list = parsed.get("todo_list", [])
            if isinstance(todo_list, list):
                return todo_list, None
    except Exception as exc:
        return [], "JSON parse error: " + str(exc)
    return [], "No todo_list found in response"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Entry point when called as a subprocess by call_execution_script."""
    if DEBUG:
        print("[todo_decomposer] Starting", file=sys.stderr, flush=True)

    args = _parse_args(sys.argv)

    orchestration_prompt, err = _load_prompt_file(args["orchestration_prompt_file"])
    if err:
        print(json.dumps({"status": "FALLBACK", "todo_list": [], "error": err}, ensure_ascii=True))
        return

    if DEBUG:
        print("[todo_decomposer] Prompt loaded (%d chars)" % len(orchestration_prompt), file=sys.stderr, flush=True)

    decompose_prompt = _build_decompose_prompt(orchestration_prompt, args["complexity_score"])

    if DEBUG:
        print("[todo_decomposer] Calling claude CLI", file=sys.stderr, flush=True)

    llm_response, err = _call_claude_cli(decompose_prompt)
    if err:
        print(json.dumps({"status": "FALLBACK", "todo_list": [], "error": err}, ensure_ascii=True))
        return

    if DEBUG:
        print("[todo_decomposer] claude CLI responded", file=sys.stderr, flush=True)

    todo_list, parse_err = _extract_todo_list(llm_response)
    if parse_err and not todo_list:
        print(
            json.dumps(
                {"status": "FALLBACK", "todo_list": [], "error": parse_err, "llm_response": llm_response[:500]},
                ensure_ascii=True,
            )
        )
        return

    result = {
        "status": "SUCCESS",
        "todo_list": todo_list,
        "error": None,
        "complexity_score": args["complexity_score"],
        "todo_count": len(todo_list),
    }
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
