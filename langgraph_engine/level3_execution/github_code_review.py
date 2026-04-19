"""
GitHub Code Review Functions

Standalone functions extracted from Level3GitHubWorkflow for code review
of pull requests. Includes diff analysis, skill-specific pattern checks,
LLM-powered simplify review, and PR comment generation.

All functions take explicit parameters instead of relying on self, making
them usable outside the class context.
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger

# ============================================================================
# DIFF ANALYSIS
# ============================================================================


def analyze_diff_for_issues(diff_text: str, diff_lines: List[str]) -> List[str]:
    """Analyze diff for common issues.

    Args:
        diff_text:  Pre-joined diff string.
        diff_lines: Raw diff lines list (needed for prefix-based addition counting).

    Returns:
        List of warning strings describing found issues.
    """
    issues: List[str] = []

    if "TODO" in diff_text or "FIXME" in diff_text:
        issues.append("Warning: Found TODO/FIXME comments in code")

    if "print(" in diff_text:
        issues.append("Warning: Found print() statements (use logging instead)")

    if "eval(" in diff_text or "exec(" in diff_text:
        issues.append("Warning: Found dangerous eval/exec calls")

    if "password" in diff_text.lower() and "***" not in diff_text:
        issues.append("Warning: Potential exposed credentials or password in code")

    additions = len([line for line in diff_lines if line.startswith("+")])
    if additions > 500:
        issues.append(f"Warning: Large addition ({additions} lines) - consider breaking into smaller commits")

    return issues


def check_python_best_practices(diff_text: str) -> List[str]:
    """Check for Python-specific best practices.

    Args:
        diff_text: Pre-joined diff string.

    Returns:
        List of warning strings for Python violations found.
    """
    issues: List[str] = []

    if "import *" in diff_text:
        issues.append("Warning: Found 'import *' - use explicit imports")

    if "except:" in diff_text:
        issues.append("Warning: Found bare 'except:' - specify exception types")

    if "global " in diff_text:
        issues.append("Warning: Found 'global' keyword - consider refactoring")

    return issues


def check_java_spring_patterns(diff_text: str) -> List[str]:
    """Check for Spring Boot/Java best practices.

    Args:
        diff_text: Pre-joined diff string.

    Returns:
        List of warning strings for Java/Spring violations found.
    """
    issues: List[str] = []

    if "@Component" in diff_text and "@Autowired" not in diff_text:
        issues.append("Warning: Found @Component but no @Autowired - verify dependency injection")

    if "new Thread(" in diff_text:
        issues.append("Warning: Found raw Thread creation - use ExecutorService instead")

    return issues


def check_docker_best_practices(diff_text: str) -> List[str]:
    """Check for Docker/DevOps best practices.

    Args:
        diff_text: Pre-joined diff string.

    Returns:
        List of warning strings for Docker violations found.
    """
    issues: List[str] = []

    if "FROM ubuntu" in diff_text or "FROM centos" in diff_text:
        issues.append("Warning: Consider using alpine for smaller images")

    if "RUN apt-get" in diff_text:
        issues.append("Warning: RUN apt-get without apt-get update - use multi-stage or combine")

    return issues


# ============================================================================
# LLM-POWERED SIMPLIFY REVIEW
# ============================================================================


def _format_simplify_issues(items: List[Any]) -> List[str]:
    """Prefix items with [Simplify] marker for PR review identification."""
    return [f"[Simplify] {str(item)}" for item in items if item]


def _parse_simplify_response(response: str) -> List[str]:
    """Parse LLM simplify review response into list of issue strings.

    Args:
        response: Raw LLM response text, expected to contain a JSON array.

    Returns:
        List of formatted issue strings.
    """
    text = response.strip()
    fmt = _format_simplify_issues

    # Try direct JSON parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return fmt(result)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON array from markdown/text wrapper
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, list):
                return fmt(result)
        except json.JSONDecodeError:
            pass

    # Fallback: treat non-empty lines as issues (LLM returned plain text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if 1 <= len(lines) <= 10:
        return fmt(lines)

    return []


def run_simplify_review(diff_text: str) -> List[str]:
    """Run LLM-powered simplify review on PR diff for reuse, quality, efficiency.

    Uses llm_call (claude_cli / anthropic provider chain) to analyze the diff
    similar to Claude Code's /simplify command. Returns actionable issues.
    Non-blocking: returns empty list on failure.

    Args:
        diff_text: Full diff text for the PR.

    Returns:
        List of issue strings found by the LLM review, or empty list on failure.
    """
    if not diff_text or len(diff_text) < 50:
        return []

    try:
        from ..llm_call import llm_call
    except ImportError:
        logger.debug("[Simplify] llm_call not available, skipping LLM review")
        return []

    # Line-aware truncation to preserve diff structure
    diff_lines = diff_text.split("\n")
    truncated = "\n".join(diff_lines[:200]) if len(diff_lines) > 200 else diff_text

    prompt = (
        "You are a code reviewer. Analyze this git diff for 3 categories:\n"
        "1. CODE REUSE: duplicated logic, existing utilities that could replace new code\n"
        "2. CODE QUALITY: redundant state, copy-paste, leaky abstractions, bare except\n"
        "3. EFFICIENCY: unnecessary work, missed concurrency, N+1 patterns, memory leaks\n\n"
        "Return ONLY a JSON array of issue strings. Each issue should be a single line.\n"
        "If the code is clean, return an empty array: []\n"
        "Do NOT include explanations outside the JSON array.\n\n"
        f"DIFF:\n```\n{truncated}\n```\n\n"
        "Response (JSON array only):"
    )

    logger.info("[Simplify] Running LLM-powered code review...")

    response = llm_call(prompt, model="balanced", temperature=0.1, timeout=30)
    if not response:
        logger.warning("[Simplify] LLM review returned no response, skipping")
        return []

    issues = _parse_simplify_response(response)
    if issues:
        logger.info(f"[Simplify] LLM review found {len(issues)} issues")
    else:
        logger.info("[Simplify] LLM review: code is clean")

    return issues


# ============================================================================
# REVIEW RECOMMENDATIONS AND PR COMMENT
# ============================================================================


def generate_review_recommendations(issues: List[str]) -> str:
    """Generate summary recommendations from review issues.

    Args:
        issues: List of issue strings from code review.

    Returns:
        Human-readable summary string.
    """
    if not issues:
        return "Code review passed all checks"

    issue_count = len(issues)
    severity_high = len([i for i in issues if i.startswith("\U0001f534")])
    severity_medium = len([i for i in issues if i.startswith("\u26a0\ufe0f")])

    return (
        f"Found {issue_count} issues: "
        f"{severity_high} critical, {severity_medium} warnings. "
        f"Please address before merge."
    )


def comment_on_pr_with_review(
    github_router: Any,
    pr_number: int,
    issues: List[str],
) -> None:
    """Add PR comment with review issues.

    Args:
        github_router: GitHubOperationRouter instance (has add_pr_comment method).
        pr_number:     GitHub PR number to comment on.
        issues:        List of issue strings to include in the comment.
    """
    try:
        comment = "## Code Review Results\n\n"
        comment += "The following issues were found during code review:/n/n"

        for issue in issues:
            comment += f"- {issue}\n"

        comment += (
            "\n**Action Required:** "
            "Please address these issues before this PR can be merged. "
            "Review the comments above and update your code accordingly."
        )

        github_router.add_pr_comment(pr_number, comment)
        logger.info(f"Added review comment to PR #{pr_number}")
    except Exception as e:
        logger.warning(f"Could not add PR comment: {e}")


# ============================================================================
# MAIN REVIEW ORCHESTRATOR
# ============================================================================


def run_code_review(
    pr_number: int,
    branch_name: str,
    selected_skills: List[str],
    selected_agents: List[str],
    git_ops: Any,
    project_root: Optional[str] = None,
    files_changed: Optional[List[str]] = None,
    pr_body: str = "",
) -> Dict[str, Any]:
    """Run code review on PR using selected skills/agents AND ReviewCriteria checklist.

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
        pr_number:       GitHub PR number.
        branch_name:     Source branch being reviewed.
        selected_skills: Skills selected in Step 5.
        selected_agents: Agents selected in Step 5.
        git_ops:         GitOperations instance for diff and repo access.
        project_root:    Optional project root path for ReviewCriteria.
        files_changed:   Optional list of files changed in PR (for ReviewCriteria).
        pr_body:         PR description text (for ReviewCriteria DC003 check).

    Returns:
        {
            "passed": bool,
            "issues": List[str],
            "recommendations": str,
            "criteria_result": Dict,
            "criteria_score": float,
        }
    """
    logger.info(
        f"Starting code review for PR #{pr_number} with "
        f"{len(selected_skills)} skills and {len(selected_agents)} agents"
    )

    try:
        diff_lines = git_ops.get_pr_diff(branch_name, "main")
        diff_text = "\n".join(diff_lines)

        issues: List[str] = analyze_diff_for_issues(diff_text, diff_lines)

        if "python-backend-engineer" in selected_skills or "python-backend-engineer" in selected_agents:
            issues.extend(check_python_best_practices(diff_text))

        if "spring-boot-microservices" in selected_skills or "spring-boot-microservices" in selected_agents:
            issues.extend(check_java_spring_patterns(diff_text))

        if "docker" in selected_skills or "devops-engineer" in selected_agents:
            issues.extend(check_docker_best_practices(diff_text))

        simplify_issues = run_simplify_review(diff_text)
        if simplify_issues:
            issues.extend(simplify_issues)

        # ReviewCriteria structured evaluation
        criteria_result: Dict[str, Any] = {}
        criteria_score: float = 1.0

        try:
            from .review_criteria import ReviewCriteria

            review_criteria = ReviewCriteria(project_root=project_root)
        except Exception as _e:
            logger.warning(f"[CodeReview] ReviewCriteria unavailable: {_e}")
            review_criteria = None

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

                for issue in eval_result.issues:
                    if issue.get("severity") == "blocking":
                        msg = f"[{issue['rule_id']}] {issue['message']}" + (
                            f" in {issue['file_path']}" if issue.get("file_path") else ""
                        )
                        issues.append(msg)

                if not eval_result.passed:
                    logger.warning("[CodeReview] ReviewCriteria FAILED - merge will be blocked")

            except Exception as criteria_err:
                logger.warning(f"[CodeReview] ReviewCriteria evaluation error (non-fatal): {criteria_err}")

        logger.info(f"Code review found {len(issues)} issues")

        passed = len(issues) == 0
        return {
            "passed": passed,
            "issues": issues,
            "recommendations": generate_review_recommendations(issues),
            "criteria_result": criteria_result,
            "criteria_score": criteria_score,
        }

    except Exception as e:
        logger.error(f"Code review analysis failed (FAIL-SAFE): {e}")
        logger.error("Blocking merge to prevent broken code - manual review required")
        return {
            "passed": False,
            "issues": [
                "CRITICAL: Code review process crashed",
                f"Error: {str(e)}",
                "Action: Merge blocked for safety. Manual review required.",
            ],
            "recommendations": (
                "Code review automation failed. "
                "This is a SAFETY block - do not force merge. "
                "Please investigate the error and retry or manually review."
            ),
            "criteria_result": {},
            "criteria_score": 0.0,
        }
