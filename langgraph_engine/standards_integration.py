"""
Standards Integration Points - Level 2 Standards System

Defines WHERE and HOW standards are applied during execution flow.
Each integration point hooks into a specific step to ensure compliance.

5 Integration Points:
  Step 1  - Before plan mode decision: inject standards context for complexity scoring
  Step 2  - During plan execution: inject naming/layer constraints for planner
  Step 5  - After skill selection: validate skill is compatible with project standards
  Step 10 - During code review: build compliance checklist from active standards
  Step 13 - During doc update: specify required documentation files and formats

Priority ordering used by conflict resolution (from standard_selector.py):
  custom(4) > team(3) > framework(2) > language(1)
  Higher numeric priority = higher precedence = wins on rule conflicts.

Uses ErrorLogger from error_logger.py for audit trail.
"""

from typing import Any, Dict, List

from .error_logger import ErrorLogger
from .flow_state import FlowState

# ============================================================================
# INTEGRATION POINTS REGISTRY
# ============================================================================

STANDARDS_INTEGRATION_POINTS = {
    "step_1": {
        "location": "Plan mode decision",
        "purpose": "Load standards for complexity assessment",
        "trigger": "before_plan_decision",
        "applies_to": ["all"],
        "blocking": False,
        "description": (
            "Standards are loaded before the plan mode decision so that "
            "complexity scoring can account for project conventions and required "
            "tooling. This prevents over-engineering simple tasks."
        ),
    },
    "step_2": {
        "location": "Plan execution",
        "purpose": "Ensure plan follows project standards",
        "trigger": "during_planning",
        "applies_to": ["all"],
        "blocking": False,
        "description": (
            "During plan execution, standards are injected so that file naming, "
            "layer separation, and framework-specific patterns are respected in "
            "the generated plan structure."
        ),
    },
    "step_5": {
        "location": "Skill selection",
        "purpose": "Validate skill selection against standards",
        "trigger": "after_skill_selection",
        "applies_to": ["all"],
        "blocking": True,
        "description": (
            "After skill/agent selection, standards are checked to confirm the "
            "chosen skill is appropriate for the project type. A Python-Flask "
            "standard would reject a Java-only skill being applied to a Python "
            "project."
        ),
    },
    "step_10": {
        "location": "Code review",
        "purpose": "Code review checks standards compliance",
        "trigger": "during_implementation",
        "applies_to": ["all"],
        "blocking": True,
        "description": (
            "During the implementation review step, code is evaluated against "
            "loaded standards (naming conventions, docstring format, test coverage "
            "thresholds). Review failures trigger a retry loop up to 3 times."
        ),
    },
    "step_13": {
        "location": "Documentation",
        "purpose": "Documentation matches standards",
        "trigger": "during_doc_update",
        "applies_to": ["all"],
        "blocking": False,
        "description": (
            "When updating documentation, standards specify which files must be "
            "updated (e.g., CLAUDE.md, README.md), the required format, and "
            "whether a version bump is needed."
        ),
    },
}


# ============================================================================
# STANDARDS LOADER HELPER
# ============================================================================


