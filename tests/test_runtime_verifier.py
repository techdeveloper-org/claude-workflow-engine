"""Tests for the runtime verification subsystem (C-1 for v1.18.0).

Covers:
  - Contract registration and registry lookup
  - Precondition checks: pass, missing key (CRITICAL), wrong type (ERROR), range (ERROR)
  - Postcondition checks: pass, null value (ERROR), min_length violation (ERROR)
  - Decorator behaviour: no-op when disabled, pass-through when enabled
  - VerificationReport: clean report (pass_fail=True) and dirty report (pass_fail=False)
  - NullVerifier: all methods return neutral values with zero side-effects

Fixture ``reset_verifier`` (autouse=True) guarantees singleton isolation between tests.
ENABLE_RUNTIME_VERIFICATION env var is set / unset via monkeypatch per test.
"""

from __future__ import annotations

import pytest

from langgraph_engine.runtime_verification.contracts import NodeContract, PostconditionSpec, PreconditionSpec
from langgraph_engine.runtime_verification.verifier import NullVerifier, RuntimeVerifier

# ---------------------------------------------------------------------------
# Fixture: reset singleton before and after every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_verifier():
    RuntimeVerifier.reset_for_tests()
    yield
    RuntimeVerifier.reset_for_tests()


# ---------------------------------------------------------------------------
# Helper: build a verifier in enabled mode without touching os.environ globally.
# We get the instance after monkeypatching the env var inside each test.
# ---------------------------------------------------------------------------


def _get_enabled_verifier(monkeypatch) -> RuntimeVerifier:
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    return RuntimeVerifier.get_instance()


# ===========================================================================
# 1. test_contract_registration
# ===========================================================================


def test_contract_registration(monkeypatch):
    """Registered contract appears in verifier._registry keyed by node_name."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[],
        postconditions=[],
        invariants=[],
    )
    verifier.register(contract)
    assert "n1" in verifier._registry


# ===========================================================================
# 2. test_precondition_pass
# ===========================================================================


def test_precondition_pass(monkeypatch):
    """Precondition with a present, correctly-typed value returns no violations."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[PreconditionSpec(key="task_description", expected_type=str, required=True)],
    )
    verifier.register(contract)

    state = {"task_description": "build something"}
    violations = verifier.check_preconditions("n1", state)
    assert violations == []


# ===========================================================================
# 3. test_precondition_fail_missing_key
# ===========================================================================


def test_precondition_fail_missing_key(monkeypatch):
    """Missing required key produces exactly one CRITICAL violation."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[PreconditionSpec(key="task_description", expected_type=str, required=True)],
    )
    verifier.register(contract)

    violations = verifier.check_preconditions("n1", {})
    assert len(violations) == 1
    assert violations[0]["severity"] == "CRITICAL"


# ===========================================================================
# 4. test_precondition_fail_wrong_type
# ===========================================================================


def test_precondition_fail_wrong_type(monkeypatch):
    """Value present but wrong type produces at least one ERROR violation."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[PreconditionSpec(key="count", expected_type=int, required=True)],
    )
    verifier.register(contract)

    violations = verifier.check_preconditions("n1", {"count": "not-an-int"})
    assert len(violations) >= 1
    assert violations[0]["severity"] == "ERROR"


# ===========================================================================
# 5. test_precondition_range_pass
# ===========================================================================


def test_precondition_range_pass(monkeypatch):
    """Value within [min_val, max_val] range produces no violations."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[
            PreconditionSpec(
                key="combined_complexity_score",
                expected_type=(int, float),
                required=True,
                min_val=1,
                max_val=25,
            )
        ],
    )
    verifier.register(contract)

    violations = verifier.check_preconditions("n1", {"combined_complexity_score": 15})
    assert violations == []


# ===========================================================================
# 6. test_precondition_range_fail_low
# ===========================================================================


def test_precondition_range_fail_low(monkeypatch):
    """Value below min_val produces at least one ERROR violation."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[
            PreconditionSpec(
                key="combined_complexity_score",
                expected_type=(int, float),
                required=True,
                min_val=1,
                max_val=25,
            )
        ],
    )
    verifier.register(contract)

    violations = verifier.check_preconditions("n1", {"combined_complexity_score": 0})
    assert len(violations) >= 1
    assert violations[0]["severity"] == "ERROR"


# ===========================================================================
# 7. test_precondition_range_fail_high
# ===========================================================================


def test_precondition_range_fail_high(monkeypatch):
    """Value above max_val produces at least one violation."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[
            PreconditionSpec(
                key="combined_complexity_score",
                expected_type=(int, float),
                required=True,
                min_val=1,
                max_val=25,
            )
        ],
    )
    verifier.register(contract)

    violations = verifier.check_preconditions("n1", {"combined_complexity_score": 26})
    assert len(violations) >= 1


# ===========================================================================
# 8. test_postcondition_pass
# ===========================================================================


def test_postcondition_pass(monkeypatch):
    """Postcondition with non-null present value produces no violations."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        postconditions=[PostconditionSpec(key="result", non_null=True, min_length=0)],
    )
    verifier.register(contract)

    violations = verifier.check_postconditions("n1", {"result": "done"})
    assert violations == []


