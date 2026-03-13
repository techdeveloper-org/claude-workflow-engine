"""
Step I/O Validator - Input and output schema validation for all 14 Level 3 steps.

Each step has a validate_step_N_input() and validate_step_N_output() method.
Validators are intentionally strict on required fields and lenient on optional
ones - they never raise exceptions, always return (valid, errors).

Return convention:
    Tuple[bool, List[str]]
    True  = valid (errors is empty)
    False = invalid (errors contains human-readable messages)
"""

from typing import Any, Dict, List, Tuple
from loguru import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_keys(d: Dict[str, Any], keys: List[str], prefix: str) -> List[str]:
    """Return error strings for any of 'keys' missing (None or absent) in dict d."""
    errors: List[str] = []
    for k in keys:
        if d.get(k) is None:
            errors.append(f"{prefix}: Missing required field '{k}'")
    return errors


def _require_type(d: Dict[str, Any], key: str, expected_type: type, prefix: str) -> List[str]:
    """Return error string if d[key] exists but has wrong type."""
    val = d.get(key)
    if val is not None and not isinstance(val, expected_type):
        return [f"{prefix}: Field '{key}' must be {expected_type.__name__}, got {type(val).__name__}"]
    return []


def _non_empty_str(d: Dict[str, Any], key: str, prefix: str) -> List[str]:
    """Return error if d[key] is present but empty/whitespace string."""
    val = d.get(key)
    if isinstance(val, str) and not val.strip():
        return [f"{prefix}: Field '{key}' must not be empty"]
    return []


# ---------------------------------------------------------------------------
# StepValidator class
# ---------------------------------------------------------------------------

