"""
Faithfulness Gate - Step 11 Gate 6 support module.

Grounds an LLM-judged check of "did Step 10's diff actually implement what
the task asked for" in the sibling claude-global-library's real
hallucination-detection-core rubric (NLI-based faithfulness taxonomy), so
the prompt sent to `claude -p` is not an invented rubric.

The check distinguishes faithfulness (grounded in the stated task) from
factuality (true per world knowledge) -- see hallucination-detection-core
SKILL.md item 6 under "What Not to Do". Only faithfulness matters here: does
the diff fabricate capability, APIs, or scope that was never requested and
is not actually present in the diff.

Two-tier opt-in wiring lives in quality_gate.py (`_evaluate_faithfulness_gate`),
mirroring Gate 5's ENABLE_RUNTIME_VERIFICATION / STRICT_RUNTIME_VERIFICATION
pattern:
    ENABLE_FAITHFULNESS_GATE=1   turns the check on (off by default -- this
                                 module spawns a real `claude -p` subprocess,
                                 which costs real time and money)
    STRICT_FAITHFULNESS_GATE=1  makes a "flag" verdict block the merge (a
                                 "block" verdict always blocks, regardless)

Python 3.8+ compatible. ASCII-only (cp1252-safe). No external dependencies
beyond the stdlib and the resolver already used elsewhere in this codebase.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CallerFn = Callable[[str], Tuple[Optional[str], Optional[str]]]

# 300s matches STEP0_ORCHESTRATOR_TIMEOUT's default in orchestrator_agent_caller.py --
# this call sends a comparably large prompt (full rubric + diff summary), and a real
# measured run took 84.6s. 60s (copied from the smaller prompt_gen_expert_caller.py
# budget without recalibrating) was too tight and hit the fail-open timeout path on
# ordinary latency, not just genuine hangs.
_TIMEOUT = int(os.getenv("FAITHFULNESS_GATE_TIMEOUT", "300"))
_MAX_FILE_PREVIEW_LINES = 40
_RUBRIC_SKILL_NAME = "hallucination-detection-core"
_VALID_VERDICTS = ("pass", "flag", "block", "uncertain")

# General (non-medical/legal) NLI faithfulness thresholds, verified against
# agents/hallucination-detector/agent.md ("general: flag at NLI < 0.4; block
# at NLI < 0.2") in the sibling claude-global-library. This is a code-review
# faithfulness check, not a medical/legal/financial one, so the stricter
# domain overrides (flag < 0.5, block < 0.3) documented in the same file do
# not apply here.
_FLAG_THRESHOLD = 0.4
_BLOCK_THRESHOLD = 0.2
_UNCERTAIN_BAND = 0.05

_FALLBACK_RUBRIC = (
    "LIBRARY UNAVAILABLE -- hallucination-detection-core SKILL.md could not "
    "be resolved; using a minimal built-in fallback rubric instead.\n"
    "Faithfulness = does the diff implement what the task asked, without "
    "fabricating capability, APIs, or scope beyond what was requested and "
    "beyond what the diff content itself supports. This is distinct from "
    "factuality (true per world knowledge) -- only faithfulness to the "
    "stated task matters for this check.\n"
    f"General thresholds: flag if faithfulness confidence < {_FLAG_THRESHOLD}; "
    f"block if < {_BLOCK_THRESHOLD}. If the verdict is within "
    f"+/-{_UNCERTAIN_BAND} of a threshold, return 'uncertain' and recommend "
    "human review instead of forcing pass/flag/block."
)


def _extract_rubric_sections(skill_content: str) -> str:
    """Extract the taxonomy + NLI faithfulness sections from the real
    hallucination-detection-core SKILL.md content.

    Pulls the substring from "## 1. Hallucination Taxonomy" up to (not
    including) "## 3. SelfCheckGPT Consistency Detection" -- this covers the
    four hallucination types, the NLI entailment/faithfulness formulas, and
    the detection thresholds table, while skipping the SelfCheckGPT/semantic
    entropy/FactScore sections that are not relevant to a single-pass diff
    faithfulness check. Falls back to the raw content (truncated) if the
    expected headings are not found, so an upstream rename of the skill
    still yields usable (if less targeted) grounding rather than an error.
    """
    start_marker = "## 1. Hallucination Taxonomy"
    end_marker = "## 3. SelfCheckGPT Consistency Detection"

    start = skill_content.find(start_marker)
    end = skill_content.find(end_marker)

    if start != -1 and end != -1 and end > start:
        return skill_content[start:end].strip()

    logger.debug("faithfulness_gate: expected rubric section markers not found; using truncated raw content")
    return skill_content[:4000].strip()


def _fetch_rubric_content() -> Tuple[str, bool]:
    """Fetch the real hallucination-detection-core rubric via the resolver.

    Fail-open per ADR-1: a missing sibling library must never abort the
    gate, only degrade the grounding quality (visible via the returned
    ``library_available`` flag).

    Returns:
        (rubric_text, library_available) -- library_available is False when
        the resolver could not reach the skill (LibrarySetupError or the
        resolver module itself being unavailable), in which case rubric_text
        is the minimal built-in fallback.
    """
    try:
        from langgraph_engine.library.resolver import LibrarySetupError, build_default_resolver
    except ImportError as exc:
        logger.warning("faithfulness_gate: resolver module unavailable, using fallback rubric: %s", exc)
        return _FALLBACK_RUBRIC, False

    try:
        resolver = build_default_resolver()
        resource = resolver.fetch_skill(_RUBRIC_SKILL_NAME)
        return _extract_rubric_sections(resource.content), True
    except LibrarySetupError as exc:
        logger.warning(
            "faithfulness_gate: rubric skill '%s' unavailable, using fallback rubric: %s",
            _RUBRIC_SKILL_NAME,
            exc,
        )
        return _FALLBACK_RUBRIC, False


def build_faithfulness_prompt(task_description: str, diff_summary: str, rubric_content: str) -> str:
    """Build the prompt sent to `claude -p` for the faithfulness verdict.

    Grounds the request in the real hallucination-detection-core rubric
    (taxonomy + NLI faithfulness formula) rather than asking the model to
    invent its own criteria, and requests structured JSON output so the
    caller can parse a verdict deterministically.

    Args:
        task_description: What the original task/prompt asked for.
        diff_summary: Summary of what Step 10 actually changed (see
            ``_build_diff_summary`` for what this does and does not contain).
        rubric_content: Grounding rubric text (real skill excerpt or fallback).

    Returns:
        The complete prompt string.
    """
    return (
        "You are auditing whether a code diff faithfully implements the task it "
        "was supposed to implement -- this is a FAITHFULNESS check, not a "
        "factuality check. Faithfulness means: does the diff do what the task "
        "asked, without fabricating capability, APIs, or scope that was never "
        "requested and is not actually present in the diff content. A diff can "
        "be faithful even if some implementation detail is debatable; a diff is "
        "unfaithful when it claims or implies functionality, endpoints, or "
        "behavior that the task never asked for and the diff does not actually "
        "contain.\n\n"
        "GROUNDING RUBRIC (hallucination-detection-core, NLI faithfulness "
        "taxonomy -- from the sibling claude-global-library skill):\n"
        "----------------------------------------------------------------\n"
        f"{rubric_content}\n"
        "----------------------------------------------------------------\n\n"
        "THRESHOLDS TO APPLY (general code-review context, not medical/legal):\n"
        f"- verdict 'pass' if the diff is well-supported by the task (faithfulness "
        f"confidence >= {_FLAG_THRESHOLD})\n"
        f"- verdict 'flag' if faithfulness confidence is between {_BLOCK_THRESHOLD} "
        f"and {_FLAG_THRESHOLD} (weak but not absent support)\n"
        f"- verdict 'block' if faithfulness confidence is below {_BLOCK_THRESHOLD} "
        "(the diff fabricates scope/capability not grounded in the task)\n"
        f"- verdict 'uncertain' if your confidence is within +/-{_UNCERTAIN_BAND} of "
        "either threshold -- in that case recommend human review rather than "
        "forcing pass/flag/block\n\n"
        "TASK DESCRIPTION (what was requested):\n"
        f"{task_description}\n\n"
        "DIFF SUMMARY (what Step 10 actually changed):\n"
        f"{diff_summary}\n\n"
        "Respond with ONLY a single JSON object, no prose before or after it, in "
        "exactly this shape:\n"
        "{\n"
        '  "verdict": "pass" | "flag" | "block" | "uncertain",\n'
        '  "faithfulness_score": <float between 0.0 and 1.0>,\n'
        '  "flagged_claims": ["<specific capability/API/scope the diff claims or '
        "implies that is not supported by the task description or by the diff "
        'content itself>", "..."],\n'
        '  "reasoning": "<one paragraph explaining the verdict>"\n'
        "}\n"
    )


def _build_diff_summary(modified_files: List[str], project_root: str) -> str:
    """Build a best-effort summary of what changed, for prompt grounding.

    NOTE ON WHAT THIS ACTUALLY CONTAINS: this is a current-content snapshot
    of each modified file (name + first ``_MAX_FILE_PREVIEW_LINES`` lines),
    not a true unified diff against a base ref. Computing a real diff would
    require a reliable base commit/branch, which is not consistently
    available to this function's callers (the gate only receives
    ``step10_modified_files``, a flat path list, from FlowState). This
    snapshot is still sufficient grounding for a faithfulness judgment --
    it lets the model see what the modified files actually contain and
    compare that against the task description -- but it is not a substitute
    for a proper before/after diff.

    Args:
        modified_files: Relative paths (from project_root) of files Step 10 touched.
        project_root: Absolute path to the project root.

    Returns:
        A human-readable, truncated summary string.
    """
    root = Path(project_root)
    parts: List[str] = [f"{len(modified_files)} modified file(s):"]

    for rel_path in modified_files:
        parts.append(f"\n--- {rel_path} ---")
        try:
            full_path = root / rel_path
            text = full_path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            preview = lines[:_MAX_FILE_PREVIEW_LINES]
            parts.append("\n".join(preview))
            remaining = len(lines) - _MAX_FILE_PREVIEW_LINES
            if remaining > 0:
                parts.append(f"... ({remaining} more line(s) omitted)")
        except OSError as exc:
            parts.append(f"(could not read file: {exc})")

    return "\n".join(parts)


def _default_caller(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Call the real `claude` CLI in headless print mode via stdin.

    Mirrors the subprocess pattern used by
    ``level3_execution/architecture/prompt_gen_expert_caller.py``'s
    ``_call_claude_cli`` (also duplicated in ``orchestrator_agent_caller.py``
    and ``todo_decomposer.py``): resolve the binary via ``shutil.which``,
    run with a bounded timeout, and always return a ``(text, error)`` tuple
    rather than raising, so gate evaluation stays fail-open.

    Returns:
        (response_text, error) -- exactly one of the two is non-None.
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        return None, "claude CLI binary not found in PATH"

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
        return None, "claude CLI call failed: %s" % exc


def _parse_verdict_response(response: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Defensively parse the JSON verdict out of a raw LLM response.

    Mirrors the ``"{" in response`` + ``json.loads`` extraction pattern used
    by ``prompt_gen_expert_caller.py``'s ``main()``.

    Returns:
        (parsed_dict, error) -- exactly one of the two is non-None.
    """
    if not response or "{" not in response:
        return None, "response contained no JSON object"

    try:
        json_start = response.index("{")
        json_end = response.rindex("}") + 1
        parsed = json.loads(response[json_start:json_end])
    except Exception as exc:
        return None, f"failed to parse JSON from response: {exc}"

    if not isinstance(parsed, dict):
        return None, "parsed JSON was not an object"

    verdict = str(parsed.get("verdict", "")).lower()
    if verdict not in _VALID_VERDICTS:
        return None, f"unrecognized verdict '{verdict}'"

    return parsed, None


