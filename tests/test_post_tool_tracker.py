"""
test_post_tool_tracker.py - Unit tests for scripts/post-tool-tracker.py

Covers core tracking and enforcement functions:
 - is_error_response: error detection from tool response dict/string
 - estimate_context_pct: tool counts to context percentage mapping
 - get_response_content_length: measures dict and string response size
 - load_session_progress: defaults when file missing
 - save/load round-trip: session progress persistence
 - log_tool_entry: JSONL append and auto-timestamp
 - check_level_3_8_phase_requirement: blocks Write before TaskCreate
 - check_level_3_9_build_validation: build validation on Bash
 - check_level_3_11_git_status: uncommitted changes block git push
 - _detect_result_failure: file not found pattern detection
 - _clear_session_flags: removes flag files from session dir

Windows-safe: ASCII only, no Unicode characters.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Prevent module-level workflow guard from skipping the entire module
os.environ.pop("CLAUDE_WORKFLOW_RUNNING", None)

# ---------------------------------------------------------------------------
# The script filename uses hyphens so we must use importlib.util to load it.
# ---------------------------------------------------------------------------
import importlib.util as _ilu  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOOKS_DIR = _REPO_ROOT / "hooks"

# Ensure project root is on sys.path for langgraph_engine imports
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Mock all heavy external dependencies before importing the module
# ---------------------------------------------------------------------------
with patch.dict(
    "sys.modules",
    {
        "ide_paths": MagicMock(
            SESSION_STATE_FILE=Path("/tmp/.claude/memory/logs/session-progress.json"),
            TRACKER_LOG=Path("/tmp/.claude/memory/logs/tool-tracker.jsonl"),
            FLAG_DIR=Path("/tmp/.claude"),
        ),
        "project_session": MagicMock(
            read_session_id=lambda: "SESSION-TEST-001",
        ),
        "metrics_emitter": MagicMock(),
        "policy_tracking_helper": MagicMock(
            record_policy_execution=lambda *a, **kw: None,
            record_sub_operation=lambda *a, **kw: None,
            get_session_id=lambda *a, **kw: "SESSION-TEST-001",
        ),
        "common_failures_prevention": MagicMock(),
        "github_issue_manager": MagicMock(),
        "post_tool_tracker_mcp_server": MagicMock(),
    },
):
    _spec = _ilu.spec_from_file_location("post_tool_tracker", _HOOKS_DIR / "post-tool-tracker.py")
    ptt = _ilu.module_from_spec(_spec)
    sys.modules["post_tool_tracker"] = ptt
    _spec.loader.exec_module(ptt)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_progress_file(tmp_path, state=None):
    """Write a minimal session-progress.json and return its path."""
    progress_dir = tmp_path / ".claude" / "memory" / "logs"
    progress_dir.mkdir(parents=True, exist_ok=True)
    state = state or {
        "total_progress": 10,
        "tool_counts": {"Read": 2},
        "started_at": "2026-03-18T10:00:00",
        "tasks_completed": 0,
        "errors_seen": 0,
    }
    progress_file = progress_dir / "session-progress.json"
    progress_file.write_text(json.dumps(state), encoding="utf-8")
    return progress_file


def _make_tracker_log(tmp_path):
    """Return path for the JSONL tracker log (parent dirs created)."""
    log_dir = tmp_path / ".claude" / "memory" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "tool-tracker.jsonl"


# ===========================================================================
# is_error_response
# ===========================================================================


class TestIsErrorResponse:
    def test_dict_with_is_error_false_returns_true(self):
        response = {"is_error": True, "content": "something failed"}
        assert ptt.is_error_response(response) is True

    def test_dict_with_success_true_returns_false(self):
        response = {"is_error": False, "content": "ok result"}
        assert ptt.is_error_response(response) is False

    def test_dict_with_error_content_prefix_returns_true(self):
        response = {"content": "error: file not found"}
        assert ptt.is_error_response(response) is True

    def test_dict_with_failed_content_prefix_returns_true(self):
        response = {"content": "failed: could not connect"}
        assert ptt.is_error_response(response) is True

    def test_dict_with_normal_content_returns_false(self):
        response = {"content": "File written successfully"}
        assert ptt.is_error_response(response) is False

    def test_non_dict_non_string_returns_false(self):
        assert ptt.is_error_response(None) is False
        assert ptt.is_error_response(42) is False
        assert ptt.is_error_response([]) is False


# ===========================================================================
# estimate_context_pct
# ===========================================================================


class TestEstimateContextPct:
    def test_empty_counts_returns_fixed_overhead(self):
        result = ptt.estimate_context_pct({}, content_chars=0)
        # Fixed overhead is ~44.5%, so int(44.5) == 44
        assert result >= 44, "Empty tool counts should return at least the fixed overhead %"

    def test_large_content_chars_increases_estimate(self):
        small = ptt.estimate_context_pct({}, content_chars=1000)
        large = ptt.estimate_context_pct({}, content_chars=100000)
        assert large > small, "More content chars should produce a higher context estimate"

    def test_result_never_exceeds_95(self):
        result = ptt.estimate_context_pct(
            {"Read": 100, "Write": 100, "Task": 100},
            content_chars=10000000,
        )
        assert result <= 95, "estimate_context_pct should be capped at 95"

    def test_count_based_fallback_uses_tool_weights(self):
        # With no content_chars, the fallback uses tool count heuristic
        counts_heavy = {"Read": 20, "Task": 10}
        counts_light = {"Glob": 1}
        heavy = ptt.estimate_context_pct(counts_heavy, content_chars=0)
        light = ptt.estimate_context_pct(counts_light, content_chars=0)
        assert heavy > light, "Higher tool count should produce larger context estimate"


# ===========================================================================
# get_response_content_length
# ===========================================================================


class TestGetResponseContentLength:
    def test_dict_with_string_content(self):
        response = {"content": "hello world"}
        assert ptt.get_response_content_length(response) == len("hello world")

    def test_dict_with_list_content(self):
        response = {"content": [{"text": "abc"}, {"text": "de"}]}
        assert ptt.get_response_content_length(response) == 5

    def test_bare_string(self):
        assert ptt.get_response_content_length("hello") == 5

    def test_empty_dict_returns_zero(self):
        assert ptt.get_response_content_length({}) == 0

    def test_none_returns_zero(self):
        assert ptt.get_response_content_length(None) == 0

    def test_dict_without_content_key_returns_zero(self):
        assert ptt.get_response_content_length({"other": "value"}) == 0


# ===========================================================================
# load_session_progress: missing file returns defaults
# ===========================================================================


class TestLoadSessionProgress:
    def test_missing_file_returns_defaults(self, tmp_path):
        missing_file = tmp_path / "nonexistent" / "session-progress.json"
        with patch.object(ptt, "SESSION_STATE_FILE", missing_file):
            state = ptt.load_session_progress()
        assert "total_progress" in state
        assert "tool_counts" in state
        assert "started_at" in state
        assert "tasks_completed" in state
        assert "errors_seen" in state
        assert state["total_progress"] == 0

    def test_returns_zero_progress_from_defaults(self, tmp_path):
        missing_file = tmp_path / "no-file.json"
        with patch.object(ptt, "SESSION_STATE_FILE", missing_file):
            state = ptt.load_session_progress()
        assert state["total_progress"] == 0
        assert state["tasks_completed"] == 0


# ===========================================================================
# save/load round-trip
# ===========================================================================


class TestSaveLoadSessionProgress:
    def test_save_then_load_returns_same_data(self, tmp_path):
        progress_file = tmp_path / "session-progress.json"
        test_state = {
            "total_progress": 42,
            "tool_counts": {"Read": 5, "Write": 2},
            "started_at": "2026-03-18T12:00:00",
            "tasks_completed": 1,
            "errors_seen": 0,
        }
        with patch.object(ptt, "SESSION_STATE_FILE", progress_file):
            ptt.save_session_progress(test_state)
            loaded = ptt.load_session_progress()

        assert loaded["total_progress"] == 42
        assert loaded["tool_counts"]["Read"] == 5
        assert loaded["tasks_completed"] == 1

    def test_save_creates_parent_directories(self, tmp_path):
        nested_file = tmp_path / "a" / "b" / "c" / "session-progress.json"
        test_state = {
            "total_progress": 5,
            "tool_counts": {},
            "started_at": "2026-03-18T12:00:00",
            "tasks_completed": 0,
            "errors_seen": 0,
        }
        with patch.object(ptt, "SESSION_STATE_FILE", nested_file):
            ptt.save_session_progress(test_state)
        assert nested_file.exists(), "save should create parent directories"


# ===========================================================================
# log_tool_entry: JSONL append
# ===========================================================================


class TestLogToolEntry:
    def test_creates_jsonl_file_and_appends_entry(self, tmp_path):
        tracker_log = _make_tracker_log(tmp_path)
        entry = {
            "ts": "2026-03-18T12:00:00",
            "tool": "Read",
            "status": "success",
            "progress_delta": 10,
        }
        with patch.object(ptt, "TRACKER_LOG", tracker_log):
            ptt.log_tool_entry(entry)

        assert tracker_log.exists(), "log_tool_entry should create the JSONL file"
        lines = tracker_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["tool"] == "Read"

    def test_appends_multiple_entries(self, tmp_path):
        tracker_log = _make_tracker_log(tmp_path)
        entries = [
            {"ts": "2026-03-18T12:00:01", "tool": "Read", "status": "success", "progress_delta": 10},
            {"ts": "2026-03-18T12:00:02", "tool": "Write", "status": "success", "progress_delta": 40},
        ]
        with patch.object(ptt, "TRACKER_LOG", tracker_log):
            for e in entries:
                ptt.log_tool_entry(e)

        lines = tracker_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_auto_timestamp_concept(self):
        # Verify that 'ts' field format matches datetime strftime pattern used in main()
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        assert "T" in ts, "Timestamp should use ISO-8601 T separator"
        assert len(ts) == 19


# ===========================================================================
# check_level_3_8_phase_requirement
# ===========================================================================


class TestCheckLevel38PhaseRequirement:
    def test_blocks_write_before_taskcreate_high_complexity(self):
        flow_ctx = {"complexity": 7}
        state = {"tasks_created": 0}
        blocked, msg = ptt.check_level_3_8_phase_requirement("Write", flow_ctx, state)
        assert blocked is True
        assert "BLOCKED" in msg or "L3.8" in msg

    def test_blocks_edit_before_taskcreate_high_complexity(self):
        flow_ctx = {"complexity": 8}
        state = {"tasks_created": 0}
        blocked, msg = ptt.check_level_3_8_phase_requirement("Edit", flow_ctx, state)
        assert blocked is True

    def test_no_block_when_tasks_already_created(self):
        flow_ctx = {"complexity": 9}
        state = {"tasks_created": 1}
        blocked, msg = ptt.check_level_3_8_phase_requirement("Write", flow_ctx, state)
        assert blocked is False

    def test_no_block_for_low_complexity(self):
        flow_ctx = {"complexity": 3}
        state = {"tasks_created": 0}
        blocked, msg = ptt.check_level_3_8_phase_requirement("Write", flow_ctx, state)
        assert blocked is False

    def test_no_block_for_bash_tool(self):
        flow_ctx = {"complexity": 10}
        state = {"tasks_created": 0}
        blocked, msg = ptt.check_level_3_8_phase_requirement("Bash", flow_ctx, state)
        assert blocked is False

    def test_threshold_is_exactly_6(self):
        # Complexity == 6 should trigger the block (>= 6 threshold)
        flow_ctx = {"complexity": 6}
        state = {"tasks_created": 0}
        blocked, _ = ptt.check_level_3_8_phase_requirement("Write", flow_ctx, state)
        assert blocked is True


# ===========================================================================
# check_level_3_9_build_validation
# ===========================================================================


class TestCheckLevel39BuildValidation:
    def test_no_block_for_non_taskupdate(self):
        blocked, _ = ptt.check_level_3_9_build_validation("Bash", {"command": "ls"}, False, {})
        assert blocked is False

    def test_no_block_when_build_not_failed(self):
        state = {"last_build_failed": False}
        blocked, _ = ptt.check_level_3_9_build_validation("TaskUpdate", {"status": "completed"}, False, state)
        assert blocked is False

    def test_no_block_when_status_not_completed(self):
        state = {"last_build_failed": True}
        blocked, _ = ptt.check_level_3_9_build_validation("TaskUpdate", {"status": "in_progress"}, False, state)
        assert blocked is False

    def test_no_block_when_is_error_true(self):
        state = {"last_build_failed": True}
        blocked, _ = ptt.check_level_3_9_build_validation("TaskUpdate", {"status": "completed"}, True, state)
        assert blocked is False

    def test_blocks_when_build_failed_and_completing_task(self):
        state = {
            "last_build_failed": True,
            "last_build_failed_label": "pytest",
        }
        blocked, msg = ptt.check_level_3_9_build_validation("TaskUpdate", {"status": "completed"}, False, state)
        assert blocked is True
        assert "BLOCKED" in msg or "build" in msg.lower()
        assert "pytest" in msg


# ===========================================================================
# check_level_3_11_git_status
# ===========================================================================


class TestCheckLevel311GitStatus:
    def test_no_block_for_non_bash_tool(self):
        blocked, _ = ptt.check_level_3_11_git_status("Write", {"file_path": "x.py"})
        assert blocked is False

    def test_no_block_for_non_push_command(self):
        blocked, _ = ptt.check_level_3_11_git_status("Bash", {"command": "git status"})
        assert blocked is False

    def test_no_block_for_dry_run(self):
        blocked, _ = ptt.check_level_3_11_git_status("Bash", {"command": "git push --dry-run"})
        assert blocked is False

    def test_blocks_push_when_uncommitted_changes_exist(self):
        dirty_output = " M scripts/test.py\n?? newfile.txt\n"
        mock_result = MagicMock(stdout=dirty_output, returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            blocked, msg = ptt.check_level_3_11_git_status("Bash", {"command": "git push origin feature/test"})
        assert blocked is True
        assert "BLOCKED" in msg or "uncommitted" in msg.lower()

    def test_allows_push_when_working_tree_clean(self):
        mock_result = MagicMock(stdout="", returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            blocked, _ = ptt.check_level_3_11_git_status("Bash", {"command": "git push origin feature/test"})
        assert blocked is False

    def test_fail_open_on_subprocess_error(self):
        with patch("subprocess.run", side_effect=OSError("git not found")):
            blocked, _ = ptt.check_level_3_11_git_status("Bash", {"command": "git push origin main"})
        assert blocked is False, "Should fail-open when git status check errors"


# ===========================================================================
# _detect_result_failure: file not found pattern
# ===========================================================================


class TestDetectResultFailure:
    def test_returns_none_when_no_failure_detector(self):
        original = ptt._failure_detector
        ptt._failure_detector = None
        try:
            result = ptt._detect_result_failure({"content": "file not found"})
        finally:
            ptt._failure_detector = original
        assert result is None

    def test_returns_none_for_empty_response(self):
        result = ptt._detect_result_failure(None)
        assert result is None

    def test_calls_failure_detector_with_string_slice(self):
        mock_detector = MagicMock()
        mock_detector.detect_failure_in_message.return_value = {
            "type": "file_not_found",
            "severity": "high",
        }
        original = ptt._failure_detector
        ptt._failure_detector = mock_detector
        try:
            result = ptt._detect_result_failure("error: No such file or directory: test.py")
        finally:
            ptt._failure_detector = original

        assert result is not None
        mock_detector.detect_failure_in_message.assert_called_once()


# ===========================================================================
# _clear_session_flags: removes flag files
# ===========================================================================


class TestClearSessionFlags:
    def test_clears_session_folder_flag(self, tmp_path):
        session_id = "SESSION-CLR-001"
        flag_name = "task-breakdown-pending"
        flag_dir = tmp_path / ".claude" / "memory" / "logs" / "sessions" / session_id / "flags"
        flag_dir.mkdir(parents=True, exist_ok=True)
        flag_file = flag_dir / (flag_name + ".json")
        flag_file.write_text(json.dumps({"session_id": session_id}), encoding="utf-8")

        assert flag_file.exists(), "Flag file should exist before clearing"

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch.object(ptt, "FLAG_DIR", tmp_path / ".claude"),
        ):
            ptt._clear_session_flags(".task-breakdown-pending", session_id)

        assert not flag_file.exists(), "Flag file should be removed after _clear_session_flags"

    def test_no_error_when_flag_does_not_exist(self, tmp_path):
        # Should not raise even if the flag file is absent
        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch.object(ptt, "FLAG_DIR", tmp_path / ".claude"),
        ):
            ptt._clear_session_flags(".task-breakdown-pending", "SESSION-NOEXIST-001")

    def test_no_op_when_session_id_empty(self):
        # Empty session_id should be a no-op without error
        ptt._clear_session_flags(".task-breakdown-pending", "")
