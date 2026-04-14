"""Tests for langgraph_engine.runtime_verification.schema_verifier.

Pure function tests -- no fixtures, no monkeypatching, no singleton state needed.
Covers: happy path, empty input, whitespace-only, too-short, error-string detection.

Constants under test:
    _MIN_PROMPT_LEN = 200
    _MIN_RESULT_LEN = 50
    _ERROR_PREFIXES: tuple of lowercase prefix strings
"""

from langgraph_engine.runtime_verification.schema_verifier import (
    verify_orchestration_prompt,
    verify_orchestrator_result,
)

# ---------------------------------------------------------------------------
# verify_orchestration_prompt -- 4 tests
# ---------------------------------------------------------------------------


def test_verify_orchestration_prompt_valid():
    """A prompt with length >= 200 and containing 'Phase' must return no errors."""
    # Arrange: 20 chars of prefix + 240 padding = 260 chars total, contains "Phase"
    prompt = "Phase A foundation: " + "x" * 240
    assert len(prompt) == 260  # sanity check for the test itself

    # Act
    errors = verify_orchestration_prompt(prompt)

    # Assert
    assert errors == [], f"Expected no errors but got: {errors}"


def test_verify_orchestration_prompt_empty():
    """An empty string must produce at least one error mentioning 'empty'."""
    # Act
    errors = verify_orchestration_prompt("")

    # Assert
    assert len(errors) >= 1
    assert any("empty" in e.lower() for e in errors), f"Expected an 'empty' error in {errors}"


def test_verify_orchestration_prompt_whitespace_only():
    """Whitespace-only input is treated as empty and must produce at least one error."""
    # Act
    errors = verify_orchestration_prompt("   ")

    # Assert -- whitespace-only triggers the empty branch (prompt.strip() is falsy)
    assert len(errors) >= 1


def test_verify_orchestration_prompt_too_short():
    """A prompt that contains 'Phase' but is under the 200-char minimum must flag length.

    The error message must reference 'short', '200', or 'min' so callers understand
    the threshold that was violated.
    """
    # Arrange: well under 200 chars, but 'Phase' keyword is present
    prompt = "Phase short"
    assert len(prompt) < 200  # sanity check

    # Act
    errors = verify_orchestration_prompt(prompt)

    # Assert: at least one error and it mentions the length constraint
    assert len(errors) >= 1
    assert any(
        "short" in e.lower() or "200" in e or "min" in e.lower() for e in errors
    ), f"Expected a length-related error in {errors}"


# ---------------------------------------------------------------------------
# verify_orchestrator_result -- 3 tests
# ---------------------------------------------------------------------------


def test_verify_orchestrator_result_valid():
    """A non-error result with length >= 50 must return no errors."""
    # Arrange: 25 chars of prefix + 80 padding = 105 chars total, no error prefix
    result = "Implementation complete. " + "y" * 80
    assert len(result) == 105  # sanity check

    # Act
    errors = verify_orchestrator_result(result)

    # Assert
    assert errors == [], f"Expected no errors but got: {errors}"


def test_verify_orchestrator_result_empty():
    """An empty result string must produce at least one error."""
    # Act
    errors = verify_orchestrator_result("")

    # Assert
    assert len(errors) >= 1


def test_verify_orchestrator_result_error_string():
    """A result that starts with an error prefix must be flagged.

    'Error: connection refused...' lowercases to 'error:...' which matches
    _ERROR_PREFIXES entry 'error:'.  The returned error message must contain
    the word 'error' so the caller can identify the category of failure.
    """
    # Arrange
    result = "Error: connection refused to claude API"

    # Act
    errors = verify_orchestrator_result(result)

    # Assert
    assert len(errors) >= 1
    assert any("error" in e.lower() for e in errors), f"Expected an error-detection message in {errors}"
