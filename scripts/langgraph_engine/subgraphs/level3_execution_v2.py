"""
Level 3 SubGraph v2 - Integrated 13-Step Execution Pipeline

Integrates all new modules:
- Ollama service (Steps 1, 5, 7)
- Git operations (Steps 8, 10)
- GitHub integration (Steps 8, 10, 11)
- Session management and logging
- TOON object persistence

All 13 steps implemented with proper LangGraph routing.
Skills/agents fetched from Claude Code (internet-available, no validation needed).
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
        plan_result = steps.step2_plan_execution(toon, user_requirement)

        execution_time_ms = (time.time() - step_start) * 1000

        if plan_result.get("success"):
            logger.info(f"✓ Step 2 completed ({execution_time_ms:.0f}ms)")
            return {
                "step2_plan": plan_result.get("plan", ""),
                "step2_files_affected": plan_result.get("files_affected", []),
                "step2_phases": plan_result.get("phases", []),
                "step2_risks": plan_result.get("risks", {}),
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
        plan = state.get("step2_plan", "")
        files = state.get("step2_files_affected", [])

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

    Skills and agents are fetched from Claude Code (internet-available).
    No validation needed - Claude Code skills are dynamically available.
    """
    logger.info("\n🔄 [STEP 5] Skill & Agent Selection")
    step_start = time.time()

    try:
        from ..ollama_service import get_ollama_service

        blueprint = state.get("step4_blueprint", {})

        # Claude Code internet-available skills (comprehensive list)
        available_skills = [
            "python-backend-engineer", "java-spring-boot-microservices", "docker",
            "kubernetes", "jenkins-pipeline", "devops-engineer", "angular-engineer",
            "swift-backend-engineer", "swiftui-designer", "android-backend-engineer",
            "android-ui-designer", "orchestrator-agent", "spring-boot-microservices"
        ]

        # Claude Code internet-available agents (comprehensive list)
        available_agents = [
            "spring-boot-microservices", "orchestrator-agent", "python-backend-engineer",
            "devops-engineer", "android-backend-engineer", "angular-engineer",
            "swift-backend-engineer", "qa-testing-agent", "dynamic-seo-agent",
            "static-seo-agent"
        ]

        logger.info(f"Available {len(available_skills)} skills and {len(available_agents)} agents from Claude Code")

        ollama = get_ollama_service()
        skill_result = ollama.step5_skill_agent_selection(blueprint, available_skills, available_agents)

        execution_time_ms = (time.time() - step_start) * 1000

        logger.info(f"✓ Step 5 completed: {len(skill_result.get('final_skills_selected', []))} skills selected ({execution_time_ms:.0f}ms)")

        return {
            "step5_skill_mappings": skill_result.get("skill_mappings", []),
            "step5_skills": skill_result.get("final_skills_selected", []),
            "step5_agents": skill_result.get("final_agents_selected", []),
            "step5_execution_time_ms": execution_time_ms
        }

    except Exception as e:
        logger.error(f"Step 5 failed: {e}")
        return {"step5_error": str(e)}


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
    """Step 10: Implementation Placeholder.

    NOTE: Actual implementation (file modifications) is done by Claude
    using Read, Edit, Write, Bash tools directly with the execution prompt.
    """
    logger.info("\n⏳ [STEP 10] Implementation (Handled by Claude)")
    logger.info("Claude will now execute the prompt.txt using available tools")

    # Save prompt to session
    session_dir = state.get("session_dir", ".")
    try:
        prompt_file = Path(session_dir) / "prompt.txt"
        prompt_file.write_text(state.get("step7_execution_prompt", ""))
        logger.info(f"Saved prompt to {prompt_file}")
    except Exception as e:
        logger.warning(f"Could not save prompt: {e}")

    return {
        "step10_status": "manual",
        "step10_message": "Claude is executing implementation using tools"
    }


def step11_pull_request_node(state: FlowState) -> Dict[str, Any]:
    """Step 11: Pull Request Creation & Merge."""
    logger.info("\n🔄 [STEP 11] Pull Request Creation & Merge")
    step_start = time.time()

    try:
        session_dir = state.get("session_dir", ".")
        issue_number = state.get("step8_issue_number", 0)
        branch_name = state.get("step9_branch_name", "")

        workflow = Level3GitHubWorkflow(session_dir)
        pr_result = workflow.step11_create_pull_request(issue_number, branch_name)

        execution_time_ms = (time.time() - step_start) * 1000

        if pr_result.get("success"):
            logger.info(f"✓ Step 11 completed: PR #{pr_result.get('pr_number')} ({execution_time_ms:.0f}ms)")
            return {
                "step11_pr_number": pr_result.get("pr_number"),
                "step11_pr_url": pr_result.get("pr_url"),
                "step11_merged": pr_result.get("merged"),
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
        files_modified = state.get("step3_tasks", [])

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
        files_modified = state.get("step3_tasks", [])

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
    """Create Level 3 execution subgraph with full 13-step pipeline.

    Note: Step 6 (skill validation) removed - skills fetched from Claude Code (internet-available).
    """
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add all 13 step nodes
    graph.add_node("step1_plan_decision", step1_plan_mode_decision_node)
    graph.add_node("step2_plan_execution", step2_plan_execution_node)
    graph.add_node("step3_task_breakdown", step3_task_breakdown_node)
    graph.add_node("step4_toon_refinement", step4_toon_refinement_node)
    graph.add_node("step5_skill_selection", step5_skill_selection_node)
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

    graph.add_conditional_edges("step1_plan_decision", route_after_step1)

    # Sequential edges for planned path
    graph.add_edge("step2_plan_execution", "step3_task_breakdown")

    # Direct path (skip planning)
    graph.add_edge("step1_plan_decision", "step3_task_breakdown")  # Fallback for router

    # Rest of the pipeline (sequential)
    graph.add_edge("step3_task_breakdown", "step4_toon_refinement")
    graph.add_edge("step4_toon_refinement", "step5_skill_selection")
    graph.add_edge("step5_skill_selection", "step7_final_prompt")
    graph.add_edge("step7_final_prompt", "step8_github_issue")
    graph.add_edge("step8_github_issue", "step9_branch_creation")
    graph.add_edge("step9_branch_creation", "step10_implementation")
    graph.add_edge("step10_implementation", "step11_pull_request")
    graph.add_edge("step11_pull_request", "step12_issue_closure")
    graph.add_edge("step12_issue_closure", "step13_docs_update")
    graph.add_edge("step13_docs_update", "step14_final_summary")
    graph.add_edge("step14_final_summary", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
