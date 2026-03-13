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

        Args:
            toon: TOON object from Level 1 (ToonAnalysis)
            user_requirement: Original user requirement text
            requirement_type: Category of the requirement (used for rule fallback).
                              e.g. "feature", "bug_fix", "refactoring", "architecture"

        Returns:
            {
                "plan_required": bool,
                "reasoning": str,
                "risk_level": "low" | "medium" | "high",
                "decision_reasoning": str,
                "execution_time_ms": float,
                "source": str - "llm" | "claude_api" | "rules",
                "fallback": bool - True if LLM was unavailable
            }
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

            # --- Primary path: Ollama LLM ---
            logger.info("Calling Ollama (qwen2.5:7b) for plan mode decision...")
            try:
                decision = self.ollama.step1_plan_mode_decision(toon, user_requirement)
                decision["source"] = "llm"
                decision["fallback"] = False
            except Exception as ollama_err:
                logger.warning(f"Ollama failed for Step 1: {ollama_err}")

                # --- Secondary path: Claude API fallback ---
                try:
                    logger.info("Falling back to Claude API for plan mode decision...")
                    claude_client = getattr(self.ollama, "claude_client", None)
                    if claude_client:
                        decision = claude_client.step1_plan_mode_decision(toon, user_requirement)
                        decision["source"] = "claude_api"
                        decision["fallback"] = True
                    else:
                        raise RuntimeError("Claude API client not available")
                except Exception as claude_err:
                    logger.warning(f"Claude API fallback also failed: {claude_err}")

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
    """
    logger.info("\n🔄 Executing STEP 1: Plan Mode Decision...")

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

        # Execute Step 1
        planner = Level3Step1Planner(session_dir)
        decision = planner.execute(toon, user_requirement)

        # Update state
        state["step1_decision"] = decision
        state["step1_plan_required"] = decision.get("plan_required", True)

        logger.info(f"✓ STEP 1 completed in {decision.get('execution_time_ms', 0):.0f}ms")

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
