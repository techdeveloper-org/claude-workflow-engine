"""
Token Budget Manager - Real-time token budget tracking and enforcement.

Each Level 3 pipeline execution has a fixed TOTAL_BUDGET of tokens across all steps.
Budget is divided into per-step allocations.  The manager tracks actual usage,
warns when a step is approaching its allocation, and raises BudgetExceededError
when cumulative usage crosses the total budget.

Usage:
    budget = TokenBudget()
    budget.check_or_raise("step_8", estimated_tokens=300)   # raises if over budget
    issue_response = create_issue()
    actual_tokens = count_tokens(issue_response)
    budget.record_usage("step_8", actual_tokens)            # records + checks total
    # Convenience aliases (acceptance-criteria API):
    budget.allocate("step_8", actual_tokens)                # alias for record_usage
    rem = budget.remaining()                                 # alias for get_remaining

# v1.15.2: removed ALLOCATIONS entries for step_1 through step_7
#           (Steps 1,3,4,5,6,7 removed from pipeline in v1.13.0).
"""

from typing import Any, Dict, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class BudgetExceededError(Exception):
    """Raised when the cumulative token usage exceeds the total budget."""

    def __init__(self, step: str, spent: int, total: int, message: str = ""):
        self.step = step
        self.spent = spent
        self.total = total
        super().__init__(message or f"Token budget exceeded at step '{step}': {spent}/{total} tokens used")


# ---------------------------------------------------------------------------
# Token budget configuration
# ---------------------------------------------------------------------------