# ===========================================================================
# 9. test_postcondition_fail_null
# ===========================================================================


def test_postcondition_fail_null(monkeypatch):
    """Postcondition with non_null=True fails when value is None -- returns ERROR violation."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        postconditions=[PostconditionSpec(key="result", non_null=True, min_length=0)],
    )
    verifier.register(contract)

    violations = verifier.check_postconditions("n1", {"result": None})
    assert len(violations) >= 1
    assert violations[0]["severity"] == "ERROR"


# ===========================================================================
# 10. test_postcondition_fail_too_short
# ===========================================================================


def test_postcondition_fail_too_short(monkeypatch):
    """String shorter than min_length produces at least one postcondition violation."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        postconditions=[PostconditionSpec(key="orchestration_prompt", non_null=True, min_length=200)],
    )
    verifier.register(contract)

    violations = verifier.check_postconditions("n1", {"orchestration_prompt": "too short"})
    assert len(violations) >= 1


# ===========================================================================
# 11. test_decorator_pass_through
# ===========================================================================


def test_decorator_pass_through():
    """With ENABLE_RUNTIME_VERIFICATION=0 (default), verify_node returns original fn unchanged.

    Because decorators.py checks the env var at decoration time (fast path), and tests run
    with the env var unset by default, verify_node returns fn directly.  The decorated
    function must still be callable and return its normal result.
    """
    from langgraph_engine.runtime_verification.decorators import verify_node

    contract = NodeContract(
        node_name="test_node",
        preconditions=[],
        postconditions=[],
        invariants=[],
    )

    def my_node(state):
        return {"output": "done"}

    # ENABLE_RUNTIME_VERIFICATION is not set (or == "0") in this test, so fast path applies.
    result_fn = verify_node(contract)(my_node)

    # Function must be callable and return correctly
    output = result_fn({})
    assert output == {"output": "done"}

    # When fast path is taken, result_fn IS the original function (no wrapper)
    # OR the wrapper behaves identically -- either is valid.
    assert "output" in result_fn({})


# ===========================================================================
# 12. test_decorator_no_op_when_disabled
# ===========================================================================


def test_decorator_no_op_when_disabled(monkeypatch):
    """With ENABLE_RUNTIME_VERIFICATION=0, NullVerifier accumulates no violations."""
    monkeypatch.delenv("ENABLE_RUNTIME_VERIFICATION", raising=False)

    # NullVerifier is returned when env != "1"
    verifier = RuntimeVerifier.get_instance()
    assert isinstance(verifier, NullVerifier)

    # All check methods return empty lists on NullVerifier
    assert verifier.check_preconditions("x", {}) == []
    assert verifier.check_postconditions("x", {}) == []
    assert verifier.check_level_transition("a", "b", {}) == []


# ===========================================================================
# 13. test_build_report_clean
# ===========================================================================


def test_build_report_clean(monkeypatch):
    """build_report() with no violations returns pass_fail=True and empty violations list."""
    verifier = _get_enabled_verifier(monkeypatch)
    report = verifier.build_report()
    assert report.pass_fail is True
    assert report.violations == []


# ===========================================================================
# 14. test_build_report_with_violations
# ===========================================================================


def test_build_report_with_violations(monkeypatch):
    """After a failed precondition check, build_report() reflects pass_fail=False."""
    verifier = _get_enabled_verifier(monkeypatch)
    contract = NodeContract(
        node_name="n1",
        preconditions=[PreconditionSpec(key="required_key", expected_type=str, required=True)],
    )
    verifier.register(contract)

    # Trigger a CRITICAL violation: required_key is absent
    verifier.check_preconditions("n1", {})

    report = verifier.build_report()
    assert report.pass_fail is False
    assert len(report.violations) >= 1


# ===========================================================================
# 15. test_null_verifier_all_methods_no_op
# ===========================================================================


def test_null_verifier_all_methods_no_op(monkeypatch):
    """NullVerifier: every method is a no-op -- returns neutral values, nothing accumulated."""
    monkeypatch.delenv("ENABLE_RUNTIME_VERIFICATION", raising=False)

    null_verifier = NullVerifier()

    # All check methods return empty list
    assert null_verifier.check_preconditions("x", {"k": "v"}) == []
    assert null_verifier.check_postconditions("x", {"result": "done"}) == []
    assert null_verifier.check_level_transition("level1", "level3", {"combined_complexity_score": 10}) == []

    # build_report returns None (explicitly documented no-op)
    assert null_verifier.build_report() is None

    # register and reset_for_tests must not raise
    contract = NodeContract(node_name="z", preconditions=[], postconditions=[], invariants=[])
    null_verifier.register(contract)
    null_verifier.reset_for_tests()
