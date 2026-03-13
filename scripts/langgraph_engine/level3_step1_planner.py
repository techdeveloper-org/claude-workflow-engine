"""
Level 3 - Step 1: Plan Mode Decision

Determines if a detailed execution plan is required based on:
- Project complexity (from Level 1 TOON)
- User requirement analysis
- Risk assessment

Primary path: Ollama local LLM (qwen2.5:7b) for fast classification.
Fallback path: Claude API -> deterministic rule-based evaluation
  (plan_decision_rules.py) when both LLM backends are unavailable.

Decision is also validated through StepValidator before returning.
Token usage is reported to a TokenBudget if one is provided.
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime

from loguru import logger
from .ollama_service import get_ollama_service
from .toon_models import ToonAnalysis
from .plan_decision_rules import build_fallback_decision, evaluate_from_toon
from .step_validator import StepValidator
from .token_manager import TokenBudget
from .timeout_wrapper import run_with_timeout, fallback_step1, STEP_TIMEOUTS

# Import LLM retry helper (lazy to avoid circular imports)
def _get_llm_retry():
    try:
        from .level3_remaining_steps import _llm_call_with_retry
        return _llm_call_with_retry
    except ImportError:
        import time as _time
        _delays = [1.0, 2.0, 4.0, 8.0]
        def _fallback_retry(call_fn, step_name="LLM", max_retries=3):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return call_fn()
                except Exception as exc:
                    last_exc = exc
                    err_lower = str(exc).lower()
                    is_retryable = any(
                        kw in err_lower for kw in
                        ("timeout", "connection", "rate_limit", "503", "overloaded")
                    )
                    if not is_retryable or attempt >= max_retries:
                        raise
                    delay = _delays[min(attempt, len(_delays) - 1)]
                    logger.warning(
                        f"[{step_name}] LLM retry {attempt+1}/{max_retries} in {delay}s: {exc}"
                    )
                    _time.sleep(delay)
            if last_exc:
                raise last_exc
        return _fallback_retry


class Level3Step1Planner:
    """Step 1: Plan Mode Decision Logic."""

    def __init__(self, session_dir_path: str, token_budget: Optional[TokenBudget] = None):
        self.session_dir = session_dir_path
        self.ollama = get_ollama_service()
        self.validator = StepValidator()
        self.token_budget = token_budget

    def execute(
        self,
        toon: Dict[str, Any],
        user_requirement: str,
        requirement_type: str = "feature",
    ) -> Dict[str, Any]:
        """
        Execute Step 1: Determine if plan mode is required.

        Primary decision comes from the Ollama LLM (qwen2.5:7b).
        If Ollama fails, falls back to Claude API.
        If Claude API also fails, falls back to deterministic rule evaluation
        via plan_decision_rules.build_fallback_decision().

        All decisions are logged via ErrorLogger pattern (logger.log_decision
        equivalent through loguru).

        Timeout: enforced at {STEP_TIMEOUTS[1]}s via timeout_wrapper.
        On timeout, returns fallback_step1() with plan_required=True for safety.

        Args:
            toon: TOON object from Level 1 (ToonAnalysis)
            user_requirement: Original user requirement text
            requirement_type: Category of the requirement (used for rule fallback).
                              e.g. "feature", "bug_fix", "refactoring", "architecture"

        Returns:
            {{
                "plan_required": bool,
                "reasoning": str,
                "risk_level": "low" | "medium" | "high",
                "decision_reasoning": str,
                "execution_time_ms": float,
                "source": str - "llm" | "claude_api" | "rules",
                "fallback": bool - True if LLM was unavailable
            }}
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 1: PLAN MODE DECISION")
        logger.info("=" * 60)

        step_start = time.time()

        # --- Input validation ---
        valid, errors = self.validator.validate_step_1_input({
            "level1_context_toon": toon,
            "user_requirement": user_requirement,
        })
        if not valid:
            logger.warning(f"Step 1 input validation issues: {errors}")

        try:
            # Log inputs
            logger.debug(f"TOON complexity: {toon.get('complexity_score')}/10")
            logger.debug(f"Files loaded: {toon.get('files_loaded_count')}")
            logger.debug(f"User requirement: {user_requirement[:100]}...")

            # --- Primary path: Ollama LLM (with exponential backoff retry) ---
            logger.info("Calling Ollama (qwen2.5:7b) for plan mode decision...")
            _llm_call_with_retry = _get_llm_retry()
            try:
                def _ollama_step1_call():
                    return self.ollama.step1_plan_mode_decision(toon, user_requirement)

                decision = _llm_call_with_retry(
                    _ollama_step1_call, "Step 1 Plan Mode Decision"
                )
                decision["source"] = "llm"
                decision["fallback"] = False
            except Exception as ollama_err:
                logger.warning(f"Ollama failed for Step 1 (after retries): {ollama_err}")

                # --- Secondary path: Claude API fallback (with retry) ---
                try:
                    logger.info("Falling back to Claude API for plan mode decision...")
                    claude_client = getattr(self.ollama, "claude_client", None)
                    if claude_client:
                        def _claude_step1_call():
                            return claude_client.step1_plan_mode_decision(
                                toon, user_requirement
                            )
                        decision = _llm_call_with_retry(
                            _claude_step1_call, "Step 1 Claude API Fallback"
                        )
                        decision["source"] = "claude_api"
                        decision["fallback"] = True
                    else:
                        raise RuntimeError("Claude API client not available")
                except Exception as claude_err:
                    logger.warning(
                        f"Claude API fallback also failed (after retries): {claude_err}"
                    )

                    # --- Tertiary path: deterministic rule-based decision ---
                    logger.info("Falling back to rule-based plan decision (plan_decision_rules)...")
                    decision = build_fallback_decision(
                        toon=toon,
                        requirement=user_requirement,
                        requirement_type=requirement_type,
                        error_msg=str(ollama_err),
                    )

            # Extract decision
            plan_required = decision.get("plan_required", True)
            reasoning = decision.get("reasoning", "Unknown")
            risk_level = decision.get("risk_level", "medium")
            source = decision.get("source", "unknown")

            execution_time_ms = (time.time() - step_start) * 1000

            # --- Log the decision (mirrors ErrorLogger.log_decision pattern) ---
            logger.info(
                f"[Step 1] DECISION: {'Plan REQUIRED' if plan_required else 'Plan NOT required'} | "
                f"source={source} | risk={risk_level}"
            )
            logger.info(f"[Step 1] Reasoning: {reasoning}")

            # --- Token budget accounting ---
            if self.token_budget is not None:
                estimated_tokens = TokenBudget.estimate_tokens(reasoning)
                try:
                    self.token_budget.record_usage("step_1", estimated_tokens)
                except Exception as budget_err:
                    logger.warning(f"[Step 1] Token budget error: {budget_err}")

            # Build result
            result = {
                "plan_required": plan_required,
                "reasoning": reasoning,
                "risk_level": risk_level,
                "decision_reasoning": self._format_decision(plan_required, risk_level, reasoning),
                "execution_time_ms": execution_time_ms,
                "source": source,
                "fallback": decision.get("fallback", False),
                "timestamp": datetime.now().isoformat()
            }

            # --- Output validation ---
            out_valid, out_errors = self.validator.validate_step_1_output(result)
            if not out_valid:
                logger.warning(f"Step 1 output validation issues: {out_errors}")
                result["validation_errors"] = out_errors

            logger.info(f"Step 1 execution time: {execution_time_ms:.0f}ms")
            return result

        except Exception as e:
            logger.error(f"Step 1 execution failed: {e}")
            execution_time_ms = (time.time() - step_start) * 1000

            # Return error result with safe defaults
            return {
                "plan_required": True,  # Default to plan mode for safety
                "reasoning": f"Error during decision: {str(e)}",
                "risk_level": "high",  # Mark as high risk due to error
                "decision_reasoning": "Error occurred, defaulting to plan mode",
                "execution_time_ms": execution_time_ms,
                "source": "error_default",
                "fallback": True,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _format_decision(self, plan_required: bool, risk_level: str, reasoning: str) -> str:
        """Format decision explanation for logging."""
        decision_str = "REQUIRED" if plan_required else "NOT REQUIRED"
        risk_icon = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🔴"
        }.get(risk_level, "⚪")

        return f"Plan Mode {decision_str} | Risk: {risk_icon} {risk_level} | {reasoning}"

    def should_enter_plan_mode(self, step1_result: Dict[str, Any]) -> bool:
        """
        Convenience method to check if plan mode should be entered.

        Returns True if plan_required is True.
        """
        return step1_result.get("plan_required", True)


