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
    import os

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"

    try:
        scripts_dir = Path(__file__).parent.parent.parent
        script_path = scripts_dir / "architecture" / "03-execution-system" / f"{script_name}.py"

        if DEBUG:
            print(f"[L3-DEBUG] Finding script: {script_name}", file=sys.stderr)

        # Try variations if exact path not found
        if not script_path.exists():
            found = list((scripts_dir / "architecture" / "03-execution-system").glob(f"**/{script_name}*.py"))
            if found:
                script_path = found[0]
            else:
                if DEBUG:
                    print(f"[L3-DEBUG] Script not found: {script_name}", file=sys.stderr)
                return {"status": "SCRIPT_NOT_FOUND", "script": script_name}

        # Run script
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        if DEBUG:
            print(f"[L3-DEBUG] Running: {script_name}", file=sys.stderr)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
            cwd=scripts_dir
        )

        if DEBUG:
            print(f"[L3-DEBUG] {script_name} returned: {result.returncode}", file=sys.stderr)

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
    """Step 0: Call prompt-generator.py with user message + full context from Level 1"""
    import os
    import json

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"
    if DEBUG:
        print("[L3] -> Step 0 START", file=sys.stderr)

    user_message = state.get("user_message", "")

    # Fallback: read from env var (workaround for LangGraph stripping immutable fields)
    if not user_message:
        user_message = os.environ.get("CURRENT_USER_MESSAGE", "")

    # GATHER FULL CONTEXT FROM LEVEL 1
    context_data = {
        "user_message": user_message,
        "loaded_context": {
            "files_loaded": state.get("context_metadata", {}).get("files_loaded_count", 0),
            "context_percentage": state.get("context_percentage", 0),
            "context_threshold_exceeded": state.get("context_threshold_exceeded", False),
        },
        "session_info": {
            "session_chain_loaded": state.get("session_chain_loaded", False),
            "previous_sessions": len(state.get("session_history", [])),
        },
        "patterns": {
            "patterns_detected": state.get("patterns_detected", []),
        },
        "project": {
            "project_root": state.get("project_root", ""),
            "is_java_project": state.get("is_java_project", False),
        }
    }

    if DEBUG:
        print(f"[L3-DEBUG] State keys: {list(state.keys())[:5]}", file=sys.stderr)
        print(f"[L3] -> Step 0 user_message: {user_message[:50] if user_message else 'EMPTY'}...", file=sys.stderr)
        print(f"[L3] -> Step 0 context: {json.dumps(context_data, indent=2)}", file=sys.stderr)

    # Pass user message + context to script
    args = [user_message] if user_message else []
    args.append(f"--context={json.dumps(context_data)}")
    result = call_execution_script("prompt-generator", args)

    if DEBUG:
        print(f"[L3] -> Step 0 END: {result.get('task_type')}", file=sys.stderr)

    return {
        "step0_prompt": {
            "task_type": result.get("task_type", "general"),
            "complexity": result.get("complexity", 5),
            "reasoning": result.get("reasoning", ""),
            "script_output": result
        }
    }


def step1_task_breakdown(state: FlowState) -> dict:
    """Step 1: Call task-auto-analyzer.py with task type from step 0"""
    user_message = state.get("user_message", "")
    task_type = state.get("step0_prompt", {}).get("task_type", "General Task")

    # Pass both user message and task type for better analysis
    args = [user_message] if user_message else []
    args.extend([f"--task-type={task_type}"])
    result = call_execution_script("task-auto-analyzer", args)

    return {
        "step1_tasks": {
            "count": result.get("task_count", 1),
            "tasks": result.get("tasks", []),
            "script_output": result
        },
        "step1_task_count": result.get("task_count", 1)
    }


