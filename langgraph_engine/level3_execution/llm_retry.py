"""
Level 3 - LLM Retry Helpers

Standalone LLM retry utilities extracted from Level3RemainingSteps.
Provides exponential-backoff retry logic for transient LLM failures.
"""

import time
from typing import Callable, List, Optional, TypeVar

from loguru import logger

# Exponential backoff delays (seconds): 1s, 2s, 4s, 8s
LLM_BACKOFF_DELAYS: List[float] = [1.0, 2.0, 4.0, 8.0]
LLM_MAX_RETRIES: int = 3

T = TypeVar("T")


def is_llm_retryable(exc: Exception) -> bool:
    """Determine if an LLM exception is transient and worth retrying.

    Retryable: network timeouts, connection errors, server overload,
               rate limiting, 5xx HTTP errors.
    Non-retryable: authentication errors, invalid model names,
                   malformed requests, programming errors.

    Args:
        exc: The exception to evaluate.

    Returns:
        True if the exception is considered transient and retrying is safe.
    """
    err_lower = str(exc).lower()
    exc_class = type(exc).__name__.lower()
    transient_keywords = (
        "timeout",
        "connection",
        "rate_limit",
        "ratelimit",
        "overloaded",
        "503",
        "502",
        "500",
        "too many requests",
        "retry",
        "network",
        "unavailable",
        "refused",
        "apiconnectionerror",
        "apitimeouterror",
        "internalservererror",
    )
    return any(kw in err_lower or kw in exc_class for kw in transient_keywords)


def llm_call_with_retry(
    call_fn: Callable[[], T],
    step_name: str,
    max_retries: int = LLM_MAX_RETRIES,
) -> T:
    """Execute an LLM call with exponential backoff retry on transient failures.

    On anthropic.APIError or connection errors: retry up to max_retries times
    with delays: 1s, 2s, 4s, 8s.

    On permanent errors (auth, invalid input): raise immediately.

    Args:
        call_fn:     No-arg callable that performs the LLM request and returns result.
        step_name:   Human-readable step name for logging (e.g. "Step 2 Plan").
        max_retries: Maximum retry attempts before re-raising.

    Returns:
        Result of call_fn() on success.

    Raises:
        Last exception if all retries are exhausted or if the error is non-retryable.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            return call_fn()

        except Exception as exc:
            last_exc = exc
            exc_name = type(exc).__name__

            # Try to detect anthropic-specific error types
            try:
                import anthropic as _anthropic  # noqa: PLC0415

                is_anthropic_err = isinstance(exc, _anthropic.APIError)
            except ImportError:
                is_anthropic_err = False

            retryable = is_anthropic_err or is_llm_retryable(exc)

            if not retryable:
                logger.error(f"[{step_name}] Non-retryable LLM error ({exc_name}): {exc}")
                raise

            if attempt < max_retries:
                delay = LLM_BACKOFF_DELAYS[min(attempt, len(LLM_BACKOFF_DELAYS) - 1)]
                logger.warning(
                    f"[{step_name}] LLM error attempt {attempt + 1}/{max_retries} "
                    f"({exc_name}) - retrying in {delay:.0f}s: {exc}"
                )
                time.sleep(delay)
            else:
                logger.error(f"[{step_name}] LLM call failed after {max_retries} retries " f"({exc_name}): {exc}")

    # All retries exhausted
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"[{step_name}] LLM call failed with no recorded exception")
