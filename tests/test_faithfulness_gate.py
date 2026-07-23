"""
Gate 6 (Faithfulness) Tests
============================
Tests for:
    langgraph_engine/level3_execution/faithfulness_gate.py
        - build_faithfulness_prompt()
        - run_faithfulness_check()
    langgraph_engine/level3_execution/quality_gate.py
        - _evaluate_faithfulness_gate() (Gate 6 wiring)

Covers the two-tier opt-in contract (ENABLE_FAITHFULNESS_GATE /
STRICT_FAITHFULNESS_GATE), the four-way verdict mapping (pass/flag/block/
uncertain), the fail-open contract on malformed responses, and that the
prompt sent to `claude -p` is genuinely grounded in the real
hallucination-detection-core SKILL.md content rather than an invented rubric.

All tests inject a fake `caller` -- the real `claude` CLI is never invoked
by this suite (see the module docstring in faithfulness_gate.py for the
one-off manual verification performed outside the automated suite).
"""

from __future__ import annotations

from typing import Optional, Tuple
from unittest.mock import Mock

from langgraph_engine.level3_execution import faithfulness_gate
from langgraph_engine.level3_execution.faithfulness_gate import build_faithfulness_prompt, run_faithfulness_check
from langgraph_engine.level3_execution.quality_gate import _evaluate_faithfulness_gate

# ---------------------------------------------------------------------------
# Fake caller helpers
# ---------------------------------------------------------------------------


def _json_caller(payload: str):
    """Return a caller stub that always responds with the given JSON payload."""

    def _caller(prompt: str) -> Tuple[Optional[str], Optional[str]]:
        return payload, None

    return _caller


def _error_caller(error: str):
    """Return a caller stub that always fails with the given error string."""

    def _caller(prompt: str) -> Tuple[Optional[str], Optional[str]]:
        return None, error

    return _caller


_PASS_JSON = '{"verdict": "pass", "faithfulness_score": 0.9, "flagged_claims": [], ' '"reasoning": "diff matches task"}'
_BLOCK_JSON = (
    '{"verdict": "block", "faithfulness_score": 0.05, '
    '"flagged_claims": ["invented an admin API never requested"], '
    '"reasoning": "diff fabricates scope"}'
)
_FLAG_JSON = (
    '{"verdict": "flag", "faithfulness_score": 0.3, '
    '"flagged_claims": ["adds an unused config flag"], '
    '"reasoning": "weak support for one claim"}'
)
_UNCERTAIN_JSON = (
    '{"verdict": "uncertain", "faithfulness_score": 0.4, "flagged_claims": [], '
    '"reasoning": "borderline, right at threshold"}'
)


# ---------------------------------------------------------------------------
# run_faithfulness_check(): verdict -> passed mapping
# ---------------------------------------------------------------------------


def test_verdict_pass_gate_passes(tmp_path, monkeypatch):
    """A 'pass' verdict must set passed=True and checked=True."""
    mod_file = tmp_path / "mod.py"
    mod_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=["mod.py"],
        project_root=str(tmp_path),
        caller=_json_caller(_PASS_JSON),
    )

    assert result["passed"] is True
    assert result["checked"] is True
    assert result["verdict"] == "pass"
    assert result["faithfulness_score"] == 0.9


def test_verdict_block_gate_fails_even_non_strict(tmp_path, monkeypatch):
    """A 'block' verdict must set passed=False regardless of strict mode."""
    monkeypatch.delenv("STRICT_FAITHFULNESS_GATE", raising=False)
    mod_file = tmp_path / "mod.py"
    mod_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=["mod.py"],
        project_root=str(tmp_path),
        caller=_json_caller(_BLOCK_JSON),
    )

    assert result["passed"] is False, f"block verdict must always block. Full result: {result}"
    assert result["verdict"] == "block"
    assert "invented an admin API" in result["flagged_claims"][0]


def test_verdict_flag_non_strict_passes_with_warning(tmp_path, monkeypatch):
    """A 'flag' verdict in non-strict mode (default) must pass (warning only)."""
    monkeypatch.delenv("STRICT_FAITHFULNESS_GATE", raising=False)
    mod_file = tmp_path / "mod.py"
    mod_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=["mod.py"],
        project_root=str(tmp_path),
        caller=_json_caller(_FLAG_JSON),
    )

    assert result["passed"] is True, f"flag in non-strict mode must not block. Full result: {result}"
    assert result["verdict"] == "flag"
    assert "non-strict" in result["reason"].lower()


def test_verdict_flag_strict_mode_blocks(tmp_path, monkeypatch):
    """A 'flag' verdict with STRICT_FAITHFULNESS_GATE=1 must set passed=False."""
    monkeypatch.setenv("STRICT_FAITHFULNESS_GATE", "1")
    mod_file = tmp_path / "mod.py"
    mod_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=["mod.py"],
        project_root=str(tmp_path),
        caller=_json_caller(_FLAG_JSON),
    )

    assert result["passed"] is False, f"flag in strict mode must block. Full result: {result}"
    assert result["verdict"] == "flag"
    assert "strict mode" in result["reason"].lower()


