# ruff: noqa: F821
"""Level 3 v2 step node wrapper.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.
"""
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


def step12_issue_closure_node(state: FlowState) -> Dict[str, Any]:
    """Step 12: Issue Closure with network retry and error handling."""

    def _with_network_retry(st):
        """GitHub API calls in step 12 get exponential backoff retry."""
        last_exc = None
        for attempt in range(3):
            try:
                return step12_issue_closure(st)
            except Exception as exc:
                exc_str = str(exc).lower()
                if any(kw in exc_str for kw in ["timeout", "connection", "network", "rate", "api"]):
                    last_exc = exc
                    infra = get_infra(st)
                    if infra["error_logger"]:
                        infra["error_logger"].log_error(
                            step="Step 12",
                            error_message=str(exc),
                            severity="WARNING",
                            error_type="NetworkError",
                            recovery_action="Retry %d/3 with backoff" % (attempt + 1),
                        )
                    from time import sleep

                    sleep(2**attempt)
                else:
                    raise
        raise last_exc or RuntimeError("Issue closure failed after 3 retries")

    result = _run_step(
        12,
        "Issue Closure",
        _with_network_retry,
        state,
        fallback_result={
            "step12_issue_closed": False,
            "step12_status": "ERROR",
        },
    )

    # -- Jira closure (after GitHub issue closed) ------------------------
    jira_key = state.get("jira_issue_key", "")
    if jira_key and state.get("jira_issue_created", False):
        try:
            from ..steps8to12_jira import Level3JiraWorkflow

            jira_wf = Level3JiraWorkflow()
            close_result = jira_wf.step12_close_jira_issue(
                jira_issue_key=jira_key,
                pr_number=int(state.get("step11_pr_id", "0")),
                files_modified=state.get("step10_modified_files", []),
                approach_taken=state.get("step12_closing_comment", ""),
            )
            result["jira_issue_closed"] = close_result.get("closed", False)
        except Exception as e:
            logger.warning("[v2] Jira closure failed (non-blocking): %s", str(e))

    # -- Figma: Comment implementation complete --
    figma_key = state.get("figma_file_key", "")
    if figma_key and state.get("figma_enabled", False):
        try:
            from ..figma_workflow import Level3FigmaWorkflow

            figma_wf = Level3FigmaWorkflow()
            figma_wf.step12_implementation_complete(
                file_key=figma_key,
                pr_number=int(state.get("step11_pr_id", "0")),
                pr_url=state.get("step11_pr_url", ""),
            )
        except Exception as e:
            logger.warning("Figma Step 12 comment failed: %s", str(e))

    return result


def step13_docs_update_node(state: FlowState) -> Dict[str, Any]:
    """Step 13: Documentation Update with file-op error handling."""

    def _with_file_error_handling(st):
        try:
            result = step13_project_documentation_update(st)
            # Track documentation files updated
            if result and result.get("step13_updates_prepared"):
                updated = result.get("step13_updated_files") or []
                if updated:
                    infra = get_infra(st)
                    if infra["metrics"]:
                        try:
                            infra["metrics"].record_files_modified(
                                step=13,
                                files=updated,
                                operation="modified",
                            )
                        except Exception:
                            pass
            return result
        except IOError as io_err:
            infra = get_infra(st)
            if infra["error_logger"]:
                infra["error_logger"].log_error(
                    step="Step 13",
                    error_message=str(io_err),
                    severity="WARNING",
                    error_type="IOError",
                    recovery_action="Documentation update skipped; continuing pipeline",
                )
            return {
                "step13_updates_prepared": False,
                "step13_documentation_status": "ERROR",
                "step13_error": f"IOError: {io_err}",
            }

    return _run_step(
        13,
        "Documentation Update",
        _with_file_error_handling,
        state,
        fallback_result={
            "step13_updates_prepared": False,
            "step13_documentation_status": "ERROR",
        },
    )


def step14_final_summary_node(state: FlowState) -> Dict[str, Any]:
    """Step 14: Final Summary with metrics print and full error handling."""

    def _with_metrics_summary(st):
        result = step14_final_summary_generation(st)
        # Print metrics summary at end of pipeline
        infra = get_infra(st)
        if infra["metrics"]:
            try:
                # Record any files modified from state
                modified_files = st.get("step10_modified_files") or st.get("step13_updated_files") or []
                if modified_files:
                    infra["metrics"].record_files_modified(
                        step=14,
                        files=modified_files,
                        operation="modified",
                    )
                infra["metrics"].print_summary()
            except Exception:
                pass
        return result

    return _run_step(
        14,
        "Final Summary",
        _with_metrics_summary,
        state,
        fallback_result={
            "step14_status": "ERROR",
            "step14_summary": {},
        },
    )


# ============================================================================
# ORCHESTRATION PRE-ANALYSIS NODE - Runs before Step 0.0
# ============================================================================
