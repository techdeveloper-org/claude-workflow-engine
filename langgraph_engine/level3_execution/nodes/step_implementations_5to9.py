"""Step 8/9 implementation functions.

Facade module: wraps Level3GitHubWorkflow (Step 8 issue creation, Step 9
branch creation) behind thin, state-dict-first functions that the step
wrappers in step_wrappers_5to9.py invoke.

Restored 2026-04-14 during v1.16.x restoration cycle (issue #213),
adapted for:
  - v1.11 physical layout (nodes/ package)
  - loguru-with-stdlib-fallback logger import pattern (matches sibling nodes)
  - Relative import paths corrected for nodes/ subpackage depth

Design patterns:
  - Facade: thin wrapper over Level3GitHubWorkflow
  - Null Object: returns well-formed ERROR-status dict on failure (never None, never raises)
  - Defensive Import: every external import wrapped in try/except

Windows-safe: ASCII only.
"""

import os
import re
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
    from ..steps8to12_github import Level3GitHubWorkflow
except ImportError:  # pragma: no cover
    Level3GitHubWorkflow = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate_issue_title(user_message: str, task_type: str, complexity: int) -> str:
    """Generate a short, descriptive GitHub issue title.

    Tries llm_call (fast model); falls back to a cleaned user message.
    """
    if not user_message:
        return "[%s] Task (complexity %d/10)" % (task_type, complexity)

    prompt = (
        "Generate a short GitHub issue title (max 70 chars) for this task. "
        "Return ONLY the title text, no quotes, no prefix, no explanation.\n\n"
        "Task type: %s\n"
        "User request: %s\n\n"
        "Title:" % (task_type, user_message[:300])
    )

    try:
        from langgraph_engine.llm_call import llm_call

        llm_title = llm_call(prompt, model="fast", temperature=0.3, timeout=30)
        if llm_title:
            llm_title = llm_title.strip().strip('"').strip("'").split("\n")[0].strip()
            if llm_title and len(llm_title) > 5:
                return llm_title[:80]
    except Exception:
        pass

    clean = user_message.strip().split("\n")[0][:70]
    if clean and clean[0].islower():
        clean = clean[0].upper() + clean[1:]
    return clean


