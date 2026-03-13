"""
Plan Convergence Criteria - Quality gating for Step 2 iterative planning.

Determines when an iterative plan generation loop has produced a plan that is
"good enough" to move forward with, based on a quality score and iteration count.

Quality assessment is multi-dimensional:
- structural_score: has phases, files_affected, risks
- coverage_score: requirement keywords appear in plan text
- specificity_score: mentions actual file paths / code identifiers
- composite: weighted average of above

Convergence exits the loop when:
1. quality >= QUALITY_THRESHOLD (plan is genuinely good), OR
2. iteration >= max_iterations (fail-safe - use best plan so far)
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

# Quality threshold: plan must score at least this to be considered "ready"
QUALITY_THRESHOLD = 0.85

# Default maximum planning iterations
DEFAULT_MAX_ITERATIONS = 3


# ---------------------------------------------------------------------------
# Quality assessment helpers
# ---------------------------------------------------------------------------

def _score_structure(plan: Dict[str, Any]) -> float:
    """
    Score the structural completeness of a plan dict.

    Awards points for:
    - plan text presence and minimum length
    - phases list with at least 1 entry
    - files_affected list
    - risks dict with a risk_level key
    """
    score = 0.0
    plan_text = plan.get("plan", "") or ""

    if len(plan_text) >= 200:
        score += 0.30
    elif len(plan_text) >= 50:
        score += 0.10

    phases = plan.get("phases", [])
    if isinstance(phases, list) and len(phases) >= 1:
        score += 0.25
        if len(phases) >= 2:
            score += 0.10  # Bonus for multi-phase

    files = plan.get("files_affected", [])
    if isinstance(files, list) and len(files) >= 1:
        score += 0.20

    risks = plan.get("risks", {})
    if isinstance(risks, dict) and risks.get("risk_level"):
        score += 0.15

    return min(score, 1.0)


def _score_coverage(plan: Dict[str, Any], requirement: str) -> float:
    """
    Score how well the plan covers keywords from the requirement.

    Splits requirement into significant words (length >= 4) and checks
    what fraction of them appear in the combined plan text.
    """
    plan_text = (plan.get("plan", "") or "").lower()
    if not plan_text or not requirement:
        return 0.0

    words = [w.lower() for w in requirement.split() if len(w) >= 4]
    if not words:
        return 0.5  # No meaningful keywords to check - neutral score

    found = sum(1 for w in words if w in plan_text)
    return found / len(words)


def _score_specificity(plan: Dict[str, Any]) -> float:
    """
    Score how specific/actionable the plan is.

    Checks for file path patterns, function/class identifiers, and
    numbered action items as signals of specificity.
    """
    plan_text = plan.get("plan", "") or ""
    score = 0.0

    # File path patterns like src/file.py or tests/test_x.py
    if re.search(r'\b\w+[/\\]\w+\.\w{2,4}\b', plan_text):
        score += 0.40

    # Numbered steps / action items
    if re.search(r'^\s*\d+[.)]\s', plan_text, re.MULTILINE):
        score += 0.30

    # Code identifiers (CamelCase class names or snake_case functions)
    if re.search(r'\b[A-Z][a-z]+[A-Z]\w+\b|\b\w+_\w+\(\)', plan_text):
        score += 0.30

    return min(score, 1.0)


def assess_plan_quality(plan: Dict[str, Any], requirement: str = "") -> float:
    """
    Compute a composite quality score [0.0, 1.0] for a plan dict.

    Weights:
        structure  40%
        coverage   35%
        specificity 25%

    Args:
        plan: Dict returned by Level3RemainingSteps.step2_plan_execution.
        requirement: Original user requirement text for coverage scoring.

    Returns:
        Float in [0.0, 1.0].
    """
    struct = _score_structure(plan)
    cover = _score_coverage(plan, requirement)
    spec = _score_specificity(plan)

    quality = (struct * 0.40) + (cover * 0.35) + (spec * 0.25)
    quality = min(max(quality, 0.0), 1.0)

    logger.debug(
        f"[PlanConvergence] quality={quality:.3f} "
        f"(struct={struct:.2f}, cover={cover:.2f}, spec={spec:.2f})"
    )
    return quality


def check_convergence(
    plan_quality: float,
    iteration: int,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> Tuple[bool, str]:
    """
    Check whether the planning loop should terminate.

    Args:
        plan_quality: Current plan quality score in [0.0, 1.0].
        iteration: 0-indexed iteration number that just completed.
        max_iterations: Hard upper bound on iterations.

    Returns:
        Tuple (converged: bool, reason: str).

    Examples:
        >>> check_convergence(0.90, 0, 3)
        (True, "Quality 0.900 >= threshold 0.850")
        >>> check_convergence(0.60, 2, 3)
        (True, "Max iterations (3) reached, using best plan")
        >>> check_convergence(0.60, 1, 3)
        (False, "Quality 0.600 < threshold 0.850, continuing (1/3)")
    """
    if plan_quality >= QUALITY_THRESHOLD:
        reason = f"Quality {plan_quality:.3f} >= threshold {QUALITY_THRESHOLD:.3f}"
        logger.info(f"[PlanConvergence] Converged: {reason}")
        return True, reason

    # Note: iteration is 0-indexed, completed_count = iteration + 1
    completed = iteration + 1
    if completed >= max_iterations:
        reason = f"Max iterations ({max_iterations}) reached, using best plan"
        logger.warning(f"[PlanConvergence] Forced convergence: {reason}")
        return True, reason

    reason = f"Quality {plan_quality:.3f} < threshold {QUALITY_THRESHOLD:.3f}, continuing ({completed}/{max_iterations})"
    logger.info(f"[PlanConvergence] Not yet converged: {reason}")
    return False, reason


# ---------------------------------------------------------------------------
# Iterative planning loop controller
# ---------------------------------------------------------------------------

def run_planning_loop(
    generate_plan_fn,
    requirement: str,
    toon: Dict[str, Any],
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> Dict[str, Any]:
    """
    Drive an iterative plan generation loop with convergence gating.

    Args:
        generate_plan_fn: Callable() -> Dict[str, Any].
            Executed each iteration to produce a new plan dict.
            The dict must contain at least a 'plan' key (string).
        requirement: Original user requirement text (used for coverage scoring).
        toon: TOON dict (used for context logging only).
        max_iterations: Hard upper bound on loop iterations.

    Returns:
        Dict with:
            plan (Dict)           - best plan produced
            quality (float)       - final quality score
            iterations (int)      - how many iterations ran
            converged (bool)      - True if quality threshold was met
            convergence_reason (str)
    """
    best_plan: Optional[Dict[str, Any]] = None
    best_quality: float = 0.0

    logger.info(
        f"[PlanConvergence] Starting planning loop "
        f"(max_iterations={max_iterations}, threshold={QUALITY_THRESHOLD})"
    )

    for iteration in range(max_iterations):
        logger.info(f"[PlanConvergence] Iteration {iteration + 1}/{max_iterations}")

        try:
            plan = generate_plan_fn()
        except Exception as exc:
            logger.error(f"[PlanConvergence] generate_plan_fn failed on iteration {iteration}: {exc}")
            plan = {}

        quality = assess_plan_quality(plan, requirement)
        logger.info(f"[PlanConvergence] Iteration {iteration + 1} quality={quality:.3f}")

        # Track best plan
        if quality > best_quality or best_plan is None:
            best_plan = plan
            best_quality = quality

        converged, reason = check_convergence(quality, iteration, max_iterations)
        if converged:
            return {
                "plan": best_plan,
                "quality": best_quality,
                "iterations": iteration + 1,
                "converged": quality >= QUALITY_THRESHOLD,
                "convergence_reason": reason,
            }

    # Should not reach here due to max_iterations check inside check_convergence,
    # but defensive fallback
    return {
        "plan": best_plan or {},
        "quality": best_quality,
        "iterations": max_iterations,
        "converged": False,
        "convergence_reason": "Loop exhausted",
    }
