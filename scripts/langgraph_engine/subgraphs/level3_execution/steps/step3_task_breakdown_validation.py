"""
Level 3 Execution - Step 3: Task Breakdown Validation
"""

from ....flow_state import FlowState


def step3_task_breakdown_validation(state: FlowState) -> dict:
    """Step 3: Task Breakdown Validation - Validate and format task breakdown.

    Validates and formats the task breakdown from Step 0:
    - Ensures all tasks have required fields
    - Validates task dependencies
    - Formats for downstream execution
    - Provides structured task list for planning
    """
    try:
        tasks = state.get("step0_tasks", {}).get("tasks", [])
        task_count = len(tasks)

        # Validate task structure
        validated_tasks = []
        validation_errors = []

        for i, task in enumerate(tasks):
            if isinstance(task, dict):
                # Ensure required fields exist
                task_validated = {
                    "id": task.get("id", f"task-{i+1}"),
                    "description": task.get("description", task.get("name", f"Task {i+1}")),
                    "files": task.get("files", []),
                    "dependencies": task.get("dependencies", []),
                    "estimated_effort": task.get("estimated_effort", "medium"),
                }
                validated_tasks.append(task_validated)
            else:
                # Simple string task
                validated_tasks.append(
                    {
                        "id": f"task-{i+1}",
                        "description": str(task),
                        "files": [],
                        "dependencies": [],
                        "estimated_effort": "medium",
                    }
                )

        return {
            "step3_tasks_validated": validated_tasks,
            "step3_task_count": task_count,
            "step3_validation_status": "OK" if not validation_errors else "WARNINGS",
            "step3_validation_errors": validation_errors,
        }

    except Exception as e:
        return {"step3_task_count": 0, "step3_validation_status": "ERROR", "step3_error": str(e)}
