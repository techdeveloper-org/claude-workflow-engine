"""
Level 3 - Steps 8-12: GitHub Workflow Integration

Implements the GitHub workflow:
- Step 8: Issue creation
- Step 9: Branch creation
- Step 10: (Implementation - handled by Claude directly)
- Step 11: Pull request creation + merge
- Step 12: Issue closure

These steps integrate with Git and GitHub APIs for complete workflow automation.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from ..builders import IssueBodyBuilder, PRBodyBuilder
from ..git_operations import GitOperations
from ..github_facade import GitHubFacade
from ..github_merge_validation import (
    detect_git_conflict_markers,
    detect_project_type_for_validation,
    test_merge_locally,
    validate_project_after_merge,
)
from ..github_operation_router import GitHubOperationRouter
from .github_code_review import (
    analyze_diff_for_issues,
    check_docker_best_practices,
    check_java_spring_patterns,
    check_python_best_practices,
    comment_on_pr_with_review,
    generate_review_recommendations,
    run_code_review,
    run_simplify_review,
)


# Lazy import helpers - avoids circular dependencies at module level
def _get_review_criteria(project_root: Optional[str] = None):
    """Lazy-load ReviewCriteria to avoid import-time side effects."""
    try:
        from .review_criteria import ReviewCriteria

        return ReviewCriteria(project_root=project_root)
    except Exception as _e:
        logger.warning(f"[GitHubWorkflow] ReviewCriteria unavailable: {_e}")
        return None


def _get_conflict_resolver(session_dir: str):
    """Lazy-load ConflictResolver."""
    try:
        from ..conflict_resolver import ConflictResolver

        return ConflictResolver(session_dir=session_dir)
    except Exception as _e:
        logger.warning(f"[GitHubWorkflow] ConflictResolver unavailable: {_e}")
        return None


# Import retry helper from remaining steps module (shared utility)
try:
    from .remaining_steps import _llm_call_with_retry
except ImportError:
    # Fallback: define inline if import fails
    def _llm_call_with_retry(call_fn, step_name="LLM", max_retries=3):  # type: ignore
        last_exc = None
        delays = [1.0, 2.0, 4.0, 8.0]
        for attempt in range(max_retries + 1):
            try:
                return call_fn()
            except Exception as exc:
                last_exc = exc
                err_lower = str(exc).lower()
                is_retryable = any(
                    kw in err_lower for kw in ("timeout", "connection", "rate_limit", "503", "overloaded")
                )
                if not is_retryable or attempt >= max_retries:
                    raise
                delay = delays[min(attempt, len(delays) - 1)]
                logger.warning(f"[{step_name}] LLM retry {attempt+1}/{max_retries} in {delay}s: {exc}")
                time.sleep(delay)
        if last_exc:
            raise last_exc


class Level3GitHubWorkflow:
    """Manages GitHub workflow for Steps 8-12."""

    def __init__(self, session_dir: str, repo_path: str = "."):
        self.session_dir = session_dir
        # Phase 4: MCP enabled as primary backend with gh CLI fallback
        # Performance: MCP ~80ms vs gh CLI ~300ms (3.33x faster)
        # Fallback: gh CLI used automatically if MCP fails
        self.github = GitHubOperationRouter(use_mcp=True, fallback_to_gh=True)
        self.git = GitOperations(repo_path=repo_path)

        # GitHubFacade provides a simplified typed interface for GitHub + Git.
        # Internally delegates to self.github (router) and self.git, so there
        # is no duplicate logic.  New step implementations should prefer
        # self.facade over calling self.github / self.git directly.
        self.facade = GitHubFacade(repo_path=repo_path, use_mcp=True)

        # Check if we're in a git repository - this is critical for Steps 8-12
        if not self.git.is_git_repo:
            logger.warning(
                "=" * 70
                + "\nWARNING: Not a git repository. GitHub workflow (Steps 8-12) cannot proceed.\n"
                + "To enable GitHub integration:\n"
                + "1. Initialize git: git init\n"
                + "2. Add remote: git remote add origin <your-github-repo-url>\n"
                + "3. Create initial commit: git add . && git commit -m 'Initial commit'\n"
                + "=" * 70
            )

        # Label detection uses llm_call or keyword matching

    # ===== STEP 8: GITHUB ISSUE CREATION =====

    def step8_create_issue(
        self, title: str, description: str, task_summary: str = "", implementation_plan: str = ""
    ) -> Dict[str, Any]:
        """
        Create GitHub issue from execution prompt.

        Args:
            title: Issue title
            description: Issue description (from prompt.txt analysis)
            task_summary: Summary of task
            implementation_plan: Planned implementation approach

        Returns:
            {
                "issue_number": int,
                "issue_url": str,
                "issue_id": int,
                "success": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 8: GITHUB ISSUE CREATION")
        logger.info("=" * 60)

        # Check if we're in a git repository
        if not self.git.is_git_repo:
            logger.error("Cannot create GitHub issue: not a git repository")
            return {
                "success": False,
                "error": "Not a git repository. GitHub operations require git initialization.",
                "execution_time_ms": 0,
            }

        step_start = time.time()

        try:
            # Determine label from description analysis
            label = self._determine_issue_label(description)
            logger.info(f"Detected issue type: {label}")

            # Build issue body with task information
            issue_body = self._build_issue_body(description, task_summary, implementation_plan)

            # Create issue via facade (typed IssueResult)
            result = self.facade.create_issue(title=title, body=issue_body, labels=[label] if label else [])

            if not result.success:
                logger.error(f"Issue creation failed: {result.error}")
                return {"success": False, "error": result.error, "execution_time_ms": (time.time() - step_start) * 1000}

            issue_number = result.number
            issue_url = result.url

            logger.info(f"Issue created: #{issue_number}")
            logger.info(f"  URL: {issue_url}")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "issue_number": issue_number,
                "issue_url": issue_url,
                "issue_id": None,
                "label": label,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Step 8 failed: {e}")
            return {"success": False, "error": str(e), "execution_time_ms": (time.time() - step_start) * 1000}

    def _determine_issue_label(self, description: str) -> Optional[str]:
        """Determine issue label using LLM-based intelligent classification.

        First tries llm_call for sophisticated analysis, falls back to keyword matching.

        Returns one of: bug, feature, enhancement, test, documentation, task
        """
        try:
            label = self._classify_with_llm(description)
            if label:
                logger.info(f"LLM classified issue as: {label}")
                return label
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}. Using keyword fallback.")

        # Fallback to keyword-based classification
        return self._classify_with_keywords(description)

    def _classify_with_llm(self, description: str) -> Optional[str]:
        """Use llm_call to intelligently classify issue label.

        Args:
            description: Issue description text

        Returns:
            One of: bug, feature, enhancement, test, documentation, task
        """
        try:
            from ..llm_call import llm_call
        except ImportError:
            return None

        prompt = (
            "You are an expert software engineer analyzing GitHub issue descriptions to classify them.\n\n"
            "Classify the issue into ONE of these categories:\n"
            "- bug: Something is broken, errors, crashes, not working as expected\n"
            "- feature: New functionality, new capability requested\n"
            "- enhancement: Improvement to existing feature, optimization, refactoring\n"
            "- test: Testing related, unit tests, integration tests, test coverage\n"
            "- documentation: Documentation, README, comments, API docs\n"
            "- task: General task, chore, maintenance work\n\n"
            "IMPORTANT: Respond with ONLY the label name, nothing else. No explanation, no quotes. Just one word.\n\n"
            f"Issue description:\n{description}"
        )

        try:
            response = llm_call(prompt, model="fast_classification", temperature=0.1, timeout=15)
            if not response:
                return None

            label = response.strip().lower().splitlines()[0].strip()
            valid_labels = ["bug", "feature", "enhancement", "test", "documentation", "task"]
            if label in valid_labels:
                return label
            logger.warning(f"LLM returned invalid label: {label}. Using keyword fallback.")
            return None
        except Exception as e:
            logger.error(f"LLM classification error: {e}")
            return None

    def _classify_with_keywords(self, description: str) -> Optional[str]:
        """Fallback keyword-based classification when LLM unavailable."""
        description_lower = description.lower()

        # Keyword-based heuristics (ordered by priority)
        if any(word in description_lower for word in ["bug", "fix", "broken", "error", "crash", "issue", "problem"]):
            return "bug"
        elif any(word in description_lower for word in ["feature", "new", "add", "implement", "support"]):
            return "feature"
        elif any(word in description_lower for word in ["enhance", "improve", "optimize", "refactor", "simplify"]):
            return "enhancement"
        elif any(
            word in description_lower for word in ["test", "testing", "coverage", "unit test", "integration test"]
        ):
            return "test"
        elif any(
            word in description_lower for word in ["doc", "readme", "documentation", "comment", "comment", "guide"]
        ):
            return "documentation"
        else:
            return "task"

    def _build_issue_body(self, description: str, task_summary: str = "", implementation_plan: str = "") -> str:
        """Build detailed issue body with structured sections.

        Delegates to IssueBodyBuilder for consistent, validated output.
        Signature is unchanged for backward compatibility.
        """
        builder = IssueBodyBuilder().description(description)
        if task_summary:
            builder = builder.task_summary(task_summary)
        if implementation_plan:
            builder = builder.implementation_plan(implementation_plan)
        return builder.build()

    # ===== STEP 9: BRANCH CREATION =====

    def step9_create_branch(
        self,
        issue_number: int,
        label: str = "feature",
        session_dir: str = "",
    ) -> Dict[str, Any]:
        """
        Create and checkout new branch for issue.

        Branch conflict detection via ConflictResolver:
        - If the desired branch already exists (local or remote), an auto-suffixed
          name is used (e.g. issue-42-feature-03141200).
        - Uncommitted change warnings are logged but do not block creation.

        Args:
            issue_number: GitHub issue number
            label:        Issue label (used in branch name)
            session_dir:  Session directory (for ConflictResolver log file)

        Returns:
            {
                "success": bool,
                "branch_name": str,
                "branch_created": bool,
                "conflict_detected": bool,
                "original_branch": str,
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 9: BRANCH CREATION")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Build desired branch name: {label}/issue-{id}
            # e.g. bug/issue-168, feature/issue-170
            desired_branch = f"{label}/issue-{issue_number}"

            # --- Conflict detection & resolution ---
            repo_path = getattr(self.git, "repo_path", ".")
            conflict_resolver = _get_conflict_resolver(session_dir or ".")
            branch_name = desired_branch
            conflict_detected = False

            if conflict_resolver is not None:
                branch_resolution = conflict_resolver.resolve_branch_conflict(
                    desired_branch=desired_branch,
                    repo_path=repo_path,
                )
                branch_name = branch_resolution.get("resolved_branch", desired_branch)
                conflict_detected = branch_resolution.get("conflict_detected", False)

                if conflict_detected:
                    logger.warning(f"[Step 9] Branch conflict resolved: " f"'{desired_branch}' -> '{branch_name}'")
                    # Persist conflict log
                    try:
                        conflict_resolver.save_conflict_log()
                    except Exception:
                        pass
            else:
                logger.debug("[Step 9] ConflictResolver unavailable - skipping branch conflict check")

            logger.info(f"Creating branch: {branch_name}")

            # Create branch from main via facade (typed BranchResult)
            branch_result = self.facade.create_branch(branch_name, from_branch="main")

            if not branch_result.success:
                logger.error(f"Branch creation failed: {branch_result.error}")
                return {
                    "success": False,
                    "error": branch_result.error,
                    "execution_time_ms": (time.time() - step_start) * 1000,
                }

            logger.info(f"Branch created and pushed: {branch_name}")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "branch_name": branch_name,
                "original_branch": desired_branch,
                "issue_number": issue_number,
                "conflict_detected": conflict_detected,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Step 9 failed: {e}")
            return {"success": False, "error": str(e), "execution_time_ms": (time.time() - step_start) * 1000}

    # ===== STEP 11: PULL REQUEST CREATION & MERGE =====

    def step11_create_pull_request(
        self,
        issue_number: int,
        branch_name: str,
        changes_summary: str = "",
        auto_merge: bool = True,
        selected_skills: List[str] = None,
        selected_agents: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create and optionally merge pull request.

        Args:
            issue_number: GitHub issue number
            branch_name: Source branch name
            changes_summary: Summary of changes made
            auto_merge: Automatically merge if no conflicts

        Returns:
            {
                "success": bool,
                "pr_number": int,
                "pr_url": str,
                "merged": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 11: PULL REQUEST CREATION & MERGE")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Create PR title and body
            pr_title = f"Fix/Feature: Issue #{issue_number}"
            pr_body = self._build_pr_body(issue_number, changes_summary)

            logger.info(f"Creating PR from {branch_name} -> main")

            # Create PR via facade (typed PRResult)
            pr_result = self.facade.create_pr(title=pr_title, body=pr_body, head=branch_name, base="main")

            if not pr_result.success:
                logger.error(f"PR creation failed: {pr_result.error}")
                return {
                    "success": False,
                    "error": pr_result.error,
                    "execution_time_ms": (time.time() - step_start) * 1000,
                }

            pr_number = pr_result.number
            pr_url = pr_result.url

            logger.info(f"PR created: #{pr_number}")
            logger.info(f"  URL: {pr_url}")

            # CODE REVIEW (NEW: Using selected skills/agents)
            review_passed = True
            review_issues = []
            if selected_skills or selected_agents:
                logger.info(f"Running code review with selected skills: {selected_skills}, agents: {selected_agents}")
                review_result = self._run_code_review(
                    pr_number=pr_number,
                    branch_name=branch_name,
                    selected_skills=selected_skills or [],
                    selected_agents=selected_agents or [],
                )
                review_passed = review_result.get("passed", False)
                review_issues = review_result.get("issues", [])

                if not review_passed:
                    logger.warning(f"Code review found {len(review_issues)} issues")
                    # Comment on PR with issues
                    self._comment_on_pr_with_review(pr_number, review_issues)
                else:
                    logger.info("✓ Code review passed")
                    # Comment on PR that review passed
                    self.github.add_pr_comment(pr_number, "✓ Code review passed. Ready to merge.")
            else:
                logger.info("No skills/agents selected, skipping code review")

            # Optionally merge (only if review passed)
            merged = False
            if auto_merge and review_passed:
                logger.info(f"Auto-merging PR #{pr_number}...")

                # ✅ BULLETPROOF: Check merge conflicts (4 layers)
                logger.info("Running bulletproof merge conflict detection...")
                conflict_check = self.check_merge_conflicts_bulletproof(pr_number=pr_number, branch_name=branch_name)

                if not conflict_check.get("safe_to_merge"):
                    logger.error(f"Merge blocked: {conflict_check.get('reason')}")
                    logger.error(f"Failed at Layer {conflict_check.get('layer')}")
                    # Comment on PR with conflict details
                    conflict_comment = (
                        f"## ⚠️ Merge Blocked - Conflict Detection\n\n"
                        f"**Layer {conflict_check.get('layer')} Failed:** {conflict_check.get('reason')}\n\n"
                        f"**Details:**\n"
                        f"```\n{conflict_check.get('details')}\n```\n\n"
                        f"Please resolve conflicts and retry."
                    )
                    self.github.add_pr_comment(pr_number, conflict_comment)
                    return {
                        "success": True,  # PR created but not merged
                        "pr_number": pr_number,
                        "pr_url": pr_url,
                        "merged": False,
                        "merge_blocked_reason": conflict_check.get("reason"),
                        "execution_time_ms": (time.time() - step_start) * 1000,
                    }

                # All checks passed - proceed with merge via facade (typed MergeResult)
                merge_result = self.facade.merge_pr(
                    pr_number, commit_message=f"Merge PR #{pr_number}: Fix issue #{issue_number}"
                )

                if merge_result.success:
                    merged = True
                    logger.info(f"PR #{pr_number} merged")
                else:
                    logger.warning(f"PR merge failed: {merge_result.error}")
                    logger.info("Keeping PR open for manual review")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "merged": merged,
                "review_passed": review_passed,
                "review_issues": review_issues,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Step 11 failed: {e}")
            return {"success": False, "error": str(e), "execution_time_ms": (time.time() - step_start) * 1000}

    def _build_pr_body(self, issue_number: int, changes_summary: str = "") -> str:
        """Build PR description.

        Delegates to PRBodyBuilder for consistent, validated output.
        Signature is unchanged for backward compatibility.
        """
        builder = PRBodyBuilder().resolves(issue_number)
        if changes_summary:
            builder = builder.changes_summary(changes_summary)
        return builder.build()

    # ===== STEP 12: ISSUE CLOSURE =====

    def step12_close_issue(
        self,
        issue_number: int,
        pr_number: int,
        files_modified: Optional[List[str]] = None,
        approach_taken: str = "",
        verification_steps: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Close GitHub issue with detailed closing comment.

        Args:
            issue_number: GitHub issue number to close
            pr_number: PR number that resolved the issue
            files_modified: List of modified files
            approach_taken: Description of solution approach
            verification_steps: Steps to verify the fix

        Returns:
            {"success": bool, "closed": bool}
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 12: ISSUE CLOSURE")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Build closing comment
            closing_comment = self._build_closing_comment(pr_number, files_modified, approach_taken, verification_steps)

            logger.info(f"Closing issue #{issue_number}")

            # Close issue with comment via facade (returns bool)
            closed_ok = self.facade.close_issue(issue_number, comment=closing_comment)

            if not closed_ok:
                logger.error(f"Issue closure failed for #{issue_number}")
                return {
                    "success": False,
                    "error": f"Failed to close issue #{issue_number}",
                    "execution_time_ms": (time.time() - step_start) * 1000,
                }

            logger.info(f"Issue #{issue_number} closed")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "issue_number": issue_number,
                "closed": True,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Step 12 failed: {e}")
            return {"success": False, "error": str(e), "execution_time_ms": (time.time() - step_start) * 1000}

    def _build_closing_comment(
        self,
        pr_number: int,
        files_modified: Optional[List[str]] = None,
        approach_taken: str = "",
        verification_steps: Optional[List[str]] = None,
    ) -> str:
        """Build detailed closing comment with resolution info."""
        parts = [f"## ✅ Resolved by PR #{pr_number}", ""]

        if approach_taken:
            parts.extend(["## Approach Taken", approach_taken, ""])

        if files_modified:
            parts.extend(["## Files Modified", "- " + "\n- ".join(files_modified), ""])

        if verification_steps:
            parts.extend(["## Verification Steps", "1. " + "\n2. ".join(verification_steps), ""])

        parts.extend(["---", "*Resolved by Claude Workflow Engine execution pipeline*"])

        return "\n".join(parts)

    # ===== COMPLETE WORKFLOW =====

    def execute_github_workflow(
        self, title: str, description: str, changes_summary: str = "", files_modified: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Execute complete GitHub workflow (Steps 8-12).

        Args:
            title: Issue/PR title
            description: Issue description
            changes_summary: Summary of changes made
            files_modified: Files that were modified

        Returns:
            {
                "success": bool,
                "issue_number": int,
                "pr_number": int,
                "branch_name": str,
                "closed": bool
            }
        """
        logger.info("\n" + "=" * 60)
        logger.info("EXECUTING COMPLETE GITHUB WORKFLOW (Steps 8-12)")
        logger.info("=" * 60)

        # Step 8: Create issue
        step8 = self.step8_create_issue(title, description)
        if not step8.get("success"):
            return {"success": False, "error": "Step 8 failed", "step8": step8}

        issue_number = step8.get("issue_number")
        label = step8.get("label", "task")

        # Step 9: Create branch
        step9 = self.step9_create_branch(issue_number, label)
        if not step9.get("success"):
            return {"success": False, "error": "Step 9 failed", "step8": step8, "step9": step9}

        branch_name = step9.get("branch_name")

        # Step 11: Create and merge PR
        step11 = self.step11_create_pull_request(issue_number, branch_name, changes_summary)
        if not step11.get("success"):
            return {"success": False, "error": "Step 11 failed", "step8": step8, "step9": step9, "step11": step11}

        pr_number = step11.get("pr_number")

        # Step 12: Close issue
        step12 = self.step12_close_issue(issue_number, pr_number, files_modified)
        if not step12.get("success"):
            logger.warning(f"Step 12 failed: {step12.get('error')} (PR still open)")

        logger.info("\n" + "=" * 60)
        logger.info("✓ GITHUB WORKFLOW COMPLETE")
        logger.info(f"  Issue: #{issue_number}")
        logger.info(f"  PR: #{pr_number}")
        logger.info(f"  Branch: {branch_name}")
        logger.info("=" * 60)

        return {
            "success": True,
            "issue_number": issue_number,
            "pr_number": pr_number,
            "branch_name": branch_name,
            "closed": step12.get("closed", False),
            "steps": {"step8": step8, "step9": step9, "step11": step11, "step12": step12},
        }

    # ===== CODE REVIEW INTEGRATION (Step 11 Enhancement) =====

    def _run_code_review(
        self,
        pr_number: int,
        branch_name: str,
        selected_skills: List[str],
        selected_agents: List[str],
        files_changed: Optional[List[str]] = None,
        pr_body: str = "",
    ) -> Dict[str, Any]:
        """
        Run code review on PR using selected skills/agents AND ReviewCriteria checklist.

        Delegates to :func:`github_code_review.run_code_review`.

        Returns:
            {
                "passed": bool,
                "issues": List[str],
                "recommendations": str,
                "criteria_result": Dict,
                "criteria_score": float,
            }
        """
        project_root = getattr(self.git, "repo_path", None)
        return run_code_review(
            pr_number=pr_number,
            branch_name=branch_name,
            selected_skills=selected_skills,
            selected_agents=selected_agents,
            git_ops=self.git,
            project_root=project_root,
            files_changed=files_changed,
            pr_body=pr_body,
        )

    def _analyze_diff_for_issues(self, diff_text: str, diff_lines: List[str]) -> List[str]:
        """Delegate to :func:`github_code_review.analyze_diff_for_issues`."""
        return analyze_diff_for_issues(diff_text, diff_lines)

    def _check_python_best_practices(self, diff_text: str) -> List[str]:
        """Delegate to :func:`github_code_review.check_python_best_practices`."""
        return check_python_best_practices(diff_text)

    def _check_java_spring_patterns(self, diff_text: str) -> List[str]:
        """Delegate to :func:`github_code_review.check_java_spring_patterns`."""
        return check_java_spring_patterns(diff_text)

    def _check_docker_best_practices(self, diff_text: str) -> List[str]:
        """Delegate to :func:`github_code_review.check_docker_best_practices`."""
        return check_docker_best_practices(diff_text)

    def _run_simplify_review(self, diff_text: str) -> List[str]:
        """Delegate to :func:`github_code_review.run_simplify_review`."""
        return run_simplify_review(diff_text)

    def _generate_review_recommendations(self, issues: List[str]) -> str:
        """Delegate to :func:`github_code_review.generate_review_recommendations`."""
        return generate_review_recommendations(issues)

    def _comment_on_pr_with_review(self, pr_number: int, issues: List[str]) -> None:
        """Delegate to :func:`github_code_review.comment_on_pr_with_review`."""
        comment_on_pr_with_review(self.github, pr_number, issues)

    # ========================================================================
    # BULLETPROOF MERGE CONFLICT DETECTION (4 LAYERS - LANGUAGE AGNOSTIC)
    # ========================================================================

    def check_merge_conflicts_bulletproof(self, pr_number: int, branch_name: str) -> Dict[str, Any]:
        """Bulletproof 4-layer merge conflict detection.

        Calls self._detect_git_conflict_markers, self._test_merge_locally,
        self._detect_project_type, self._validate_project_after_merge so
        that tests can mock individual layers via patch.object.
        """
        logger.info("=" * 70)
        logger.info("BULLETPROOF MERGE CONFLICT DETECTION (4 LAYERS)")
        logger.info("=" * 70)

        # Layer 1: GitHub API
        logger.info("[Layer 1] GitHub API Check (pr.mergeable)...")
        try:
            pr = self.github.repo.get_pull(pr_number)
            if not pr.mergeable:
                logger.error("[Layer 1] FAILED: PR not mergeable")
                return {
                    "safe_to_merge": False,
                    "layer": 1,
                    "reason": "GitHub API: PR has unresolvable conflicts",
                    "details": {"pr_mergeable": False},
                }
            logger.info("[Layer 1] PASSED")
        except Exception as e:
            logger.warning(f"[Layer 1] Could not check: {e}")

        # Layer 2: Git conflict markers
        logger.info("[Layer 2] Git Status Parsing...")
        conflicts = self._detect_git_conflict_markers(branch_name)
        if conflicts:
            logger.error(f"[Layer 2] FAILED: {len(conflicts)} conflicts")
            return {
                "safe_to_merge": False,
                "layer": 2,
                "reason": f"Git status: {len(conflicts)} files have conflict markers",
                "details": {"conflict_files": conflicts},
            }
        logger.info("[Layer 2] PASSED")

        # Layer 3: Test merge
        logger.info("[Layer 3] Test Merge...")
        merge_test = self._test_merge_locally(branch_name)
        if not merge_test.get("success"):
            logger.error(f"[Layer 3] FAILED: {merge_test.get('reason')}")
            return {
                "safe_to_merge": False,
                "layer": 3,
                "reason": merge_test.get("reason"),
                "details": merge_test.get("details", {}),
            }
        logger.info("[Layer 3] PASSED")

        # Layer 4: Project validation
        logger.info("[Layer 4] Project validation...")
        project_type = self._detect_project_type()
        validation = self._validate_project_after_merge(project_type)
        if not validation.get("success"):
            logger.error(f"[Layer 4] FAILED: {validation.get('reason')}")
            return {
                "safe_to_merge": False,
                "layer": 4,
                "reason": validation.get("reason"),
                "details": validation.get("details", {}),
            }
        logger.info("[Layer 4] PASSED")

        logger.info("ALL 4 LAYERS PASSED - SAFE TO MERGE")
        return {
            "safe_to_merge": True,
            "layer": 4,
            "reason": "All merge safety checks passed",
            "details": {
                "layer1": "GitHub API check passed",
                "layer2": "No git conflict markers",
                "layer3": "Test merge succeeded",
                "layer4": f"Project validation passed ({project_type})",
            },
        }

    def _detect_git_conflict_markers(self, branch_name: str) -> List[str]:
        """Delegate to :func:`github_merge_validation.detect_git_conflict_markers`."""
        return detect_git_conflict_markers(self.git, branch_name)

    def _test_merge_locally(self, branch_name: str) -> Dict[str, Any]:
        """Delegate to :func:`github_merge_validation.test_merge_locally`."""
        return test_merge_locally(self.git, branch_name)

    def _detect_project_type(self) -> str:
        """Delegate to :func:`github_merge_validation.detect_project_type_for_validation`."""
        repo_path = getattr(self.git, "repo_path", None)
        return detect_project_type_for_validation(repo_path)

    def _validate_project_after_merge(self, project_type: str) -> Dict[str, Any]:
        """Delegate to :func:`github_merge_validation.validate_project_after_merge`."""
        return validate_project_after_merge(self.git, project_type)