def load_standards(state: FlowState) -> Dict[str, Any]:
    """Load applicable standards from FlowState.

    Aggregates all standards data from FlowState into a single
    dict for use by integration hooks. Includes:
    - Tool optimization rules (from tool_optimization_rules state field)
    - Spring Boot patterns (from spring_boot_patterns state field)
    - Merged rules from standards selector (from standards_merged_rules state field)
    - Framework detection result (from standard_selector.detect_framework)

    Args:
        state: Current FlowState with loaded standards data.

    Returns:
        Dict with standards data and metadata keyed by standards domain.
    """
    standards: Dict[str, Any] = {}

    # Tool optimization rules (always present after Level 2)
    tool_rules = state.get("tool_optimization_rules")
    if tool_rules:
        standards["tool_optimization"] = tool_rules

    # Java/Spring standards
    spring_patterns = state.get("spring_boot_patterns")
    if spring_patterns:
        standards["spring_boot"] = spring_patterns

    # Merged rules from standards selector (conflict-resolved)
    merged_rules = state.get("standards_merged_rules")
    if merged_rules:
        standards["merged_rules"] = merged_rules

    # Full standards selection result (includes traceability)
    standards_selection = state.get("standards_selection")
    if standards_selection:
        standards["selection"] = standards_selection

    # Derive project_type from multiple sources (most specific wins)
    is_java = state.get("is_java_project", False)
    detected_framework = state.get("detected_framework", "")
    selection_project_type = (standards_selection or {}).get("project_type", "") if standards_selection else ""

    # Use selection result when available (most accurate), else fall back to is_java flag
    if selection_project_type:
        project_type = selection_project_type
    elif is_java:
        project_type = "java"
    else:
        project_type = "python"

    # Standards count from common loader
    standards_count = state.get("standards_count", 0)
    standards["__meta"] = {
        "count": standards_count,
        "loaded": state.get("standards_loaded", False),
        "level2_status": state.get("level2_status", "UNKNOWN"),
        "project_type": project_type,
        "framework": detected_framework or (standards_selection or {}).get("framework", "unknown"),
        "priority_chain": "custom(4) > team(3) > framework(2) > language(1)",
    }

    return standards


# ============================================================================
# INTEGRATION HOOK IMPLEMENTATIONS
# ============================================================================


def apply_standards_at_step(step: int, state: FlowState) -> FlowState:
    """Apply standards at a specific pipeline step.

    Entry point for all standard enforcement. Looks up the integration point
    definition, loads applicable standards, validates them, and merges the
    result back into state.

    Args:
        step: Step number (1, 2, 5, 10, or 13).
        state: Current FlowState.

    Returns:
        Updated FlowState with standards_applied_at_step_N flag set.
    """
    step_key = f"step_{step}"
    integration = STANDARDS_INTEGRATION_POINTS.get(step_key)

    if not integration:
        # No integration point defined for this step - silently pass through
        return state

    import os

    session_id = state.get("session_id") or os.environ.get("CURRENT_SESSION_ID", "") or "unknown-session"
    logger = ErrorLogger(session_id)

    logger.log_decision(
        step=f"Level 2 Standards - Step {step}",
        decision=f"Applying standards at {integration['location']}",
        reasoning=integration["purpose"],
        options=["apply", "skip"],
        chosen_option="apply",
    )

    standards = load_standards(state)

    # Dispatch to the correct integration hook
    hook_dispatch = {
        1: _apply_step1_standards,
        2: _apply_step2_standards,
        5: _apply_step5_standards,
        10: _apply_step10_standards,
        13: _apply_step13_standards,
    }

    hook_fn = hook_dispatch.get(step)
    if hook_fn:
        try:
            result = hook_fn(state, standards, logger)
            if result:
                state.update(result)
        except Exception as exc:
            logger.log_error(
                step=f"Level 2 - Step {step}",
                error_message=f"Standards hook raised an exception: {exc}",
                severity="WARNING",
                error_type="StandardsHookError",
                recovery_action="Continuing without standards enforcement for this step",
                context={"step": step, "integration_point": step_key},
            )

    # Mark that standards were applied at this step
    state[f"standards_applied_step{step}"] = True
    logger.save_audit_trail()

    return state


# ============================================================================
# STEP-SPECIFIC HOOK IMPLEMENTATIONS
# ============================================================================


