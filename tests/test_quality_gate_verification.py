"""
C-4 Runtime Verification Gate Tests (v1.18.0)
==============================================
Tests for Gate 5 (_evaluate_verification_gate) in:
    langgraph_engine/level3_execution/quality_gate.py

Covers:
  1. Gate skipped when ENABLE_RUNTIME_VERIFICATION is not set / set to '0'
  2. Gate passes on a clean verification report (0 violations)
  3. Gate does NOT block in non-strict mode (violations present, no exception raised)
  4. Gate blocks (passed=False) in strict mode when violations are present

All tests manipulate environment variables via monkeypatch so they are
isolated and do not affect each other or the rest of the test suite.
"""

from __future__ import annotations

from langgraph_engine.level3_execution.quality_gate import _evaluate_verification_gate

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def _clean_report() -> dict:
    """Minimal verification report with no violations -- all checks passed."""
    return {
        "verified_nodes": [],
        "violations": [],
        "warnings": [],
        "pass_fail": True,
        "elapsed_ms_per_node": {},
    }


def _failing_report() -> dict:
    """Verification report that contains one ERROR-level violation."""
    return {
        "verified_nodes": ["n1"],
        "violations": [
            {
                "node_name": "n1",
                "check_type": "precondition",
                "key": "x",
                "message": "missing required key 'x'",
                "severity": "ERROR",
            }
        ],
        "warnings": [],
        "pass_fail": False,
        "elapsed_ms_per_node": {"n1": 12},
    }


# ---------------------------------------------------------------------------
# Test 1: Gate skipped when ENABLE_RUNTIME_VERIFICATION is disabled
# ---------------------------------------------------------------------------


def test_gate5_skip_when_disabled(monkeypatch):
    """Gate 5 must pass immediately when ENABLE_RUNTIME_VERIFICATION is not '1'.

    The implementation checks os.getenv('ENABLE_RUNTIME_VERIFICATION', '0') != '1'
    and returns early with passed=True and a 'disabled' reason string.
    """
    # Ensure the env var is explicitly absent / set to '0'
    monkeypatch.delenv("ENABLE_RUNTIME_VERIFICATION", raising=False)
    monkeypatch.delenv("STRICT_RUNTIME_VERIFICATION", raising=False)

    # State deliberately has no 'verification_report' key -- gate must not inspect it
    state: dict = {}

    result = _evaluate_verification_gate(state)

    # Gate must pass
    assert result["passed"] is True, "Expected gate to pass (disabled) but got passed=False. " f"Full result: {result}"

    # Reason must mention disabled state
    reason_lower = result.get("reason", "").lower()
    assert "disabled" in reason_lower, (
        "Expected 'disabled' in reason when gate is off. " f"Got reason: {result.get('reason')!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: Gate passes on clean report (zero violations)
# ---------------------------------------------------------------------------


def test_gate5_pass_clean_report(monkeypatch):
    """Gate 5 must pass when verification_report contains 0 violations.

    A report with an empty violations list and pass_fail=True should result
    in passed=True regardless of strict-mode setting.
    """
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    monkeypatch.delenv("STRICT_RUNTIME_VERIFICATION", raising=False)

    state = {"verification_report": _clean_report()}

    result = _evaluate_verification_gate(state)

    assert result["passed"] is True, (
        "Expected gate to pass for a clean report but got passed=False. " f"Full result: {result}"
    )
    assert (
        result["violation_count"] == 0
    ), f"Expected violation_count=0 for clean report, got {result['violation_count']}"
    # Reason should mention '0 violations' (see implementation line ~555)
    assert (
        "0" in result.get("reason", "") or "violation" in result.get("reason", "").lower()
    ), f"Expected reason to reference violation count. Got: {result.get('reason')!r}"


# ---------------------------------------------------------------------------
# Test 3: Gate does NOT raise in non-strict mode with violations present
# ---------------------------------------------------------------------------


def test_gate5_warn_non_strict(monkeypatch):
    """Gate 5 must not raise and must NOT block when STRICT_RUNTIME_VERIFICATION=0.

    With violations present and strict mode off, the gate should:
      - NOT raise any exception
      - return a result dict (not None)
      - keep passed=True (non-blocking warning behaviour)
      - include a reason that references violations
    """
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    monkeypatch.setenv("STRICT_RUNTIME_VERIFICATION", "0")

    state = {"verification_report": _failing_report()}

    # Must not raise any exception
    result = _evaluate_verification_gate(state)

    assert result is not None, "Gate returned None; expected a result dict"
    assert isinstance(result, dict), f"Expected dict result, got {type(result)}"

    # In non-strict mode the gate should NOT block (passed=True)
    assert result["passed"] is True, (
        "Expected non-strict mode gate to pass (warning only), but got passed=False. " f"Full result: {result}"
    )

    # Reason should communicate that violations were found but are non-blocking
    reason = result.get("reason", "").lower()
    assert "violation" in reason or "non-strict" in reason, (
        f"Expected reason to reference violations or non-strict mode. " f"Got: {result.get('reason')!r}"
    )

    # Violation count must be populated correctly
    assert (
        result.get("violation_count", 0) >= 1
    ), f"Expected at least 1 violation_count but got {result.get('violation_count')}"


# ---------------------------------------------------------------------------
# Test 4: Gate blocks (passed=False) in strict mode with violations present
# ---------------------------------------------------------------------------


def test_gate5_halt_strict_mode(monkeypatch):
    """Gate 5 must set passed=False when STRICT_RUNTIME_VERIFICATION=1 and violations exist.

    B-10 implementation sets passed=False rather than raising an exception.
    The test verifies:
      - No exception is raised
      - passed=False is returned
      - violation_count >= 1
      - reason contains a reference to violations
    """
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    monkeypatch.setenv("STRICT_RUNTIME_VERIFICATION", "1")

    state = {"verification_report": _failing_report()}

    # Must not raise even in strict mode
    result = _evaluate_verification_gate(state)

    assert result is not None, "Gate returned None; expected a result dict"

    # In strict mode with violations the gate MUST block
    assert result["passed"] is False, (
        "Expected strict mode to set passed=False when violations present, "
        f"but got passed={result['passed']}. Full result: {result}"
    )

    # Violation count must reflect what was in the report
    assert (
        result.get("violation_count", 0) >= 1
    ), f"Expected violation_count >= 1 in strict mode but got {result.get('violation_count')}"

    # Reason should reference the violation count
    reason = result.get("reason", "").lower()
    assert "violation" in reason, (
        f"Expected reason to reference violations in strict mode. " f"Got: {result.get('reason')!r}"
    )
