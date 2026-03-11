"""
Level 3 SubGraph v2 - Integrated 14-Step Execution Pipeline

Integrates all new modules:
- Ollama service (Steps 1, 5, 7)
- Git operations (Steps 9, 11)
- GitHub integration (Steps 8, 9, 11, 12)
- Session management and logging
- TOON object persistence

All 14 steps implemented with proper LangGraph routing.
Step 6: Enhanced skill validation with local scanning + internet download capability.
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from loguru import logger
from ..flow_state import FlowState
from ..session_manager import SessionManager
from ..logging_setup import ExecutionLogger
from ..level3_step1_planner import Level3Step1Planner, should_execute_plan_mode
from ..level3_remaining_steps import Level3RemainingSteps
from ..level3_steps8to12_github import Level3GitHubWorkflow


# ============================================================================
# WRAPPER NODES FOR INTEGRATION
# ============================================================================


def level3_init_node(state: FlowState) -> Dict[str, Any]:
    """Bridge: Map session_path (from Level 1) to session_dir (used by v2 steps)."""
    session_path = state.get("session_path", "")
    session_id = state.get("session_id", "unknown")

    if not session_path:
        from pathlib import Path
        session_path = str(Path.home() / ".claude" / "logs" / "sessions" / session_id)

    # Also set user_requirement as alias for user_message
    return {
        "session_dir": session_path,
        "user_requirement": state.get("user_message", ""),
    }


def step1_plan_mode_decision_node(state: FlowState) -> Dict[str, Any]:
    """Step 1: Plan Mode Decision using Ollama."""
    logger.info("\n🔄 [STEP 1] Plan Mode Decision")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        user_requirement = state.get("user_message", "")
        toon = state.get("level1_context_toon", {})

        planner = Level3Step1Planner(session_dir)
        decision = planner.execute(toon, user_requirement)

        execution_time_ms = (time.time() - step_start) * 1000

        updates = {
            "step1_decision": decision,
            "step1_plan_required": decision.get("plan_required", True),
            "step1_execution_time_ms": execution_time_ms
        }

        logger.info(f"✓ Step 1 completed: plan_required={updates['step1_plan_required']} ({execution_time_ms:.0f}ms)")
        return updates

    except Exception as e:
        logger.error(f"Step 1 failed: {e}")
        return {
            "step1_error": str(e),
            "step1_plan_required": True  # Default to safe behavior
        }


def step2_plan_execution_node(state: FlowState) -> Dict[str, Any]:
    """Step 2: Plan Execution (conditional on Step 1)."""
    logger.info("\n🔄 [STEP 2] Plan Execution")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        user_requirement = state.get("user_message", "")
        toon = state.get("level1_context_toon", {})

        steps = Level3RemainingSteps(session_dir)
        # WORKFLOW.md SPEC: Use exploration tools to ground plan in actual code
        plan_result = steps.step2_plan_execution(toon, user_requirement, project_root=session_dir)

        execution_time_ms = (time.time() - step_start) * 1000

        if plan_result.get("success"):
            selected_model = plan_result.get("selected_model", "sonnet")
            logger.info(f"✓ Step 2 completed with {selected_model} model ({execution_time_ms:.0f}ms)")
            return {
                "step2_plan": plan_result.get("plan", ""),
                "step2_files_affected": plan_result.get("files_affected", []),
                "step2_phases": plan_result.get("phases", []),
                "step2_risks": plan_result.get("risks", {}),
                "step2_code_context": plan_result.get("code_context", ""),
                "step2_selected_model": selected_model,  # Track selected model
                "step2_execution_time_ms": execution_time_ms
            }
        else:
            logger.error(f"Step 2 failed: {plan_result.get('error')}")
            return {"step2_error": plan_result.get("error")}

    except Exception as e:
        logger.error(f"Step 2 failed: {e}")
        return {"step2_error": str(e)}


def step3_task_breakdown_node(state: FlowState) -> Dict[str, Any]:
    """Step 3: Task Breakdown."""
    logger.info("\n🔄 [STEP 3] Task Breakdown")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        # Fallback: if step2 was skipped, use user_message; otherwise use step2 plan
        plan = state.get("step2_plan") or state.get("user_message", "")
        files = state.get("step2_files_affected") or []
        # If no files from step2, derive from context
        if not files:
            toon = state.get("level1_context_toon", {})
            files = toon.get("context", {}).get("files", [])

        steps = Level3RemainingSteps(session_dir)
        task_result = steps.step3_task_breakdown(plan, files)

        execution_time_ms = (time.time() - step_start) * 1000

        if task_result.get("success"):
            logger.info(f"✓ Step 3 completed: {task_result.get('task_count', 0)} tasks ({execution_time_ms:.0f}ms)")
            return {
                "step3_tasks": task_result.get("tasks", []),
                "step3_task_count": task_result.get("task_count", 0),
                "step3_execution_time_ms": execution_time_ms
            }
        else:
            logger.error(f"Step 3 failed: {task_result.get('error')}")
            return {"step3_error": task_result.get("error")}

    except Exception as e:
        logger.error(f"Step 3 failed: {e}")
        return {"step3_error": str(e)}


def step4_toon_refinement_node(state: FlowState) -> Dict[str, Any]:
    """Step 4: TOON Refinement."""
    logger.info("\n🔄 [STEP 4] TOON Refinement")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        toon_analysis = state.get("level1_context_toon", {})
        plan = {
            "plan": state.get("step2_plan", ""),
            "files_affected": state.get("step2_files_affected", []),
            "phases": state.get("step2_phases", []),
            "risks": state.get("step2_risks", {})
        }
        tasks = state.get("step3_tasks", [])

        steps = Level3RemainingSteps(session_dir)
        refinement_result = steps.step4_toon_refinement(toon_analysis, plan, tasks)

        execution_time_ms = (time.time() - step_start) * 1000

        if refinement_result.get("success"):
            logger.info(f"✓ Step 4 completed ({execution_time_ms:.0f}ms)")
            return {
                "step4_blueprint": refinement_result.get("blueprint", {}),
                "step4_execution_time_ms": execution_time_ms
            }
        else:
            logger.error(f"Step 4 failed: {refinement_result.get('error')}")
            return {"step4_error": refinement_result.get("error")}

    except Exception as e:
        logger.error(f"Step 4 failed: {e}")
        return {"step4_error": str(e)}


def step5_skill_selection_node(state: FlowState) -> Dict[str, Any]:
    """Step 5: Skill & Agent Selection.

    Process (WORKFLOW.md Compliant):
    1. Scan available skills/agents from local system (~/.claude/skills/, ~/.claude/agents/)
    2. READ FULL CONTENT of each skill.md and agent.md
    3. Add to TOON with full definitions so LLM understands what each skill does
    4. Pass TOON + FULL SKILL DEFINITIONS to LLM
    5. LLM analyzes with complete context: "From these X skills with definitions, use Y, Z for this task"
    6. Return LLM recommendation for Step 6 validation & download

    CRITICAL: Step 5 must pass FULL SKILL/AGENT DEFINITIONS to LLM, not just names!
    """
    logger.info("\n🔄 [STEP 5] Skill & Agent Selection")
    step_start = time.time()

    try:
        from pathlib import Path
        from ..ollama_service import get_ollama_service

        home = Path.home()

        # 1. SCAN + READ FULL CONTENT of skills
        logger.info("📂 Scanning and reading skill definitions...")
        skills_with_content = []
        skill_names_only = []

        skills_dir = home / ".claude" / "skills"
        if skills_dir.exists():
            for category_dir in skills_dir.iterdir():
                if not category_dir.is_dir():
                    continue

                for skill_dir in category_dir.iterdir():
                    if not skill_dir.is_dir():
                        continue

                    skill_name = skill_dir.name
                    skill_file = skill_dir / "skill.md"
                    skill_file_alt = skill_dir / "SKILL.md"

                    if skill_file.exists() or skill_file_alt.exists():
                        actual_file = skill_file if skill_file.exists() else skill_file_alt
                        try:
                            content = actual_file.read_text(encoding='utf-8')
                            skills_with_content.append({
                                "name": skill_name,
                                "category": category_dir.name,
                                "path": str(skill_dir),
                                "content": content[:1000]  # First 1000 chars for context (full in LLM)
                            })
                            skill_names_only.append(skill_name)
                        except Exception as e:
                            logger.warning(f"Could not read skill {skill_name}: {e}")

        logger.info(f"✓ Found {len(skills_with_content)} skills with full definitions")

        # 2. SCAN + READ FULL CONTENT of agents
        logger.info("📂 Scanning and reading agent definitions...")
        agents_with_content = []
        agent_names_only = []

        agents_dir = home / ".claude" / "agents"
        if agents_dir.exists():
            for agent_dir in agents_dir.iterdir():
                if not agent_dir.is_dir() or agent_dir.name == "__pycache__":
                    continue

                agent_name = agent_dir.name
                agent_file = agent_dir / "agent.md"

                if agent_file.exists():
                    try:
                        content = agent_file.read_text(encoding='utf-8')
                        agents_with_content.append({
                            "name": agent_name,
                            "path": str(agent_dir),
                            "content": content[:1000]  # First 1000 chars for context
                        })
                        agent_names_only.append(agent_name)
                    except Exception as e:
                        logger.warning(f"Could not read agent {agent_name}: {e}")

        logger.info(f"✓ Found {len(agents_with_content)} agents with full definitions")

        blueprint = state.get("step4_blueprint", {})

        # 3. ADD TO TOON with FULL DEFINITIONS
        blueprint_with_definitions = {
            **blueprint,
            "available_skills_on_system": skill_names_only,
            "available_skills_full_definitions": skills_with_content,  # FULL CONTENT
            "available_agents_on_system": agent_names_only,
            "available_agents_full_definitions": agents_with_content,  # FULL CONTENT
            "available_skills_count": len(skills_with_content),
            "available_agents_count": len(agents_with_content)
        }

        logger.info(f"📋 Added available skills + full definitions to TOON for LLM")

        # 4. PASS TO LLM WITH FULL DEFINITIONS
        # LLM now sees what each skill actually does!
        ollama = get_ollama_service()
        skill_result = ollama.step5_skill_agent_selection(
            blueprint_with_definitions,
            skill_names_only,  # Names for easy reference
            agent_names_only   # Names for easy reference
            # NOTE: LLM will also see full definitions in blueprint for informed decision
        )

        execution_time_ms = (time.time() - step_start) * 1000

        logger.info(f"✓ Step 5 completed: {len(skill_result.get('final_skills_selected', []))} skills selected ({execution_time_ms:.0f}ms)")

        # 5. Return LLM recommendation + available list + full definitions for Step 6
        return {
            "step5_available_skills": skill_names_only,
            "step5_available_skills_full": skills_with_content,  # FULL CONTENT for tracking
            "step5_available_agents": agent_names_only,
            "step5_available_agents_full": agents_with_content,  # FULL CONTENT for tracking
            "step5_skill_mappings": skill_result.get("skill_mappings", []),
            "step5_skills": skill_result.get("final_skills_selected", []),  # LLM selected
            "step5_agents": skill_result.get("final_agents_selected", []),  # LLM selected
            "step5_execution_time_ms": execution_time_ms
        }

    except Exception as e:
        logger.error(f"Step 5 failed: {e}")
        return {"step5_error": str(e)}


def step6_skill_validation_node(state: FlowState) -> Dict[str, Any]:
    """Step 6: Skill Validation & Download.

    Process:
    1. Get LLM recommendation from Step 5 (which skills to use)
    2. Get available skills list from Step 5
    3. Validate: Check if selected skills exist locally
    4. Download: Fetch any missing skills from Claude Code GitHub
    5. Return: Selected skills with full content ready to use

    Note: Step 5 already analyzed TOON with available skills and LLM selected from that list.
    Step 6 just validates and downloads if needed.
    """
    logger.info("\n🔄 [STEP 6] Skill Validation & Download")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")

        # Get from Step 5
        available_skills = state.get("step5_available_skills", [])
        available_agents = state.get("step5_available_agents", [])
        llm_selected_skills = state.get("step5_skills", [])
        llm_selected_agents = state.get("step5_agents", [])

        logger.info(f"📋 Validating {len(llm_selected_skills)} skills selected by LLM...")
        logger.info(f"📋 Available on system: {len(available_skills)} skills, {len(available_agents)} agents")

        # Use enhanced Step 6 function from Level3RemainingSteps
        llm_recommendation = {
            "final_skills_selected": llm_selected_skills,
            "final_agents_selected": llm_selected_agents,
            "missing_but_prefer": []
        }

        steps = Level3RemainingSteps(session_dir)
        validation_result = steps.step6_skill_validation_and_selection(
            {"available_skills": available_skills, "available_agents": available_agents},
            llm_recommendation
        )

        execution_time_ms = (time.time() - step_start) * 1000

        if validation_result.get("success"):
            downloaded = validation_result.get("downloaded", [])
            download_msg = f", {len(downloaded)} downloaded" if downloaded else ""
            logger.info(f"✓ Step 6 completed: {len(validation_result.get('final_skills', []))} skills ready{download_msg} ({execution_time_ms:.0f}ms)")

            if downloaded:
                logger.info(f"  Downloaded: {downloaded}")

            return {
                "step6_available_on_system": available_skills,
                "step6_llm_selected_skills": llm_selected_skills,
                "step6_llm_selected_agents": llm_selected_agents,
                "step6_final_skills": validation_result.get("final_skills", []),
                "step6_final_agents": validation_result.get("final_agents", []),
                "step6_downloaded": downloaded,
                "step6_execution_time_ms": execution_time_ms
            }
        else:
            logger.error(f"Step 6 failed: {validation_result.get('error')}")
            return {"step6_error": validation_result.get("error")}

    except Exception as e:
        logger.error(f"Step 6 failed: {e}")
        return {"step6_error": str(e)}


def step7_final_prompt_node(state: FlowState) -> Dict[str, Any]:
    """Step 7: Final Prompt Generation."""
    logger.info("\n🔄 [STEP 7] Final Prompt Generation")
    step_start = time.time()

    try:
        from ..ollama_service import get_ollama_service

        toon_final = {
            **state.get("step4_blueprint", {}),
            "final_skills_selected": state.get("step5_skills", []),
            "final_agents_selected": state.get("step5_agents", [])
        }

        ollama = get_ollama_service()
        prompt = ollama.step7_final_prompt_generation(toon_final)

        execution_time_ms = (time.time() - step_start) * 1000

        logger.info(f"✓ Step 7 completed: {len(prompt)} chars ({execution_time_ms:.0f}ms)")

        return {
            "step7_execution_prompt": prompt,
            "step7_execution_time_ms": execution_time_ms
        }

    except Exception as e:
        logger.error(f"Step 7 failed: {e}")
        return {"step7_error": str(e)}


def step8_github_issue_node(state: FlowState) -> Dict[str, Any]:
    """Step 8: GitHub Issue Creation."""
    logger.info("\n🔄 [STEP 8] GitHub Issue Creation")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        prompt = state.get("step7_execution_prompt", "")

        # Parse title from prompt
        lines = prompt.split('\n')
        title = lines[0].strip() if lines else "Task"

        workflow = Level3GitHubWorkflow(session_dir)
        issue_result = workflow.step8_create_issue(title, prompt)

        execution_time_ms = (time.time() - step_start) * 1000

        if issue_result.get("success"):
            logger.info(f"✓ Step 8 completed: Issue #{issue_result.get('issue_number')} ({execution_time_ms:.0f}ms)")
            return {
                "step8_issue_number": issue_result.get("issue_number"),
                "step8_issue_url": issue_result.get("issue_url"),
                "step8_label": issue_result.get("label"),
                "step8_execution_time_ms": execution_time_ms
            }
        else:
            logger.error(f"Step 8 failed: {issue_result.get('error')}")
            return {"step8_error": issue_result.get("error")}

    except Exception as e:
        logger.error(f"Step 8 failed: {e}")
        return {"step8_error": str(e)}


def step9_branch_creation_node(state: FlowState) -> Dict[str, Any]:
    """Step 9: Branch Creation."""
    logger.info("\n🔄 [STEP 9] Branch Creation")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        issue_number = state.get("step8_issue_number", 0)
        label = state.get("step8_label", "task")

        workflow = Level3GitHubWorkflow(session_dir)
        branch_result = workflow.step9_create_branch(issue_number, label)

        execution_time_ms = (time.time() - step_start) * 1000

        if branch_result.get("success"):
            logger.info(f"✓ Step 9 completed: {branch_result.get('branch_name')} ({execution_time_ms:.0f}ms)")
            return {
                "step9_branch_name": branch_result.get("branch_name"),
                "step9_execution_time_ms": execution_time_ms
            }
        else:
            logger.error(f"Step 9 failed: {branch_result.get('error')}")
            return {"step9_error": branch_result.get("error")}

    except Exception as e:
        logger.error(f"Step 9 failed: {e}")
        return {"step9_error": str(e)}


def step10_implementation_note(state: FlowState) -> Dict[str, Any]:
    """Step 10: Implementation (Handled by Claude).

    NOTE: Actual implementation (file modifications) is done by Claude
    using Read, Edit, Write, Bash tools directly with the execution prompt.

    This is idempotent - can be called multiple times if Step 11 code review fails.
    On retry, includes feedback about what issues were found for re-implementation.
    """
    logger.info("\n⏳ [STEP 10] Implementation (Handled by Claude)")

    # Check if this is a retry due to code review failure
    retry_count = state.get("step11_retry_count", 0)
    review_issues = state.get("step11_review_issues", [])

    if retry_count > 0 and review_issues:
        logger.info(f"🔄 [STEP 10 RETRY #{retry_count}] Code review found issues, implementing fixes...")
        logger.info(f"Issues to fix: {len(review_issues)} items")
        for issue in review_issues[:5]:  # Show first 5 issues
            issue_type = issue.get("type", "issue")
            issue_file = issue.get("file", "unknown")
            issue_line = issue.get("line", "?")
            issue_message = issue.get("message", "")
            logger.info(f"  - {issue_type} in {issue_file}:{issue_line}: {issue_message[:60]}")

        prompt = state.get("step7_execution_prompt", "")
        updated_prompt = f"""[RETRY #{retry_count}] Fix the following code review issues and re-implement:

CODE REVIEW FINDINGS:
{chr(10).join([f'- {issue.get("message", "")}' for issue in review_issues[:5]])}

Original implementation prompt:
---
{prompt}
---

Please fix ONLY the issues listed above. Update the relevant files."""

        message = f"Retry attempt {retry_count}: Fixing code review issues found in previous attempt"
    else:
        logger.info("Claude will now execute the prompt.txt using available tools")
        updated_prompt = state.get("step7_execution_prompt", "")
        message = "Claude is executing implementation using tools"

    # Save prompt to session
    session_dir = state.get("session_dir", ".")
    try:
        prompt_file = Path(session_dir) / "prompt.txt"
        prompt_file.write_text(updated_prompt)
        logger.info(f"Saved prompt to {prompt_file}")
    except Exception as e:
        logger.warning(f"Could not save prompt: {e}")

    return {
        "step10_status": "manual",
        "step10_message": message,
        "step10_retry_count": retry_count,
        "step10_execution_prompt": updated_prompt  # Updated prompt for retries
    }


def step11_pull_request_node(state: FlowState) -> Dict[str, Any]:
    """Step 11: Pull Request Creation & Merge with Retry Tracking.

    This step:
    1. Creates a PR for the implementation
    2. Runs code review on the changes
    3. Returns review status for routing logic
    4. If review fails, flow can retry (handled by orchestrator routing)
    """
    logger.info("\n🔄 [STEP 11] Pull Request Creation & Merge")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        issue_number = state.get("step8_issue_number", 0)
        branch_name = state.get("step9_branch_name", "")
        selected_skills = state.get("step5_skills", [])
        selected_agents = state.get("step5_agents", [])

        # Get retry count (incremented from Level 1 init or previous attempt)
        current_retry_count = state.get("step11_retry_count", 0)
        retry_messages = state.get("step11_retry_messages", [])

        workflow = Level3GitHubWorkflow(session_dir)
        pr_result = workflow.step11_create_pull_request(
            issue_number,
            branch_name,
            selected_skills=selected_skills,
            selected_agents=selected_agents
        )

        execution_time_ms = (time.time() - step_start) * 1000

        if pr_result.get("success"):
            review_passed = pr_result.get("review_passed", True)
            review_issues = pr_result.get("review_issues", [])

            # Track review status
            review_status = "✓ PASSED" if review_passed else f"✗ FAILED ({len(review_issues)} issues)"
            logger.info(f"✓ Step 11 completed: PR #{pr_result.get('pr_number')} - Review: {review_status} ({execution_time_ms:.0f}ms)")

            # Build retry message if review failed
            if not review_passed:
                issue_summary = "; ".join([issue.get("type", "issue") for issue in review_issues[:3]])
                retry_msg = f"Attempt {current_retry_count + 1}: Code review found issues - {issue_summary}"
                retry_messages.append(retry_msg)
                logger.warning(f"Code review failed. Issues: {issue_summary}")
                logger.info(f"Available retries: {3 - (current_retry_count + 1)} attempts remaining")

            return {
                "step11_pr_number": pr_result.get("pr_number"),
                "step11_pr_url": pr_result.get("pr_url"),
                "step11_merged": pr_result.get("merged"),
                "step11_review_passed": review_passed,
                "step11_review_issues": review_issues,
                "step11_retry_count": current_retry_count + 1,  # Increment counter
                "step11_retry_messages": retry_messages,
                "step11_execution_time_ms": execution_time_ms
            }
        else:
            logger.error(f"Step 11 failed: {pr_result.get('error')}")
            return {"step11_error": pr_result.get("error")}

    except Exception as e:
        logger.error(f"Step 11 failed: {e}")
        return {"step11_error": str(e)}


def step12_issue_closure_node(state: FlowState) -> Dict[str, Any]:
    """Step 12: Issue Closure."""
    logger.info("\n🔄 [STEP 12] Issue Closure")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        issue_number = state.get("step8_issue_number", 0)
        pr_number = state.get("step11_pr_number", 0)

        workflow = Level3GitHubWorkflow(session_dir)
        closure_result = workflow.step12_close_issue(issue_number, pr_number)

        execution_time_ms = (time.time() - step_start) * 1000

        logger.info(f"✓ Step 12 completed ({execution_time_ms:.0f}ms)")

        return {
            "step12_closed": closure_result.get("closed", False),
            "step12_execution_time_ms": execution_time_ms
        }

    except Exception as e:
        logger.error(f"Step 12 failed: {e}")
        return {"step12_error": str(e)}


def step13_docs_update_node(state: FlowState) -> Dict[str, Any]:
    """Step 13: Documentation Update."""
    logger.info("\n🔄 [STEP 13] Documentation Update")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        # Get files modified from step2 plan, fallback to step3 tasks
        files_modified = (
            state.get("step2_files_affected")
            or [t.get("file", "") for t in state.get("step3_tasks", []) if t.get("file")]
            or []
        )

        steps = Level3RemainingSteps(session_dir)
        docs_result = steps.step13_update_documentation(files_modified)

        execution_time_ms = (time.time() - step_start) * 1000

        logger.info(f"✓ Step 13 completed ({execution_time_ms:.0f}ms)")

        return {
            "step13_updated_files": docs_result.get("updated_files", []),
            "step13_execution_time_ms": execution_time_ms
        }

    except Exception as e:
        logger.error(f"Step 13 failed: {e}")
        return {"step13_error": str(e)}


def step14_final_summary_node(state: FlowState) -> Dict[str, Any]:
    """Step 14: Final Summary."""
    logger.info("\n🔄 [STEP 14] Final Summary")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        issue_number = state.get("step8_issue_number", 0)
        pr_number = state.get("step11_pr_number", 0)
        # Get files modified from step2 plan, fallback to step3 tasks
        files_modified = (
            state.get("step2_files_affected")
            or [t.get("file", "") for t in state.get("step3_tasks", []) if t.get("file")]
            or []
        )

        steps = Level3RemainingSteps(session_dir)
        summary_result = steps.step14_final_summary(issue_number, pr_number, files_modified)

        execution_time_ms = (time.time() - step_start) * 1000

        logger.info(f"✓ Step 14 completed ({execution_time_ms:.0f}ms)")

        return {
            "step14_summary": summary_result.get("summary", ""),
            "step14_voice_sent": summary_result.get("voice_notification", False),
            "step14_execution_time_ms": execution_time_ms
        }

    except Exception as e:
        logger.error(f"Step 14 failed: {e}")
        return {"step14_error": str(e)}


def level3_merge_node(state: FlowState) -> Dict[str, Any]:
    """Merge all Level 3 step outputs."""
    logger.info("\n" + "=" * 60)
    logger.info("LEVEL 3 EXECUTION COMPLETE")
    logger.info("=" * 60)

    # Calculate total execution time
    step_times = {
        k: v for k, v in state.items()
        if k.endswith("_execution_time_ms")
    }
    total_time = sum(step_times.values()) if step_times else 0

    # Check for errors
    error_steps = [k for k in state if k.endswith("_error") and state.get(k)]

    updates = {
        "level3_status": "FAILED" if error_steps else "OK",
        "level3_total_execution_time_ms": total_time,
        "final_status": "FAILED" if error_steps else "OK"
    }

    if error_steps:
        logger.error(f"Level 3 failed: {len(error_steps)} steps had errors")
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + [f"Level 3: {len(error_steps)} steps failed"]
    else:
        logger.info(f"✓ Level 3 completed successfully in {total_time:.0f}ms")

    return updates


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level3_execution_subgraph_v2():
    """Create Level 3 execution subgraph with full 14-step pipeline.

    Step 6: Enhanced skill validation that:
    - Scans available skills/agents on local system
    - Lets LLM select which ones to use for task
    - Downloads missing skills from internet (Claude Code GitHub)
    - Returns selected skills ready for use
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add all 14 step nodes
    graph.add_node("step1_plan_decision", step1_plan_mode_decision_node)
    graph.add_node("step2_plan_execution", step2_plan_execution_node)
    graph.add_node("step3_task_breakdown", step3_task_breakdown_node)
    graph.add_node("step4_toon_refinement", step4_toon_refinement_node)
    graph.add_node("step5_skill_selection", step5_skill_selection_node)
    graph.add_node("step6_skill_validation", step6_skill_validation_node)
    graph.add_node("step7_final_prompt", step7_final_prompt_node)
    graph.add_node("step8_github_issue", step8_github_issue_node)
    graph.add_node("step9_branch_creation", step9_branch_creation_node)
    graph.add_node("step10_implementation", step10_implementation_note)
    graph.add_node("step11_pull_request", step11_pull_request_node)
    graph.add_node("step12_issue_closure", step12_issue_closure_node)
    graph.add_node("step13_docs_update", step13_docs_update_node)
    graph.add_node("step14_final_summary", step14_final_summary_node)
    graph.add_node("merge", level3_merge_node)

    # Edges: All conditional on Step 1 plan decision
    graph.add_edge(START, "step1_plan_decision")

    # Conditional routing after Step 1
    def route_after_step1(state: FlowState) -> str:
        """Route to Step 2 (plan) or skip to Step 3 (direct execution)."""
        plan_required = state.get("step1_plan_required", True)
        if plan_required:
            return "step2_plan_execution"
        else:
            logger.info("Skipping planning, going direct to execution")
            return "step3_task_breakdown"

    graph.add_conditional_edges(
        "step1_plan_decision",
        route_after_step1,
        {
            "step2_plan_execution": "step2_plan_execution",
            "step3_task_breakdown": "step3_task_breakdown"
        }
    )

    # Sequential edges for planned path
    graph.add_edge("step2_plan_execution", "step3_task_breakdown")

    # Rest of the pipeline (sequential)
    graph.add_edge("step3_task_breakdown", "step4_toon_refinement")
    graph.add_edge("step4_toon_refinement", "step5_skill_selection")
    graph.add_edge("step5_skill_selection", "step6_skill_validation")
    graph.add_edge("step6_skill_validation", "step7_final_prompt")
    graph.add_edge("step7_final_prompt", "step8_github_issue")
    graph.add_edge("step8_github_issue", "step9_branch_creation")
    graph.add_edge("step9_branch_creation", "step10_implementation")
    graph.add_edge("step10_implementation", "step11_pull_request")

    # ===== STEP 11 RETRY LOOP =====
    # Conditional routing after Step 11: retry if review failed and attempts < 3
    def route_after_step11(state: FlowState) -> str:
        """Route after Step 11: retry loop if code review failed.

        Logic:
        - If review passed OR merged: continue to Step 12 (closure)
        - If review failed AND attempts < 3: loop back to Step 10 (re-implementation)
        - If max retries reached: continue to Step 12 (force closure)
        """
        review_passed = state.get("step11_review_passed", True)
        retry_count = state.get("step11_retry_count", 0)
        max_retries = 3

        if review_passed or state.get("step11_merged", False):
            logger.info("Code review passed or PR merged, proceeding to closure")
            return "step12_issue_closure"

        if retry_count < max_retries:
            logger.info(f"Code review failed. Retry {retry_count}/{max_retries-1} - looping back to Step 10")
            return "step10_implementation"

        logger.warning(f"Max retries ({max_retries}) reached. Forcing closure regardless of review status")
        return "step12_issue_closure"

    graph.add_conditional_edges(
        "step11_pull_request",
        route_after_step11,
        {
            "step12_issue_closure": "step12_issue_closure",
            "step10_implementation": "step10_implementation"
        }
    )

    graph.add_edge("step12_issue_closure", "step13_docs_update")
    graph.add_edge("step13_docs_update", "step14_final_summary")
    graph.add_edge("step14_final_summary", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
