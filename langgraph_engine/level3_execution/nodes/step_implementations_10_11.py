"""Step 10/11 implementation functions.

Facade module: wraps llm_call (Step 10) and Level3GitHubWorkflow (Step 11)
behind thin, state-dict-first functions that the step wrappers in
step_wrappers_10_11.py invoke.

Restored 2026-04-13 during v1.16.x restoration cycle (issue #211),
adapted for:
  - llm_call 2-provider chain (replaces purged hybrid_inference)
  - v1.11 physical layout (nodes/ package)
  - loguru-with-stdlib-fallback logger import pattern (matches sibling nodes)

Design patterns:
  - Facade: thin wrapper over llm_call + Level3GitHubWorkflow
  - Null Object: returns well-formed ERROR-status dict on failure (never None, never raises)
  - Defensive Import: every external import wrapped in try/except

Windows-safe: ASCII only.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    from ...flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

try:
    from langgraph_engine.llm_call import llm_call
except ImportError:  # pragma: no cover

    def llm_call(  # type: ignore[misc]
        prompt: str,
        model: str = "balanced",
        temperature: float = 0.3,
        timeout: int = 120,
        json_mode: bool = False,
    ) -> Optional[str]:
        logger.error("llm_call unavailable; returning None")
        return None


try:
    from ..helpers import _extract_modified_files
except ImportError:  # pragma: no cover

    def _extract_modified_files(llm_response: str, project_root: str = ".") -> List[str]:  # type: ignore[misc]
        return []


try:
    from ..steps8to12_github import Level3GitHubWorkflow
except ImportError:  # pragma: no cover
    Level3GitHubWorkflow = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Step 10: Implementation Execution
# ---------------------------------------------------------------------------


def step10_implementation_execution(state: FlowState) -> Dict[str, Any]:
    """Step 10: Implementation execution via llm_call.

    Loads system_prompt.txt + user_message.txt from the session directory,
    builds a final prompt (with optional retry history from state), invokes
    llm_call with model="deep", persists the response to disk, then extracts
    modified files via _extract_modified_files.

    Returns a well-formed result dict with step10_* keys.  On any failure
    returns an ERROR-status dict (never raises, never returns None) so the
    pipeline can fall back gracefully via _run_step.

    State keys consumed:
        session_dir / session_path  - where system_prompt.txt lives
        project_root                - cwd for file extraction
        step7_execution_prompt      - base implementation prompt (fallback)
        step10_execution_prompt     - override from wrapper if set
        step11_review_issues        - populated on retry attempts

    State keys produced (always present in return dict):
        step10_implementation_status  - "SUCCESS" | "ERROR"
        step10_tasks_executed         - 1 on success, 0 on error
        step10_modified_files         - list[str]
        step10_llm_invoked            - bool
        step10_system_prompt_loaded   - bool
        step10_user_message_loaded    - bool
        step10_execution_time_ms      - float
        step10_llm_response           - str (raw LLM text)
        step10_changes_summary        - dict (files_modified, count, length)
        step10_error                  - str (empty on success)
    """
    step_start = time.time()

    result: Dict[str, Any] = {
        "step10_implementation_status": "ERROR",
        "step10_tasks_executed": 0,
        "step10_modified_files": [],
        "step10_llm_invoked": False,
        "step10_system_prompt_loaded": False,
        "step10_user_message_loaded": False,
        "step10_execution_time_ms": 0.0,
        "step10_llm_response": "",
        "step10_changes_summary": {},
        "step10_error": "",
    }

    try:
        # --- Resolve session directory ---
        session_dir: str = state.get("session_dir") or state.get("session_path") or ""
        if not session_dir:
            logger.warning("[Step10] session_dir not set in state; using cwd")
            session_dir = os.getcwd()

        project_root: str = state.get("project_root", ".") or "."

        # --- Load system prompt from disk ---
        system_prompt = ""
        system_prompt_path = Path(session_dir) / "system_prompt.txt"
        if system_prompt_path.exists():
            try:
                system_prompt = system_prompt_path.read_text(encoding="utf-8", errors="replace")
                result["step10_system_prompt_loaded"] = True
                logger.debug("[Step10] Loaded system_prompt.txt (%d chars)", len(system_prompt))
            except Exception as exc:
                logger.warning("[Step10] Failed to read system_prompt.txt: %s", exc)
        else:
            logger.debug("[Step10] system_prompt.txt not found at %s", system_prompt_path)

        # --- Load user message from disk (or fall back to state prompt) ---
        user_message = ""
        user_message_path = Path(session_dir) / "user_message.txt"
        if user_message_path.exists():
            try:
                user_message = user_message_path.read_text(encoding="utf-8", errors="replace")
                result["step10_user_message_loaded"] = True
                logger.debug("[Step10] Loaded user_message.txt (%d chars)", len(user_message))
            except Exception as exc:
                logger.warning("[Step10] Failed to read user_message.txt: %s", exc)

        if not user_message:
            # Use wrapper-injected prompt or the base execution prompt
            user_message = state.get("step10_execution_prompt") or state.get("step7_execution_prompt") or ""
            if user_message:
                result["step10_user_message_loaded"] = True
                logger.debug("[Step10] Using execution prompt from state (%d chars)", len(user_message))

        # --- Compose final prompt ---
        if system_prompt and user_message:
            final_prompt = "SYSTEM:\n%s\n\nUSER:\n%s" % (system_prompt.strip(), user_message.strip())
        elif system_prompt:
            final_prompt = system_prompt.strip()
        elif user_message:
            final_prompt = user_message.strip()
        else:
            result["step10_error"] = "No prompt available: system_prompt.txt missing and step7_execution_prompt empty"
            result["step10_execution_time_ms"] = (time.time() - step_start) * 1000
            logger.error("[Step10] %s", result["step10_error"])
            return result

        # --- Invoke LLM ---
        timeout = int(os.environ.get("STEP10_LLM_TIMEOUT", "300"))
        logger.info("[Step10] Invoking llm_call (model=deep, timeout=%ds)", timeout)
        result["step10_llm_invoked"] = True

        llm_response: Optional[str] = llm_call(
            prompt=final_prompt,
            model="deep",
            temperature=0.2,
            timeout=timeout,
        )

        if not llm_response:
            result["step10_error"] = "llm_call returned None or empty response"
            result["step10_execution_time_ms"] = (time.time() - step_start) * 1000
            logger.error("[Step10] %s", result["step10_error"])
            return result

        result["step10_llm_response"] = llm_response
        logger.info("[Step10] LLM response received (%d chars)", len(llm_response))

        # --- Persist response to disk ---
        try:
            response_path = Path(session_dir) / "step10_llm_response.txt"
            response_path.write_text(llm_response, encoding="utf-8", errors="replace")
            logger.debug("[Step10] Persisted response to %s", response_path)
        except Exception as exc:
            logger.warning("[Step10] Could not persist LLM response: %s", exc)

        # --- Extract modified files ---
        modified_files: List[str] = _extract_modified_files(llm_response, project_root)
        result["step10_modified_files"] = modified_files
        logger.info("[Step10] Extracted %d modified files", len(modified_files))

        # --- Build changes summary (read by Figma path in wrapper at line 497) ---
        changes_summary: Dict[str, Any] = {
            "files_modified": modified_files,
            "files_modified_count": len(modified_files),
            "llm_response_length": len(llm_response),
            "llm_response_preview": llm_response[:500] if llm_response else "",
        }
        result["step10_changes_summary"] = changes_summary

        # --- Mark success ---
        result["step10_implementation_status"] = "SUCCESS"
        result["step10_tasks_executed"] = 1
        result["step10_error"] = ""

    except Exception as exc:
        result["step10_error"] = str(exc)
        result["step10_implementation_status"] = "ERROR"
        logger.exception("[Step10] Unexpected error: %s", exc)

    result["step10_execution_time_ms"] = (time.time() - step_start) * 1000
    logger.info(
        "[Step10] Done: status=%s, files=%d, elapsed=%.0fms",
        result["step10_implementation_status"],
        len(result["step10_modified_files"]),
        result["step10_execution_time_ms"],
    )
    return result


# ---------------------------------------------------------------------------
# Step 11: Pull Request & Code Review
# ---------------------------------------------------------------------------


def step11_pull_request_review(state: FlowState) -> Dict[str, Any]:
    """Step 11: Pull Request creation and code review via Level3GitHubWorkflow.

    Reads branch/issue context from state, delegates to
    Level3GitHubWorkflow.step11_create_pull_request(), and maps the result
    to step11_* keys.

    Returns a well-formed result dict (never raises, never returns None).
    Returns SKIPPED-status when branch or Level3GitHubWorkflow is unavailable.

    State keys consumed:
        session_dir / session_path    - passed to Level3GitHubWorkflow ctor
        project_root                  - repo_path for Level3GitHubWorkflow ctor
        step8_issue_id                - GitHub issue number
        step9_branch_created          - gate: skip if False/missing
        step9_branch_name             - source branch for PR
        step10_modified_files         - list of changed files for summary
        step10_implementation_summary - optional narrative summary
        step10_changes_summary        - dict with files_modified list
        step0_selected_skills         - passed through to PR creation
        step0_selected_agents         - passed through to PR creation

    State keys produced (always present in return dict):
        step11_pr_id          - str (PR number)
        step11_pr_url         - str
        step11_review_passed  - bool
        step11_review_issues  - list[str]
        step11_merged         - bool
        step11_status         - "OK" | "ERROR" | "SKIPPED"
        step11_execution_time_ms - float
        step11_error          - str (empty on success)
    """
    step_start = time.time()

    result: Dict[str, Any] = {
        "step11_pr_id": "0",
        "step11_pr_url": "",
        "step11_review_passed": True,
        "step11_review_issues": [],
        "step11_merged": False,
        "step11_status": "ERROR",
        "step11_execution_time_ms": 0.0,
        "step11_error": "",
    }

    try:
        # --- Gate: branch must exist ---
        if not state.get("step9_branch_created", False):
            result["step11_status"] = "SKIPPED"
            result["step11_error"] = "step9_branch_created is False; skipping PR creation"
            logger.warning("[Step11] %s", result["step11_error"])
            result["step11_execution_time_ms"] = (time.time() - step_start) * 1000
            return result

        # --- Gate: Level3GitHubWorkflow must be importable ---
        if Level3GitHubWorkflow is None:
            result["step11_status"] = "SKIPPED"
            result["step11_error"] = "Level3GitHubWorkflow import failed; skipping PR creation"
            logger.warning("[Step11] %s", result["step11_error"])
            result["step11_execution_time_ms"] = (time.time() - step_start) * 1000
            return result

        # --- Resolve session dir + repo path ---
        session_dir: str = state.get("session_dir") or state.get("session_path") or os.getcwd()
        project_root: str = state.get("project_root", ".") or "."

        # --- Extract issue number ---
        raw_issue_id = state.get("step8_issue_id", "0") or "0"
        try:
            issue_number = int(str(raw_issue_id).strip())
        except (ValueError, TypeError):
            issue_number = 0

        # --- Extract branch name ---
        branch_name: str = state.get("step9_branch_name", "") or ""
        if not branch_name:
            result["step11_status"] = "SKIPPED"
            result["step11_error"] = "step9_branch_name is empty; cannot create PR"
            logger.warning("[Step11] %s", result["step11_error"])
            result["step11_execution_time_ms"] = (time.time() - step_start) * 1000
            return result

        # --- Build changes summary string ---
        changes_summary_str: str = state.get("step10_implementation_summary", "") or ""
        if not changes_summary_str:
            # Fall back to list of modified files
            modified: List[str] = (
                state.get("step10_modified_files", [])
                or (state.get("step10_changes_summary") or {}).get("files_modified", [])
                or []
            )
            if modified:
                changes_summary_str = "Modified files:\n" + "\n".join("- %s" % f for f in modified)

        # --- Auto-merge flag ---
        auto_merge: bool = os.environ.get("STEP11_AUTO_MERGE", "1") != "0"

        # --- Skills / agents context ---
        selected_skills: List[str] = state.get("step0_selected_skills", []) or []
        selected_agents: List[str] = state.get("step0_selected_agents", []) or []

        # --- Invoke GitHub workflow ---
        logger.info(
            "[Step11] Creating PR: issue=#%d, branch=%s, auto_merge=%s",
            issue_number,
            branch_name,
            auto_merge,
        )

        github_wf = Level3GitHubWorkflow(session_dir=session_dir, repo_path=project_root)
        pr_result: Dict[str, Any] = github_wf.step11_create_pull_request(
            issue_number=issue_number,
            branch_name=branch_name,
            changes_summary=changes_summary_str,
            auto_merge=auto_merge,
            selected_skills=selected_skills,
            selected_agents=selected_agents,
        )

        # --- Map result to step11_* keys ---
        success: bool = pr_result.get("success", False)
        pr_number = pr_result.get("pr_number", 0) or 0
        pr_url: str = pr_result.get("pr_url", "") or ""
        merged: bool = pr_result.get("merged", False)

        result["step11_pr_id"] = str(pr_number)
        result["step11_pr_url"] = pr_url
        result["step11_merged"] = merged
        result["step11_review_passed"] = success
        result["step11_status"] = "OK" if success else "ERROR"

        if not success:
            err = pr_result.get("error", "PR creation returned success=False")
            result["step11_error"] = err
            result["step11_review_issues"] = [err]
            logger.error("[Step11] PR creation failed: %s", err)
        else:
            logger.info(
                "[Step11] PR created: #%s at %s (merged=%s)",
                pr_number,
                pr_url,
                merged,
            )

    except Exception as exc:
        result["step11_error"] = str(exc)
        result["step11_status"] = "ERROR"
        result["step11_review_issues"] = [str(exc)]
        logger.exception("[Step11] Unexpected error: %s", exc)

    result["step11_execution_time_ms"] = (time.time() - step_start) * 1000
    logger.info(
        "[Step11] Done: status=%s, pr=%s, elapsed=%.0fms",
        result["step11_status"],
        result["step11_pr_id"],
        result["step11_execution_time_ms"],
    )
    return result
