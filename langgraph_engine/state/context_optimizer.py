"""WorkflowContextOptimizer - Smart context compression for LLM efficiency.

Uses smart filtering and compression to minimize tokens while maintaining info flow.
"""

from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from .state_definition import FlowState


class WorkflowContextOptimizer:
    """Optimizes context passing between workflow steps.

    Uses smart filtering and compression to minimize tokens while maintaining info flow.
    """

    # Rough token estimates: ~4 chars = 1 token
    TOKEN_RATIO = 4

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for text."""
        if isinstance(text, str):
            return len(text) // WorkflowContextOptimizer.TOKEN_RATIO
        return 0

    @staticmethod
    def extract_essential_fields(data: Dict, essential_keys: List[str]) -> Dict:
        """Extract only essential fields from a dict for next step.

        Args:
            data: Full output from current step
            essential_keys: Keys that next step actually needs

        Returns:
            Optimized dict with only essential data
        """
        if not data:
            return {}

        optimized = {}
        for key in essential_keys:
            if key in data:
                optimized[key] = data[key]
        return optimized

    @staticmethod
    def compress_task_list(tasks: List[Dict]) -> Dict:
        """Compress task list for Level 1->2 transition.

        Full: [{"id": 1, "name": "x", "description": "...", "dependencies": []}]
        Compressed: {"_schema": "task_list", "essential": {"count": N, ...}}
        """
        if not tasks:
            essential = {"count": 0, "summary": "No tasks"}
            return {"_schema": "task_list", "essential": essential, "_memory_key": "step1_tasks"}

        essential = {
            "count": len(tasks),
            "summary": "%d tasks identified" % len(tasks),
            "critical_tasks": [t.get("name", "Unknown") for t in tasks[:3]],
            "task_types": list(set(t.get("type", "unknown") for t in tasks)),
        }

        return {"_schema": "task_list", "essential": essential, "_memory_key": "step1_tasks"}

    @staticmethod
    def compress_context_status(context_data: Dict) -> Dict:
        """Compress context status for Level 1->2 transition.

        Full: {"metadata": {...}, "loaded_files": [...], ...}
        Compressed: {"_schema": "context_status", "essential": {"status": "OK", "pct": 85, ...}}
        """
        essential = {
            "status": "OK" if context_data.get("context_loaded") else "PENDING",
            "usage_pct": context_data.get("context_percentage", 0),
            "threshold_exceeded": context_data.get("context_threshold_exceeded", False),
        }

        return {"_schema": "context_status", "essential": essential, "_memory_key": "level1_context"}

    @staticmethod
    def build_optimized_context(state: "FlowState") -> Dict:
        """Build optimized context dict for LLM consumption.

        Rules:
        - Level -1: Keep minimal (status only)
        - Level 1->2: Summary only, not full data
        - Level 2->3: Critical info only
        - Level 3 steps: Only next-step-specific data

        Returns:
            Optimized dict with only LLM-necessary info
        """
        optimized = {}

        # Level -1 outcome (minimal)
        optimized["level_minus1"] = {
            "status": state.get("level_minus1_status", "UNKNOWN"),
            "auto_fixes_applied": len(state.get("auto_fix_applied", [])),
        }

        # Level 1 outcome (summary only)
        if state.get("level1_status"):
            optimized["level1"] = {
                "status": state.get("level1_status"),
                "context": WorkflowContextOptimizer.compress_context_status(
                    {
                        "context_loaded": state.get("context_loaded"),
                        "context_percentage": state.get("context_percentage"),
                        "context_threshold_exceeded": state.get("context_threshold_exceeded"),
                    }
                ),
            }

        # Level 2 outcome (summary only)
        if state.get("level2_status"):
            optimized["level2"] = {
                "status": state.get("level2_status"),
                "standards_active": state.get("standards_count", 0),
                "is_java": state.get("is_java_project", False),
            }

        # Level 3 step context (only what's needed for next step)
        current_step = WorkflowContextOptimizer._find_current_level3_step(state)
        if current_step:
            optimized["current_step"] = {"name": current_step.get("name"), "step_number": current_step.get("order")}

        return optimized

    @staticmethod
    def _find_current_level3_step(state: "FlowState") -> Optional[Dict]:
        """Find the last completed Level 3 step."""
        pipeline = state.get("pipeline", [])
        level3_steps = [s for s in pipeline if s.get("level") == 3]
        return level3_steps[-1] if level3_steps else None

    @staticmethod
    def store_step_output(state: "FlowState", step_name: str, output: Dict) -> "FlowState":
        """Store full step output in workflow_memory."""
        if not state.get("workflow_memory"):
            state["workflow_memory"] = {}

        state["workflow_memory"][step_name] = output

        # Update memory size estimate
        import json

        try:
            size_kb = len(json.dumps(state["workflow_memory"]).encode()) / 1024
            state["workflow_memory_size_kb"] = size_kb
        except Exception:
            pass

        return state

    @staticmethod
    def get_memory_item(state: "FlowState", step_name: str) -> Optional[Dict]:
        """Retrieve full output from workflow memory."""
        memory = state.get("workflow_memory", {})
        return memory.get(step_name)
