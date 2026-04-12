# ruff: noqa: F821
"""Level 3 v2 step node wrapper.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.

CHANGE LOG (v1.13.0):
  Removed Steps 5, 6, 7 node wrappers -- collapsed into Step 0 template call.
  Steps 8 and 9 are unchanged.
  _build_retry_history_context is kept (consumed by step10_implementation_note).
"""
import os
from typing import Any, Dict

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    from ...flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]


# REMOVED: step5_skill_selection_node -- collapsed into Step 0 template (v1.13.0)
# REMOVED: step6_skill_validation_node -- collapsed into Step 0 template (v1.13.0)
# REMOVED: step7_final_prompt_node -- collapsed into Step 0 template (v1.13.0)
#
# Outputs these nodes used to produce are now written by step0_task_analysis_node
# after the orchestration template LLM call. See impact_map.md Section 2.


def step8_github_issue_node(state: FlowState) -> Dict[str, Any]:
    """Step 8: GitHub Issue Creation with retry and full error handling."""

    def _with_network_retry(st):
        """Network calls in step 8 get exponential backoff retry."""
        from time import sleep

        import requests

        last_exc = None
        for attempt in range(3):
            try:
                return step8_github_issue_creation(st)
            except requests.RequestException as req_exc:
                last_exc = req_exc
                infra = get_infra(st)
                if infra["error_logger"]:
                    infra["error_logger"].log_error(
                        step="Step 8",
                        error_message=str(req_exc),
                        severity="WARNING",
                        error_type="NetworkError",
                        recovery_action=f"Retry {attempt + 1}/3 with backoff",
                    )
                logger.warning(f"[Step 8] Network error attempt {attempt + 1}/3: {req_exc}")
                sleep(2**attempt)
            except Exception:
                # Non-network errors: don't retry
                raise

        # All retries exhausted
        raise last_exc or RuntimeError("GitHub issue creation failed after 3 retries")

    result = _run_step(
        8,
        "GitHub Issue Creation",
        _with_network_retry,
        state,
        fallback_result={
            "step8_issue_id": "0",
            "step8_issue_url": "",
            "step8_issue_created": False,
            "step8_status": "ERROR",
        },
    )

    # -- Jira Integration (after GitHub issue is created) ----------------
    if os.environ.get("ENABLE_JIRA", "0") == "1":
        try:
            from ..steps8to12_jira import Level3JiraWorkflow

            jira_wf = Level3JiraWorkflow()
            jira_result = jira_wf.step8_create_jira_issue(
                title=result.get("step8_title", ""),
                description=state.get("user_message", ""),
                label=result.get("step8_label", "task"),
                github_issue_url=result.get("step8_issue_url", ""),
                github_issue_number=int(result.get("step8_issue_id", "0")),
            )
            result["jira_enabled"] = True
            result["jira_issue_key"] = jira_result.get("jira_issue_key", "")
            result["jira_issue_url"] = jira_result.get("jira_issue_url", "")
            result["jira_issue_created"] = jira_result.get("success", False)
            if not jira_result.get("success"):
                result["jira_error"] = jira_result.get("error", "Unknown")
            logger.info("[v2] Jira issue created: %s", jira_result.get("jira_issue_key", ""))
        except Exception as e:
            logger.warning("[v2] Jira integration failed (non-blocking): %s", str(e))
            result["jira_enabled"] = True
            result["jira_issue_created"] = False
            result["jira_error"] = str(e)

    return result


def step9_branch_creation_node(state: FlowState) -> Dict[str, Any]:
    """Step 9: Branch Creation with network retry and error handling."""

    def _with_network_retry(st):
        """Git/GitHub calls in step 9 get exponential backoff retry."""
        # -- Jira branch naming override (before branch creation) --------
        jira_key = st.get("jira_issue_key", "")
        if jira_key and st.get("jira_issue_created", False):
            label = st.get("step8_label", "feature")
            jira_branch = "{}/{}".format(label, jira_key.lower())
            # Inject override into a mutable copy so the underlying step
            # picks it up via state["step9_branch_name"] if it checks that field,
            # or via a dedicated override key that step9_branch_creation reads.
            st = dict(st)
            st["step9_jira_branch_override"] = jira_branch
            logger.info("[v2] Jira branch override: %s", jira_branch)

        last_exc = None
        for attempt in range(3):
            try:
                return step9_branch_creation(st)
            except Exception as exc:
                # Retry on network-like errors (connection, timeout, git push)
                exc_str = str(exc).lower()
                if any(kw in exc_str for kw in ["timeout", "connection", "network", "remote", "push"]):
                    last_exc = exc
                    infra = get_infra(st)
                    if infra["error_logger"]:
                        infra["error_logger"].log_error(
                            step="Step 9",
                            error_message=str(exc),
                            severity="WARNING",
                            error_type="NetworkError",
                            recovery_action="Retry %d/3 with backoff" % (attempt + 1),
                        )
                    from time import sleep

                    sleep(2**attempt)
                else:
                    raise  # Non-network errors: don't retry
        raise last_exc or RuntimeError("Branch creation failed after 3 retries")

    return _run_step(
        9,
        "Branch Creation",
        _with_network_retry,
        state,
        fallback_result={
            "step9_branch_name": "fallback-branch",
            "step9_branch_created": False,
            "step9_status": "ERROR",
        },
    )


def _build_retry_history_context(state) -> str:
    """Build complete retry history context for inclusion in execution prompt.

    Returns empty string on first attempt (retry_count == 0).
    On retries, builds a formatted block showing:
    - Previous attempt summaries
    - Current issues to fix (truncated to first 10)
    - Retry status with remaining attempts
    - FINAL ATTEMPT warning when no retries remain
    """
    retry_count = state.get("step11_retry_count", 0)
    if retry_count == 0:
        return ""

    retry_messages = state.get("step11_retry_messages", [])
    review_issues = state.get("step11_review_issues", [])
    max_retries = 3
    remaining = max(0, max_retries - retry_count)

    lines = []
    lines.append("=" * 70)
    lines.append("COMPLETE RETRY HISTORY")
    lines.append("=" * 70)
    lines.append("")
    lines.append("PREVIOUS ATTEMPTS (What was fixed):")
    lines.append("-" * 70)

    for i, msg in enumerate(retry_messages, 1):
        lines.append("")
        lines.append("  Attempt %d:" % i)
        lines.append("  %s" % msg)

    lines.append("")
    lines.append("CURRENT ISSUES TO FIX:")
    lines.append("-" * 70)

    display_issues = review_issues[:10]
    for i, issue in enumerate(display_issues, 1):
        lines.append("  %d. %s" % (i, issue))

    if len(review_issues) > 10:
        lines.append("  ... and %d more issues" % (len(review_issues) - 10))

    lines.append("")
    lines.append("RETRY STATUS:")
    lines.append("-" * 70)
    lines.append("  Current Attempt: #%d of %d" % (retry_count, max_retries))
    lines.append("  Remaining Attempts: %d" % remaining)

    if remaining == 0:
        lines.append("")
        lines.append("FINAL ATTEMPT - PR will be blocked for manual review")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)
