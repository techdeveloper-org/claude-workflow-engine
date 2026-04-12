#!/usr/bin/env python3
"""
Level 3 - Prompt Generation Expert Caller

Reads CLI args, loads the orchestration system prompt template,
fills the 7 placeholders, calls the claude CLI subprocess, and writes
JSON to stdout.

Invoked by: call_execution_script("prompt_gen_expert_caller", args)
Output: JSON with keys: status, prompt, llm_response, error (on failure)

Environment:
  STEP0_PROMPT_GEN_TIMEOUT  max seconds for claude CLI (default: 60)
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
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE_FILE = _TEMPLATES_DIR / "orchestration_system_prompt.txt"

DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
_TIMEOUT = int(os.getenv("STEP0_PROMPT_GEN_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_args(argv):
    """Parse CLI arguments into a dict.

    Supported flags:
      --task-description <str>
      --complexity-score <int>        (space-separated)
      --complexity-score=<int>        (equals form)
      --call-graph-json <json-string>
      --runtime-context-json <json-string>
    """
    args = {
        "task_description": "",
        "complexity_score": 5,
        "call_graph_json": "{}",
        "runtime_context_json": "{}",
    }

    i = 1
    while i < len(argv):
        token = argv[i]
        if token == "--task-description" and i + 1 < len(argv):
            args["task_description"] = argv[i + 1]
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
        elif token == "--call-graph-json" and i + 1 < len(argv):
            args["call_graph_json"] = argv[i + 1]
            i += 2
        elif token == "--runtime-context-json" and i + 1 < len(argv):
            args["runtime_context_json"] = argv[i + 1]
            i += 2
        else:
            i += 1

    return args


def _load_template():
    """Load orchestration_system_prompt.txt. Returns (text, error)."""
    if not _TEMPLATE_FILE.exists():
        return None, "Template file not found: " + str(_TEMPLATE_FILE)
    try:
        content = _TEMPLATE_FILE.read_text(encoding="utf-8", errors="replace")
        return content, None
    except Exception as exc:
        return None, "Failed to read template: " + str(exc)


def _build_filled_prompt(template, args):
    """Fill the 7 placeholders in the template with runtime values."""
    call_graph = {}
    try:
        call_graph = json.loads(args["call_graph_json"]) if args["call_graph_json"] else {}
    except (json.JSONDecodeError, TypeError):
        call_graph = {}

    runtime_context = {}
    try:
        runtime_context = json.loads(args["runtime_context_json"]) if args["runtime_context_json"] else {}
    except (json.JSONDecodeError, TypeError):
        runtime_context = {}

    risk_level = call_graph.get("risk_level", "unknown")
    danger_zones = call_graph.get("danger_zones", [])
    affected_methods = call_graph.get("affected_methods", [])
    hot_nodes = call_graph.get("hot_nodes", [])

    danger_zones_str = ", ".join(danger_zones) if danger_zones else "none"
    affected_str = ", ".join(affected_methods[:10]) if affected_methods else "none"
    hot_nodes_str = ", ".join(hot_nodes[:10]) if hot_nodes else "none"

    runtime_block = json.dumps(runtime_context, indent=2, ensure_ascii=True)

    # combined_complexity_score is on a 1-25 scale (not 1-10)
    complexity = args["complexity_score"]
    if complexity <= 8:
        tier = "low"
    elif complexity <= 16:
        tier = "medium"
    else:
        tier = "high"
    complexity_display = str(complexity) + "/25 (" + tier + ")"

    filled = template
    filled = filled.replace("{user_requirements}", args["task_description"])
    filled = filled.replace("{runtime_context_json_block}", runtime_block)
    filled = filled.replace("{complexity_score_display}", complexity_display)
    filled = filled.replace("{codebase_risk_level}", str(risk_level))
    filled = filled.replace("{codebase_danger_zones}", danger_zones_str)
    filled = filled.replace("{codebase_affected_methods}", affected_str)
    filled = filled.replace("{codebase_hot_nodes}", hot_nodes_str)

    return filled


def _call_claude_cli(prompt):
    """Call claude CLI as subprocess. Returns (response_text, error)."""
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
            print("[prompt_gen_expert_caller] Running: claude CLI", file=sys.stderr, flush=True)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )

        if result.returncode != 0 and not result.stdout:
            stderr_preview = (result.stderr or "")[:300]
            return None, "claude CLI non-zero exit (%d): %s" % (result.returncode, stderr_preview)

        # Parse JSON output from claude CLI
        response_text = result.stdout or ""
        try:
            json_out = json.loads(response_text)
            # claude --json returns {"type":"result","result":"..."}
            if isinstance(json_out, dict) and "result" in json_out:
                return json_out["result"], None
            # Fallback: return raw text content
            return response_text, None
        except (json.JSONDecodeError, ValueError):
            # Non-JSON output; return as-is
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if DEBUG:
        print("[prompt_gen_expert_caller] Starting", file=sys.stderr, flush=True)

    args = _parse_args(sys.argv)

    if not args["task_description"]:
        print(json.dumps({"status": "ERROR", "error": "No --task-description provided"}))
        return

    # Load template
    template, err = _load_template()
    if err:
        print(json.dumps({"status": "ERROR", "error": err}))
        return

    if DEBUG:
        print("[prompt_gen_expert_caller] Template loaded", file=sys.stderr, flush=True)

    # Fill placeholders
    filled_prompt = _build_filled_prompt(template, args)

    if DEBUG:
        print("[prompt_gen_expert_caller] Calling claude CLI", file=sys.stderr, flush=True)

    # Call claude CLI subprocess
    llm_response, err = _call_claude_cli(filled_prompt)
    if err:
        print(json.dumps({"status": "ERROR", "error": err, "prompt": filled_prompt[:500]}))
        return

    if DEBUG:
        print("[prompt_gen_expert_caller] claude CLI responded", file=sys.stderr, flush=True)

    # Try to parse response as JSON (it should be per template instructions)
    parsed_plan = None
    try:
        if llm_response and "{" in llm_response:
            json_start = llm_response.index("{")
            json_end = llm_response.rindex("}") + 1
            parsed_plan = json.loads(llm_response[json_start:json_end])
    except Exception:
        parsed_plan = None

    result = {
        "status": "SUCCESS",
        "prompt": filled_prompt,
        "llm_response": llm_response,
        "parsed_plan": parsed_plan,
        "complexity_score": args["complexity_score"],
    }

    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
