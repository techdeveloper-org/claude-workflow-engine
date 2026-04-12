"""
Decision Explainer - Human-readable explanations for all pipeline decisions.

Explains three categories of decisions:
1. Plan Required Decision (Step 1) - Why detailed planning was or was not needed
2. Skill Selection Decision (Step 5) - Why a particular skill was chosen
3. Approach Decision (Step 10) - Why a specific implementation approach was chosen

Each explanation includes:
- Primary reason (the main factor that drove the decision)
- Supporting evidence (data points from the pipeline state)
- Alternatives considered (what other options were evaluated)
- Confidence score (0-100)

Usage:
    from .decision_explainer import DecisionExplainer

    explainer = DecisionExplainer()

    # Explain plan decision
    plan_exp = explainer.explain_plan_decision(
        plan_required=True,
        task_complexity=8,
        task_count=5,
        reasoning="Multiple files need modification with potential conflicts",
    )
    print(plan_exp.summary)

    # Explain skill selection
    skill_exp = explainer.explain_skill_selection(
        selected_skill="python-backend-engineer",
        task_description="Build REST API with Flask",
        candidate_skills=["python-backend-engineer", "flask-expert"],
        capability_scores={"python-backend-engineer": 92, "flask-expert": 85},
    )
    print(skill_exp.summary)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Explanation dataclass
# ---------------------------------------------------------------------------


@dataclass
class DecisionExplanation:
    """Structured explanation for a pipeline decision."""

    decision_type: str  # plan / skill / approach
    decision_made: str  # Short label for the decision taken
    primary_reason: str  # Single sentence explaining the main driver
    supporting_evidence: List[str] = field(default_factory=list)
    alternatives_considered: List[str] = field(default_factory=list)
    confidence: int = 0  # 0-100
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Return a compact multi-line summary suitable for console output."""
        lines = [
            f"Decision: {self.decision_made}",
            f"Why: {self.primary_reason}",
            f"Confidence: {self.confidence}%",
        ]
        if self.supporting_evidence:
            lines.append("Evidence:")
            for ev in self.supporting_evidence:
                lines.append(f"  - {ev}")
        if self.alternatives_considered:
            lines.append("Alternatives considered:")
            for alt in self.alternatives_considered:
                lines.append(f"  - {alt}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "decision_type": self.decision_type,
            "decision_made": self.decision_made,
            "primary_reason": self.primary_reason,
            "supporting_evidence": self.supporting_evidence,
            "alternatives_considered": self.alternatives_considered,
            "confidence": self.confidence,
            "extra": self.extra,
        }


# ---------------------------------------------------------------------------
# Threshold and scoring constants
# ---------------------------------------------------------------------------

# Complexity thresholds that drive the plan decision
COMPLEXITY_PLAN_THRESHOLD = 6  # Score >= this triggers plan mode
TASK_COUNT_PLAN_THRESHOLD = 3  # >= this many sub-tasks triggers plan mode
FILE_COUNT_PLAN_THRESHOLD = 4  # >= this many files triggers plan mode

# Capability score thresholds for skill selection confidence
SKILL_HIGH_CONFIDENCE = 85
SKILL_MEDIUM_CONFIDENCE = 65


# ---------------------------------------------------------------------------
# DecisionExplainer
# ---------------------------------------------------------------------------