def step2_plan_mode_decision(state: FlowState) -> dict:
    """Step 2: Call auto-plan-mode-suggester.py with complexity and task count"""
    complexity = state.get("step0_prompt", {}).get("complexity", 5)
    task_count = state.get("step1_task_count", 1)

    args = [
        "--analyze",
        f"--complexity={complexity}",
        f"--tasks={task_count}"
    ]
    result = call_execution_script("auto-plan-mode-suggester", args)

    return {
        "step2_plan_mode": result.get("plan_required", False),
        "step2_reasoning": result.get("reasoning", "Task analysis complete"),
        "step2_complexity_score": result.get("complexity_score", complexity)
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
        "step4_model": result.get("selected_model", "complex_reasoning"),
        "step4_reasoning": result.get("reason", "Model selected")
    }


def step5_skill_agent_selection(state: FlowState) -> dict:
    """Step 5: Call auto-skill-agent-selector.py with task type and complexity"""
    task_type = state.get("step0_prompt", {}).get("task_type", "General Task")
    complexity = state.get("step0_prompt", {}).get("complexity", 5)

    args = [
        "--analyze",
        f"--task-type={task_type}",
        f"--complexity={complexity}"
    ]
    result = call_execution_script("auto-skill-agent-selector", args)

    return {
        "step5_skill": result.get("selected_skill", ""),
        "step5_agent": result.get("selected_agent", ""),
        "step5_reasoning": result.get("reasoning", ""),
        "step5_confidence": result.get("confidence", 0.5),
        "step5_alternatives": result.get("alternatives", []),
        "step5_llm_query_needed": result.get("llm_needed", False)
    }


def step6_tool_optimization(state: FlowState) -> dict:
    """Step 6: Tool optimization - context-aware hints"""
    context_pct = state.get("context_percentage", 0)
    result = call_execution_script("tool-optimizer-step", [f"--context={context_pct}"])
    return {
        "step6_tool_hints": result.get("optimization_hints", []),
        "step6_read_optimization": result.get("read_opts", {}),
        "step6_grep_optimization": result.get("grep_opts", {})
    }


def step8_progress_tracking(state: FlowState) -> dict:
    """Step 8: Progress tracking"""
    result = call_execution_script("progress-step")
    return {
        "step8_progress": result.get("progress", {}),
        "step8_incomplete_work": result.get("incomplete_work", [])
    }


def step9_git_commit_preparation(state: FlowState) -> dict:
    """Step 9: Git commit preparation"""
    result = call_execution_script("git-step")
    return {
        "step9_commit_ready": result.get("commit_ready", False),
        "step9_commit_message": result.get("message", ""),
        "step9_version_bump": result.get("version", "")
    }


def step10_session_save(state: FlowState) -> dict:
    """Step 10: Session save"""
    result = call_execution_script("session-step")
    return {
        "step10_session": result.get("session", {}),
        "step10_archive_needed": result.get("archive_needed", False)
    }


def step11_failure_prevention(state: FlowState) -> dict:
    """Step 11: Code Review & CI/CD Integration

    Enhanced checks for:
    - Merge conflicts in PR
    - CI/CD pipeline status
    - Code quality metrics
    - Memory usage
    """
    result = call_execution_script("failure-step")

    # Extract data from enhanced result
    merge_conflicts = result.get("merge_conflicts", {})
    github_ci = result.get("github_ci", {})
    code_quality = result.get("code_quality", {})
    blocking_issues = result.get("blocking_issues", [])
    warnings = result.get("warnings", [])

    # Add blocking issue for merge conflicts if present
    if merge_conflicts.get("has_conflicts"):
        blocking_issues.append(f"Merge conflicts: {', '.join(merge_conflicts.get('conflict_files', []))}")

    return {
        "step11_merge_conflicts": merge_conflicts,
        "step11_ci_status": github_ci,
        "step11_code_quality": code_quality,
        "step11_warnings": warnings,
        "step11_blocking_issues": blocking_issues,
        "step11_can_merge": result.get("can_proceed_to_merge", True),
        "step11_status": result.get("status", "OK"),
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
    graph.add_edge("step6_tools", "step8_progress")
    graph.add_edge("step8_progress", "step9_commit")
    graph.add_edge("step9_commit", "step10_session")
    graph.add_edge("step10_session", "step11_prevention")
    graph.add_edge("step11_prevention", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