def _slugify_title(title: str, max_len: int = 50) -> str:
    """Convert a title to a branch-name-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len].rstrip("-")


# ---------------------------------------------------------------------------
# Step 8: GitHub Issue Creation
# ---------------------------------------------------------------------------


def step8_github_issue_creation(state: FlowState) -> Dict[str, Any]:
    """Step 8: Create GitHub issue for tracking the implementation task.

    Skips issue creation for very short prompts, system notifications, and
    LLM-analysis failures.  Falls back gracefully when GitHub is unreachable.

    Returns step8_* keys including issue_id, issue_url, and status.
    """
    try:
        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH")
        project_root = state.get("project_root", ".")
        user_msg = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")

        task_type = state.get("step0_task_type", "General Task")
        complexity = state.get("step0_complexity", 5)
        reasoning = state.get("step0_reasoning", "")
        msg_lower = user_msg.strip().lower()

        # Smart-skip conditions
        should_skip = False
        skip_reason = ""

        if len(msg_lower) < 10:
            should_skip = True
            skip_reason = "prompt too short (%d chars)" % len(msg_lower)
        elif msg_lower.startswith("<task-notification>") or msg_lower.startswith("<system"):
            should_skip = True
            skip_reason = "system notification"
        elif "LLM analysis parsing failed" in reasoning:
            should_skip = True
            skip_reason = "LLM analysis failed"
        elif task_type == "General Task" and complexity == 5 and not reasoning:
            should_skip = True
            skip_reason = "default task type with no analysis"

        if should_skip:
            logger.info("Step 8: Skipping issue creation -- %s", skip_reason)
            return {
                "step8_issue_id": "0",
                "step8_issue_url": "",
                "step8_issue_created": False,
                "step8_title": "",
                "step8_label": "",
                "step8_status": "SKIPPED",
                "step8_skip_reason": skip_reason,
            }

        skill = state.get("step5_skill", "")
        agent = state.get("step5_agent", "")
        framework = state.get("detected_framework", "unknown")
        title = _generate_issue_title(user_msg, task_type, complexity)

        # Build issue body
        body_parts = [
            "## Task Summary",
            user_msg[:500],
            "",
            "## Details",
            "- **Type**: %s" % task_type,
            "- **Complexity**: %d/10" % complexity,
            "- **Framework**: %s" % framework,
        ]
        if skill:
            body_parts.append("- **Skill**: %s" % skill)
        if agent:
            body_parts.append("- **Agent**: %s" % agent)
        body_parts.append("")

        tasks = state.get("step0_tasks", {}).get("tasks", [])
        if tasks:
            body_parts.append("## Implementation Checklist")
            for task in tasks[:10]:
                if isinstance(task, dict):
                    body_parts.append("- [ ] %s" % task.get("description", task.get("id", "")))
                else:
                    body_parts.append("- [ ] %s" % str(task))
            body_parts.append("")

        body_parts += ["---", "*Generated by Claude Workflow Engine*"]
        body = "\n".join(body_parts)

        plan_text = state.get("step2_plan", "")
        if isinstance(plan_text, dict):
            plan_text = str(plan_text)

        if Level3GitHubWorkflow is not None:
            try:
                workflow = Level3GitHubWorkflow(session_dir=session_path or ".", repo_path=project_root)
                result = workflow.step8_create_issue(
                    title=title,
                    description=body,
                    task_summary=user_msg,
                    implementation_plan=plan_text,
                )
                if result.get("success"):
                    return {
                        "step8_issue_id": str(result.get("issue_number", "0")),
                        "step8_issue_url": result.get("issue_url", ""),
                        "step8_issue_created": True,
                        "step8_title": title,
                        "step8_label": result.get("label", task_type),
                        "step8_status": "OK",
                    }
                else:
                    logger.warning("GitHub issue creation failed: %s. Using fallback.", result.get("error"))
            except Exception as gh_err:
                logger.warning("Level3GitHubWorkflow unavailable: %s. Using fallback.", gh_err)

        # Fallback
        return {
            "step8_issue_id": "0",
            "step8_issue_url": "",
            "step8_issue_created": False,
            "step8_title": title,
            "step8_label": task_type,
            "step8_status": "FALLBACK",
        }

    except Exception as e:
        return {"step8_issue_created": False, "step8_status": "ERROR", "step8_error": str(e)}


# ---------------------------------------------------------------------------
# Step 9: Branch Creation
# ---------------------------------------------------------------------------


def step9_branch_creation(state: FlowState) -> Dict[str, Any]:
    """Step 9: Create feature branch for the implementation.

    Skips branch creation when no real GitHub issue exists (issue_id == 0).
    Falls back gracefully when GitHub remote is unreachable.

    Returns step9_* keys including branch_name, branch_created, and status.
    """
    try:
        issue_id = state.get("step8_issue_id", "0")
        task_type = state.get("step0_task_type", "task").lower()
        label = state.get("step8_label", task_type)
        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH", ".")
        project_root = state.get("project_root", ".")

        branch_label = label.lower().strip() if label else task_type.lower().replace(" ", "-")

        # Skip if no real issue was created
        if issue_id == "0" or not state.get("step8_issue_created", False):
            logger.info("Step 9: Skipping branch creation -- no GitHub issue created (issue_id=0)")
            return {"step9_branch_name": "", "step9_branch_created": False, "step9_status": "SKIPPED"}

        if Level3GitHubWorkflow is not None:
            try:
                workflow = Level3GitHubWorkflow(session_dir=session_path, repo_path=project_root)
                result = workflow.step9_create_branch(
                    issue_number=int(issue_id) if issue_id.isdigit() else 0,
                    label=branch_label,
                    session_dir=session_path,
                )
                if result.get("success"):
                    return {
                        "step9_branch_name": result.get("branch_name", ""),
                        "step9_branch_created": True,
                        "step9_conflict_detected": result.get("conflict_detected", False),
                        "step9_status": "OK",
                    }
                else:
                    logger.warning("Branch creation failed: %s. Using fallback.", result.get("error"))
            except Exception as gh_err:
                logger.warning("Level3GitHubWorkflow unavailable for branch: %s. Using fallback.", gh_err)

        # Fallback
        branch_name = "%s/issue-%s" % (branch_label, issue_id)
        return {
            "step9_branch_name": branch_name,
            "step9_branch_created": False,
            "step9_status": "FALLBACK",
        }

    except Exception as e:
        return {"step9_branch_created": False, "step9_status": "ERROR", "step9_error": str(e)}