def test_verdict_uncertain_passes_with_human_review_note(tmp_path, monkeypatch):
    """An 'uncertain' verdict must pass but clearly flag human review is recommended."""
    mod_file = tmp_path / "mod.py"
    mod_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=["mod.py"],
        project_root=str(tmp_path),
        caller=_json_caller(_UNCERTAIN_JSON),
    )

    assert result["passed"] is True
    assert result["verdict"] == "uncertain"
    assert "human review" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Fail-open contract
# ---------------------------------------------------------------------------


def test_malformed_response_fails_open(tmp_path):
    """A non-JSON / malformed caller response must never crash the gate --
    it must return passed=True, checked=False (fail-open)."""
    mod_file = tmp_path / "mod.py"
    mod_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=["mod.py"],
        project_root=str(tmp_path),
        caller=_json_caller("this is not json at all"),
    )

    assert result["passed"] is True
    assert result["checked"] is False
    assert "not be used" in result["reason"] or "fail-open" in result["reason"]


def test_caller_error_fails_open(tmp_path):
    """A caller-reported error (e.g. claude binary missing, timeout) must
    fail open: passed=True, checked=False, never raise."""
    mod_file = tmp_path / "mod.py"
    mod_file.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=["mod.py"],
        project_root=str(tmp_path),
        caller=_error_caller("claude CLI binary not found in PATH"),
    )

    assert result["passed"] is True
    assert result["checked"] is False
    assert "claude CLI binary not found" in result["reason"]


def test_no_modified_files_skips_without_calling(tmp_path):
    """With no modified files, the check must skip entirely and never invoke caller."""
    fake_caller = Mock()

    result = run_faithfulness_check(
        task_description="Add a function that returns 1",
        modified_files=[],
        project_root=str(tmp_path),
        caller=fake_caller,
    )

    assert result["passed"] is True
    assert result["checked"] is False
    fake_caller.assert_not_called()


# ---------------------------------------------------------------------------
# Gate 6 wiring: two-tier opt-in (ENABLE_FAITHFULNESS_GATE / STRICT_FAITHFULNESS_GATE)
# ---------------------------------------------------------------------------


def test_gate6_disabled_by_default_never_calls_check(tmp_path, monkeypatch):
    """Gate 6 must be OFF by default and must not even import/call
    run_faithfulness_check -- proving zero added cost when the feature is off."""
    monkeypatch.delenv("ENABLE_FAITHFULNESS_GATE", raising=False)

    fake_check = Mock()
    monkeypatch.setattr(faithfulness_gate, "run_faithfulness_check", fake_check)

    state = {
        "user_message": "Add a function that returns 1",
        "step10_modified_files": ["mod.py"],
    }

    result = _evaluate_faithfulness_gate(str(tmp_path), state)

    assert result["passed"] is True
    assert result["checked"] is False
    assert "disabled" in result["reason"].lower()
    fake_check.assert_not_called()


def test_gate6_enabled_invokes_check_and_propagates_result(tmp_path, monkeypatch):
    """When enabled, Gate 6 must call run_faithfulness_check and propagate its result."""
    monkeypatch.setenv("ENABLE_FAITHFULNESS_GATE", "1")
    monkeypatch.delenv("STRICT_FAITHFULNESS_GATE", raising=False)

    fake_check = Mock(
        return_value={
            "passed": False,
            "reason": "Faithfulness check blocked. fabricated scope",
            "verdict": "block",
            "faithfulness_score": 0.05,
            "flagged_claims": ["invented an admin API"],
            "checked": True,
            "library_available": True,
        }
    )
    monkeypatch.setattr(faithfulness_gate, "run_faithfulness_check", fake_check)

    state = {
        "user_message": "Add a function that returns 1",
        "step10_modified_files": ["mod.py"],
    }

    result = _evaluate_faithfulness_gate(str(tmp_path), state)

    fake_check.assert_called_once()
    assert result["passed"] is False
    assert result["verdict"] == "block"


def test_gate6_evaluation_error_fails_safe(tmp_path, monkeypatch):
    """If run_faithfulness_check raises unexpectedly, Gate 6 must fail-safe
    (passed=True) rather than propagate the exception."""
    monkeypatch.setenv("ENABLE_FAITHFULNESS_GATE", "1")

    def _boom(*args, **kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(faithfulness_gate, "run_faithfulness_check", _boom)

    state = {
        "user_message": "Add a function that returns 1",
        "step10_modified_files": ["mod.py"],
    }

    result = _evaluate_faithfulness_gate(str(tmp_path), state)

    assert result["passed"] is True
    assert "fail-safe" in result["reason"].lower()


# test_prompt_contains_real_skill_content moved to
# tests/integration/test_library_resolver_real_sibling.py (requires the real
# claude-global-library sibling checkout, absent in CI)


def test_prompt_asks_for_structured_json_and_thresholds():
    """The prompt must request structured JSON output and state the general
    (non-medical/legal) thresholds explicitly."""
    prompt = build_faithfulness_prompt(
        task_description="Add a function that returns 1",
        diff_summary="--- mod.py ---\ndef f():\n    return 1",
        rubric_content="(rubric placeholder for this unit test)",
    )

    assert '"verdict"' in prompt
    assert '"faithfulness_score"' in prompt
    assert '"flagged_claims"' in prompt
    assert "0.4" in prompt  # flag threshold
    assert "0.2" in prompt  # block threshold
    assert "uncertain" in prompt.lower()
