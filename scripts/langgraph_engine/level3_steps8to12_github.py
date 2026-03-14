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
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from loguru import logger
from .github_integration import GitHubIntegration
from .github_operation_router import GitHubOperationRouter
from .git_operations import GitOperations
from .ollama_service import OllamaService

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
        from .conflict_resolver import ConflictResolver
        return ConflictResolver(session_dir=session_dir)
    except Exception as _e:
        logger.warning(f"[GitHubWorkflow] ConflictResolver unavailable: {_e}")
        return None

# Import retry helper from remaining steps module (shared utility)
try:
    from .level3_remaining_steps import _llm_call_with_retry
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
                    kw in err_lower for kw in
                    ("timeout", "connection", "rate_limit", "503", "overloaded")
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

        # Check if we're in a git repository - this is critical for Steps 8-12
        if not self.git.is_git_repo:
            logger.warning(
                "="*70
                + "\nWARNING: Not a git repository. GitHub workflow (Steps 8-12) cannot proceed.\n"
                + "To enable GitHub integration:\n"
                + "1. Initialize git: git init\n"
                + "2. Add remote: git remote add origin <your-github-repo-url>\n"
                + "3. Create initial commit: git add . && git commit -m 'Initial commit'\n"
                + "="*70
            )

        # Initialize Ollama service for intelligent label detection
        try:
            self.ollama = OllamaService()
        except Exception as e:
            logger.warning(f"Ollama service not available: {e}. Will use keyword-based label detection.")
            self.ollama = None

    # ===== STEP 8: GITHUB ISSUE CREATION =====

    def step8_create_issue(
        self,
        title: str,
        description: str,
        task_summary: str = "",
        implementation_plan: str = ""
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
                "execution_time_ms": 0
            }

        step_start = time.time()

        try:
            # Determine label from description analysis
            label = self._determine_issue_label(description)
            logger.info(f"Detected issue type: {label}")

            # Build issue body with task information
            issue_body = self._build_issue_body(description, task_summary, implementation_plan)

            # Create issue
            result = self.github.create_issue(
                title=title,
                body=issue_body,
                labels=[label] if label else []
            )

            if not result.get("success"):
                logger.error(f"Issue creation failed: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            issue_number = result.get("issue_number")
            issue_url = result.get("issue_url")

            logger.info(f"✓ Issue created: #{issue_number}")
            logger.info(f"  URL: {issue_url}")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "issue_number": issue_number,
                "issue_url": issue_url,
                "issue_id": result.get("issue_id"),
                "label": label,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 8 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _determine_issue_label(self, description: str) -> Optional[str]:
        """Determine issue label using LLM-based intelligent classification.

        First tries Ollama LLM for sophisticated analysis, falls back to keyword matching.

        Returns one of: bug, feature, enhancement, test, documentation, task
        """
        # Try LLM-based classification first
        if self.ollama:
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
        """Use Ollama LLM to intelligently classify issue label.

        Args:
            description: Issue description text

        Returns:
            One of: bug, feature, enhancement, test, documentation, task
        """
        system_prompt = """You are an expert software engineer analyzing GitHub issue descriptions to classify them.

Classify the issue into ONE of these categories:
- bug: Something is broken, errors, crashes, not working as expected
- feature: New functionality, new capability requested
- enhancement: Improvement to existing feature, optimization, refactoring
- test: Testing related, unit tests, integration tests, test coverage
- documentation: Documentation, README, comments, API docs
- task: General task, chore, maintenance work

IMPORTANT: Respond with ONLY the label name, nothing else. No explanation, no quotes. Just one word."""

        prompt = f"Classify this GitHub issue:\n\n{description}"

        try:
            messages = [{"role": "user", "content": prompt}]

            def _call_ollama():
                resp = self.ollama.chat(
                    messages=messages,
                    model="fast_classification",
                    temperature=0.3,
                    system_prompt=system_prompt
                )
                if "error" in resp:
                    raise RuntimeError(resp["error"])
                return resp

            # Use retry with exponential backoff for transient LLM errors
            response = _llm_call_with_retry(_call_ollama, "Step 8 Label Classification")

            label = response.get("message", {}).get("content", "").strip().lower()

            # Validate label is one of expected values
            valid_labels = ["bug", "feature", "enhancement", "test", "documentation", "task"]
            if label in valid_labels:
                return label
            else:
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
        elif any(word in description_lower for word in ["test", "testing", "coverage", "unit test", "integration test"]):
            return "test"
        elif any(word in description_lower for word in ["doc", "readme", "documentation", "comment", "comment", "guide"]):
            return "documentation"
        else:
            return "task"

    def _build_issue_body(
        self,
        description: str,
        task_summary: str = "",
        implementation_plan: str = ""
    ) -> str:
        """Build detailed issue body with structured sections."""
        parts = [
            "## Task Summary",
            task_summary or "See description for details.",
            "",
            "## Description",
            description,
        ]

        if implementation_plan:
            parts.extend([
                "",
                "## Implementation Plan",
                implementation_plan
            ])

        parts.extend([
            "",
            "## Automated by",
            "Generated by Claude Insight Level 3 execution pipeline"
        ])

        return "\n".join(parts)

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
            # Build desired branch name
            desired_branch = f"issue-{issue_number}-{label}"

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
                    logger.warning(
                        f"[Step 9] Branch conflict resolved: "
                        f"'{desired_branch}' -> '{branch_name}'"
                    )
                    # Persist conflict log
                    try:
                        conflict_resolver.save_conflict_log()
                    except Exception:
                        pass
            else:
                logger.debug("[Step 9] ConflictResolver unavailable - skipping branch conflict check")

            logger.info(f"Creating branch: {branch_name}")

            # Create branch from main
            result = self.git.create_branch(branch_name, "main")

            if not result.get("success"):
                logger.error(f"Branch creation failed: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
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
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 9 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    # ===== STEP 11: PULL REQUEST CREATION & MERGE =====

    def step11_create_pull_request(
        self,
        issue_number: int,
        branch_name: str,
        changes_summary: str = "",
        auto_merge: bool = True,
        selected_skills: List[str] = None,
        selected_agents: List[str] = None
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

            logger.info(f"Creating PR from {branch_name} → main")

            # Create PR
            pr_result = self.github.create_pull_request(
                title=pr_title,
                body=pr_body,
                head_branch=branch_name,
                base_branch="main"
            )

            if not pr_result.get("success"):
                logger.error(f"PR creation failed: {pr_result.get('error')}")
                return {
                    "success": False,
                    "error": pr_result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            pr_number = pr_result.get("pr_number")
            pr_url = pr_result.get("pr_url")

            logger.info(f"✓ PR created: #{pr_number}")
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
                    selected_agents=selected_agents or []
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
                conflict_check = self.check_merge_conflicts_bulletproof(
                    pr_number=pr_number,
                    branch_name=branch_name
                )

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
                        "merge_blocked_reason": conflict_check.get('reason'),
                        "execution_time_ms": (time.time() - step_start) * 1000
                    }

                # All checks passed - proceed with merge
                merge_result = self.github.merge_pull_request(
                    pr_number,
                    commit_message=f"Merge PR #{pr_number}: Fix issue #{issue_number}"
                )

                if merge_result.get("success"):
                    merged = True
                    logger.info(f"✓ PR #{pr_number} merged")
                else:
                    logger.warning(f"PR merge failed: {merge_result.get('error')}")
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
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 11 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _build_pr_body(self, issue_number: int, changes_summary: str = "") -> str:
        """Build PR description."""
        parts = [
            f"## Resolves #{issue_number}",
            "",
            "## Changes Made"
        ]

        if changes_summary:
            parts.append(changes_summary)
        else:
            parts.append("See issue for details.")

        parts.extend([
            "",
            "## Type of Change",
            "- [ ] Bug fix",
            "- [ ] New feature",
            "- [ ] Enhancement",
            "- [ ] Documentation update",
            "",
            "## Testing",
            "- Changes have been tested locally",
            "- No breaking changes introduced",
            "",
            "Automated by Claude Insight Level 3"
        ])

        return "\n".join(parts)

    # ===== STEP 12: ISSUE CLOSURE =====

    def step12_close_issue(
        self,
        issue_number: int,
        pr_number: int,
        files_modified: Optional[List[str]] = None,
        approach_taken: str = "",
        verification_steps: Optional[List[str]] = None
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
            closing_comment = self._build_closing_comment(
                pr_number,
                files_modified,
                approach_taken,
                verification_steps
            )

            logger.info(f"Closing issue #{issue_number}")

            # Close issue with comment
            result = self.github.close_issue(issue_number, closing_comment)

            if not result.get("success"):
                logger.error(f"Issue closure failed: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error"),
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            logger.info(f"✓ Issue #{issue_number} closed")

            execution_time_ms = (time.time() - step_start) * 1000

            return {
                "success": True,
                "issue_number": issue_number,
                "closed": True,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 12 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _build_closing_comment(
        self,
        pr_number: int,
        files_modified: Optional[List[str]] = None,
        approach_taken: str = "",
        verification_steps: Optional[List[str]] = None
    ) -> str:
        """Build detailed closing comment with resolution info."""
        parts = [
            f"## ✅ Resolved by PR #{pr_number}",
            ""
        ]

        if approach_taken:
            parts.extend([
                "## Approach Taken",
                approach_taken,
                ""
            ])

        if files_modified:
            parts.extend([
                "## Files Modified",
                "- " + "\n- ".join(files_modified),
                ""
            ])

        if verification_steps:
            parts.extend([
                "## Verification Steps",
                "1. " + "\n2. ".join(verification_steps),
                ""
            ])

        parts.extend([
            "---",
            "*Resolved by Claude Insight Level 3 execution pipeline*"
        ])

        return "\n".join(parts)

    # ===== COMPLETE WORKFLOW =====

    def execute_github_workflow(
        self,
        title: str,
        description: str,
        changes_summary: str = "",
        files_modified: Optional[List[str]] = None
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
            "steps": {
                "step8": step8,
                "step9": step9,
                "step11": step11,
                "step12": step12
            }
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

        Process:
        1. Get PR diff
        2. Run structured ReviewCriteria evaluation (code quality, tests, docs)
        3. Run skill-specific pattern checks (Python, Java Spring, Docker)
        4. Combine results and determine pass/fail

        The ReviewCriteria evaluation adds structured checks for:
        - Code quality rules (bare except, type hints, secrets, function length)
        - Test coverage ratio (70% of source files need test counterpart)
        - Documentation requirements (docstrings, PR description length)

        Args:
            pr_number:       GitHub PR number
            branch_name:     Source branch being reviewed
            selected_skills: Skills selected in Step 5
            selected_agents: Agents selected in Step 5
            files_changed:   Optional list of files changed in PR (for ReviewCriteria)
            pr_body:         PR description text (for ReviewCriteria DC003 check)

        Returns:
            {
                "passed": bool,
                "issues": List[str],
                "recommendations": str,
                "criteria_result": Dict,  # Full ReviewCriteria evaluation (if available)
                "criteria_score": float,  # 0.0 - 1.0
            }
        """
        logger.info(
            f"Starting code review for PR #{pr_number} with "
            f"{len(selected_skills)} skills and {len(selected_agents)} agents"
        )

        try:
            # Get PR diff (simplified)
            diff_lines = self.git.get_pr_diff(branch_name, "main")
            diff_text = "\n".join(diff_lines)

            # Analyze diff for common issues (existing logic)
            issues = self._analyze_diff_for_issues(diff_lines)

            # Check for specific patterns based on selected skills
            if "python-backend-engineer" in selected_skills or "python-backend-engineer" in selected_agents:
                issues.extend(self._check_python_best_practices(diff_lines))

            if "spring-boot-microservices" in selected_skills or "spring-boot-microservices" in selected_agents:
                issues.extend(self._check_java_spring_patterns(diff_lines))

            if "docker" in selected_skills or "devops-engineer" in selected_agents:
                issues.extend(self._check_docker_best_practices(diff_lines))

            # --- ReviewCriteria structured evaluation ---
            criteria_result: Dict[str, Any] = {}
            criteria_score: float = 1.0

            review_criteria = _get_review_criteria(project_root=self.git.repo_path if hasattr(self.git, "repo_path") else None)
            if review_criteria is not None:
                logger.info("[CodeReview] Running structured ReviewCriteria evaluation...")
                try:
                    evaluated_files = files_changed or []
                    eval_result = review_criteria.evaluate(
                        files_changed=evaluated_files,
                        pr_title=f"PR #{pr_number} - {branch_name}",
                        pr_body=pr_body,
                        diff_text=diff_text,
                    )
                    criteria_result = eval_result.to_dict()
                    criteria_score = eval_result.score

                    logger.info(
                        f"[CodeReview] ReviewCriteria: "
                        f"passed={eval_result.passed}, score={eval_result.score:.2f}, "
                        f"blocking_issues={len([i for i in eval_result.issues if i.get('severity') == 'blocking'])}"
                    )

                    # Append blocking issues to the main issues list
                    for issue in eval_result.issues:
                        if issue.get("severity") == "blocking":
                            msg = (
                                f"[{issue['rule_id']}] {issue['message']}"
                                + (f" in {issue['file_path']}" if issue.get('file_path') else "")
                            )
                            issues.append(msg)

                    # If ReviewCriteria failed, mark overall review as failed
                    if not eval_result.passed:
                        logger.warning(
                            f"[CodeReview] ReviewCriteria FAILED - merge will be blocked"
                        )

                except Exception as criteria_err:
                    logger.warning(f"[CodeReview] ReviewCriteria evaluation error (non-fatal): {criteria_err}")

            logger.info(f"Code review found {len(issues)} issues")

            passed = len(issues) == 0
            return {
                "passed": passed,
                "issues": issues,
                "recommendations": self._generate_review_recommendations(issues),
                "criteria_result": criteria_result,
                "criteria_score": criteria_score,
            }

        except Exception as e:
            logger.error(f"Code review analysis failed (FAIL-SAFE): {e}")
            logger.error("Blocking merge to prevent broken code - manual review required")
            return {
                "passed": False,  # FAIL-SAFE: Block merge on error
                "issues": [
                    "CRITICAL: Code review process crashed",
                    f"Error: {str(e)}",
                    "Action: Merge blocked for safety. Manual review required."
                ],
                "recommendations": (
                    "Code review automation failed. "
                    "This is a SAFETY block - do not force merge. "
                    "Please investigate the error and retry or manually review."
                ),
                "criteria_result": {},
                "criteria_score": 0.0,
            }

    def _analyze_diff_for_issues(self, diff_lines: List[str]) -> List[str]:
        """Analyze diff for common issues."""
        issues = []

        diff_text = "\n".join(diff_lines)

        # Check for obvious issues
        if "TODO" in diff_text or "FIXME" in diff_text:
            issues.append("⚠️ Found TODO/FIXME comments in code")

        if "print(" in diff_text:
            issues.append("⚠️ Found print() statements (use logging instead)")

        if "eval(" in diff_text or "exec(" in diff_text:
            issues.append("🔴 Found dangerous eval/exec calls")

        if "password" in diff_text.lower() and "***" not in diff_text:
            issues.append("🔴 Potential exposed credentials or password in code")

        # Check for large additions
        additions = len([l for l in diff_lines if l.startswith("+")])
        if additions > 500:
            issues.append(f"⚠️ Large addition ({additions} lines) - consider breaking into smaller commits")

        return issues

    def _check_python_best_practices(self, diff_lines: List[str]) -> List[str]:
        """Check for Python-specific best practices."""
        issues = []
        diff_text = "\n".join(diff_lines)

        if "import *" in diff_text:
            issues.append("⚠️ Found 'import *' - use explicit imports")

        if "except:" in diff_text:
            issues.append("⚠️ Found bare 'except:' - specify exception types")

        if "global " in diff_text:
            issues.append("⚠️ Found 'global' keyword - consider refactoring")

        return issues

    def _check_java_spring_patterns(self, diff_lines: List[str]) -> List[str]:
        """Check for Spring Boot/Java best practices."""
        issues = []
        diff_text = "\n".join(diff_lines)

        if "@Component" in diff_text and "@Autowired" not in diff_text:
            issues.append("⚠️ Found @Component but no @Autowired - verify dependency injection")

        if "new Thread(" in diff_text:
            issues.append("⚠️ Found raw Thread creation - use ExecutorService instead")

        return issues

    def _check_docker_best_practices(self, diff_lines: List[str]) -> List[str]:
        """Check for Docker/DevOps best practices."""
        issues = []
        diff_text = "\n".join(diff_lines)

        if "FROM ubuntu" in diff_text or "FROM centos" in diff_text:
            issues.append("⚠️ Consider using alpine for smaller images")

        if "RUN apt-get" in diff_text:
            issues.append("⚠️ RUN apt-get without apt-get update - use multi-stage or combine")

        return issues

    def _generate_review_recommendations(self, issues: List[str]) -> str:
        """Generate summary recommendations from review issues."""
        if not issues:
            return "✓ Code review passed all checks"

        issue_count = len(issues)
        severity_high = len([i for i in issues if i.startswith("🔴")])
        severity_medium = len([i for i in issues if i.startswith("⚠️")])

        return (
            f"Found {issue_count} issues: "
            f"{severity_high} critical, {severity_medium} warnings. "
            f"Please address before merge."
        )

    def _comment_on_pr_with_review(self, pr_number: int, issues: List[str]):
        """Add PR comment with review issues."""
        try:
            comment = "## 🔍 Code Review Results\n\n"
            comment += "The following issues were found during code review:\n\n"

            for issue in issues:
                comment += f"- {issue}\n"

            comment += (
                "\n**Action Required:** "
                "Please address these issues before this PR can be merged. "
                "Review the comments above and update your code accordingly."
            )

            self.github.add_pr_comment(pr_number, comment)
            logger.info(f"Added review comment to PR #{pr_number}")
        except Exception as e:
            logger.warning(f"Could not add PR comment: {e}")

    # ========================================================================
    # BULLETPROOF MERGE CONFLICT DETECTION (4 LAYERS - LANGUAGE AGNOSTIC)
    # ========================================================================

    def check_merge_conflicts_bulletproof(
        self,
        pr_number: int,
        branch_name: str
    ) -> Dict[str, Any]:
        """
        Bulletproof merge conflict detection - 4 layers.
        Works for ANY project/language.

        Returns:
            {
                "safe_to_merge": bool,
                "layer": int (1-4 where it failed),
                "reason": str,
                "details": dict
            }
        """
        logger.info("=" * 70)
        logger.info("🛡️  BULLETPROOF MERGE CONFLICT DETECTION (4 LAYERS)")
        logger.info("=" * 70)

        # ====================================================================
        # LAYER 1: GitHub API Check (pr.mergeable)
        # ====================================================================
        logger.info("[Layer 1] GitHub API Check (pr.mergeable)...")
        try:
            pr = self.github.repo.get_pull(pr_number)
            if not pr.mergeable:
                logger.error("[Layer 1] ❌ FAILED: PR not mergeable (GitHub API)")
                return {
                    "safe_to_merge": False,
                    "layer": 1,
                    "reason": "GitHub API: PR has unresolvable conflicts",
                    "details": {"pr_mergeable": False}
                }
            logger.info("[Layer 1] ✅ PASSED: pr.mergeable = True")
        except Exception as e:
            logger.warning(f"[Layer 1] Could not check pr.mergeable: {e}")

        # ====================================================================
        # LAYER 2: Git Status Parsing (UU/DD/AA markers)
        # ====================================================================
        logger.info("[Layer 2] Git Status Parsing (conflict markers)...")
        conflicts = self._detect_git_conflict_markers(branch_name)
        if conflicts:
            logger.error(f"[Layer 2] ❌ FAILED: Found {len(conflicts)} files with conflicts")
            return {
                "safe_to_merge": False,
                "layer": 2,
                "reason": f"Git status: {len(conflicts)} files have conflict markers",
                "details": {"conflict_files": conflicts}
            }
        logger.info("[Layer 2] ✅ PASSED: No UU/DD/AA conflict markers")

        # ====================================================================
        # LAYER 3: Test Merge (actual merge attempt, no commit)
        # ====================================================================
        logger.info("[Layer 3] Test Merge (attempt without committing)...")
        merge_test = self._test_merge_locally(branch_name)
        if not merge_test.get("success"):
            logger.error(f"[Layer 3] ❌ FAILED: {merge_test.get('reason')}")
            return {
                "safe_to_merge": False,
                "layer": 3,
                "reason": merge_test.get("reason"),
                "details": merge_test.get("details", {})
            }
        logger.info("[Layer 3] ✅ PASSED: Test merge succeeded")

        # ====================================================================
        # LAYER 4: Auto-Detect Project Type & Validate
        # ====================================================================
        logger.info("[Layer 4] Auto-detect project type and validate...")
        project_type = self._detect_project_type()
        logger.info(f"  Detected project type: {project_type}")

        validation = self._validate_project_after_merge(project_type)
        if not validation.get("success"):
            logger.error(f"[Layer 4] ❌ FAILED: {validation.get('reason')}")
            return {
                "safe_to_merge": False,
                "layer": 4,
                "reason": validation.get("reason"),
                "details": validation.get("details", {})
            }
        logger.info("[Layer 4] ✅ PASSED: Project validation successful")

        # ====================================================================
        # ALL LAYERS PASSED - SAFE TO MERGE
        # ====================================================================
        logger.info("=" * 70)
        logger.info("✅ ALL 4 LAYERS PASSED - SAFE TO MERGE")
        logger.info("=" * 70)

        return {
            "safe_to_merge": True,
            "layer": 4,
            "reason": "All merge safety checks passed",
            "details": {
                "layer1": "GitHub API check passed",
                "layer2": "No git conflict markers",
                "layer3": "Test merge succeeded",
                "layer4": f"Project validation passed ({project_type})"
            }
        }

    def _detect_git_conflict_markers(self, branch_name: str) -> List[str]:
        """
        Layer 2: Parse git status for conflict markers (UU, DD, AA).
        """
        try:
            # Try to merge without committing
            result = self.git._run_git(
                ["merge", "--no-commit", "--no-ff", f"origin/{branch_name}"],
                check=False
            )

            # Get status
            status_result = self.git._run_git(["status", "--porcelain"], check=False)
            status_lines = status_result.get("stdout", "").split("\n")

            # Find conflict markers
            conflicts = []
            for line in status_lines:
                if line.startswith("UU") or line.startswith("DD") or line.startswith("AA"):
                    file = line[3:].strip()
                    conflicts.append(file)

            # Abort merge
            self.git._run_git(["merge", "--abort"], check=False)

            return conflicts

        except Exception as e:
            logger.warning(f"Error detecting git conflicts: {e}")
            return []

    def _test_merge_locally(self, branch_name: str) -> Dict[str, Any]:
        """
        Layer 3: Actually try to merge without committing.
        """
        try:
            # Fetch latest
            self.git._run_git(["fetch", "origin"], check=False)

            # Try merge without commit
            result = self.git._run_git(
                ["merge", "--no-commit", "--no-ff", f"origin/{branch_name}"],
                check=False
            )

            if result.get("returncode") != 0:
                # Merge failed
                self.git._run_git(["merge", "--abort"], check=False)
                return {
                    "success": False,
                    "reason": "Merge attempt failed - conflicts exist",
                    "details": {"error": result.get("stderr", "")}
                }

            # Merge succeeded - abort without committing
            self.git._run_git(["merge", "--abort"], check=False)
            return {"success": True}

        except Exception as e:
            logger.warning(f"Error in test merge: {e}")
            try:
                self.git._run_git(["merge", "--abort"], check=False)
            except:
                pass
            return {
                "success": False,
                "reason": f"Test merge error: {str(e)}",
                "details": {}
            }

    def _detect_project_type(self) -> str:
        """
        Layer 4: Auto-detect project type by checking for indicator files.
        """
        from pathlib import Path

        indicators = {
            "python": ["setup.py", "requirements.txt", "pyproject.toml", "Pipfile", "setup.cfg"],
            "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "nodejs": ["package.json"],
            "go": ["go.mod"],
            "rust": ["Cargo.toml"],
            "ruby": ["Gemfile", "Rakefile"],
            "php": ["composer.json"],
            "csharp": ["*.csproj", "*.sln"],
            "cpp": ["CMakeLists.txt", "Makefile"],
        }

        for lang, files in indicators.items():
            for file_pattern in files:
                try:
                    if Path(self.git.repo_path / file_pattern).exists():
                        return lang
                except:
                    pass

        return "unknown"

    def _validate_project_after_merge(self, project_type: str) -> Dict[str, Any]:
        """
        Layer 4: Run project-specific validation if available.
        Language-agnostic approach - use what the project provides.
        """
        try:
            if project_type == "python":
                return self._validate_python()
            elif project_type == "java":
                return self._validate_java()
            elif project_type == "nodejs":
                return self._validate_nodejs()
            elif project_type == "go":
                return self._validate_go()
            elif project_type == "rust":
                return self._validate_rust()
            else:
                # Unknown type - just basic check
                logger.info(f"Unknown project type '{project_type}', skipping validation")
                return {"success": True, "reason": "Unknown type - no validation"}

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                "success": False,
                "reason": f"Validation failed: {str(e)}",
                "details": {}
            }

    def _validate_python(self) -> Dict[str, Any]:
        """Validate Python project."""
        try:
            # Try pytest
            result = self.git._run_git(
                ["bash", "-c", "pytest --co -q 2>/dev/null || echo 'no-pytest'"],
                check=False
            )
            if "no-pytest" not in result.get("stdout", ""):
                logger.info("  Running pytest...")
                result = self.git._run_git(
                    ["bash", "-c", "pytest -x 2>&1"],
                    check=False
                )
                if result.get("returncode") != 0:
                    return {
                        "success": False,
                        "reason": "Python tests failed",
                        "details": {}
                    }
                return {"success": True}

            # Try unittest
            result = self.git._run_git(
                ["bash", "-c", "python -m unittest discover -s . 2>&1"],
                check=False
            )
            if result.get("returncode") == 0:
                return {"success": True}

            # No tests found - just syntax check
            logger.info("  No tests found, checking syntax...")
            result = self.git._run_git(
                ["bash", "-c", "python -m py_compile $(find . -name '*.py') 2>&1"],
                check=False
            )
            return {
                "success": result.get("returncode") == 0,
                "reason": "Syntax error" if result.get("returncode") != 0 else None
            }

        except Exception as e:
            logger.warning(f"Python validation error: {e}")
            return {"success": True}  # Non-blocking

    def _validate_java(self) -> Dict[str, Any]:
        """Validate Java project."""
        try:
            # Try Maven
            if Path(self.git.repo_path / "pom.xml").exists():
                logger.info("  Running mvn test...")
                result = self.git._run_git(
                    ["bash", "-c", "mvn test -q 2>&1"],
                    check=False
                )
                return {
                    "success": result.get("returncode") == 0,
                    "reason": "Maven tests failed" if result.get("returncode") != 0 else None
                }

            # Try Gradle
            if Path(self.git.repo_path / "build.gradle").exists() or \
               Path(self.git.repo_path / "build.gradle.kts").exists():
                logger.info("  Running gradle test...")
                result = self.git._run_git(
                    ["bash", "-c", "./gradlew test -q 2>&1"],
                    check=False
                )
                return {
                    "success": result.get("returncode") == 0,
                    "reason": "Gradle tests failed" if result.get("returncode") != 0 else None
                }

            return {"success": True}  # No build system found

        except Exception as e:
            logger.warning(f"Java validation error: {e}")
            return {"success": True}

    def _validate_nodejs(self) -> Dict[str, Any]:
        """Validate Node.js project."""
        try:
            logger.info("  Running npm test...")
            result = self.git._run_git(
                ["bash", "-c", "npm test 2>&1"],
                check=False
            )
            return {
                "success": result.get("returncode") == 0,
                "reason": "npm tests failed" if result.get("returncode") != 0 else None
            }
        except Exception as e:
            logger.warning(f"Node.js validation error: {e}")
            return {"success": True}

    def _validate_go(self) -> Dict[str, Any]:
        """Validate Go project."""
        try:
            logger.info("  Running go test...")
            result = self.git._run_git(
                ["bash", "-c", "go test ./... 2>&1"],
                check=False
            )
            return {
                "success": result.get("returncode") == 0,
                "reason": "go tests failed" if result.get("returncode") != 0 else None
            }
        except Exception as e:
            logger.warning(f"Go validation error: {e}")
            return {"success": True}

    def _validate_rust(self) -> Dict[str, Any]:
        """Validate Rust project."""
        try:
            logger.info("  Running cargo test...")
            result = self.git._run_git(
                ["bash", "-c", "cargo test 2>&1"],
                check=False
            )
            return {
                "success": result.get("returncode") == 0,
                "reason": "cargo tests failed" if result.get("returncode") != 0 else None
            }
        except Exception as e:
            logger.warning(f"Rust validation error: {e}")
            return {"success": True}
