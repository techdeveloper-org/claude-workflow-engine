"""
Level 3 Execution - Step 4: TOON Refinement
"""

from ....flow_state import FlowState


def step4_toon_refinement(state: FlowState) -> dict:
    """Step 4: TOON Refinement - Enhance TOON with FULL task context.

    Enriches initial TOON from Level 1 with:
    - Validated task breakdown from Step 3
    - Plan details from Step 2 (if planning enabled)
    - Complexity score from Step 0
    - Skill hints from patterns

    This prepares comprehensive TOON for skill/agent selection in Step 5.
    """

    try:
        # Get initial TOON from Level 1
        level1_toon = state.get("level1_context_toon", {})
        if not level1_toon:
            return {"step4_toon_refined": level1_toon, "step4_refinement_status": "SKIPPED"}

        # Get ALL task context
        validated_tasks = state.get("step3_tasks_validated", [])
        plan_details = state.get("step2_plan_execution", {})
        task_type = state.get("step0_task_type", "")
        complexity = state.get("step0_complexity", 5)
        patterns = state.get("patterns_detected", [])
        user_message = state.get("user_message", "")

        # Build complete refinement context
        refinement_data = {
            "user_message": user_message,
            "task_type": task_type,
            "complexity": complexity,
            "plan_details": plan_details,
            "validated_tasks": validated_tasks,
            "patterns_detected": patterns,
        }

        # Enhance TOON with ALL insights
        refined_toon = dict(level1_toon)

        # Add task insights from validated tasks
        if validated_tasks:
            task_files = set()
            task_deps = []
            for task in validated_tasks:
                task_files.update(task.get("files", []))
                if task.get("dependencies"):
                    task_deps.append(task.get("dependencies"))

            refined_toon["estimated_files"] = len(task_files)
            refined_toon["has_dependencies"] = len(task_deps) > 0
            refined_toon["task_descriptions"] = [t.get("description", "") for t in validated_tasks]

        # Add plan insights
        if plan_details:
            refined_toon["planned_phases"] = len(plan_details.get("phases", []))
            refined_toon["planned_steps"] = plan_details.get("estimated_steps", 0)

        # Add pattern insights for better skill selection
        if patterns:
            refined_toon["detected_patterns"] = patterns

        # Adjust complexity based on actual tasks
        base_complexity = refined_toon.get("complexity_score", 5)
        adjusted_complexity = min(10, base_complexity + (len(validated_tasks) - 1) // 2)
        refined_toon["adjusted_complexity"] = adjusted_complexity
        refined_toon["refinement_context"] = refinement_data  # Store full context

        return {
            "step4_toon_refined": refined_toon,
            "step4_refinement_status": "OK",
            "step4_complexity_adjusted": adjusted_complexity,
            "step4_context_provided": True,  # Mark that full context was used
            "step4_tasks_included": len(validated_tasks),
        }

    except Exception as e:
        return {
            "step4_toon_refined": state.get("level1_context_toon", {}),
            "step4_refinement_status": "ERROR",
            "step4_error": str(e),
        }