def _apply_step1_standards(
    state: FlowState,
    standards: Dict[str, Any],
    logger: ErrorLogger,
) -> Dict[str, Any]:
    """Step 1 hook: inject standards metadata before plan mode decision.

    Makes the plan complexity scorer aware of how many standards are active
    so that it can factor framework-mandated boilerplate into its estimate.
    Also exposes the detected framework so Step 1's LLM prompt can tailor
    its complexity assessment to the project's tech stack.

    Returns:
        State updates to merge (sets step1_standards_context in FlowState).
    """
    updates: Dict[str, Any] = {}

    meta = standards.get("__meta", {})
    standards_count = meta.get("count", 0)
    project_type = meta.get("project_type", "unknown")
    framework = meta.get("framework", "unknown")
    has_merged_rules = bool(standards.get("merged_rules"))
    has_selection = bool(standards.get("selection"))

    # Store context so Step 1 LLM prompt can reference it
    updates["step1_standards_context"] = {
        "active_standards": standards_count,
        "project_type": project_type,
        "framework": framework,
        "tool_rules_loaded": "tool_optimization" in standards,
        "merged_rules_available": has_merged_rules,
        "standards_selection_available": has_selection,
        "priority_chain": "custom(4) > team(3) > framework(2) > language(1)",
        "note": (
            f"Account for {project_type}/{framework} standards when scoring complexity. "
            "Higher standard count may increase required steps."
        ),
    }

    logger.log_decision(
        step="Level 2 - Step 1",
        decision="Standards context prepared for plan decision",
        reasoning=f"project_type={project_type}, framework={framework}, active_standards={standards_count}",
        chosen_option="standards_context_injected",
    )

    return updates


def _apply_step2_standards(
    state: FlowState,
    standards: Dict[str, Any],
    logger: ErrorLogger,
) -> Dict[str, Any]:
    """Step 2 hook: inject standards constraints during plan execution.

    Adds framework-specific naming and layer rules to the planning context.

    Returns:
        State updates to merge.
    """
    updates: Dict[str, Any] = {}

    project_type = standards.get("__meta", {}).get("project_type", "unknown")

    constraints = _build_planning_constraints(project_type, standards)

    updates["step2_standards_constraints"] = {
        "project_type": project_type,
        "constraints": constraints,
        "enforce_layers": True,
        "note": "Plan must respect these naming and structural constraints.",
    }

    logger.log_decision(
        step="Level 2 - Step 2",
        decision="Planning constraints injected",
        reasoning=f"project_type={project_type}, constraints count={len(constraints)}",
        chosen_option="constraints_active",
    )

    return updates