def step1_plan_mode_decision_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node wrapper for Step 1.

    Receives FlowState with:
    - session_dir
    - user_requirement
    - level1_context_toon

    Updates state with:
    - step1_decision
    - step1_plan_required

    Timeout: {STEP_TIMEOUTS[1]}s enforced via run_with_timeout().
    On timeout, defaults to plan_required=True (safest assumption).
    """
    logger.info("\nExecuting STEP 1: Plan Mode Decision...")

    try:
        # Extract from state
        session_dir = state.get("session_dir")
        user_requirement = state.get("user_requirement")
        toon = state.get("level1_context_toon")

        # Validate inputs
        if not session_dir:
            logger.error("Missing session_dir in state")
            return state

        if not user_requirement:
            logger.error("Missing user_requirement in state")
            user_requirement = "No requirement provided"

        if not toon:
            logger.error("Missing level1_context_toon in state")
            toon = {}

        # Execute Step 1 with timeout enforcement
        planner = Level3Step1Planner(session_dir)
        decision = run_with_timeout(
            fn=planner.execute,
            step_number=1,
            args=(toon, user_requirement),
            fallback=fallback_step1(),
        )

        # Update state
        state["step1_decision"] = decision
        state["step1_plan_required"] = decision.get("plan_required", True)

        logger.info(f"STEP 1 completed in {decision.get('execution_time_ms', 0):.0f}ms")

        return state

    except Exception as e:
        logger.error(f"Step 1 node error: {e}")
        state["step1_error"] = str(e)
        state["step1_plan_required"] = True  # Default to safe behavior
        return state


# Routing function for Level 3 conditional flow
def should_execute_plan_mode(state: Dict[str, Any]) -> bool:
    """
    Router function: Determine if Level 3 should enter plan mode.

    Used as conditional edge in LangGraph:
    add_edge("step_1", "step_2_plan_mode", should_execute_plan_mode)
    add_edge("step_1", "step_3_task_breakdown", lambda s: not should_execute_plan_mode(s))
    """
    decision = state.get("step1_decision", {})
    plan_required = decision.get("plan_required", True)

    logger.info(f"Router decision: {'PLAN MODE' if plan_required else 'DIRECT EXECUTION'}")

    return plan_required
