"""
Level 3 Execution - Step 9: Branch Creation
"""

from loguru import logger

from ....flow_state import FlowState


def step9_branch_creation(state: FlowState) -> dict:
    """Step 9: Branch Creation - Create feature branch for implementation.

    Creates a feature branch from main:
    - Branch name: {issue_id}-{label}
    - Tracks to origin/main

    Returns branch_name for next step.
    """
    try:
        import os

        issue_id = state.get("step8_issue_id", "0")
        state.get("step8_title", "")
        task_type = state.get("step0_task_type", "task").lower()
        label = state.get("step8_label", task_type)
        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH", ".")
        project_root = state.get("project_root", ".")

        # Branch name format: {label}/issue-{id}
        # e.g. bug/issue-168, feature/issue-170, task/issue-171
        # Label comes from Step 8 (LLM classification: bug, feature, task, etc.)
        branch_label = label.lower().strip() if label else task_type.lower().replace(" ", "-")

        # Skip branch creation if no real issue was created (issue_id=0 means fallback)
        if issue_id == "0" or not state.get("step8_issue_created", False):
            logger.info("Step 9: Skipping branch creation - no GitHub issue created (issue_id=0)")
            return {"step9_branch_name": "", "step9_branch_created": False, "step9_status": "SKIPPED"}

        # Use Level3GitHubWorkflow for real branch creation
        try:
            from ....level3_execution.steps8to12_github import Level3GitHubWorkflow

            workflow = Level3GitHubWorkflow(session_dir=session_path, repo_path=project_root)
            result = workflow.step9_create_branch(
                issue_number=int(issue_id) if issue_id.isdigit() else 0, label=branch_label, session_dir=session_path
            )

            if result.get("success"):
                return {
                    "step9_branch_name": result.get("branch_name", ""),
                    "step9_branch_created": True,
                    "step9_conflict_detected": result.get("conflict_detected", False),
                    "step9_status": "OK",
                }
            else:
                logger.warning(f"Branch creation failed: {result.get('error')}. Using fallback.")

        except Exception as gh_err:
            logger.warning(f"Level3GitHubWorkflow unavailable for branch: {gh_err}. Using fallback.")

        # Fallback: return branch name without actually creating it
        branch_name = f"{branch_label}/issue-{issue_id}"
        return {"step9_branch_name": branch_name, "step9_branch_created": False, "step9_status": "FALLBACK"}

    except Exception as e:
        return {"step9_branch_created": False, "step9_status": "ERROR", "step9_error": str(e)}