def _apply_step5_standards(
    state: FlowState,
    standards: Dict[str, Any],
    logger: ErrorLogger,
) -> Dict[str, Any]:
    """Step 5 hook: validate skill selection against project standards.

    If the selected skill is flagged as incompatible (e.g., a Java-only
    skill assigned to a Python project), log a warning and suggest
    alternatives. Checks cross-language mismatches for Python, Java,
    JavaScript/TypeScript, Go, Rust, and C# projects.

    Integration point: step_5 (blocking=True in STANDARDS_INTEGRATION_POINTS).
    Warnings do NOT block execution - they are recorded in FlowState for
    the Step 11 code review checklist to verify.

    Returns:
        State updates to merge (sets step5_standards_validation in FlowState).
    """
    updates: Dict[str, Any] = {}

    meta = standards.get("__meta", {})
    project_type = meta.get("project_type", "unknown")
    framework = meta.get("framework", "unknown")
    selected_skill = state.get("step5_skill", "") or ""
    selected_agent = state.get("step5_agent", "") or ""

    validation_warnings: List[str] = []
    validation_info: List[str] = []

    # Cross-language mismatch checks
    cross_type_checks = [
        ("java", _is_python_only_skill, "Python-only", "Java/Spring"),
        ("python", _is_java_only_skill, "Java-only", "Python/Flask/Django/FastAPI"),
        ("go", _is_python_only_skill, "Python-only", "Go"),
        ("go", _is_java_only_skill, "Java-only", "Go"),
        ("rust", _is_python_only_skill, "Python-only", "Rust"),
        ("rust", _is_java_only_skill, "Java-only", "Rust"),
    ]

    for pt, check_fn, skill_label, suggestion in cross_type_checks:
        if project_type == pt and check_fn(selected_skill):
            msg = (
                f"Skill '{selected_skill}' appears {skill_label} but project is {project_type.upper()}. "
                f"Consider using a {suggestion} skill instead."
            )
            validation_warnings.append(msg)
            logger.log_error(
                step="Level 2 - Step 5",
                error_message=msg,
                severity="WARNING",
                error_type="SkillMismatch",
                recovery_action="Warning logged; execution continues with selected skill",
                context={
                    "project_type": project_type,
                    "framework": framework,
                    "selected_skill": selected_skill,
                },
            )
            break  # Only one mismatch message per skill

    if not validation_warnings:
        validation_info.append(f"Skill '{selected_skill}' is compatible with {project_type}/{framework} project")

    updates["step5_standards_validation"] = {
        "passed": len(validation_warnings) == 0,
        "warnings": validation_warnings,
        "info": validation_info,
        "project_type": project_type,
        "framework": framework,
        "skill_checked": selected_skill,
        "agent_checked": selected_agent,
        "traceability": {
            "checks_run": len(cross_type_checks),
            "priority_chain": meta.get("priority_chain", "custom(4) > team(3) > framework(2) > language(1)"),
        },
    }

    logger.log_validation_result(
        step="Level 2 - Step 5",
        check_name="Skill/Standards compatibility",
        passed=len(validation_warnings) == 0,
        details=(
            "; ".join(validation_warnings)
            if validation_warnings
            else f"Skill '{selected_skill}' compatible with {project_type}/{framework}"
        ),
    )

    return updates


def _apply_step10_standards(
    state: FlowState,
    standards: Dict[str, Any],
    logger: ErrorLogger,
) -> Dict[str, Any]:
    """Step 10 hook: provide standards checklist for code review.

    Builds a structured checklist based on active standards that the code
    review step can use to verify compliance.

    Returns:
        State updates to merge.
    """
    updates: Dict[str, Any] = {}

    project_type = standards.get("__meta", {}).get("project_type", "unknown")
    checklist = _build_review_checklist(project_type, standards)

    updates["step10_standards_checklist"] = {
        "checklist": checklist,
        "total_checks": len(checklist),
        "project_type": project_type,
        "note": "All checklist items must pass before PR can be merged.",
    }

    logger.log_decision(
        step="Level 2 - Step 10",
        decision="Code review standards checklist prepared",
        reasoning=f"project_type={project_type}, checks={len(checklist)}",
        chosen_option="checklist_ready",
    )

    return updates


