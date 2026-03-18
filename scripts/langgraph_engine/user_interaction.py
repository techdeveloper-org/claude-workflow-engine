"""
User Interaction Module - Structured user interaction for the pipeline.

Design
------
Claude Code IS the user interface.  When the pipeline needs user input at any
step, it generates structured questions stored in flow_state.  Claude Code reads
these and presents them to the user.  The user's responses are stored back in
flow_state for the pipeline to continue.

Key insight: the pipeline does NOT block waiting for user input.  Instead it:
  1. Creates interaction requests and appends them to flow_state
  2. Returns control so Claude Code can present the questions
  3. On the next pipeline invocation, reads responses from flow_state

Public API
----------
make_interaction_request(...)     - Factory for InteractionRequest dicts
InteractionManager                - Manages request lifecycle for one session
generate_step0_questions(state)   - Step 0 task-type question
generate_step2_questions(state)   - Step 2 high-risk planning question
generate_step5_questions(state)   - Step 5 low-confidence skill question
generate_step10_questions(state)  - Step 10 unresolved dependency questions
generate_step11_questions(state)  - Step 11 breaking-change review question
generate_step13_questions(state)  - Step 13 major-change doc-update question

Usage
-----
    from scripts.langgraph_engine.user_interaction import (
        InteractionManager,
        generate_step2_questions,
    )

    manager = InteractionManager()
    questions = generate_step2_questions(state)
    for q in questions:
        manager.ask_user(**q)   # or simply append the dicts

    if manager.has_pending():
        # Persist to flow_state and surface to Claude Code
        state["pending_interactions"] = manager.get_all()
        print(manager.to_prompt_context())
    else:
        # All answered - apply responses and continue
        manager.apply_defaults()
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_RISK_LEVELS = frozenset({"low", "medium", "high"})
_VALID_STATUSES = frozenset({"pending", "answered", "applied"})

# Maximum unresolved dependency entries shown per interaction to keep
# the prompt readable.
_MAX_DEP_INTERACTIONS = 3


# ---------------------------------------------------------------------------
# InteractionRequest factory
# ---------------------------------------------------------------------------

def make_interaction_request(
    step: Union[int, str],
    question: str,
    suggestion: str = "",
    options: Optional[List[str]] = None,
    risk_level: str = "low",
    context: str = "",
    fallback: str = "",
) -> Dict[str, Any]:
    """Create a structured interaction request dict.

    The returned dict is JSON-serializable so it can be stored directly in
    flow_state without modification.

    Args:
        step:        Pipeline step number or label (e.g. 2 or "step_2").
        question:    The question presented to the user.
        suggestion:  Claude's recommendation or preferred answer.
        options:     List of answer choices shown to the user.  If None, the
                     user may supply free-form text.
        risk_level:  Severity hint - "low", "medium", or "high".
        context:     Why this question is being asked (shown as help text).
        fallback:    Default answer applied when running non-interactively or
                     when the user does not respond.

    Returns:
        Dict conforming to the InteractionRequest schema.
    """
    if risk_level not in _VALID_RISK_LEVELS:
        logger.warning(
            "make_interaction_request: unknown risk_level %r; defaulting to 'low'",
            risk_level,
        )
        risk_level = "low"

    timestamp_ms = int(time.time() * 1000)
    interaction_id = "interaction_{step}_{ts}".format(
        step=str(step).replace(" ", "_"),
        ts=timestamp_ms,
    )

    return {
        "id": interaction_id,
        "step": step,
        "question": question,
        "suggestion": suggestion,
        "options": list(options) if options is not None else [],
        "risk_level": risk_level,
        "context": context,
        "fallback": fallback,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "response": None,
    }


# ---------------------------------------------------------------------------
# InteractionManager
# ---------------------------------------------------------------------------

class InteractionManager:
    """Manages interaction requests for a single pipeline session.

    All public methods are fail-safe: they catch unexpected exceptions,
    log a warning, and return a safe empty/no-op value so a single bad
    interaction never crashes the pipeline.

    Thread safety: this class is NOT thread-safe.  The LangGraph pipeline
    runs nodes sequentially per state checkpoint so no locking is needed.

    Attributes:
        _interactions: Ordered list of all interaction dicts created this
                       session (includes answered and applied entries).
    """

    def __init__(self) -> None:
        self._interactions: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Core creation helpers
    # ------------------------------------------------------------------

    def ask_user(
        self,
        step: Union[int, str],
        question: str,
        suggestion: str = "",
        options: Optional[List[str]] = None,
        risk_level: str = "low",
        context: str = "",
        fallback: str = "",
    ) -> Dict[str, Any]:
        """Create and register an interaction request.

        Args:
            step:        Pipeline step number or label.
            question:    The question presented to the user.
            suggestion:  Claude's recommendation or preferred answer.
            options:     Answer choices.  Empty list = free-form text.
            risk_level:  "low", "medium", or "high".
            context:     Why this question is being asked.
            fallback:    Default answer for non-interactive runs.

        Returns:
            The new interaction request dict (already stored internally).
        """
        try:
            req = make_interaction_request(
                step=step,
                question=question,
                suggestion=suggestion,
                options=options,
                risk_level=risk_level,
                context=context,
                fallback=fallback,
            )
            self._interactions.append(req)
            logger.debug(
                "InteractionManager.ask_user: created %s (step=%s, risk=%s)",
                req["id"],
                step,
                risk_level,
            )
            return req
        except Exception as exc:  # pragma: no cover
            logger.warning("ask_user failed unexpectedly: %s", exc)
            return {}

    def confirm_with_user(
        self,
        step: Union[int, str],
        action_description: str,
        risk_level: str = "medium",
    ) -> Dict[str, Any]:
        """Ask the user to confirm or skip a risky action.

        The question is auto-generated from *action_description*.

        Args:
            step:               Pipeline step number or label.
            action_description: Human-readable description of the action.
            risk_level:         "low", "medium", or "high".

        Returns:
            The new interaction request dict.
        """
        try:
            return self.ask_user(
                step=step,
                question="Should I proceed with: %s?" % action_description,
                suggestion="Proceeding is safe in most cases.",
                options=["Yes, proceed", "No, skip", "Let me decide later"],
                risk_level=risk_level,
                context="Confirmation required before executing: %s"
                % action_description,
                fallback="Yes, proceed",
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("confirm_with_user failed unexpectedly: %s", exc)
            return {}

    def request_info(
        self,
        step: Union[int, str],
        what_needed: str,
        why_needed: str,
        fallback: str = "",
    ) -> Dict[str, Any]:
        """Request specific information from the user.

        Args:
            step:        Pipeline step number or label.
            what_needed: The specific information requested (used as question).
            why_needed:  Explanation for why the info is required (context).
            fallback:    Default value to use when info is not provided.

        Returns:
            The new interaction request dict.
        """
        try:
            return self.ask_user(
                step=step,
                question=what_needed,
                suggestion="",
                options=[],
                risk_level="low",
                context=why_needed,
                fallback=fallback,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("request_info failed unexpectedly: %s", exc)
            return {}

    def suggest_and_confirm(
        self,
        step: Union[int, str],
        suggestion: str,
        reasoning: str,
    ) -> Dict[str, Any]:
        """Present a suggestion with reasoning and ask for confirmation.

        Args:
            step:       Pipeline step number or label.
            suggestion: The recommended option or value.
            reasoning:  Why this suggestion was chosen.

        Returns:
            The new interaction request dict.
        """
        try:
            return self.ask_user(
                step=step,
                question="I recommend: %s. Do you agree?" % suggestion,
                suggestion=suggestion,
                options=[
                    "Yes, use this",
                    "No, I prefer something else",
                    "Show alternatives",
                ],
                risk_level="low",
                context=reasoning,
                fallback="Yes, use this",
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("suggest_and_confirm failed unexpectedly: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Response recording
    # ------------------------------------------------------------------

    def record_response(self, interaction_id: str, response: str) -> bool:
        """Record the user's response for a given interaction.

        Args:
            interaction_id: The ``id`` field of the interaction request.
            response:        The user's answer.

        Returns:
            True if the interaction was found and updated; False otherwise.
        """
        try:
            for req in self._interactions:
                if req.get("id") == interaction_id:
                    req["response"] = response
                    req["status"] = "answered"
                    logger.debug(
                        "InteractionManager.record_response: %s answered",
                        interaction_id,
                    )
                    return True
            logger.warning(
                "record_response: interaction_id %r not found", interaction_id
            )
            return False
        except Exception as exc:  # pragma: no cover
            logger.warning("record_response failed unexpectedly: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_pending(self) -> List[Dict[str, Any]]:
        """Return all interactions that have not yet been answered."""
        try:
            return [r for r in self._interactions if r.get("status") == "pending"]
        except Exception as exc:  # pragma: no cover
            logger.warning("get_pending failed: %s", exc)
            return []

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all interactions (pending, answered, and applied)."""
        try:
            return list(self._interactions)
        except Exception as exc:  # pragma: no cover
            logger.warning("get_all failed: %s", exc)
            return []

    def get_for_step(self, step: Union[int, str]) -> List[Dict[str, Any]]:
        """Return all interactions for a specific pipeline step.

        Both integer and string step labels are matched by equality so
        ``get_for_step(2)`` matches step ``2`` but not ``"step_2"``.

        Args:
            step: Step number or label to filter on.

        Returns:
            List of matching interaction dicts (may be empty).
        """
        try:
            return [r for r in self._interactions if r.get("step") == step]
        except Exception as exc:  # pragma: no cover
            logger.warning("get_for_step failed: %s", exc)
            return []

    def has_pending(self) -> bool:
        """Return True if any interactions are still awaiting a response."""
        try:
            return any(r.get("status") == "pending" for r in self._interactions)
        except Exception as exc:  # pragma: no cover
            logger.warning("has_pending failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def to_prompt_context(self) -> str:
        """Render pending interactions as a formatted prompt string.

        The returned string is intended to be injected into a Claude Code
        prompt so the user sees all open questions at once.

        Returns:
            A multi-line string with one block per pending interaction.
            Returns an empty string when there are no pending interactions.
        """
        try:
            pending = self.get_pending()
            if not pending:
                return ""

            lines: List[str] = ["=== USER INPUT NEEDED ==="]

            for req in pending:
                step = req.get("step", "?")
                risk = req.get("risk_level", "low").upper()
                question = req.get("question", "")
                suggestion = req.get("suggestion", "")
                options = req.get("options", [])
                context_text = req.get("context", "")

                lines.append("")
                lines.append("[Step %s] Risk: %s" % (step, risk))
                if context_text:
                    lines.append("Context: %s" % context_text)
                lines.append("Question: %s" % question)
                if suggestion:
                    lines.append("My suggestion: %s" % suggestion)
                if options:
                    lines.append("Options:")
                    for idx, opt in enumerate(options, start=1):
                        marker = " (recommended)" if idx == 1 and suggestion else ""
                        lines.append("  %d. %s%s" % (idx, opt, marker))

            lines.append("")
            lines.append("===")
            return "\n".join(lines)
        except Exception as exc:  # pragma: no cover
            logger.warning("to_prompt_context failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Non-interactive defaults
    # ------------------------------------------------------------------

    def apply_defaults(self) -> int:
        """Apply fallback answers to all pending interactions.

        Used in hook mode (CLAUDE_HOOK_MODE=1) or when the pipeline runs
        non-interactively.  Each pending interaction receives its
        ``fallback`` value as the ``response`` and is marked ``answered``.

        Returns:
            Number of interactions that had defaults applied.
        """
        try:
            count = 0
            for req in self._interactions:
                if req.get("status") == "pending":
                    fallback = req.get("fallback", "")
                    req["response"] = fallback
                    req["status"] = "answered"
                    count += 1
                    logger.debug(
                        "apply_defaults: %s -> %r", req.get("id"), fallback
                    )
            if count:
                logger.info(
                    "InteractionManager.apply_defaults: applied %d default(s)", count
                )
            return count
        except Exception as exc:  # pragma: no cover
            logger.warning("apply_defaults failed: %s", exc)
            return 0


# ---------------------------------------------------------------------------
# Pipeline-specific question generators
# ---------------------------------------------------------------------------

def generate_step0_questions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate questions for Step 0 (Task Analysis) when the task type is ambiguous.

    A question is generated only when ``step0_task_type`` is absent or is
    the generic "General Task" placeholder set by the pipeline default.

    Args:
        state: Current flow_state dict.

    Returns:
        List of InteractionRequest dicts (zero or one element).
    """
    questions: List[Dict[str, Any]] = []
    try:
        task_type = state.get("step0_task_type", "")
        if not task_type or task_type == "General Task":
            questions.append(
                make_interaction_request(
                    step=0,
                    question="What type of task is this?",
                    suggestion=(
                        "Based on your message, this looks like a feature request."
                    ),
                    options=[
                        "New Feature",
                        "Bug Fix",
                        "Refactoring",
                        "Documentation",
                        "Other",
                    ],
                    risk_level="low",
                    context=(
                        "Task type affects planning strategy and skill selection."
                    ),
                    fallback="General Task",
                )
            )
    except Exception as exc:
        logger.warning("generate_step0_questions failed: %s", exc)
    return questions


def generate_step2_questions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate questions for Step 2 (Planning) when the call graph risk is HIGH.

    A question is generated only when ``step2_graph_risk_level`` equals
    "high".  The affected method count is extracted from
    ``step2_affected_methods`` for the question body.

    Args:
        state: Current flow_state dict.

    Returns:
        List of InteractionRequest dicts (zero or one element).
    """
    questions: List[Dict[str, Any]] = []
    try:
        risk = state.get("step2_graph_risk_level", "low")
        if risk == "high":
            affected = state.get("step2_affected_methods", [])
            affected_count = len(affected) if isinstance(affected, list) else 0
            questions.append(
                make_interaction_request(
                    step=2,
                    question=(
                        "Risk is HIGH - %d method(s) could be affected. "
                        "How should I plan?" % affected_count
                    ),
                    suggestion=(
                        "I recommend careful, phased planning with extra testing "
                        "at each phase."
                    ),
                    options=[
                        "Careful phased planning (recommended)",
                        "Standard planning",
                        "I'll handle the risk manually",
                    ],
                    risk_level="high",
                    context=(
                        "CallGraph shows many callers could break. "
                        "Careful planning reduces regressions."
                    ),
                    fallback="Careful phased planning",
                )
            )
    except Exception as exc:
        logger.warning("generate_step2_questions failed: %s", exc)
    return questions


def generate_step5_questions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate questions for Step 5 (Skill Selection) when confidence is low.

    A question is generated when ``step5_confidence`` is below 0.70.

    Args:
        state: Current flow_state dict.

    Returns:
        List of InteractionRequest dicts (zero or one element).
    """
    questions: List[Dict[str, Any]] = []
    try:
        skill = state.get("step5_skill", "")
        confidence = float(state.get("step5_confidence", 1.0))
        if confidence < 0.7:
            confidence_pct = int(confidence * 100)
            questions.append(
                make_interaction_request(
                    step=5,
                    question=(
                        "I'm not very confident about skill selection: '%s'. "
                        "Is this correct?" % skill
                    ),
                    suggestion=(
                        "Based on the codebase patterns, '%s' seems like the "
                        "best match." % skill
                    ),
                    options=[
                        "Yes, use %s" % skill,
                        "No, let me specify",
                        "Show all available skills",
                    ],
                    risk_level="low",
                    context=(
                        "Low confidence (%d%%) in skill matching." % confidence_pct
                    ),
                    fallback=skill,
                )
            )
    except Exception as exc:
        logger.warning("generate_step5_questions failed: %s", exc)
    return questions


def generate_step10_questions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate questions for Step 10 (Implementation) about unresolved dependencies.

    At most ``_MAX_DEP_INTERACTIONS`` questions are generated to avoid
    flooding the prompt when many dependencies are unresolved.

    Args:
        state: Current flow_state dict.

    Returns:
        List of InteractionRequest dicts (zero to _MAX_DEP_INTERACTIONS elements).
    """
    questions: List[Dict[str, Any]] = []
    try:
        unresolved = state.get("unresolved_internal_deps", [])
        if not isinstance(unresolved, list):
            return questions

        for dep in unresolved[:_MAX_DEP_INTERACTIONS]:
            dep_name = dep.get("name", "") if isinstance(dep, dict) else str(dep)
            if not dep_name:
                continue
            questions.append(
                make_interaction_request(
                    step=10,
                    question=(
                        "I found dependency '%s' but cannot find its source "
                        "locally. Where is it?" % dep_name
                    ),
                    suggestion=(
                        "If it is in a private repo (Nexus/Artifactory), "
                        "provide the URL. Otherwise I will treat it as external."
                    ),
                    options=[
                        "Provide path",
                        "It's external - ignore",
                        "Skip this dependency",
                    ],
                    risk_level="low",
                    context=(
                        "Resolving internal dependencies improves call graph "
                        "accuracy and prevents breaking changes."
                    ),
                    fallback="Treat as external",
                )
            )
    except Exception as exc:
        logger.warning("generate_step10_questions failed: %s", exc)
    return questions


def generate_step11_questions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate questions for Step 11 (Review) when breaking changes are detected.

    A question is generated whenever ``step11_breaking_changes`` is a
    non-empty list.  The first five breaking change method names are
    embedded in the context text.

    Args:
        state: Current flow_state dict.

    Returns:
        List of InteractionRequest dicts (zero or one element).
    """
    questions: List[Dict[str, Any]] = []
    try:
        breaking = state.get("step11_breaking_changes", [])
        if not isinstance(breaking, list) or not breaking:
            return questions

        method_names = [
            b.get("method", "") if isinstance(b, dict) else str(b)
            for b in breaking[:5]
        ]
        context_detail = ", ".join(m for m in method_names if m)

        questions.append(
            make_interaction_request(
                step=11,
                question=(
                    "%d breaking change(s) detected. Should I fix them before "
                    "merging?" % len(breaking)
                ),
                suggestion=(
                    "I recommend fixing breaking changes before merge to prevent "
                    "regressions."
                ),
                options=[
                    "Fix all breaking changes (recommended)",
                    "Fix critical only",
                    "Proceed without fixing",
                    "Show details",
                ],
                risk_level="high",
                context="Breaking changes: %s" % context_detail
                if context_detail
                else "Breaking changes detected in the current diff.",
                fallback="Fix all breaking changes",
            )
        )
    except Exception as exc:
        logger.warning("generate_step11_questions failed: %s", exc)
    return questions


def generate_step13_questions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate questions for Step 13 (Documentation) for high-complexity tasks.

    A question is generated when ``step0_complexity`` is 7 or higher.

    Args:
        state: Current flow_state dict.

    Returns:
        List of InteractionRequest dicts (zero or one element).
    """
    questions: List[Dict[str, Any]] = []
    try:
        complexity = int(state.get("step0_complexity", 5))
        if complexity >= 7:
            questions.append(
                make_interaction_request(
                    step=13,
                    question=(
                        "This was a major change (complexity %d/10). "
                        "Should I update all docs?" % complexity
                    ),
                    suggestion=(
                        "I recommend updating SRS, README, CHANGELOG, CLAUDE.md, "
                        "and regenerating UML diagrams."
                    ),
                    options=[
                        "Update all (recommended)",
                        "Only CHANGELOG + UML",
                        "Skip doc updates",
                        "Let me choose",
                    ],
                    risk_level="low",
                    context=(
                        "Major changes often affect architecture docs. "
                        "Keeping them in sync prevents confusion."
                    ),
                    fallback="Update all",
                )
            )
    except Exception as exc:
        logger.warning("generate_step13_questions failed: %s", exc)
    return questions
