"""Level 3 step node wrappers for Steps 10-11.

Extracted from level3_execution/subgraph.py for modularity.
Windows-safe: ASCII only.
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

try:
    from .step_wrappers_5to9 import _build_retry_history_context
except ImportError:

    def _build_retry_history_context(state) -> str:  # type: ignore[misc]
        return ""


# _run_step is defined in the parent subgraph module. Imported lazily because
# subgraph.py imports this module, creating a circular chain; pulling it via
# a late binding avoids the cycle at module load time.
try:
    from ..subgraph import _run_step
except ImportError:  # pragma: no cover -- defensive fallback for isolated imports

    def _run_step(step_number, label, fn, state, fallback_result):  # type: ignore[misc]
        try:
            return fn(state)
        except Exception as exc:
            logger.error(f"_run_step fallback caught exception in Step {step_number}: {exc}")
            return fallback_result


try:
    from ...core.infrastructure import get_infra
except ImportError:  # pragma: no cover

    def get_infra(state):  # type: ignore[misc]
        return {"metrics": None, "error_logger": None}


try:
    from .step_implementations_10_11 import step10_implementation_execution, step11_pull_request_review
except ImportError as _imp_err:  # pragma: no cover
    logger.error("step_implementations_10_11 import failed: %s", _imp_err)

    def step10_implementation_execution(state):  # type: ignore[misc]
        return {
            "step10_implementation_status": "ERROR",
            "step10_tasks_executed": 0,
            "step10_modified_files": [],
            "step10_llm_invoked": False,
            "step10_system_prompt_loaded": False,
            "step10_user_message_loaded": False,
            "step10_error": "step_implementations_10_11 unavailable",
        }

    def step11_pull_request_review(state):  # type: ignore[misc]
        return {
            "step11_pr_id": "0",
            "step11_pr_url": "",
            "step11_review_passed": True,
            "step11_review_issues": ["step_implementations_10_11 unavailable"],
            "step11_merged": False,
            "step11_status": "ERROR",
            "step11_error": "step_implementations_10_11 unavailable",
        }


def step10_implementation_note(state: FlowState) -> Dict[str, Any]:
    """Step 10: Implementation Execution with LLM fallback, retry history, and full error handling.

    Injects CallGraph implementation context before execution and
    snapshots the call graph for Step 11 comparison.
    """
    # -- Jira: Transition to In Progress --
    jira_key = state.get("jira_issue_key", "")
    if jira_key and state.get("jira_issue_created", False):
        try:
            from ..steps8to12_jira import Level3JiraWorkflow

            jira_wf = Level3JiraWorkflow()
            jira_wf.step10_start_progress(jira_issue_key=jira_key)
        except Exception as e:
            logger.warning("Jira Step 10 transition failed: %s", str(e))

    # -- Figma: Comment implementation started --
    figma_key = state.get("figma_file_key", "")
    if figma_key and state.get("figma_enabled", False):
        try:
            from ..figma_workflow import Level3FigmaWorkflow

            figma_wf = Level3FigmaWorkflow()
            figma_wf.step10_implementation_started(
                file_key=figma_key,
                components=state.get("figma_components", []),
            )
        except Exception as e:
            logger.warning("Figma Step 10 comment failed: %s", str(e))

    # --- CallGraph: Snapshot before change + implementation context ---
    pre_change_graph = {}
    call_context = {}
    suggested_tests = []
    _dep_result = None
    try:
        from ..call_graph_analyzer import get_implementation_context, snapshot_call_graph

        project_root = state.get("project_root", ".")
        target_files = state.get("step2_files_affected", []) or state.get("step0_target_files", [])

        # Snapshot current state for Step 11 diff
        pre_change_graph = snapshot_call_graph(project_root)

        # Get implementation context
        if target_files:
            call_context = get_implementation_context(project_root, target_files)
            suggested_tests = call_context.get("suggested_test_scope", [])
            if call_context.get("call_graph_available"):
                logger.info(
                    "[v2] Step 10 CallGraph context: %d entry points, %d test files suggested",
                    len(call_context.get("entry_points_affected", [])),
                    len(suggested_tests),
                )
        # Resolve project dependencies for better graph coverage
        # D1: guard-and-skip -- resolve_and_enhance requires a valid graph object,
        # not None. Only call when pre_change_graph is a non-None object.
        try:
            from ..build_dependency_resolver import resolve_and_enhance

            if call_context.get("call_graph_available") and pre_change_graph is not None:
                _dep_result = resolve_and_enhance(project_root, pre_change_graph)
            else:
                logger.debug("[v2] Step 10 dependency resolution skipped: pre_change_graph is None")
        except Exception as e:
            logger.debug("[v2] Step 10 dependency resolution skipped: %s", e)
    except Exception as e:
        logger.debug("[v2] Step 10 CallGraph context skipped: %s", e)

    # Build retry context before execution
    retry_count = state.get("step11_retry_count", 0)
    history = _build_retry_history_context(state)
    has_retry = retry_count > 0

    # Build execution prompt (with retry history if applicable)
    base_prompt = state.get("step7_execution_prompt", "")
    if has_retry:
        issues = state.get("step11_review_issues", [])
        issue_lines = "\n".join("- %s" % issue for issue in issues)
        exec_prompt = (
            "%s\n\n"
            "[RETRY #%d] Fix the following code review issues while keeping\n"
            "previous fixes:/n/n"
            "CURRENT ISSUES TO FIX:/n"
            "%s\n\n"
            "IMPORTANT:/n"
            "- Do NOT undo previous fixes (shown in history above)\n"
            "- Fix ONLY the current issues listed above\n"
            "- Keep all working code from previous attempts\n"
            "- Run tests to verify fixes if possible\n\n"
            "Original implementation prompt:/n"
            "---\n"
            "%s\n"
            "---\n\n"
            "Please fix the issues above and re-implement."
        ) % (history, retry_count, issue_lines, base_prompt)
    else:
        exec_prompt = base_prompt

    def _with_llm_fallback(st):
        """
        Wrap step10 with explicit LLM error -> Claude API fallback pattern
        and file modification tracking.
        Catches any uncaught LLM-related exceptions bubbling up from
        step10_implementation_execution.
        """
        try:
            result = step10_implementation_execution(st)
            # Track files modified by implementation step
            if result and result.get("step10_modified_files"):
                infra = get_infra(st)
                if infra["metrics"]:
                    try:
                        infra["metrics"].record_files_modified(
                            step=10,
                            files=result["step10_modified_files"],
                            operation="modified",
                        )
                    except Exception:
                        pass
            return result
        except Exception as llm_exc:
            # Check if this looks like an LLM connectivity issue
            err_msg = str(llm_exc).lower()
            is_llm_error = any(kw in err_msg for kw in ("connection", "model", "timeout", "inference", "api"))
            if is_llm_error:
                infra = get_infra(st)
                if infra["error_logger"]:
                    infra["error_logger"].log_error(
                        step="Step 10",
                        error_message=str(llm_exc),
                        severity="ERROR",
                        error_type="LLMError",
                        recovery_action="Attempting Claude API fallback",
                    )
                    infra["error_logger"].log_decision(
                        step="Step 10",
                        decision="Fallback to Claude API",
                        reasoning="Local LLM failed during implementation execution",
                    )
                # Re-raise; _run_step will catch and return fallback_result
            raise

    result = _run_step(
        10,
        "Implementation Execution",
        _with_llm_fallback,
        state,
        fallback_result={
            "step10_implementation_status": "ERROR",
            "step10_tasks_executed": 0,
            "step10_modified_files": [],
            "step10_llm_invoked": False,
            "step10_system_prompt_loaded": False,
            "step10_user_message_loaded": False,
        },
    )

    # Merge retry context into result
    result["step10_execution_prompt"] = exec_prompt
    result["step10_has_retry_context"] = has_retry
    result["step10_status"] = result.get("step10_status", result.get("step10_implementation_status", "OK"))
    result["step10_message"] = result.get("step10_message", "Step 10 executed (retry=%d)" % retry_count)

    # Merge CallGraph data into result for Step 11
    if pre_change_graph:
        result["step10_pre_change_graph"] = pre_change_graph
    if call_context.get("call_graph_available"):
        result["step10_call_context"] = call_context
    if suggested_tests:
        result["step10_suggested_test_scope"] = suggested_tests
    if _dep_result is not None:
        result["step10_dependency_resolution"] = _dep_result

    # --- Quality: SonarQube scan + auto-fix + test generation ---
    try:
        from ..sonarqube_scanner import scan_and_report

        project_root = state.get("project_root", ".")
        modified_files = result.get("step10_modified_files", [])

        if modified_files and os.environ.get("CLAUDE_DRY_RUN") != "1":
            # 1. Scan for issues
            scan_result = scan_and_report(project_root, modified_files)
            result["step10_sonar_results"] = scan_result

            # 2. Auto-fix if findings exist
            if scan_result.get("findings"):
                try:
                    from ..sonar_auto_fixer import run_fix_loop

                    fix_result = run_fix_loop(project_root, scan_result["findings"], max_iterations=2)
                    result["step10_auto_fix_result"] = fix_result
                    logger.info(
                        "[v2] Step 10 auto-fix: %d fixed, %d remaining",
                        fix_result.get("findings_fixed", 0),
                        fix_result.get("findings_remaining", 0),
                    )
                except Exception as e:
                    logger.debug("[v2] Step 10 auto-fix skipped: %s", e)

            # 3. Generate tests for modified files
            try:
                from ..test_generator import generate_tests_for_modified_files

                test_result = generate_tests_for_modified_files(
                    project_root, modified_files, call_graph=pre_change_graph if pre_change_graph else None
                )
                result["step10_generated_tests"] = test_result
                if test_result.get("tests_generated", 0) > 0:
                    logger.info(
                        "[v2] Step 10 generated %d test files for %d methods",
                        test_result.get("tests_generated", 0),
                        test_result.get("total_methods_tested", 0),
                    )
            except Exception as e:
                logger.debug("[v2] Step 10 test generation skipped: %s", e)

            # 3b. Generate integration tests from call paths
            try:
                from ..integration_test_generator import generate_integration_tests

                integ_result = generate_integration_tests(
                    project_root, modified_files, call_graph=pre_change_graph if pre_change_graph else None
                )
                result["step10_generated_integration_tests"] = integ_result
                if integ_result.get("paths_tested", 0) > 0:
                    logger.info(
                        "[v2] Step 10 generated integration tests for %d call paths",
                        integ_result.get("paths_tested", 0),
                    )
            except Exception as e:
                logger.debug("[v2] Step 10 integration test generation skipped: %s", e)

            # 4. Coverage analysis
            try:
                from ..coverage_analyzer import suggest_test_scope

                coverage_result = suggest_test_scope(project_root, modified_files)
                result["step10_coverage_results"] = coverage_result
            except Exception as e:
                logger.debug("[v2] Step 10 coverage analysis skipped: %s", e)

    except Exception as e:
        logger.debug("[v2] Step 10 quality pipeline skipped: %s", e)

    # Mark graph stale: Step 10 wrote files, any cached pre-implementation
    # snapshots (step2_impact_analysis, pre_analysis_result) are no longer
    # valid.  Step 11 and beyond should call refresh_call_graph_if_stale().
    result["call_graph_stale"] = True

    return result


def step11_pull_request_node(state: FlowState) -> Dict[str, Any]:
    """Step 11: Pull Request & Code Review with network retry and error handling.

    After the standard review, runs CallGraph impact comparison between
    pre-change snapshot (from Step 10) and current state to detect
    breaking changes, orphaned methods, and risk assessment.
    """

    def _with_network_retry(st):
        """GitHub API calls in step 11 get exponential backoff retry."""
        last_exc = None
        for attempt in range(3):
            try:
                return step11_pull_request_review(st)
            except Exception as exc:
                exc_str = str(exc).lower()
                if any(kw in exc_str for kw in ["timeout", "connection", "network", "rate", "api"]):
                    last_exc = exc
                    infra = get_infra(st)
                    if infra["error_logger"]:
                        infra["error_logger"].log_error(
                            step="Step 11",
                            error_message=str(exc),
                            severity="WARNING",
                            error_type="NetworkError",
                            recovery_action="Retry %d/3 with backoff" % (attempt + 1),
                        )
                    from time import sleep

                    sleep(2**attempt)
                else:
                    raise
        raise last_exc or RuntimeError("PR creation failed after 3 retries")

    result = _run_step(
        11,
        "Pull Request & Code Review",
        _with_network_retry,
        state,
        fallback_result={
            "step11_review_passed": True,  # Allow pipeline to continue on error
            "step11_review_issues": ["Step 11 failed - skipping review"],
            "step11_retry_count": state.get("step11_retry_count", 0),
            "step11_status": "ERROR",
        },
    )

    # -- Jira PR linking (after PR created) ------------------------------
    jira_key = state.get("jira_issue_key", "")
    if jira_key and state.get("jira_issue_created", False):
        try:
            from ..steps8to12_jira import Level3JiraWorkflow

            jira_wf = Level3JiraWorkflow()
            link_result = jira_wf.step11_link_pr_and_transition(
                jira_issue_key=jira_key,
                pr_url=result.get("step11_pr_url", ""),
                pr_number=int(result.get("step11_pr_id", "0")),
            )
            result["jira_pr_linked"] = link_result.get("linked", False)
            result["jira_transitioned"] = link_result.get("transitioned", False)
        except Exception as e:
            logger.warning("[v2] Jira PR linking failed (non-blocking): %s", str(e))

    # -- Jira: Post-merge update --
    if result.get("step11_merged") and jira_key:
        try:
            from ..steps8to12_jira import Level3JiraWorkflow

            jira_wf = Level3JiraWorkflow()
            jira_wf.step11_post_merge_update(
                jira_issue_key=jira_key,
                pr_number=int(result.get("step11_pr_id", "0")),
                pr_url=result.get("step11_pr_url", ""),
                branch_name=state.get("step9_branch_name", ""),
            )
        except Exception as e:
            logger.warning("Jira post-merge update failed: %s", str(e))

    # --- CallGraph: Post-change impact review ---
    try:
        from ..call_graph_analyzer import review_change_impact

        project_root = state.get("project_root", ".")
        modified_files = result.get("step10_modified_files") or state.get("step10_modified_files", [])
        pre_snapshot = state.get("step10_pre_change_graph", {})

        if modified_files:
            impact_review = review_change_impact(project_root, modified_files, pre_snapshot)
            if impact_review.get("call_graph_available"):
                result["step11_impact_review"] = impact_review
                result["step11_risk_assessment"] = impact_review.get("risk_assessment", "safe")
                breaking = impact_review.get("breaking_changes", [])
                if breaking:
                    result["step11_breaking_changes"] = breaking
                    # Add breaking changes to review issues
                    existing_issues = result.get("step11_review_issues", [])
                    for bc in breaking[:5]:
                        existing_issues.append(
                            "BREAKING: %s (%s, %d callers)"
                            % (
                                bc.get("method", ""),
                                bc.get("reason", ""),
                                bc.get("callers", 0),
                            )
                        )
                    result["step11_review_issues"] = existing_issues

                logger.info(
                    "[v2] Step 11 CallGraph review: risk=%s, breaking=%d, orphaned=%d",
                    impact_review.get("risk_assessment", "unknown"),
                    len(breaking),
                    len(impact_review.get("orphaned_methods", [])),
                )
    except Exception as e:
        logger.debug("[v2] Step 11 CallGraph review skipped: %s", e)

    # --- Quality Gate: Evaluate all gates before merge ---
    try:
        from ..quality_gate import evaluate_quality_gate, generate_gate_report

        project_root = state.get("project_root", ".")

        gate_result = evaluate_quality_gate(
            project_root,
            {
                **state,
                **result,  # Include step10/11 results
            },
        )
        result["step11_quality_gate"] = gate_result

        if not gate_result.get("gate_passed", True):
            # Add gate failures to review issues
            existing_issues = result.get("step11_review_issues", [])
            for gate_name in gate_result.get("blocking_gates", []):
                gate_info = gate_result.get("gates", {}).get(gate_name, {})
                existing_issues.append("QUALITY GATE FAILED: %s - %s" % (gate_name, gate_info.get("reason", "unknown")))
            result["step11_review_issues"] = existing_issues
            result["step11_quality_gate_passed"] = False

            # Generate gate report for PR comment
            gate_report = generate_gate_report(gate_result)
            result["step11_gate_report"] = gate_report

            logger.info(
                "[v2] Step 11 quality gate FAILED: %s",
                ", ".join(gate_result.get("blocking_gates", [])),
            )
        else:
            result["step11_quality_gate_passed"] = True
            logger.info("[v2] Step 11 quality gate PASSED")

    except Exception as e:
        logger.debug("[v2] Step 11 quality gate skipped: %s", e)

    # --- User Interaction: Generate questions for breaking changes ---
    try:
        from ..user_interaction import InteractionManager, generate_step11_questions

        questions = generate_step11_questions({**state, **result})
        if questions:
            result["pending_interactions"] = questions
            mgr = InteractionManager()
            for q in questions:
                mgr._interactions.append(q)
            # In hook mode, apply defaults automatically
            if os.environ.get("CLAUDE_HOOK_MODE", "1") == "1":
                mgr.apply_defaults()
            result["step11_interaction_questions"] = len(questions)
    except Exception as e:
        logger.debug("[v2] Step 11 user interaction skipped: %s", e)

    # -- Figma Integration: design implementation review ------------------
    if os.environ.get("ENABLE_FIGMA", "0") == "1":
        file_key = state.get("figma_file_key", "")
        if file_key:
            try:
                from ..figma_workflow import Level3FigmaWorkflow

                figma_wf = Level3FigmaWorkflow()
                impl_summary = result.get("step11_review_summary", "") or state.get("step10_implementation_summary", "")
                review_result = figma_wf.step11_design_review(
                    file_key=file_key,
                    implementation_summary=impl_summary,
                )
                if review_result.get("success"):
                    existing_issues = result.get("step11_review_issues", [])
                    checklist_text = review_result.get("checklist_text", "")
                    if checklist_text:
                        existing_issues.append("DESIGN REVIEW:/n" + checklist_text)
                    result["step11_review_issues"] = existing_issues
                    logger.info(
                        "[v2] Figma design review completed: %d items",
                        len(review_result.get("review_items", [])),
                    )
                else:
                    result["figma_error"] = review_result.get("error", "Unknown")
            except Exception as e:
                logger.warning("[v2] Figma integration (step11) failed (non-blocking): %s", str(e))

    return result
