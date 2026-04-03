"""
Level 3 Execution - Step 1: Plan Mode Decision
"""

import json

from ....flow_state import FlowState
from ..helpers import call_execution_script


def step1_plan_mode_decision(state: FlowState) -> dict:
    """Step 1: Plan Mode Decision - Determine if detailed planning is needed.

    Uses FULL context from Step 0 (user message, task type, complexity, task details)
    to decide whether detailed planning is needed.

    Returns:
    - step1_plan_required: bool (True if planning needed)
    - step1_reasoning: str (explanation of decision)
    """
    # Get all relevant context
    user_message = state.get("user_message", "")
    task_type = state.get("step0_task_type", "General Task")
    complexity = state.get("step0_complexity", 5)
    task_count = state.get("step0_task_count", 1)
    tasks = state.get("step0_tasks", {}).get("tasks", [])
    patterns = state.get("patterns_detected", [])
    reasoning_from_step0 = state.get("step0_reasoning", "")

    # Build complete context for better decision
    task_descriptions = []
    for task in tasks:
        if isinstance(task, dict):
            task_descriptions.append(task.get("description", ""))
        else:
            task_descriptions.append(str(task))

    # Pass rich context to LLM
    context_data = {
        "user_message": user_message,
        "task_type": task_type,
        "complexity": complexity,
        "task_count": task_count,
        "task_descriptions": task_descriptions,
        "patterns_detected": patterns,
        "step0_reasoning": reasoning_from_step0,
    }

    args = ["--analyze", f"--context={json.dumps(context_data)}"]
    result = call_execution_script("auto-plan-mode-suggester", args, model_tier="fast")

    return {
        "step1_plan_required": result.get("plan_required", False),
        "step1_reasoning": result.get("reasoning", "Task analysis complete"),
        "step1_complexity_score": result.get("complexity_score", complexity),
        "step1_context_provided": True,  # Mark that context was passed
    }
