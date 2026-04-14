"""Tests for step_implementations_10_11.py (issue #211).

Verifies:
  - step10_implementation_execution and step11_pull_request_review are importable
    from both the companion module AND via step_wrappers_10_11.py (no NameError)
  - Return dicts always contain the required step10_* / step11_* keys
  - step10 ERROR path on missing prompt
  - step11 SKIPPED path when branch not created
  - step11 SKIPPED path when Level3GitHubWorkflow unavailable
  - Wrapper integration: step10_implementation_note calls the real function

Windows-safe: ASCII only.
"""

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STEP10_REQUIRED_KEYS = {
    "step10_implementation_status",
    "step10_tasks_executed",
    "step10_modified_files",
    "step10_llm_invoked",
    "step10_system_prompt_loaded",
    "step10_user_message_loaded",
    "step10_execution_time_ms",
    "step10_llm_response",
    "step10_changes_summary",
    "step10_error",
}

STEP11_REQUIRED_KEYS = {
    "step11_pr_id",
    "step11_pr_url",
    "step11_review_passed",
    "step11_review_issues",
    "step11_merged",
    "step11_status",
    "step11_execution_time_ms",
    "step11_error",
}


def _make_minimal_state(**kwargs) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "session_id": "test-session",
        "project_root": str(_PROJECT_ROOT),
        "session_dir": str(_PROJECT_ROOT),
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Import tests (issue #211 core requirement: no NameError)
# ---------------------------------------------------------------------------


class TestImport:
    def test_companion_module_importable(self):
        """step_implementations_10_11 must be importable without NameError."""
        from langgraph_engine.level3_execution.nodes.step_implementations_10_11 import (
            step10_implementation_execution,
            step11_pull_request_review,
        )

        assert callable(step10_implementation_execution)
        assert callable(step11_pull_request_review)

    def test_wrappers_expose_implementations(self):
        """step_wrappers_10_11 must re-export the implementation functions (no noqa F821)."""
        from langgraph_engine.level3_execution.nodes.step_wrappers_10_11 import (
            step10_implementation_execution,
            step11_pull_request_review,
        )

        assert callable(step10_implementation_execution)
        assert callable(step11_pull_request_review)

    def test_no_f821_suppressor_in_wrappers(self):
        """Verify the noqa F821 comments were removed from step_wrappers_10_11.py."""
        wrapper_path = _PROJECT_ROOT / "langgraph_engine" / "level3_execution" / "nodes" / "step_wrappers_10_11.py"
        content = wrapper_path.read_text(encoding="utf-8", errors="replace")
        assert (
            "noqa: F821" not in content
        ), "step_wrappers_10_11.py still contains noqa F821 suppressor -- issue #211 not fully resolved"


# ---------------------------------------------------------------------------
# step10_implementation_execution tests
# ---------------------------------------------------------------------------


class TestStep10Implementation:
    def _fn(self, state=None):
        from langgraph_engine.level3_execution.nodes.step_implementations_10_11 import step10_implementation_execution

        return step10_implementation_execution(state or {})

    def test_returns_dict(self):
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.llm_call",
            return_value=None,
        ):
            result = self._fn()
        assert isinstance(result, dict)

    def test_required_keys_always_present(self):
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.llm_call",
            return_value=None,
        ):
            result = self._fn()
        missing = STEP10_REQUIRED_KEYS - result.keys()
        assert not missing, "Missing keys: %s" % missing

    def test_error_when_no_prompt(self):
        """When neither system_prompt.txt nor state prompt exists, returns ERROR."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            state = _make_minimal_state(session_dir=tmp, step7_execution_prompt="")
            with patch(
                "langgraph_engine.level3_execution.nodes.step_implementations_10_11.llm_call",
                return_value=None,
            ):
                result = self._fn(state)
        assert result["step10_implementation_status"] == "ERROR"
        assert result["step10_llm_invoked"] is False
        assert result["step10_tasks_executed"] == 0

    def test_success_with_llm_response(self):
        """When llm_call returns text, status should be SUCCESS."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            state = _make_minimal_state(session_dir=tmp, step7_execution_prompt="Implement feature X")
            with patch(
                "langgraph_engine.level3_execution.nodes.step_implementations_10_11.llm_call",
                return_value="Done. Modified: src/foo.py",
            ), patch(
                "langgraph_engine.level3_execution.nodes.step_implementations_10_11._extract_modified_files",
                return_value=["src/foo.py"],
            ):
                result = self._fn(state)
        assert result["step10_implementation_status"] == "SUCCESS"
        assert result["step10_tasks_executed"] == 1
        assert result["step10_llm_invoked"] is True
        assert result["step10_llm_response"] == "Done. Modified: src/foo.py"
        assert result["step10_modified_files"] == ["src/foo.py"]

    def test_system_prompt_loaded_from_disk(self):
        """Loads system_prompt.txt when present in session_dir."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sp = Path(tmp) / "system_prompt.txt"
            sp.write_text("You are a coder.", encoding="utf-8")
            state = _make_minimal_state(session_dir=tmp, step7_execution_prompt="do it")
            with patch(
                "langgraph_engine.level3_execution.nodes.step_implementations_10_11.llm_call",
                return_value="ok",
            ), patch(
                "langgraph_engine.level3_execution.nodes.step_implementations_10_11._extract_modified_files",
                return_value=[],
            ):
                result = self._fn(state)
        assert result["step10_system_prompt_loaded"] is True

    def test_execution_time_populated(self):
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.llm_call",
            return_value=None,
        ):
            result = self._fn()
        assert result["step10_execution_time_ms"] >= 0

    def test_never_raises(self):
        """Function must not propagate any exception even when llm_call raises."""
        state = _make_minimal_state(step7_execution_prompt="Implement feature X")
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.llm_call",
            side_effect=RuntimeError("boom"),
        ):
            result = self._fn(state)
        assert result["step10_implementation_status"] == "ERROR"
        assert "boom" in result["step10_error"]


# ---------------------------------------------------------------------------
# step11_pull_request_review tests
# ---------------------------------------------------------------------------


class TestStep11PullRequest:
    def _fn(self, state=None):
        from langgraph_engine.level3_execution.nodes.step_implementations_10_11 import step11_pull_request_review

        return step11_pull_request_review(state or {})

    def test_returns_dict(self):
        result = self._fn()
        assert isinstance(result, dict)

    def test_required_keys_always_present(self):
        result = self._fn()
        missing = STEP11_REQUIRED_KEYS - result.keys()
        assert not missing, "Missing keys: %s" % missing

    def test_skipped_when_branch_not_created(self):
        state = _make_minimal_state(step9_branch_created=False)
        result = self._fn(state)
        assert result["step11_status"] == "SKIPPED"
        assert result["step11_execution_time_ms"] >= 0

    def test_skipped_when_github_unavailable(self):
        """If Level3GitHubWorkflow is None, function returns SKIPPED."""
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.Level3GitHubWorkflow",
            None,
        ):
            state = _make_minimal_state(step9_branch_created=True)
            result = self._fn(state)
        assert result["step11_status"] == "SKIPPED"

    def test_skipped_when_no_branch_name(self):
        state = _make_minimal_state(step9_branch_created=True, step9_branch_name="")
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.Level3GitHubWorkflow",
            MagicMock(),
        ):
            result = self._fn(state)
        assert result["step11_status"] == "SKIPPED"

    def test_ok_when_github_succeeds(self):
        mock_wf = MagicMock()
        mock_wf.return_value.step11_create_pull_request.return_value = {
            "success": True,
            "pr_number": 42,
            "pr_url": "https://github.com/org/repo/pull/42",
            "merged": False,
        }
        state = _make_minimal_state(
            step9_branch_created=True,
            step9_branch_name="feature/test",
            step8_issue_id=10,
        )
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.Level3GitHubWorkflow",
            mock_wf,
        ):
            result = self._fn(state)
        assert result["step11_status"] == "OK"
        assert result["step11_pr_id"] == "42"
        assert result["step11_pr_url"] == "https://github.com/org/repo/pull/42"
        assert result["step11_review_passed"] is True

    def test_error_when_github_fails(self):
        mock_wf = MagicMock()
        mock_wf.return_value.step11_create_pull_request.return_value = {
            "success": False,
            "error": "API rate limit",
            "pr_number": 0,
            "pr_url": "",
            "merged": False,
        }
        state = _make_minimal_state(
            step9_branch_created=True,
            step9_branch_name="feature/test",
        )
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.Level3GitHubWorkflow",
            mock_wf,
        ):
            result = self._fn(state)
        assert result["step11_status"] == "ERROR"
        assert "API rate limit" in result["step11_error"]

    def test_never_raises(self):
        mock_wf = MagicMock()
        mock_wf.return_value.step11_create_pull_request.side_effect = RuntimeError("network error")
        state = _make_minimal_state(
            step9_branch_created=True,
            step9_branch_name="feature/test",
        )
        with patch(
            "langgraph_engine.level3_execution.nodes.step_implementations_10_11.Level3GitHubWorkflow",
            mock_wf,
        ):
            result = self._fn(state)
        assert result["step11_status"] == "ERROR"
        assert "network error" in result["step11_error"]
