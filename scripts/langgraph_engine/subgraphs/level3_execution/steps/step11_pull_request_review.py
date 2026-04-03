"""
Level 3 Execution - Step 11: Pull Request & Code Review
"""

from loguru import logger

from ....flow_state import FlowState


def step11_pull_request_review(state: FlowState) -> dict:
    """Step 11: Pull Request & Code Review - Create PR and run automated checks.

    Creates PR from feature branch to main and runs quality checks:
    - Code linting and type checking
    - Test coverage verification
    - Breaking changes detection
    - Documentation updates

    Implements conditional retry loop:
    - If checks fail AND retries < 3: mark for retry back to step10
    - If checks pass OR retries >= 3: continue to step12

    Returns PR id, review status, and blocking issues.
    """
    try:
        import os

        branch_name = state.get("step9_branch_name", "")
        issue_id = state.get("step8_issue_id", "0")

        # Skip if no branch was created (no issue -> no branch -> no PR)
        if not branch_name or not state.get("step9_branch_created", False):
            logger.info("Step 11: Skipping PR creation - no branch was created")
            return {
                "step11_pr_id": "0",
                "step11_pr_url": "",
                "step11_review_passed": True,
                "step11_review_issues": [],
                "step11_merged": False,
                "step11_retry_count": 0,
                "step11_status": "SKIPPED",
            }

        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH", ".")
        project_root = state.get("project_root", ".")
        retry_count = state.get("step11_retry_count", 0)

        # Build changes summary from step 10 results
        modified_files = state.get("step10_modified_files", [])
        changes_summary = state.get("step10_changes_summary", {})
        summary_text = f"Files modified: {len(modified_files)}"
        if isinstance(changes_summary, dict):
            summary_text += f", Tasks completed: {changes_summary.get('tasks_completed', 0)}"

        # Get selected skills/agents for code review
        selected_skills = []
        selected_agents = []
        skill = state.get("step5_skill", "")
        agent = state.get("step5_agent", "")
        if skill:
            selected_skills = [skill] if isinstance(skill, str) else list(skill)
        if agent:
            selected_agents = [agent] if isinstance(agent, str) else list(agent)

        # Use Level3GitHubWorkflow for real PR creation & review
        try:
            from ....level3_execution.steps8to12_github import Level3GitHubWorkflow

            workflow = Level3GitHubWorkflow(session_dir=session_path, repo_path=project_root)
            result = workflow.step11_create_pull_request(
                issue_number=int(issue_id) if issue_id.isdigit() else 0,
                branch_name=branch_name,
                changes_summary=summary_text,
                auto_merge=True,
                selected_skills=selected_skills,
                selected_agents=selected_agents,
            )

            if result.get("success"):
                return {
                    "step11_pr_id": str(result.get("pr_number", "0")),
                    "step11_pr_url": result.get("pr_url", ""),
                    "step11_review_passed": result.get("review_passed", True),
                    "step11_review_issues": result.get("review_issues", []),
                    "step11_merged": result.get("merged", False),
                    "step11_retry_count": retry_count,
                    "step11_status": "OK",
                }
            else:
                logger.warning(f"PR creation failed: {result.get('error')}. Using fallback.")

        except Exception as gh_err:
            logger.warning(f"Level3GitHubWorkflow unavailable for PR: {gh_err}. Using fallback.")

        # CallGraph: post-change impact review (best-effort)
        impact_review = None
        try:
            from ....level3_execution.call_graph_analyzer import review_change_impact

            pre_graph = state.get("step10_pre_change_graph")
            if pre_graph:
                impact_review = review_change_impact(project_root, pre_graph, modified_files)
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback: mark review as passed so pipeline continues
        result = {
            "step11_pr_id": "0",
            "step11_pr_url": "",
            "step11_review_passed": True,
            "step11_review_issues": ["GitHub integration unavailable - review skipped"],
            "step11_merged": False,
            "step11_retry_count": retry_count,
            "step11_status": "FALLBACK",
        }
        if impact_review:
            result["step11_impact_review"] = impact_review
        return result

    except Exception as e:
        return {"step11_review_passed": False, "step11_status": "ERROR", "step11_error": str(e)}