def _apply_step13_standards(
    state: FlowState,
    standards: Dict[str, Any],
    logger: ErrorLogger,
) -> Dict[str, Any]:
    """Step 13 hook: specify documentation requirements from standards.

    Returns a list of files that must be updated and the expected format
    for each, derived from the active standards.

    Returns:
        State updates to merge.
    """
    updates: Dict[str, Any] = {}

    project_type = standards.get("__meta", {}).get("project_type", "unknown")
    doc_requirements = _build_doc_requirements(project_type, standards)

    updates["step13_standards_doc_requirements"] = {
        "required_updates": doc_requirements,
        "total_required": len(doc_requirements),
        "project_type": project_type,
        "note": "Documentation must satisfy these requirements before closure.",
    }

    logger.log_decision(
        step="Level 2 - Step 13",
        decision="Documentation requirements loaded from standards",
        reasoning=f"project_type={project_type}, required_updates={len(doc_requirements)}",
        chosen_option="doc_requirements_set",
    )

    return updates


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _build_planning_constraints(
    project_type: str,
    standards: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Build planning constraints based on project type."""
    constraints: List[Dict[str, str]] = []

    if project_type == "python":
        constraints += [
            {"rule": "naming.files", "value": "snake_case.py"},
            {"rule": "naming.classes", "value": "PascalCase"},
            {"rule": "naming.functions", "value": "snake_case"},
            {"rule": "structure.business_logic", "value": "services/ layer"},
            {"rule": "structure.data_access", "value": "repositories/ layer"},
            {"rule": "structure.endpoints", "value": "routes/ layer (thin handlers)"},
        ]
    elif project_type == "java":
        spring_patterns = standards.get("spring_boot", {})
        annotations = spring_patterns.get("annotations", [])
        patterns = spring_patterns.get("patterns", [])

        constraints += [
            {"rule": "naming.classes", "value": "PascalCase"},
            {"rule": "naming.methods", "value": "camelCase"},
            {"rule": "annotations.required", "value": ", ".join(annotations)},
            {"rule": "patterns.required", "value": ", ".join(patterns)},
        ]

    return constraints


def _build_review_checklist(
    project_type: str,
    standards: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Build code review checklist derived from active standards."""
    checklist: List[Dict[str, str]] = []

    # Universal checks
    checklist += [
        {"check": "no_syntax_errors", "description": "Code has no syntax errors"},
        {"check": "no_bare_except", "description": "No bare except clauses"},
        {"check": "no_hardcoded_secrets", "description": "No hardcoded API keys or passwords"},
    ]

    if project_type == "python":
        checklist += [
            {"check": "snake_case_functions", "description": "All function names use snake_case"},
            {"check": "pascal_case_classes", "description": "All class names use PascalCase"},
            {"check": "type_hints_present", "description": "Public functions have type hints"},
            {"check": "docstrings_present", "description": "Public functions have docstrings"},
            {"check": "pytest_tests_exist", "description": "pytest tests present for new code"},
            {"check": "service_layer_separation", "description": "Business logic in services/, not in route handlers"},
        ]

        # Tool optimization check
        tool_rules = standards.get("tool_optimization", {})
        if tool_rules:
            checklist.append(
                {
                    "check": "tool_optimization_compliant",
                    "description": (
                        f"Read calls respect {tool_rules.get('read_max_lines', 500)} line limit; "
                        f"Grep calls use head_limit <= {tool_rules.get('grep_max_results', 100)}"
                    ),
                }
            )

    elif project_type == "java":
        checklist += [
            {"check": "spring_annotations", "description": "Spring annotations used correctly"},
            {"check": "service_layer", "description": "@Service classes contain business logic"},
            {"check": "repository_layer", "description": "@Repository classes handle persistence"},
            {"check": "exception_handling", "description": "Exceptions handled via @ControllerAdvice or similar"},
        ]

    return checklist


def _build_doc_requirements(
    project_type: str,
    standards: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Build documentation update requirements from standards."""
    requirements: List[Dict[str, str]] = [
        {
            "file": "CLAUDE.md",
            "action": "update",
            "note": "Reflect any new components, patterns, or dependencies added",
        },
    ]

    if project_type == "python":
        requirements += [
            {
                "file": "requirements.txt",
                "action": "update_if_changed",
                "note": "Keep in sync if new packages were added",
            },
        ]
    elif project_type == "java":
        requirements += [
            {
                "file": "pom.xml / build.gradle",
                "action": "update_if_changed",
                "note": "Keep dependency versions accurate",
            },
        ]

    return requirements


def _is_python_only_skill(skill_name: str) -> bool:
    """Return True if a skill name is clearly Python-only."""
    python_keywords = {"flask", "django", "fastapi", "python", "pydantic", "sqlalchemy"}
    name_lower = skill_name.lower()
    return any(kw in name_lower for kw in python_keywords)


def _is_java_only_skill(skill_name: str) -> bool:
    """Return True if a skill name is clearly Java-only."""
    java_keywords = {"spring", "java", "maven", "gradle", "hibernate", "jpa", "quarkus"}
    name_lower = skill_name.lower()
    return any(kw in name_lower for kw in java_keywords)
