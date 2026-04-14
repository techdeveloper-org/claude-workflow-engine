from __future__ import annotations

from typing import List

_ERROR_PREFIXES = (
    "error:",
    "exception:",
    "traceback",
    "failed:",
    "connectionerror",
    "timeout:",
    "ratelimiterror",
)

_MIN_PROMPT_LEN = 200
_MIN_RESULT_LEN = 50


def verify_orchestration_prompt(prompt: str) -> List[str]:
    """Validate structure of the orchestration prompt from prompt_gen_expert_caller.

    Returns a list of error strings. Empty list means the prompt is valid.
    """
    errors: List[str] = []
    if not prompt or not prompt.strip():
        errors.append("orchestration_prompt is empty")
        return errors
    if len(prompt) < _MIN_PROMPT_LEN:
        errors.append("orchestration_prompt too short: %d chars (min %d)" % (len(prompt), _MIN_PROMPT_LEN))
    if "Phase" not in prompt:
        errors.append("orchestration_prompt missing 'Phase' keyword -- may not be a valid orchestration prompt")
    return errors


def verify_orchestrator_result(result: str) -> List[str]:
    """Validate structure of the orchestrator agent result from orchestrator_agent_caller.

    Returns a list of error strings. Empty list means the result is valid.
    """
    errors: List[str] = []
    if not result or not result.strip():
        errors.append("orchestrator_result is empty")
        return errors
    if len(result) < _MIN_RESULT_LEN:
        errors.append("orchestrator_result too short: %d chars (min %d)" % (len(result), _MIN_RESULT_LEN))
    stripped_lower = result.strip().lower()
    if any(stripped_lower.startswith(prefix) for prefix in _ERROR_PREFIXES):
        errors.append("orchestrator_result appears to be an error string: %r" % result[:80])
    return errors