class StepValidator:
    """Validates input and output dicts for all 14 Level 3 steps."""

    # ==========================================================================
    # STEP 1 - Plan Mode Decision
    # ==========================================================================

    def validate_step_1_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate Step 1 input state.

        Required:
            toon_object (dict) or level1_context_toon (dict)
            user_requirement (str) or user_message (str)
        """
        errors: List[str] = []
        prefix = "Step1Input"

        # Accept either field name for TOON
        toon = state.get("toon_object") or state.get("level1_context_toon")
        if not toon:
            errors.append(f"{prefix}: Missing TOON object (toon_object or level1_context_toon)")

        # Accept either field name for requirement
        req = state.get("user_requirement") or state.get("user_message")
        if not req:
            errors.append(f"{prefix}: Missing user requirement (user_requirement or user_message)")

        return _result(errors, "Step1Input")

    def validate_step_1_output(self, decision: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate Step 1 output.

        Required:
            plan_required (bool)
            reasoning (str, non-empty)
        """
        errors: List[str] = []
        prefix = "Step1Output"

        if not isinstance(decision.get("plan_required"), bool):
            errors.append(f"{prefix}: 'plan_required' must be a boolean")

        errors += _non_empty_str(decision, "reasoning", prefix)
        if decision.get("reasoning") is None:
            errors.append(f"{prefix}: Missing 'reasoning'")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 2 - Plan Execution
    # ==========================================================================

    def validate_step_2_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: toon, user_requirement, step1_plan_required=True."""
        errors: List[str] = []
        prefix = "Step2Input"

        toon = state.get("toon_object") or state.get("level1_context_toon")
        if not toon:
            errors.append(f"{prefix}: Missing TOON object")

        req = state.get("user_requirement") or state.get("user_message")
        if not req:
            errors.append(f"{prefix}: Missing user_requirement")

        if state.get("step1_plan_required") is False:
            errors.append(f"{prefix}: step1_plan_required is False - Step 2 should be skipped")

        return _result(errors, prefix)

    def validate_step_2_output(self, plan: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: plan (str), files_affected (list), phases (list)."""
        errors: List[str] = []
        prefix = "Step2Output"

        errors += _require_keys(plan, ["plan"], prefix)
        errors += _non_empty_str(plan, "plan", prefix)
        errors += _require_type(plan, "files_affected", list, prefix)
        errors += _require_type(plan, "phases", list, prefix)

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 3 - Task Breakdown
    # ==========================================================================

    def validate_step_3_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: user_requirement (or user_message)."""
        errors: List[str] = []
        prefix = "Step3Input"

        req = state.get("user_requirement") or state.get("user_message")
        if not req:
            errors.append(f"{prefix}: Missing user_requirement")

        return _result(errors, prefix)

    def validate_step_3_output(self, tasks: Any) -> Tuple[bool, List[str]]:
        """Requires: non-empty list of task dicts each with an 'id' and 'name'."""
        errors: List[str] = []
        prefix = "Step3Output"

        if not isinstance(tasks, list):
            errors.append(f"{prefix}: tasks must be a list")
            return _result(errors, prefix)

        if len(tasks) == 0:
            errors.append(f"{prefix}: Task list must not be empty")

        for i, task in enumerate(tasks):
            if not isinstance(task, dict):
                errors.append(f"{prefix}: Task at index {i} is not a dict")
                continue
            if not task.get("id") and task.get("id") != 0:
                errors.append(f"{prefix}: Task at index {i} missing 'id'")
            name = task.get("name") or task.get("title") or ""
            if not name.strip():
                errors.append(f"{prefix}: Task at index {i} missing 'name'/'title'")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 4 - TOON Refinement
    # ==========================================================================

    def validate_step_4_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step3_tasks (list), level1_context_toon (dict)."""
        errors: List[str] = []
        prefix = "Step4Input"

        tasks = state.get("step3_tasks") or state.get("step3_tasks_validated")
        if not tasks:
            errors.append(f"{prefix}: Missing step3_tasks")

        toon = state.get("level1_context_toon")
        if not toon:
            errors.append(f"{prefix}: Missing level1_context_toon")

        return _result(errors, prefix)

    def validate_step_4_output(self, blueprint: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: complexity_score (int), plan (str)."""
        errors: List[str] = []
        prefix = "Step4Output"

        if blueprint.get("complexity_score") is None:
            errors.append(f"{prefix}: Missing complexity_score")
        elif not isinstance(blueprint["complexity_score"], int):
            errors.append(f"{prefix}: complexity_score must be int")

        errors += _non_empty_str(blueprint, "plan", prefix)

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 5 - Skill Selection
    # ==========================================================================

    def validate_step_5_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step3_tasks (list)."""
        errors: List[str] = []
        prefix = "Step5Input"

        tasks = state.get("step3_tasks") or state.get("step3_tasks_validated")
        if not tasks:
            errors.append(f"{prefix}: Missing task list for skill selection")

        return _result(errors, prefix)

    def validate_step_5_output(self, selection: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step5_skills or step5_available_skills (list)."""
        errors: List[str] = []
        prefix = "Step5Output"

        skills = selection.get("step5_skills") or selection.get("step5_available_skills")
        if skills is None:
            errors.append(f"{prefix}: Missing skill selection result")
        elif not isinstance(skills, list):
            errors.append(f"{prefix}: Skill selection must be a list")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 6 - Skill Validation & Download
    # ==========================================================================

    def validate_step_6_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step5_skills or step5_available_skills."""
        errors: List[str] = []
        prefix = "Step6Input"

        skills = state.get("step5_skills") or state.get("step5_available_skills")
        if skills is None:
            errors.append(f"{prefix}: Missing step5 skill selection")

        return _result(errors, prefix)

    def validate_step_6_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step6_skill_ready (bool)."""
        errors: List[str] = []
        prefix = "Step6Output"

        if not isinstance(result.get("step6_skill_ready"), bool):
            errors.append(f"{prefix}: 'step6_skill_ready' must be a boolean")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 7 - Final Prompt Generation
    # ==========================================================================

    def validate_step_7_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step3_tasks (list), user_requirement."""
        errors: List[str] = []
        prefix = "Step7Input"

        req = state.get("user_requirement") or state.get("user_message")
        if not req:
            errors.append(f"{prefix}: Missing user_requirement")

        tasks = state.get("step3_tasks") or state.get("step3_tasks_validated")
        if not tasks:
            errors.append(f"{prefix}: Missing task list")

        return _result(errors, prefix)

    def validate_step_7_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step7_execution_prompt (str, non-empty)."""
        errors: List[str] = []
        prefix = "Step7Output"

        prompt = result.get("step7_execution_prompt") or result.get("execution_prompt") or ""
        if not prompt or not prompt.strip():
            errors.append(f"{prefix}: Missing or empty execution prompt")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 8 - GitHub Issue Creation
    # ==========================================================================

    def validate_step_8_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step7_execution_prompt, user_requirement."""
        errors: List[str] = []
        prefix = "Step8Input"

        req = state.get("user_requirement") or state.get("user_message")
        if not req:
            errors.append(f"{prefix}: Missing user_requirement")

        return _result(errors, prefix)

    def validate_step_8_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step8_issue_id (str), step8_issue_created (bool)."""
        errors: List[str] = []
        prefix = "Step8Output"

        if not isinstance(result.get("step8_issue_created"), bool):
            errors.append(f"{prefix}: 'step8_issue_created' must be boolean")

        if result.get("step8_issue_created") and not result.get("step8_issue_id"):
            errors.append(f"{prefix}: 'step8_issue_id' required when issue was created")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 9 - Branch Creation
    # ==========================================================================

    def validate_step_9_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step8_issue_id."""
        errors: List[str] = []
        prefix = "Step9Input"

        if not state.get("step8_issue_id"):
            errors.append(f"{prefix}: Missing step8_issue_id for branch naming")

        return _result(errors, prefix)

    def validate_step_9_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step9_branch_name (str), step9_branch_created (bool)."""
        errors: List[str] = []
        prefix = "Step9Output"

        if not isinstance(result.get("step9_branch_created"), bool):
            errors.append(f"{prefix}: 'step9_branch_created' must be boolean")

        if result.get("step9_branch_created"):
            name = result.get("step9_branch_name") or ""
            if not name.strip():
                errors.append(f"{prefix}: 'step9_branch_name' required when branch was created")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 10 - Implementation Execution
    # ==========================================================================

    def validate_step_10_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step9_branch_name, step3_tasks."""
        errors: List[str] = []
        prefix = "Step10Input"

        if not state.get("step9_branch_name"):
            errors.append(f"{prefix}: Missing step9_branch_name")

        tasks = state.get("step3_tasks") or state.get("step3_tasks_validated")
        if not tasks:
            errors.append(f"{prefix}: Missing task list for implementation")

        return _result(errors, prefix)

    def validate_step_10_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step10_implementation_status, step10_tasks_executed (int)."""
        errors: List[str] = []
        prefix = "Step10Output"

        if not result.get("step10_implementation_status"):
            errors.append(f"{prefix}: Missing 'step10_implementation_status'")

        tasks_executed = result.get("step10_tasks_executed")
        if tasks_executed is None:
            errors.append(f"{prefix}: Missing 'step10_tasks_executed'")
        elif not isinstance(tasks_executed, int):
            errors.append(f"{prefix}: 'step10_tasks_executed' must be int")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 11 - Pull Request & Code Review
    # ==========================================================================

    def validate_step_11_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step9_branch_name, step8_issue_id."""
        errors: List[str] = []
        prefix = "Step11Input"

        if not state.get("step9_branch_name"):
            errors.append(f"{prefix}: Missing step9_branch_name for PR creation")

        if not state.get("step8_issue_id"):
            errors.append(f"{prefix}: Missing step8_issue_id for PR linkage")

        return _result(errors, prefix)

    def validate_step_11_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step11_review_passed (bool)."""
        errors: List[str] = []
        prefix = "Step11Output"

        if not isinstance(result.get("step11_review_passed"), bool):
            errors.append(f"{prefix}: 'step11_review_passed' must be boolean")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 12 - Issue Closure
    # ==========================================================================

    def validate_step_12_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step8_issue_id, step11_review_passed=True."""
        errors: List[str] = []
        prefix = "Step12Input"

        if not state.get("step8_issue_id"):
            errors.append(f"{prefix}: Missing step8_issue_id")

        if state.get("step11_review_passed") is False:
            errors.append(f"{prefix}: step11_review_passed is False - cannot close issue")

        return _result(errors, prefix)

    def validate_step_12_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step12_issue_closed (bool)."""
        errors: List[str] = []
        prefix = "Step12Output"

        if not isinstance(result.get("step12_issue_closed"), bool):
            errors.append(f"{prefix}: 'step12_issue_closed' must be boolean")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 13 - Project Documentation
    # ==========================================================================

    def validate_step_13_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step10_modified_files (list)."""
        errors: List[str] = []
        prefix = "Step13Input"

        modified = state.get("step10_modified_files")
        if modified is None:
            errors.append(f"{prefix}: Missing step10_modified_files")
        elif not isinstance(modified, list):
            errors.append(f"{prefix}: step10_modified_files must be a list")

        return _result(errors, prefix)

    def validate_step_13_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step13_updates_prepared (bool)."""
        errors: List[str] = []
        prefix = "Step13Output"

        if not isinstance(result.get("step13_updates_prepared"), bool):
            errors.append(f"{prefix}: 'step13_updates_prepared' must be boolean")

        return _result(errors, prefix)

    # ==========================================================================
    # STEP 14 - Final Summary
    # ==========================================================================

    def validate_step_14_input(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: level3_status or step12_issue_closed present."""
        errors: List[str] = []
        prefix = "Step14Input"

        if not state.get("level3_status") and not state.get("step12_issue_closed"):
            errors.append(
                f"{prefix}: Missing level3_status or step12_issue_closed - "
                "pipeline may not be complete"
            )

        return _result(errors, prefix)

    def validate_step_14_output(self, result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Requires: step14_summary (dict or str, non-empty)."""
        errors: List[str] = []
        prefix = "Step14Output"

        summary = result.get("step14_summary")
        if summary is None:
            errors.append(f"{prefix}: Missing 'step14_summary'")
        elif isinstance(summary, str) and not summary.strip():
            errors.append(f"{prefix}: 'step14_summary' must not be empty")
        elif isinstance(summary, dict) and not summary:
            errors.append(f"{prefix}: 'step14_summary' dict must not be empty")

        return _result(errors, prefix)


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _result(errors: List[str], label: str) -> Tuple[bool, List[str]]:
    """Standardise return and emit a single log line per validation call."""
    valid = len(errors) == 0
    if valid:
        logger.debug(f"[StepValidator] {label}: PASS")
    else:
        logger.warning(f"[StepValidator] {label}: FAIL ({len(errors)} error(s)): {errors}")
    return valid, errors
