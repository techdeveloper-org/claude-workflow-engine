"""
Level 3 Execution - Step 8: GitHub Issue Creation
"""

import re

from loguru import logger

from ....flow_state import FlowState


def _generate_issue_title(user_message: str, task_type: str, complexity: int) -> str:
    """Generate a short, descriptive GitHub issue title from user message using Ollama.

    Falls back to a cleaned-up version of the user message if LLM is unavailable.

    Args:
        user_message: Original user request
        task_type: Detected task type (bug fix, feature, etc.)
        complexity: Complexity score 1-10

    Returns:
        Descriptive title string (max ~80 chars)
    """

    if not user_message:
        return f"[{task_type}] Task (complexity {complexity}/10)"

    prompt = (
        "Generate a short GitHub issue title (max 70 chars) for this task. "
        "Return ONLY the title text, no quotes, no prefix, no explanation.\n\n"
        f"Task type: {task_type}\n"
        f"User request: {user_message[:300]}\n\n"
        "Title:"
    )

    # Use shared LLM call (Ollama -> Claude CLI fallback)
    try:
        from ....llm_call import llm_call

        llm_title = llm_call(prompt, model="fast", temperature=0.3, timeout=30)
        if llm_title:
            llm_title = llm_title.strip().strip('"').strip("'").split("\n")[0].strip()
            if llm_title and len(llm_title) > 5:
                return llm_title[:80]
    except Exception:
        pass

    # Fallback: clean up user message as title
    clean = user_message.strip().split("\n")[0][:70]
    if clean and clean[0].islower():
        clean = clean[0].upper() + clean[1:]
    return clean


def _slugify_title(title: str, max_len: int = 50) -> str:
    """Convert a title to a branch-name-safe slug.

    Example: 'Fix authentication bug in dashboard' -> 'fix-authentication-bug-in-dashboard'
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len].rstrip("-")


def step8_github_issue_creation(state: FlowState) -> dict:
    """Step 8: GitHub Issue Creation - Create GitHub issue for tracking.

    Skips issue creation for:
    - Empty/very short prompts (< 5 chars)
    - System notifications (task-notification, system-reminder XML)
    - Non-task prompts (greetings, questions)

    Returns issue_id and issue_url for next step.
    """
    try:
        import os

        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH")
        project_root = state.get("project_root", ".")
        user_msg = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")

        # Smart skip: only create issues for REAL tasks (not chat, greetings, system messages)
        task_type = state.get("step0_task_type", "General Task")
        complexity = state.get("step0_complexity", 5)
        reasoning = state.get("step0_reasoning", "")
        msg_lower = user_msg.strip().lower()

        # Skip conditions:
        # 1. Very short prompts (< 10 chars) - greetings, yes/no, etc.
        # 2. System notifications (XML tags)
        # 3. LLM analysis failed AND complexity is default (5) - means Ollama was down
        # 4. Task type is still "General Task" (fallback) with no real reasoning
        should_skip = False
        skip_reason = ""

        if len(msg_lower) < 10:
            should_skip = True
            skip_reason = f"prompt too short ({len(msg_lower)} chars)"
        elif msg_lower.startswith("<task-notification>") or msg_lower.startswith("<system"):
            should_skip = True
            skip_reason = "system notification"
        elif "LLM analysis parsing failed" in reasoning:
            should_skip = True
            skip_reason = "LLM analysis failed (Ollama down?)"
        elif task_type == "General Task" and complexity == 5 and not reasoning:
            should_skip = True
            skip_reason = "default task type with no analysis"

        if should_skip:
            logger.info(f"Step 8: Skipping issue - {skip_reason}")
            return {
                "step8_issue_id": "0",
                "step8_issue_url": "",
                "step8_issue_created": False,
                "step8_title": "",
                "step8_label": "",
                "step8_status": "SKIPPED",
                "step8_skip_reason": skip_reason,
            }

        # Extract metadata from state
        task_type = state.get("step0_task_type", "General")
        complexity = state.get("step0_complexity", 5)
        user_msg = state.get("user_message", "") or os.environ.get("CURRENT_USER_MESSAGE", "")
        skill = state.get("step5_skill", "")
        agent = state.get("step5_agent", "")
        framework = state.get("detected_framework", "unknown")

        # Generate descriptive title using LLM (Ollama)
        title = _generate_issue_title(user_msg, task_type, complexity)

        # Build CLEAN issue body (no system prompt dump!)
        body_parts = []
        body_parts.append("## Task Summary")
        body_parts.append(f"{user_msg[:500]}")
        body_parts.append("")
        body_parts.append("## Details")
        body_parts.append(f"- **Type**: {task_type}")
        body_parts.append(f"- **Complexity**: {complexity}/10")
        body_parts.append(f"- **Framework**: {framework}")
        if skill:
            body_parts.append(f"- **Skill**: {skill}")
        if agent:
            body_parts.append(f"- **Agent**: {agent}")
        body_parts.append("")

        # Task breakdown as checklist
        tasks = state.get("step0_tasks", {}).get("tasks", [])
        if tasks:
            body_parts.append("## Implementation Checklist")
            for i, task in enumerate(tasks[:10], 1):
                if isinstance(task, dict):
                    body_parts.append(f"- [ ] {task.get('description', task.get('id'))}")
                else:
                    body_parts.append(f"- [ ] {str(task)}")
            body_parts.append("")

        body_parts.append("---")
        body_parts.append("*Generated by Claude Workflow Engine v6.0.0*")

        body = "\n".join(body_parts)

        # Build implementation plan from state
        plan_text = state.get("step2_plan", "")
        if isinstance(plan_text, dict):
            plan_text = str(plan_text)

        # Use Level3GitHubWorkflow for real GitHub issue creation
        try:
            from ....level3_execution.steps8to12_github import Level3GitHubWorkflow

            workflow = Level3GitHubWorkflow(session_dir=session_path or ".", repo_path=project_root)
            result = workflow.step8_create_issue(
                title=title, description=body, task_summary=user_msg, implementation_plan=plan_text
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
                logger.warning(f"GitHub issue creation failed: {result.get('error')}. Using fallback.")

        except Exception as gh_err:
            logger.warning(f"Level3GitHubWorkflow unavailable: {gh_err}. Using fallback.")

        # Fallback: return with issue_id=0 indicating no real issue was created
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