class TokenBudget:
    """
    Real-time token budget tracker for the Level 3 pipeline.

    Budget allocation strategy (active steps only):
        step_0:  900     Task Analysis (orchestration prompt + orchestrator call)
        step_8:  300     GitHub issue creation (template-based)
        step_9:  100     Branch name generation
        step_10: 1200    Implementation notes (logging only)
        step_11:  500    Code review
        step_12:  100    Issue closure (no LLM)
        step_13:  500    Documentation update
        step_14:  200    Summary generation
        reserve:  800    Safety buffer for unexpected overruns

    v1.15.2: removed step_1 through step_7 (steps removed from pipeline in v1.13.0).
    """

    TOTAL_BUDGET: int = 10000

    # Per-step soft allocations (active steps: Pre-0/0, 8-14)
    # v1.15.2: removed dead entries step_1 through step_7
    ALLOCATIONS: Dict[str, int] = {
        "step_0": 900,
        "step_8": 300,
        "step_9": 100,
        "step_10": 1200,
        "step_11": 500,
        "step_12": 100,
        "step_13": 500,
        "step_14": 200,
        "reserve": 800,
    }

    # Warn when a step uses more than this fraction of its allocation
    _WARN_RATIO: float = 0.90

    def __init__(self, total_budget: Optional[int] = None):
        """
        Args:
            total_budget: Override the class-level TOTAL_BUDGET if supplied.
        """
        self.total_budget = total_budget if total_budget is not None else self.TOTAL_BUDGET
        # Per-step recorded usage
        self.usage: Dict[str, int] = {}

        logger.info(
            f"[TokenBudget] Initialized: total_budget={self.total_budget}, "
            f"allocations={sum(self.ALLOCATIONS.values())} allocated"
        )

    # ---------------------------------------------------------------------------
    # Querying
    # ---------------------------------------------------------------------------

    def get_spent(self) -> int:
        """Return total tokens spent across all recorded steps."""
        return sum(self.usage.values())

    def get_remaining(self) -> int:
        """Return tokens remaining in the total budget."""
        return self.total_budget - self.get_spent()

    def get_step_allocation(self, step: str) -> int:
        """Return per-step soft allocation for a step, 0 if unknown."""
        return self.ALLOCATIONS.get(step, 0)

    def get_step_usage(self, step: str) -> int:
        """Return tokens already recorded for a step."""
        return self.usage.get(step, 0)

    def can_proceed(self, step: str, estimated: int) -> bool:
        """
        Check whether estimated token usage fits in the remaining budget.

        Does NOT raise - callers that want hard enforcement should use
        check_or_raise() instead.

        Args:
            step: Step name (e.g. "step_8").
            estimated: Estimated token count for the upcoming operation.

        Returns:
            True if the step can proceed within the total budget.
        """
        remaining = self.get_remaining()
        can = estimated <= remaining

        if not can:
            logger.warning(
                f"[TokenBudget] '{step}' wants {estimated} tokens, "
                f"but only {remaining} remain (total={self.total_budget})"
            )
        return can

    def check_or_raise(self, step: str, estimated: int) -> None:
        """
        Assert that a step can proceed; raise BudgetExceededError if not.

        Should be called BEFORE an LLM call to pre-screen budget viability.

        Args:
            step: Step name.
            estimated: Estimated token count.

        Raises:
            BudgetExceededError if estimated > remaining.
        """
        if not self.can_proceed(step, estimated):
            spent = self.get_spent()
            raise BudgetExceededError(
                step=step,
                spent=spent + estimated,
                total=self.total_budget,
                message=(
                    f"[TokenBudget] Step '{step}' estimated {estimated} tokens but only "
                    f"{self.get_remaining()} remain ({spent}/{self.total_budget} used)"
                ),
            )

    # ---------------------------------------------------------------------------
    # Recording
    # ---------------------------------------------------------------------------

    def record_usage(self, step: str, tokens: int) -> None:
        """
        Record actual token usage for a step.

        Accumulates usage if the step is called multiple times (e.g. retries).
        Logs a warning if the step exceeded its soft allocation.
        Raises BudgetExceededError if cumulative total exceeds the hard budget.

        Args:
            step: Step name.
            tokens: Actual tokens used by this call.

        Raises:
            BudgetExceededError if total usage after recording exceeds TOTAL_BUDGET.
        """
        if tokens < 0:
            logger.warning(f"[TokenBudget] Negative token count for '{step}': {tokens} - ignoring")
            tokens = 0

        # Accumulate
        previous = self.usage.get(step, 0)
        self.usage[step] = previous + tokens
        total_used = self.get_spent()

        # Log
        allocation = self.get_step_allocation(step)
        step_total = self.usage[step]
        remaining = self.total_budget - total_used

        logger.info(
            f"[TokenBudget] '{step}': +{tokens} tokens "
            f"(step_total={step_total}, alloc={allocation}, "
            f"global_used={total_used}/{self.total_budget}, remaining={remaining})"
        )

        # Soft allocation warning
        if allocation > 0 and step_total > allocation * self._WARN_RATIO:
            logger.warning(
                f"[TokenBudget] '{step}' has used {step_total}/{allocation} tokens "
                f"({100 * step_total // allocation}% of allocation)"
            )

        # Hard budget enforcement
        if total_used > self.total_budget:
            raise BudgetExceededError(
                step=step,
                spent=total_used,
                total=self.total_budget,
            )

    # ---------------------------------------------------------------------------
    # Acceptance-criteria convenience aliases
    # ---------------------------------------------------------------------------

    def allocate(self, step_number: Any, tokens_used: int) -> None:
        """
        Record actual token usage for a step (acceptance-criteria alias for record_usage).

        Identical behaviour to record_usage(); exists so callers can use the
        verb "allocate" to signal they are *spending* from the budget.

        Args:
            step_number: Step identifier.  Accepts an int (8-14) or a string
                         like "step_8".  Integers are normalised to "step_N".
            tokens_used: Actual tokens consumed by this operation.

        Raises:
            BudgetExceededError if cumulative total exceeds TOTAL_BUDGET.
        """
        step = self._normalise_step(step_number)
        self.record_usage(step, tokens_used)

    def remaining(self) -> int:
        """
        Return tokens remaining in the total budget (acceptance-criteria alias).

        Equivalent to get_remaining().
        """
        return self.get_remaining()

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _normalise_step(step: Any) -> str:
        """
        Normalise a step identifier to the canonical "step_N" string format.

        Accepts:
            int 8-14  -> "step_8" .. "step_14"
            str "8"   -> "step_8"
            str "step_10" -> "step_10" (returned as-is)
            any other str -> returned as-is
        """
        if isinstance(step, int):
            return f"step_{step}"
        s = str(step).strip()
        if s.isdigit():
            return f"step_{s}"
        return s

    # ---------------------------------------------------------------------------
    # Reporting
    # ---------------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """
        Return a summary dict of the current budget state.

        Returns:
            Dict with:
                total_budget (int)
                spent (int)
                remaining (int)
                utilization_pct (float)
                per_step (Dict[str, Dict])
                    - usage (int)
                    - allocation (int)
                    - utilization_pct (float)
        """
        spent = self.get_spent()
        per_step = {}
        for step, alloc in self.ALLOCATIONS.items():
            used = self.usage.get(step, 0)
            pct = (100.0 * used / alloc) if alloc > 0 else 0.0
            per_step[step] = {
                "usage": used,
                "allocation": alloc,
                "utilization_pct": round(pct, 1),
            }

        # Also include any steps that recorded usage but aren't in ALLOCATIONS
        for step, used in self.usage.items():
            if step not in per_step:
                per_step[step] = {
                    "usage": used,
                    "allocation": 0,
                    "utilization_pct": 0.0,
                }

        return {
            "total_budget": self.total_budget,
            "spent": spent,
            "remaining": self.get_remaining(),
            "utilization_pct": round(100.0 * spent / self.total_budget, 1) if self.total_budget else 0.0,
            "per_step": per_step,
        }

    def log_summary(self) -> None:
        """Emit a formatted budget summary to the logger."""
        summary = self.get_summary()
        logger.info(
            f"[TokenBudget] Summary: "
            f"spent={summary['spent']}/{summary['total_budget']} "
            f"({summary['utilization_pct']}% used, "
            f"{summary['remaining']} remaining)"
        )
        for step, info in summary["per_step"].items():
            if info["usage"] > 0:
                logger.info(
                    f"[TokenBudget]   {step}: {info['usage']}/{info['allocation']} " f"({info['utilization_pct']}%)"
                )

    # ---------------------------------------------------------------------------
    # Convenience: estimate tokens from text
    # ---------------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough token estimate from a string (4 chars ~= 1 token).

        This is the same heuristic used in WorkflowContextOptimizer.

        Args:
            text: Any string (prompt, response, etc.)

        Returns:
            Estimated integer token count.
        """
        if not isinstance(text, str):
            text = str(text)
        return max(1, len(text) // 4)