class DecisionExplainer:
    """Generates human-readable explanations for all pipeline decisions.

    Designed to be stateless - each explain_* call receives all required
    context as parameters and returns a DecisionExplanation object.
    """

    # -----------------------------------------------------------------------
    # 1. Plan Decision Explanation
    # -----------------------------------------------------------------------

    def explain_plan_decision(
        self,
        plan_required: bool,
        task_complexity: int = 5,
        task_count: int = 1,
        files_affected: int = 0,
        reasoning: str = "",
        model_used: str = "",
        user_message_snippet: str = "",
    ) -> DecisionExplanation:
        """
        Explain why plan mode was required or skipped.

        Args:
            plan_required:        True if Step 1 decided detailed planning was needed.
            task_complexity:      Complexity score (1-10) from complexity_calculator.
            task_count:           Number of sub-tasks identified in breakdown.
            files_affected:       Number of files expected to change.
            reasoning:            Raw reasoning string from the LLM (Step 1 output).
            model_used:           Which inference model was used for this decision.
            user_message_snippet: Short excerpt of the user message (for context).

        Returns:
            DecisionExplanation with full explanation of the plan decision.
        """
        evidence: List[str] = []
        alternatives: List[str] = []
        confidence = 70

        if plan_required:
            decision_label = "Detailed planning required (EnterPlanMode)"

            # Build evidence
            if task_complexity >= COMPLEXITY_PLAN_THRESHOLD:
                evidence.append(
                    f"Task complexity score is {task_complexity}/10 " f"(threshold: {COMPLEXITY_PLAN_THRESHOLD})"
                )
                confidence += 10
            if task_count >= TASK_COUNT_PLAN_THRESHOLD:
                evidence.append(
                    f"Task breaks down into {task_count} sub-tasks " f"(threshold: {TASK_COUNT_PLAN_THRESHOLD})"
                )
                confidence += 5
            if files_affected >= FILE_COUNT_PLAN_THRESHOLD:
                evidence.append(
                    f"{files_affected} files expected to be affected " f"(threshold: {FILE_COUNT_PLAN_THRESHOLD})"
                )
                confidence += 5

            # Derive primary reason
            if reasoning:
                primary = _truncate(reasoning, 120)
            elif task_complexity >= COMPLEXITY_PLAN_THRESHOLD:
                primary = (
                    f"The task has a complexity score of {task_complexity}/10, "
                    "which indicates multiple interdependent changes that require "
                    "structured planning before implementation."
                )
            else:
                primary = (
                    "Multiple factors indicate that unstructured implementation "
                    "would risk missed requirements or conflicting changes."
                )

            alternatives.append("Direct implementation (skipped - too risky without a plan)")
            alternatives.append("Partial planning (skipped - full plan needed given complexity)")

        else:
            decision_label = "Direct implementation (planning skipped)"

            if task_complexity < COMPLEXITY_PLAN_THRESHOLD:
                evidence.append(
                    f"Task complexity score is {task_complexity}/10 " f"(below threshold {COMPLEXITY_PLAN_THRESHOLD})"
                )
                confidence += 10
            if task_count < TASK_COUNT_PLAN_THRESHOLD:
                evidence.append(
                    f"Task involves {task_count} sub-task(s) " f"(below threshold {TASK_COUNT_PLAN_THRESHOLD})"
                )
                confidence += 5

            if reasoning:
                primary = _truncate(reasoning, 120)
            else:
                primary = (
                    f"The task is straightforward with a complexity score of "
                    f"{task_complexity}/10 and {task_count} sub-task(s). "
                    "Direct implementation is efficient and sufficient."
                )

            alternatives.append("Full planning mode (considered but not needed for this complexity)")

        if model_used:
            evidence.append(f"Decision made by: {model_used}")
        if user_message_snippet:
            evidence.append(f'Task summary: "{_truncate(user_message_snippet, 80)}"')

        confidence = min(100, confidence)

        return DecisionExplanation(
            decision_type="plan",
            decision_made=decision_label,
            primary_reason=primary,
            supporting_evidence=evidence,
            alternatives_considered=alternatives,
            confidence=confidence,
            extra={
                "task_complexity": task_complexity,
                "task_count": task_count,
                "files_affected": files_affected,
            },
        )

    # -----------------------------------------------------------------------
    # 2. Skill Selection Explanation
    # -----------------------------------------------------------------------

    def explain_skill_selection(
        self,
        selected_skill: str,
        task_description: str = "",
        candidate_skills: Optional[List[str]] = None,
        capability_scores: Optional[Dict[str, int]] = None,
        missing_capabilities: Optional[List[str]] = None,
        selection_reasoning: str = "",
        llm_query_used: bool = False,
    ) -> DecisionExplanation:
        """
        Explain why a specific skill was selected in Step 5.

        Args:
            selected_skill:       Name of the skill that was selected.
            task_description:     Short description of the task requirements.
            candidate_skills:     All skills that were evaluated.
            capability_scores:    Score (0-100) per skill name.
            missing_capabilities: Capabilities not covered by selected skill.
            selection_reasoning:  Raw reasoning string from skill selector.
            llm_query_used:       True if LLM was needed to break ties.

        Returns:
            DecisionExplanation explaining the skill selection.
        """
        evidence: List[str] = []
        alternatives: List[str] = []
        candidate_skills = candidate_skills or []
        capability_scores = capability_scores or {}
        missing_capabilities = missing_capabilities or []

        selected_score = capability_scores.get(selected_skill, 0)

        if selected_score >= SKILL_HIGH_CONFIDENCE:
            confidence = selected_score
        elif selected_score >= SKILL_MEDIUM_CONFIDENCE:
            confidence = selected_score - 5
        else:
            confidence = max(50, selected_score)

        # Decision label
        if selected_skill:
            decision_label = f"Selected skill: {selected_skill}"
        else:
            decision_label = "No specific skill selected (using general capabilities)"

        # Primary reason
        if selection_reasoning:
            primary = _truncate(selection_reasoning, 150)
        elif selected_skill and selected_score > 0:
            primary = (
                f"'{selected_skill}' scored {selected_score}/100 for capability "
                f"coverage against the task requirements."
            )
        elif selected_skill:
            primary = (
                f"'{selected_skill}' was identified as the best match for "
                "the detected task domain and required capabilities."
            )
        else:
            primary = (
                "No skill in the registry had sufficient capability overlap "
                "with the task requirements. General execution mode applies."
            )

        # Evidence
        if selected_score > 0:
            evidence.append(f"Capability match score: {selected_score}/100")
        if task_description:
            evidence.append(f'Task requirements: "{_truncate(task_description, 80)}"')
        if len(candidate_skills) > 1:
            evidence.append(f"Evaluated {len(candidate_skills)} candidate skill(s)")
        if llm_query_used:
            evidence.append("LLM consulted to break scoring tie between candidates")
        if missing_capabilities:
            missing_str = ", ".join(missing_capabilities[:3])
            evidence.append(f"Gaps in coverage: {missing_str} " "(handled by general implementation)")

        # Alternatives
        for skill in candidate_skills:
            if skill == selected_skill:
                continue
            alt_score = capability_scores.get(skill, 0)
            if alt_score > 0:
                alternatives.append(f"{skill} (score: {alt_score}/100 - ranked lower)")
            else:
                alternatives.append(f"{skill} (evaluated but score unavailable)")

        if not selected_skill:
            alternatives.append("Waiting for matching skill to be added to registry")

        return DecisionExplanation(
            decision_type="skill",
            decision_made=decision_label,
            primary_reason=primary,
            supporting_evidence=evidence,
            alternatives_considered=alternatives,
            confidence=confidence,
            extra={
                "selected_skill": selected_skill,
                "all_candidates": candidate_skills,
                "scores": capability_scores,
            },
        )

    # -----------------------------------------------------------------------
    # 3. Approach Decision Explanation
    # -----------------------------------------------------------------------

    def explain_approach_decision(
        self,
        approach: str,
        task_description: str = "",
        framework: str = "",
        standards_applied: bool = False,
        files_to_modify: Optional[List[str]] = None,
        reasoning: str = "",
        alternatives_evaluated: Optional[List[Dict[str, str]]] = None,
        risk_level: str = "LOW",
    ) -> DecisionExplanation:
        """
        Explain why a specific implementation approach was chosen in Step 10.

        Args:
            approach:               Short label for the chosen approach.
            task_description:       What the task is trying to accomplish.
            framework:              Detected project framework (flask/django/fastapi).
            standards_applied:      True if Level 2 standards were enforced.
            files_to_modify:        List of files that will be changed.
            reasoning:              Raw reasoning from the implementation planner.
            alternatives_evaluated: List of {approach, reason_rejected} dicts.
            risk_level:             LOW / MEDIUM / HIGH - risk assessment.

        Returns:
            DecisionExplanation for the implementation approach.
        """
        evidence: List[str] = []
        alternatives: List[str] = []
        files_to_modify = files_to_modify or []
        alternatives_evaluated = alternatives_evaluated or []

        # Confidence based on risk level
        confidence_map = {"LOW": 90, "MEDIUM": 75, "HIGH": 60}
        confidence = confidence_map.get(risk_level, 75)

        # Decision label
        decision_label = approach if approach else "Standard implementation approach"

        # Primary reason
        if reasoning:
            primary = _truncate(reasoning, 150)
        elif framework:
            primary = (
                f"The {framework} framework conventions and project-specific "
                "standards were used to determine the most maintainable approach."
            )
        else:
            primary = (
                "The approach was selected to minimize risk, maintain code "
                "consistency, and satisfy all task requirements."
            )

        # Evidence
        if framework:
            evidence.append(f"Project framework detected: {framework}")
        if standards_applied:
            evidence.append("Level 2 coding standards applied (naming, structure, layers)")
        if files_to_modify:
            fnames = ", ".join(files_to_modify[:4])
            suffix = f" (+{len(files_to_modify) - 4} more)" if len(files_to_modify) > 4 else ""
            evidence.append(f"Files targeted: {fnames}{suffix}")
        if risk_level != "LOW":
            evidence.append(f"Risk assessment: {risk_level} - additional review recommended")
        if task_description:
            evidence.append(f'Requirement: "{_truncate(task_description, 80)}"')

        # Alternatives
        for alt in alternatives_evaluated:
            alt_approach = alt.get("approach", "Unknown approach")
            alt_reason = alt.get("reason_rejected", "Not selected")
            alternatives.append(f"{alt_approach} - {_truncate(alt_reason, 80)}")

        return DecisionExplanation(
            decision_type="approach",
            decision_made=decision_label,
            primary_reason=primary,
            supporting_evidence=evidence,
            alternatives_considered=alternatives,
            confidence=confidence,
            extra={
                "framework": framework,
                "risk_level": risk_level,
                "files_to_modify": files_to_modify,
                "standards_applied": standards_applied,
            },
        )

    # -----------------------------------------------------------------------
    # Batch explanation from FlowState
    # -----------------------------------------------------------------------

    def explain_from_state(self, state: Dict[str, Any]) -> Dict[str, DecisionExplanation]:
        """
        Generate all available explanations from a pipeline FlowState dict.

        Args:
            state: FlowState dict (or any dict with pipeline fields).

        Returns:
            Dict with key "approach" (where available).
            Note: "plan" and "skill" keys removed -- Steps 1-7 removed in v1.13.
        """
        explanations: Dict[str, DecisionExplanation] = {}

        # Approach decision (derived from orchestrator result)
        orchestrator_result = state.get("orchestrator_result", "")
        if orchestrator_result:
            explanations["approach"] = self.explain_approach_decision(
                approach="Orchestrator-driven implementation",
                task_description=state.get("user_message", "")[:120],
                framework=state.get("detected_framework", ""),
                standards_applied=bool(state.get("standards_applied_step10")),
                files_to_modify=[],
                reasoning=str(orchestrator_result)[:200],
            )

        return explanations


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, appending '...' if truncated."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."
