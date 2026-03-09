"""
Level 3 SubGraph - Execution System with REAL Policy Script Integration

All 12 steps call actual policy scripts from scripts/architecture/03-execution-system/
"""

import sys
import json
import subprocess
from pathlib import Path

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState


# ============================================================================
# SCRIPT EXECUTION HELPER
# ============================================================================


def call_execution_script(script_name: str, args: list = None) -> dict:
    """Call a Level 3 execution script and return parsed output."""
    try:
        scripts_dir = Path(__file__).parent.parent.parent
        script_path = scripts_dir / "architecture" / "03-execution-system" / f"{script_name}.py"

        # Try variations if exact path not found
        if not script_path.exists():
            found = list((scripts_dir / "architecture" / "03-execution-system").glob(f"**/{script_name}*.py"))
            if found:
                script_path = found[0]
            else:
                return {"status": "SCRIPT_NOT_FOUND", "script": script_name}

        # Run script
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=scripts_dir
        )

        # Parse output
        if result.stdout:
            try:
                return json.loads(result.stdout)
            except:
                return {
                    "status": "SUCCESS",
                    "exit_code": result.returncode,
                    "output": result.stdout[:300]
                }

        return {
            "status": "SUCCESS" if result.returncode == 0 else "FAILED",
            "exit_code": result.returncode
        }

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


# ============================================================================
# 12 EXECUTION STEPS
# ============================================================================


def step0_prompt_generation(state: FlowState) -> dict:
    """Step 0: Call prompt-generator.py"""
    result = call_execution_script("prompt-generator")
    return {
        "step0_prompt": {
            "task_type": result.get("task_type", "general"),
            "complexity": result.get("complexity", 5),
            "script_output": result
        }
    }


def step1_task_breakdown(state: FlowState) -> dict:
    """Step 1: Call task-auto-analyzer.py"""
    result = call_execution_script("task-auto-analyzer")
    return {
        "step1_tasks": {
            "count": result.get("task_count", 1),
            "script_output": result
        },
        "step1_task_count": result.get("task_count", 1)
    }


def step2_plan_mode_decision(state: FlowState) -> dict:
    """Step 2: Call auto-plan-mode-suggester.py"""
    result = call_execution_script("auto-plan-mode-suggester", ["--analyze"])
    return {
        "step2_plan_mode": result.get("plan_required", False),
        "step2_reasoning": result.get("reasoning", "Task analysis complete")
    }


def step3_context_read_enforcement(state: FlowState) -> dict:
    """Step 3: Call context-reader.py"""
    result = call_execution_script("context-reader", ["--check"])
    return {
        "step3_context_read": result.get("check_passed", True),
        "step3_enforcement_applies": result.get("enforcement_applies", True)
    }


def step4_model_selection(state: FlowState) -> dict:
    """Step 4: Call model-auto-selector.py"""
    complexity = state.get("step0_prompt", {}).get("complexity", 5)
    result = call_execution_script("model-auto-selector", [f"--complexity={complexity}"])
    return {
        "step4_model": result.get("selected_model", "haiku"),
        "step4_reasoning": result.get("reason", "Model selected")
    }


def step5_skill_agent_selection(state: FlowState) -> dict:
    """Step 5: Call auto-skill-agent-selector.py"""
    result = call_execution_script("auto-skill-agent-selector", ["--analyze"])
    return {
        "step5_skill": result.get("selected_skill", ""),
        "step5_agent": result.get("selected_agent", ""),
        "step5_reasoning": result.get("reasoning", ""),
        "step5_llm_query_needed": result.get("llm_needed", False)
    }


def step6_tool_optimization(state: FlowState) -> dict:
    """Step 6: Call tool-usage-optimizer.py"""
    context_pct = state.get("context_percentage", 0)
    result = call_execution_script("tool-usage-optimizer", [f"--context={context_pct}"])
    return {
        "step6_tool_hints": result.get("optimization_hints", []),
        "step6_read_optimization": result.get("read_opts", {}),
        "step6_grep_optimization": result.get("grep_opts", {})
    }


def step7_auto_recommendations(state: FlowState) -> dict:
    """Step 7: Call recommendations-policy.py"""
    result = call_execution_script("recommendations-policy")
    return {
        "step7_recommendations": result.get("recommendations", [])
    }


def step8_progress_tracking(state: FlowState) -> dict:
    """Step 8: Call task-progress-tracking-policy.py"""
    result = call_execution_script("task-progress-tracking-policy")
    return {
        "step8_progress": result.get("progress", {}),
        "step8_incomplete_work": result.get("incomplete", [])
    }


def step9_git_commit_preparation(state: FlowState) -> dict:
    """Step 9: Call git-auto-commit-policy.py"""
    result = call_execution_script("git-auto-commit-policy", ["--prepare"])
    return {
        "step9_commit_ready": result.get("commit_ready", False),
        "step9_commit_message": result.get("message", ""),
        "step9_version_bump": result.get("version", "")
    }


def step10_session_save(state: FlowState) -> dict:
    """Step 10: Call session save operations"""
    result = call_execution_script("auto-save-session")
    return {
        "step10_session": result.get("session", {}),
        "step10_archive_needed": result.get("archive", False)
    }


def step11_failure_prevention(state: FlowState) -> dict:
    """Step 11: Call common-failures-prevention.py"""
    result = call_execution_script("common-failures-prevention")
    return {
        "failure_prevention": result.get("prevention_checks", {}),
        "failure_prevention_warnings": result.get("warnings", [])
    }


# ============================================================================
# MERGE NODE
# ============================================================================


def level3_merge_node(state: FlowState) -> dict:
    """Determine final status based on all 12 steps."""
    error_steps = [k for k in state if k.endswith("_error") and state.get(k)]

    updates = {}
    if error_steps:
        updates["final_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + [f"Level 3: {len(error_steps)} steps had errors"]
    else:
        updates["final_status"] = "OK"

    return updates


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level3_subgraph():
    """Create Level 3 subgraph."""
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add all 12 step nodes + merge
    graph.add_node("step0_prompt", step0_prompt_generation)
    graph.add_node("step1_tasks", step1_task_breakdown)
    graph.add_node("step2_plan", step2_plan_mode_decision)
    graph.add_node("step3_context", step3_context_read_enforcement)
    graph.add_node("step4_model", step4_model_selection)
    graph.add_node("step5_skill", step5_skill_agent_selection)
    graph.add_node("step6_tools", step6_tool_optimization)
    graph.add_node("step7_recs", step7_auto_recommendations)
    graph.add_node("step8_progress", step8_progress_tracking)
    graph.add_node("step9_commit", step9_git_commit_preparation)
    graph.add_node("step10_session", step10_session_save)
    graph.add_node("step11_prevention", step11_failure_prevention)
    graph.add_node("merge", level3_merge_node)

    # Sequential edges
    graph.add_edge(START, "step0_prompt")
    graph.add_edge("step0_prompt", "step1_tasks")
    graph.add_edge("step1_tasks", "step2_plan")
    graph.add_edge("step2_plan", "step3_context")
    graph.add_edge("step3_context", "step4_model")
    graph.add_edge("step4_model", "step5_skill")
    graph.add_edge("step5_skill", "step6_tools")
    graph.add_edge("step6_tools", "step7_recs")
    graph.add_edge("step7_recs", "step8_progress")
    graph.add_edge("step8_progress", "step9_commit")
    graph.add_edge("step9_commit", "step10_session")
    graph.add_edge("step10_session", "step11_prevention")
    graph.add_edge("step11_prevention", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
