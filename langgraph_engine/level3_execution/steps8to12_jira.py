"""
Jira Workflow Integration for Level 3 Pipeline Steps 8-12.

Runs alongside GitHub workflow when ENABLE_JIRA=1.
Creates Jira issues, links PRs, transitions workflow states.

Version: 1.4.1
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Label to Jira issue type mapping
# ---------------------------------------------------------------------------

LABEL_TO_JIRA_TYPE = {
    "bug": "Bug",
    "bugfix": "Bug",
    "feature": "Story",
    "enhancement": "Task",
    "test": "Task",
    "documentation": "Task",
    "task": "Task",
    "refactor": "Task",
}

# Transition name candidates (tried in order, case-insensitive)
IN_REVIEW_TRANSITIONS = ["In Review", "In Progress", "Start Review", "Code Review"]
DONE_TRANSITIONS = ["Done", "Closed", "Resolved", "Complete"]
IN_PROGRESS_TRANSITIONS = ["In Progress", "Start Progress", "Begin Work", "Working"]


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _is_jira_enabled() -> bool:
    """Check if Jira integration is enabled via environment."""
    return os.environ.get("ENABLE_JIRA", "0") == "1"


def _get_jira_project() -> str:
    """Get default Jira project key."""
    return os.environ.get("JIRA_DEFAULT_PROJECT", "")


def _is_jira_configured() -> bool:
    """Return True when all required Jira env vars are present."""
    return all(os.environ.get(k) for k in ("JIRA_URL", "JIRA_USER", "JIRA_API_TOKEN"))


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class Level3JiraWorkflow:
    """Jira workflow integration for pipeline Steps 8, 9, 11, 12.

    Mirrors Level3GitHubWorkflow but creates/manages Jira issues.
    Only active when ENABLE_JIRA=1 and JIRA_URL is configured.
    """

    def __init__(self) -> None:
        """Initialize with lazy import of Jira MCP tools."""
        self._jira_tools = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_tools(self):
        """Lazy load Jira MCP server tools.

        Returns the jira_mcp_server module on success, or None when the
        module is not importable (e.g. missing optional dependencies).
        """
        if self._jira_tools is None:
            try:
                src_mcp_path = str(Path(__file__).resolve().parent.parent.parent / "src" / "mcp")
                if src_mcp_path not in sys.path:
                    sys.path.insert(0, src_mcp_path)
                import jira_mcp_server as jira  # type: ignore[import]

                self._jira_tools = jira
                logger.debug("[JiraWorkflow] Jira MCP server loaded successfully")
            except ImportError as exc:
                logger.warning("[JiraWorkflow] Jira MCP server not available: %s", exc)
                self._jira_tools = None
        return self._jira_tools

    def _map_label_to_issue_type(self, label: str) -> str:
        """Map a GitHub-style label to a Jira issue type string."""
        return LABEL_TO_JIRA_TYPE.get(label.lower(), "Task")

    def _try_transition(
        self,
        issue_key: str,
        transition_candidates: List[str],
        jira,
    ) -> Dict[str, Any]:
        """Attempt workflow transitions by trying each candidate name in order.

        Args:
            issue_key: Jira issue key (e.g. PROJ-123).
            transition_candidates: Ordered list of transition names to try.
            jira: Loaded jira_mcp_server module.

        Returns:
            Dict with transitioned (bool), transition_name (str), error (str).
        """
        # Fetch available transitions first to avoid repeated 404 calls
        try:
            transitions_resp = jira.jira_get_transitions(issue_key=issue_key)
            available = {t.get("name", "").lower(): t.get("name", "") for t in transitions_resp.get("transitions", [])}
        except Exception as exc:
            logger.warning("[JiraWorkflow] Could not fetch transitions for %s: %s", issue_key, exc)
            available = {}

        for candidate in transition_candidates:
            canonical = available.get(candidate.lower())
            if canonical is None:
                continue
            try:
                jira.jira_transition_issue(
                    issue_key=issue_key,
                    transition_name=canonical,
                )
                logger.info("[JiraWorkflow] Transitioned %s via '%s'", issue_key, canonical)
                return {"transitioned": True, "transition_name": canonical, "error": ""}
            except Exception as exc:
                logger.warning("[JiraWorkflow] Transition '%s' failed for %s: %s", canonical, issue_key, exc)

        names_tried = ", ".join(transition_candidates)
        logger.warning(
            "[JiraWorkflow] No matching transition found for %s " "(tried: %s; available: %s)",
            issue_key,
            names_tried,
            ", ".join(available.values()) or "none",
        )
        return {
            "transitioned": False,
            "transition_name": "",
            "error": "No matching transition found. Tried: " + names_tried,
        }

    # ------------------------------------------------------------------
    # Step 8: Create Jira issue
    # ------------------------------------------------------------------

    def step8_create_jira_issue(
        self,
        title: str,
        description: str,
        label: str,
        github_issue_url: str = "",
        github_issue_number: int = 0,
    ) -> Dict[str, Any]:
        """Create Jira issue and link to GitHub issue.

        Called after GitHub issue is created in Step 8.

        Args:
            title: Issue title (same as GitHub issue).
            description: Issue description/body.
            label: Issue type (bug/feature/enhancement/task).
            github_issue_url: URL of GitHub issue for cross-linking.
            github_issue_number: GitHub issue number for reference.

        Returns:
            Dict with jira_issue_key, jira_issue_url, success, etc.
        """
        logger.info("[JiraWorkflow] Step 8 - Create Jira issue: %s", title)

        if not _is_jira_enabled():
            logger.debug("[JiraWorkflow] Jira integration disabled (ENABLE_JIRA != 1)")
            return {"success": False, "reason": "Jira integration not enabled"}

        if not _is_jira_configured():
            logger.warning("[JiraWorkflow] Jira env vars missing; skipping issue creation")
            return {"success": False, "reason": "Jira environment not configured"}

        project_key = _get_jira_project()
        if not project_key:
            logger.warning("[JiraWorkflow] JIRA_DEFAULT_PROJECT not set; skipping")
            return {"success": False, "reason": "JIRA_DEFAULT_PROJECT not set"}

        jira = self._get_tools()
        if jira is None:
            return {"success": False, "reason": "Jira MCP server unavailable"}

        step_start = time.time()

        try:
            issue_type = self._map_label_to_issue_type(label)

            result = jira.jira_create_issue(
                project_key=project_key,
                summary=title,
                issue_type=issue_type,
                description=description,
            )

            jira_key = result.get("issue_key", "")
            jira_url = result.get("issue_url", "")

            logger.info("[JiraWorkflow] Created %s: %s", jira_key, jira_url)

            # Add cross-link comment if GitHub issue info is available
            if github_issue_url and jira_key:
                comment_text = "Linked to GitHub Issue: #" + str(github_issue_number) + " - " + github_issue_url
                try:
                    jira.jira_add_comment(issue_key=jira_key, body=comment_text)
                    logger.debug("[JiraWorkflow] Added GitHub cross-link comment to %s", jira_key)
                except Exception as comment_exc:
                    logger.warning("[JiraWorkflow] Could not add cross-link comment to %s: %s", jira_key, comment_exc)

            return {
                "success": True,
                "jira_issue_key": jira_key,
                "jira_issue_url": jira_url,
                "jira_issue_id": result.get("issue_id", ""),
                "issue_type": issue_type,
                "project_key": project_key,
                "execution_time_ms": (time.time() - step_start) * 1000,
            }

        except Exception as exc:
            logger.error("[JiraWorkflow] Step 8 failed: %s", exc)
            return {
                "success": False,
                "reason": str(exc),
                "execution_time_ms": (time.time() - step_start) * 1000,
            }

    # ------------------------------------------------------------------
    # Step 9: Generate Jira-keyed branch name
    # ------------------------------------------------------------------

    def step9_get_branch_name(
        self,
        jira_issue_key: str,
        label: str,
    ) -> str:
        """Generate branch name from Jira issue key.

        When Jira is enabled, branch format is: {label}/{JIRA_KEY}
        e.g. feature/PROJ-123 instead of feature/issue-42

        Args:
            jira_issue_key: Jira issue key (e.g. PROJ-123).
            label: Issue type used as branch prefix.

        Returns:
            Branch name string, or empty string when Jira is disabled or
            jira_issue_key is empty.
        """
        if not _is_jira_enabled():
            logger.debug("[JiraWorkflow] Step 9 - Jira disabled; no Jira branch name")
            return ""

        if not jira_issue_key:
            logger.debug("[JiraWorkflow] Step 9 - No jira_issue_key; skipping branch override")
            return ""

        prefix = label.lower() if label else "feature"
        branch_name = prefix + "/" + jira_issue_key
        logger.info("[JiraWorkflow] Step 9 - Jira branch name: %s", branch_name)
        return branch_name

    # ------------------------------------------------------------------
    # Step 10: Transition Jira to In Progress
    # ------------------------------------------------------------------

    def step10_start_progress(
        self,
        jira_issue_key: str,
    ) -> Dict[str, Any]:
        """Transition Jira issue to In Progress when implementation starts.

        Called at the beginning of Step 10 (Implementation).

        Args:
            jira_issue_key: Jira issue key.

        Returns:
            Dict with transitioned (bool), success (bool).
        """
        logger.info("[JiraWorkflow] Step 10 - Start progress on %s", jira_issue_key)

        if not _is_jira_enabled():
            return {"success": False, "reason": "Jira integration not enabled"}

        if not jira_issue_key:
            return {"success": False, "reason": "No jira_issue_key provided"}

        jira = self._get_tools()
        if jira is None:
            return {"success": False, "reason": "Jira MCP server unavailable"}

        step_start = time.time()

        # Transition to "In Progress"
        transition_result = self._try_transition(jira_issue_key, IN_PROGRESS_TRANSITIONS, jira)

        # Add comment
        try:
            jira.jira_add_comment(
                issue_key=jira_issue_key,
                body="Implementation started.",
            )
        except Exception as exc:
            logger.warning("[JiraWorkflow] Could not add progress comment to %s: %s", jira_issue_key, exc)

        return {
            "success": transition_result.get("transitioned", False),
            "transitioned": transition_result.get("transitioned", False),
            "transition_name": transition_result.get("transition_name", ""),
            "jira_issue_key": jira_issue_key,
            "execution_time_ms": (time.time() - step_start) * 1000,
        }

    # ------------------------------------------------------------------
    # Step 11: Link PR and transition to In Review
    # ------------------------------------------------------------------

    def step11_link_pr_and_transition(
        self,
        jira_issue_key: str,
        pr_url: str,
        pr_number: int,
        transition_name: str = "In Review",
    ) -> Dict[str, Any]:
        """Link GitHub PR to Jira issue and transition to In Review.

        Called during Step 11 after PR is created.

        Args:
            jira_issue_key: Jira issue key.
            pr_url: GitHub PR URL for remote link.
            pr_number: PR number for link title.
            transition_name: Preferred Jira workflow transition name.

        Returns:
            Dict with linked (bool), transitioned (bool), success (bool), etc.
        """
        logger.info("[JiraWorkflow] Step 11 - Link PR #%d to %s", pr_number, jira_issue_key)

        if not _is_jira_enabled():
            logger.debug("[JiraWorkflow] Jira integration disabled")
            return {"success": False, "reason": "Jira integration not enabled"}

        if not jira_issue_key:
            logger.warning("[JiraWorkflow] No jira_issue_key provided; skipping step 11")
            return {"success": False, "reason": "No jira_issue_key provided"}

        jira = self._get_tools()
        if jira is None:
            return {"success": False, "reason": "Jira MCP server unavailable"}

        step_start = time.time()
        linked = False
        link_error = ""
        transition_result: Dict[str, Any] = {}

        # 1. Create remote link from Jira issue to GitHub PR
        try:
            jira.jira_link_pr(
                issue_key=jira_issue_key,
                pr_url=pr_url,
                pr_number=pr_number,
            )
            linked = True
            logger.info("[JiraWorkflow] PR #%d linked to %s", pr_number, jira_issue_key)
        except Exception as exc:
            link_error = str(exc)
            logger.warning("[JiraWorkflow] Could not link PR to %s: %s", jira_issue_key, exc)

        # 2. Transition issue to "In Review" (try candidates)
        candidates = [transition_name] + [c for c in IN_REVIEW_TRANSITIONS if c != transition_name]
        transition_result = self._try_transition(jira_issue_key, candidates, jira)

        # 3. Add PR comment
        try:
            comment = "Pull Request created: PR #" + str(pr_number) + " - " + pr_url
            jira.jira_add_comment(issue_key=jira_issue_key, body=comment)
        except Exception as comment_exc:
            logger.warning("[JiraWorkflow] Could not add PR comment to %s: %s", jira_issue_key, comment_exc)

        success = linked or transition_result.get("transitioned", False)

        return {
            "success": success,
            "linked": linked,
            "link_error": link_error,
            "transitioned": transition_result.get("transitioned", False),
            "transition_name": transition_result.get("transition_name", ""),
            "transition_error": transition_result.get("error", ""),
            "jira_issue_key": jira_issue_key,
            "execution_time_ms": (time.time() - step_start) * 1000,
        }

    # ------------------------------------------------------------------
    # Step 11 (post-merge): Update Jira with merge details
    # ------------------------------------------------------------------

    def step11_post_merge_update(
        self,
        jira_issue_key: str,
        pr_number: int,
        pr_url: str,
        branch_name: str = "",
    ) -> Dict[str, Any]:
        """Update Jira after PR is merged.

        Called in Step 11 after a successful merge.

        Args:
            jira_issue_key: Jira issue key.
            pr_number: Merged PR number.
            pr_url: PR URL.
            branch_name: Branch that was merged.

        Returns:
            Dict with success (bool).
        """
        logger.info("[JiraWorkflow] Step 11 - Post-merge update for %s (PR #%d)", jira_issue_key, pr_number)

        if not _is_jira_enabled() or not jira_issue_key:
            return {"success": False, "reason": "Jira disabled or no key"}

        jira = self._get_tools()
        if jira is None:
            return {"success": False, "reason": "Jira MCP server unavailable"}

        try:
            comment_parts = ["PR #{} merged successfully.".format(pr_number)]
            if branch_name:
                comment_parts.append("Branch: {}".format(branch_name))
            if pr_url:
                comment_parts.append("URL: {}".format(pr_url))
            jira.jira_add_comment(
                issue_key=jira_issue_key,
                body="\n".join(comment_parts),
            )
            return {"success": True, "jira_issue_key": jira_issue_key}
        except Exception as exc:
            logger.warning("[JiraWorkflow] Post-merge comment failed for %s: %s", jira_issue_key, exc)
            return {"success": False, "reason": str(exc)}

    # ------------------------------------------------------------------
    # Step 12: Close Jira issue with implementation summary
    # ------------------------------------------------------------------

    def step12_close_jira_issue(
        self,
        jira_issue_key: str,
        pr_number: int = 0,
        files_modified: Optional[List[str]] = None,
        approach_taken: str = "",
    ) -> Dict[str, Any]:
        """Close Jira issue with implementation summary.

        Called during Step 12 after GitHub issue is closed.

        Args:
            jira_issue_key: Jira issue key to close.
            pr_number: PR that resolved the issue.
            files_modified: List of modified files.
            approach_taken: Implementation approach summary.

        Returns:
            Dict with closed (bool), transitioned (bool), success (bool), etc.
        """
        logger.info("[JiraWorkflow] Step 12 - Close Jira issue %s", jira_issue_key)

        if not _is_jira_enabled():
            logger.debug("[JiraWorkflow] Jira integration disabled")
            return {"success": False, "reason": "Jira integration not enabled"}

        if not jira_issue_key:
            logger.warning("[JiraWorkflow] No jira_issue_key provided; skipping step 12")
            return {"success": False, "reason": "No jira_issue_key provided"}

        jira = self._get_tools()
        if jira is None:
            return {"success": False, "reason": "Jira MCP server unavailable"}

        step_start = time.time()

        # 1. Build closing comment with implementation details
        comment_parts = ["Implementation complete."]

        if pr_number:
            comment_parts.append("Resolved by PR #" + str(pr_number) + ".")

        if approach_taken:
            comment_parts.append("\nApproach:/n" + approach_taken)

        if files_modified:
            file_list = "\n".join("- " + f for f in files_modified[:20])
            if len(files_modified) > 20:
                file_list += "\n- ... and " + str(len(files_modified) - 20) + " more"
            comment_parts.append("\nFiles modified:/n" + file_list)

        closing_comment = " ".join(comment_parts)

        comment_added = False
        try:
            jira.jira_add_comment(issue_key=jira_issue_key, body=closing_comment)
            comment_added = True
            logger.debug("[JiraWorkflow] Closing comment added to %s", jira_issue_key)
        except Exception as exc:
            logger.warning("[JiraWorkflow] Could not add closing comment to %s: %s", jira_issue_key, exc)

        # 2. Transition to "Done" (try common names)
        transition_result = self._try_transition(jira_issue_key, DONE_TRANSITIONS, jira)

        success = comment_added or transition_result.get("transitioned", False)

        return {
            "success": success,
            "closed": transition_result.get("transitioned", False),
            "transitioned": transition_result.get("transitioned", False),
            "transition_name": transition_result.get("transition_name", ""),
            "transition_error": transition_result.get("error", ""),
            "comment_added": comment_added,
            "jira_issue_key": jira_issue_key,
            "execution_time_ms": (time.time() - step_start) * 1000,
        }
