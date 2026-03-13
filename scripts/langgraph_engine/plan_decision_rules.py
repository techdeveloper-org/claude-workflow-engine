"""
Plan Decision Rules - Rule-based logic for Step 1 plan mode decision.

Supplements Ollama LLM analysis with deterministic rule-based fallback.
Rules are evaluated in priority order; first match wins.

Rules:
- complexity >= 6                      -> plan required
- requirement_type in ALWAYS_PLAN_TYPES -> plan required (unconditional)
- bug_fix + complexity >= 4            -> plan required
- everything else                      -> plan not required
"""

from typing import Dict, Any, Optional, Tuple
from loguru import logger

# Requirement types that always require planning, regardless of complexity
ALWAYS_PLAN_TYPES = frozenset(["refactoring", "architecture", "migration", "security_audit"])

# Threshold values (easy to tune)
COMPLEXITY_HARD_THRESHOLD = 6          # complexity >= this -> always plan
BUG_FIX_COMPLEXITY_THRESHOLD = 4       # bug_fix + complexity >= this -> plan

# Risk bands derived from complexity
_RISK_BANDS = {
    (0, 3): "low",
    (4, 6): "medium",
    (7, 10): "high",
}


def _complexity_to_risk(complexity_score: int) -> str:
    """Map integer complexity score to a risk band string."""
    for (lo, hi), band in _RISK_BANDS.items():
        if lo <= complexity_score <= hi:
            return band
    return "medium"


def should_plan(complexity_score: int, requirement_type: str) -> Tuple[bool, str]:
    """
    Determine whether planning is required for a given task.

    Args:
        complexity_score: Integer 1-10 from TOON complexity_score field.
        requirement_type: Lower-cased requirement category string.
            Known values: "bug_fix", "feature", "refactoring", "architecture",
                          "documentation", "migration", "security_audit", "test"

    Returns:
        Tuple of (plan_required: bool, reason: str) so callers can log decisions.

    Examples:
        >>> should_plan(7, "feature")
        (True, "High complexity (7/10) exceeds threshold of 6")
        >>> should_plan(3, "bug_fix")
        (False, "Low complexity bug fix, direct execution sufficient")
        >>> should_plan(4, "bug_fix")
        (True, "Bug fix with non-trivial complexity (4/10) requires planning")
        >>> should_plan(2, "refactoring")
        (True, "Requirement type 'refactoring' always requires a plan")
    """
    norm_type = (requirement_type or "").strip().lower()

    # Rule 1: hard complexity threshold (highest priority)
    if complexity_score >= COMPLEXITY_HARD_THRESHOLD:
        reason = (
            f"High complexity ({complexity_score}/10) exceeds threshold of {COMPLEXITY_HARD_THRESHOLD}"
        )
        logger.debug(f"[PlanDecisionRules] Rule 1 matched: {reason}")
        return True, reason

    # Rule 2: unconditional types
    if norm_type in ALWAYS_PLAN_TYPES:
        reason = f"Requirement type '{norm_type}' always requires a plan"
        logger.debug(f"[PlanDecisionRules] Rule 2 matched: {reason}")
        return True, reason

    # Rule 3: bug_fix with moderate complexity
    if norm_type == "bug_fix" and complexity_score >= BUG_FIX_COMPLEXITY_THRESHOLD:
        reason = (
            f"Bug fix with non-trivial complexity ({complexity_score}/10) requires planning"
        )
        logger.debug(f"[PlanDecisionRules] Rule 3 matched: {reason}")
        return True, reason

    # Default: no plan required
    reason = (
        f"Complexity {complexity_score}/10 + type '{norm_type}' within direct-execution range"
    )
    logger.debug(f"[PlanDecisionRules] No rule matched, plan not required: {reason}")
    return False, reason


def evaluate_from_toon(toon: Dict[str, Any], requirement_type: str) -> Dict[str, Any]:
    """
    Evaluate plan decision using data extracted directly from a TOON object.

    Args:
        toon: TOON dict with at least a 'complexity_score' key.
        requirement_type: Requirement type string (see should_plan).

    Returns:
        Dict with keys:
            plan_required (bool)
            reasoning (str)
            risk_level (str) - "low" | "medium" | "high"
            complexity_score (int)
            requirement_type (str)
            source (str) - always "rules"
    """
    complexity_score = int(toon.get("complexity_score") or 5)
    plan_required, reasoning = should_plan(complexity_score, requirement_type)
    risk_level = _complexity_to_risk(complexity_score)

    logger.info(
        f"[PlanDecisionRules] plan_required={plan_required}, "
        f"complexity={complexity_score}, risk={risk_level}"
    )

    return {
        "plan_required": plan_required,
        "reasoning": reasoning,
        "risk_level": risk_level,
        "complexity_score": complexity_score,
        "requirement_type": requirement_type,
        "source": "rules",
    }


def build_fallback_decision(
    toon: Dict[str, Any],
    requirement: str,
    requirement_type: str,
    error_msg: str,
) -> Dict[str, Any]:
    """
    Build a safe fallback decision when LLM analysis fails.

    Applies deterministic rules from this module and marks the decision
    with fallback metadata so callers know an error occurred upstream.

    Args:
        toon: TOON dict (may be partial if LLM failed mid-parse).
        requirement: Original user requirement text (for audit logging).
        requirement_type: Requirement type string.
        error_msg: The error that triggered fallback.

    Returns:
        Decision dict, same shape as evaluate_from_toon, with extra keys:
            fallback (bool) - always True
            fallback_error (str) - original error message
    """
    decision = evaluate_from_toon(toon, requirement_type)
    decision["fallback"] = True
    decision["fallback_error"] = error_msg
    decision["reasoning"] = (
        f"[FALLBACK] LLM analysis failed ({error_msg}). "
        f"Applied rule-based decision: {decision['reasoning']}"
    )

    logger.warning(
        f"[PlanDecisionRules] Using fallback decision due to LLM error: {error_msg}"
    )
    logger.warning(
        f"[PlanDecisionRules] Fallback result: plan_required={decision['plan_required']}"
    )
    return decision