def run_faithfulness_check(
    task_description: str,
    modified_files: List[str],
    project_root: str,
    caller: Optional[CallerFn] = None,
) -> Dict[str, Any]:
    """Run the faithfulness check for the current Step 10 diff.

    Fail-open contract: any failure to actually run the check (no modified
    files, no task description, claude binary missing, timeout, malformed
    response) returns ``passed=True, checked=False`` -- the gate never
    blocks a merge just because the check itself could not run.

    Args:
        task_description: What the original task asked for.
        modified_files: Relative paths of files Step 10 modified.
        project_root: Absolute path to the project root.
        caller: Injectable ``(prompt) -> (response_text, error)`` callable,
            defaulting to the real `claude -p` subprocess caller. Tests
            inject a fake here instead of invoking the real CLI.

    Returns:
        {
            "passed": bool,
            "reason": str,
            "verdict": "pass" | "flag" | "block" | "uncertain",
            "faithfulness_score": float | None,
            "flagged_claims": List[str],
            "checked": bool,          # False whenever the check did not
                                       # actually run (see fail-open contract)
            "library_available": bool,  # False when the rubric skill had to
                                         # fall back to the built-in rubric
        }
    """
    result: Dict[str, Any] = {
        "passed": True,
        "reason": "",
        "verdict": "uncertain",
        "faithfulness_score": None,
        "flagged_claims": [],
        "checked": False,
        "library_available": True,
    }

    if not modified_files:
        result["reason"] = "No modified files to check; faithfulness check skipped."
        return result

    if not task_description:
        result["reason"] = "No task description available; faithfulness check skipped."
        return result

    caller_fn = caller or _default_caller

    rubric_content, library_available = _fetch_rubric_content()
    result["library_available"] = library_available

    diff_summary = _build_diff_summary(modified_files, project_root)
    prompt = build_faithfulness_prompt(task_description, diff_summary, rubric_content)

    response, call_error = caller_fn(prompt)
    if call_error:
        result["reason"] = f"Faithfulness check could not run (fail-open): {call_error}"
        return result

    parsed, parse_error = _parse_verdict_response(response or "")
    if parse_error:
        result["reason"] = f"Faithfulness check response could not be used (fail-open): {parse_error}"
        return result

    verdict = str(parsed.get("verdict", "uncertain")).lower()
    flagged_claims = parsed.get("flagged_claims") or []
    if not isinstance(flagged_claims, list):
        flagged_claims = [str(flagged_claims)]
    reasoning = str(parsed.get("reasoning", "")).strip()
    if not library_available:
        reasoning = "[library unavailable; used built-in fallback rubric] " + reasoning

    result["checked"] = True
    result["verdict"] = verdict
    result["faithfulness_score"] = parsed.get("faithfulness_score")
    result["flagged_claims"] = flagged_claims

    if verdict == "pass":
        result["passed"] = True
        result["reason"] = f"Faithfulness check passed. {reasoning}".strip()
    elif verdict == "uncertain":
        result["passed"] = True
        result["reason"] = f"Faithfulness check uncertain -- recommend human review. {reasoning}".strip()
    elif verdict == "flag":
        strict = os.getenv("STRICT_FAITHFULNESS_GATE", "0") == "1"
        result["passed"] = not strict
        mode_note = "strict mode -- blocking" if strict else "non-strict mode -- warning only"
        result["reason"] = f"Faithfulness check flagged ({mode_note}). {reasoning}".strip()
    else:  # "block"
        result["passed"] = False
        result["reason"] = f"Faithfulness check blocked. {reasoning}".strip()

    return result
