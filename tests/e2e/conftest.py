"""Shared pytest fixtures for e2e runtime verification tests.

All fixtures are offline -- zero live network calls, no .env reads,
no real claude CLI subprocess.  External I/O is mocked at the
boundaries defined in the blueprint (B.1 through B.8).

Run:
    pytest tests/e2e/ -m e2e
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap (mirrors test_pipeline_scenarios.py convention)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_SRC_MCP_DIR = _PROJECT_ROOT / "src" / "mcp"

for _p in [str(_PROJECT_ROOT), str(_SCRIPTS_DIR), str(_SRC_MCP_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Singleton isolation: reset RuntimeVerifier before + after every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_verifier():
    """Guarantee singleton isolation between every test in the e2e suite."""
    from langgraph_engine.runtime_verification.verifier import RuntimeVerifier

    RuntimeVerifier.reset_for_tests()
    yield
    RuntimeVerifier.reset_for_tests()


# ---------------------------------------------------------------------------
# Minimal valid FlowState builders
# ---------------------------------------------------------------------------

_GOOD_PROMPT = "A" * 250  # satisfies PROMPT_GEN_CONTRACT min_length=200


@pytest.fixture
def base_hook_state():
    """Minimal FlowState for hook-mode pipeline (CLAUDE_HOOK_MODE=1).

    Contains user_message (required by PRE_ANALYSIS_CONTRACT) and
    combined_complexity_score in valid range [1, 25].
    """
    return {
        "user_message": "implement runtime verification e2e test scenario",
        "task_description": "implement runtime verification e2e test scenario",
        "project_root": str(_PROJECT_ROOT),
        "combined_complexity_score": 10,
        "call_graph_metrics": {},
        "pre_analysis_result": {},
        "template_fast_path": False,
    }


@pytest.fixture
def base_full_state():
    """Minimal FlowState for full-mode pipeline (CLAUDE_HOOK_MODE=0).

    Extends base_hook_state with orchestration_prompt for Step 0 Phase 2.
    """
    return {
        "user_message": "implement runtime verification full-mode e2e scenario",
        "task_description": "implement runtime verification full-mode e2e scenario",
        "project_root": str(_PROJECT_ROOT),
        "combined_complexity_score": 12,
        "call_graph_metrics": {},
        "pre_analysis_result": {},
        "template_fast_path": False,
        "orchestration_prompt": _GOOD_PROMPT,
        "orchestrator_result": {"plan": "mock-plan"},
    }


# ---------------------------------------------------------------------------
# B.1 -- call_execution_script mock (happy path)
# ---------------------------------------------------------------------------

_HAPPY_EXEC_RESULT = {"orchestration_prompt": _GOOD_PROMPT, "status": "ok"}
_VIOLATION_EXEC_RESULT = {"orchestration_prompt": "too short", "status": "ok"}


@pytest.fixture
def mock_call_execution_script_happy():
    """B.1 happy: returns orchestration_prompt of 250 chars -- satisfies postcondition."""
    with patch(
        "langgraph_engine.level3_execution.helpers.call_execution_script",
        return_value=_HAPPY_EXEC_RESULT,
    ) as mock:
        yield mock


@pytest.fixture
def mock_call_execution_script_violation():
    """B.1 violation: returns short orchestration_prompt -- triggers postcondition failure."""
    with patch(
        "langgraph_engine.level3_execution.helpers.call_execution_script",
        return_value=_VIOLATION_EXEC_RESULT,
    ) as mock:
        yield mock


# ---------------------------------------------------------------------------
# B.3 / B.4 -- GitHub-related step mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_step8():
    """B.3: stub GitHub issue creation (Step 8)."""
    with patch(
        "langgraph_engine.level3_execution.nodes.step_wrappers_5to9.step8_github_issue_creation",
        return_value={"github_issue_number": 42, "github_issue_url": "https://github.com/mock/issues/42"},
    ) as mock:
        yield mock


@pytest.fixture
def mock_step9():
    """B.4: stub branch creation (Step 9)."""
    with patch(
        "langgraph_engine.level3_execution.nodes.step_wrappers_5to9.step9_branch_creation",
        return_value={"branch_name": "feature/mock-42"},
    ) as mock:
        yield mock


# ---------------------------------------------------------------------------
# B.8 -- OTel create_span mock (ADR-4)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_create_span():
    """B.8: patch create_span in decorators module (ADR-4 path).

    Yields a MagicMock context manager so tests can assert span attributes
    without requiring a real OTLP collector.
    """
    span_mock = MagicMock()
    span_mock.__enter__ = MagicMock(return_value=span_mock)
    span_mock.__exit__ = MagicMock(return_value=False)

    with patch(
        "langgraph_engine.runtime_verification.decorators.create_span",
        return_value=span_mock,
    ) as mock:
        yield mock, span_mock
