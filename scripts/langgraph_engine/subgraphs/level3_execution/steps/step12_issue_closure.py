"""
Level 3 Execution - Step 12: Issue Closure
"""

from loguru import logger

from ....flow_state import FlowState


def step12_issue_closure(state: FlowState) -> dict:
    """Step 12: Issue Closure - Close GitHub issue after implementation.

    Closes the GitHub issue with:
    - PR link
    - Implementation summary
    - Test results
    - Next steps (if any)

    Returns closure status.
    """
    try:
        # Skip if no issue was created
        if not state.get("step8_issue_created", False) or state.get("step8_issue_id", "0") == "0":
            logger.info("Step 12: Skipping issue closure - no issue was created")
            return {"step12_issue_closed": False, "step12_closing_comment": "", "step12_status": "SKIPPED"}
        import os

        issue_id = state.get("step8_issue_id", "0")
        pr_id = state.get("step11_pr_id", "0")
        pr_url = state.get("step11_pr_url", "")
        review_passed = state.get("step11_review_passed", False)
        modified_files = state.get("step10_modified_files", [])
        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH", ".")
        project_root = state.get("project_root", ".")

        # Build approach description from state
        task_type = state.get("step0_task_type", "Task")
        skill = state.get("step5_skill", "")
        approach = f"{task_type} execution"
        if skill:
            approach += f" using {skill}"

        # Use Level3GitHubWorkflow for real issue closure
        try:
            from ....level3_execution.steps8to12_github import Level3GitHubWorkflow

            workflow = Level3GitHubWorkflow(session_dir=session_path, repo_path=project_root)
            result = workflow.step12_close_issue(
                issue_number=int(issue_id) if issue_id.isdigit() else 0,
                pr_number=int(pr_id) if pr_id.isdigit() else 0,
                files_modified=modified_files,
                approach_taken=approach,
                verification_steps=[
                    "Code review passed" if review_passed else "Code review pending",
                    f"PR: {pr_url}" if pr_url else "PR not created",
                ],
            )

            if result.get("success"):
                # Post-merge cleanup: checkout main, pull, delete merged branch
                branch_name = state.get("step9_branch_name", "")
                if branch_name and state.get("step11_merged", False):
                    try:
                        cleanup = workflow.git.post_merge_cleanup(branch_name)
                        if cleanup.get("success"):
                            logger.info(f"Post-merge cleanup: {cleanup.get('message')}")
                        else:
                            logger.warning(f"Post-merge cleanup issue: {cleanup.get('error')}")
                    except Exception as cleanup_err:
                        logger.warning(f"Post-merge cleanup skipped: {cleanup_err}")

                return {
                    "step12_issue_closed": True,
                    "step12_closing_comment": f"Issue #{issue_id} closed via PR #{pr_id}",
                    "step12_status": "OK",
                }
            else:
                logger.warning(f"Issue closure failed: {result.get('error')}. Using fallback.")

        except Exception as gh_err:
            logger.warning(f"Level3GitHubWorkflow unavailable for closure: {gh_err}. Using fallback.")

        # Fallback: report closure was not performed
        closing_comment = f"""## Implementation Complete

PR: {pr_url}
Status: {'Passed' if review_passed else 'Needs Work'}

See PR for details."""

        return {"step12_issue_closed": False, "step12_closing_comment": closing_comment, "step12_status": "FALLBACK"}

    except Exception as e:
        return {"step12_issue_closed": False, "step12_status": "ERROR", "step12_error": str(e)}
