"""
test_pre_tool_enforcer.py - Unit tests for scripts/pre-tool-enforcer.py

Covers core enforcement functions:
 - check_bash: Windows command detection
 - check_python_unicode: non-ASCII detection in .py files
 - check_grep: head_limit warnings
 - check_read: offset/limit warnings for large files
 - check_checkpoint_pending: blocks Write while flag exists
 - check_task_breakdown_pending: blocks Edit while flag exists
 - check_skill_selection_pending: blocks Write while flag exists
 - check_level1_sync_complete: blocks without Level 1 trace
 - check_level2_standards_complete: blocks without Level 2 trace
 - check_write_edit: calls unicode check for .py files
 - check_dynamic_skill_context: detects .py extension
 - _load_flow_trace_context: returns empty dict when file missing
 - find_session_flag: expired flags return None

Windows-safe: ASCII only, no Unicode characters.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

# Prevent module-level side effects: CLAUDE_WORKFLOW_RUNNING guard must stay off
os.environ.pop("CLAUDE_WORKFLOW_RUNNING", None)

# ---------------------------------------------------------------------------
# Module import with all problematic top-level side effects mocked.
# The script filename uses hyphens so we must use importlib.util to load it.
# ---------------------------------------------------------------------------
import importlib.util as _ilu  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOOKS_DIR = _REPO_ROOT / "hooks"

# Ensure project root is on sys.path for langgraph_engine imports
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# We patch the hard external deps at import time so the module loads cleanly.
with patch.dict(
    "sys.modules",
    {
        "ide_paths": MagicMock(FLAG_DIR=Path("/tmp/.claude"), CURRENT_SESSION_FILE=Path("/tmp/.current-session.json")),
        "project_session": MagicMock(get_project_session_file=lambda: Path("/tmp/.current-session.json")),
        "metrics_emitter": MagicMock(),
        "policy_tracking_helper": MagicMock(
            record_policy_execution=lambda *a, **kw: None,
            record_sub_operation=lambda *a, **kw: None,
            get_session_id=lambda *a, **kw: "SESSION-TEST-001",
        ),
        "tool_usage_optimization_policy": MagicMock(),
        "common_failures_prevention": MagicMock(),
        "mcp_hook_integration": MagicMock(
            should_suggest_mcp=lambda: False,
            enhance_read_blocking_message=lambda m, *a: m,
            enhance_grep_blocking_message=lambda m: m,
            log_mcp_routing_decision=lambda *a, **kw: None,
        ),
    },
):
    _spec = _ilu.spec_from_file_location("pre_tool_enforcer", _HOOKS_DIR / "pre-tool-enforcer.py")
    pte = _ilu.module_from_spec(_spec)
    sys.modules["pre_tool_enforcer"] = pte
    _spec.loader.exec_module(pte)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flag(tmp_path, flag_name, session_id, created_at=None, extra=None):
    """Write a minimal flag JSON file into tmp_path."""
    flag_dir = tmp_path / "flags"
    flag_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "session_id": session_id,
        "created_at": (created_at or datetime.now()).isoformat(),
        "prompt_preview": "test task preview",
    }
    if extra:
        data.update(extra)
    flag_file = flag_dir / (flag_name.lstrip(".") + ".json")
    flag_file.write_text(json.dumps(data), encoding="utf-8")
    return flag_file


# ===========================================================================
# check_bash
# ===========================================================================


class TestCheckBash:
    def test_blocks_windows_del_command(self):
        hints, blocks = pte.check_bash("del file.txt")
        assert blocks, "Expected a block for 'del' command"
        assert "Windows" in blocks[0] or "Detected" in blocks[0] or "BLOCKED" in blocks[0]

    def test_blocks_windows_copy_command(self):
        hints, blocks = pte.check_bash("copy src.txt dst.txt")
        assert blocks, "Expected a block for 'copy' command"

    def test_blocks_windows_dir_command(self):
        hints, blocks = pte.check_bash("dir /b")
        assert blocks, "Expected a block for 'dir' command"

    def test_allows_unix_rm_command(self):
        hints, blocks = pte.check_bash("rm -rf /tmp/test")
        # rm is not a Windows command - no Windows block should fire
        windows_blocks = [b for b in blocks if "Windows command" in b]
        assert not windows_blocks, "rm should not be blocked as a Windows command"

    def test_allows_unix_ls_command(self):
        hints, blocks = pte.check_bash("ls -la")
        windows_blocks = [b for b in blocks if "Windows command" in b]
        assert not windows_blocks, "ls should not be blocked as a Windows command"

    def test_allows_pytest_command(self):
        hints, blocks = pte.check_bash("pytest tests/ -v")
        windows_blocks = [b for b in blocks if "Windows command" in b]
        assert not windows_blocks


# ===========================================================================
# check_python_unicode
# ===========================================================================


class TestCheckPythonUnicode:
    def test_blocks_non_ascii_emoji(self):
        # Use a known Unicode danger char (checkmark emoji)
        content = "result = " + "\u2705"
        blocks = pte.check_python_unicode(content)
        assert blocks, "Expected a block for non-ASCII emoji in Python content"
        assert "BLOCKED" in blocks[0] or "unicode" in blocks[0].lower()

    def test_blocks_smart_quotes(self):
        content = "msg = " + "\u201c" + "hello" + "\u201d"
        blocks = pte.check_python_unicode(content)
        assert blocks, "Expected a block for smart quotes"

    def test_allows_pure_ascii_content(self):
        content = "def hello():\n    return 'world'\n"
        blocks = pte.check_python_unicode(content)
        assert not blocks, "Pure ASCII content should not be blocked"

    def test_allows_ascii_with_numbers(self):
        content = "x = 42\ny = 3.14\nz = 'ok'\n"
        blocks = pte.check_python_unicode(content)
        assert not blocks

    def test_reports_count_of_violations(self):
        # Two different danger chars
        content = "\u2705 and \u274c in file"
        blocks = pte.check_python_unicode(content)
        assert blocks
        assert "2" in blocks[0]


# ===========================================================================
# check_grep
# ===========================================================================


class TestCheckGrep:
    def test_warns_when_head_limit_missing_content_mode(self):
        tool_input = {"output_mode": "content", "pattern": "foo"}
        hints, blocks = pte.check_grep(tool_input)
        # content mode without head_limit should BLOCK
        assert blocks, "Expected block for content mode without head_limit"

    def test_warns_when_head_limit_missing_default_mode(self):
        tool_input = {"pattern": "foo"}
        hints, blocks = pte.check_grep(tool_input)
        # files_with_matches mode without head_limit -> hint, not block
        assert hints or not blocks, "Non-content mode without head_limit should be a hint or pass"

    def test_no_block_when_head_limit_set(self):
        tool_input = {"output_mode": "content", "pattern": "foo", "head_limit": 50}
        hints, blocks = pte.check_grep(tool_input)
        # head_limit=50 is within max (100), so no block from head_limit missing
        missing_limit_blocks = [b for b in blocks if "requires head_limit" in b]
        assert not missing_limit_blocks

    def test_blocks_head_limit_exceeding_max(self):
        tool_input = {"output_mode": "content", "pattern": "bar", "head_limit": 500}
        hints, blocks = pte.check_grep(tool_input)
        assert blocks, "Expected block when head_limit exceeds max (100)"
        assert "exceeds max" in blocks[0]


# ===========================================================================
# check_read
# ===========================================================================


class TestCheckRead:
    def test_warns_when_no_offset_or_limit_on_large_file(self, tmp_path):
        large_file = tmp_path / "big.py"
        # Write >50KB of content
        large_file.write_text("x = 1\n" * 10000, encoding="utf-8")
        tool_input = {"file_path": str(large_file)}
        hints, blocks = pte.check_read(tool_input)
        assert blocks, "Expected block for large file without offset/limit"
        assert "BLOCKED" in blocks[0] or "50KB" in blocks[0] or "limit" in blocks[0]

    def test_no_block_when_limit_is_set(self, tmp_path):
        large_file = tmp_path / "big.py"
        large_file.write_text("x = 1\n" * 10000, encoding="utf-8")
        tool_input = {"file_path": str(large_file), "limit": 200}
        hints, blocks = pte.check_read(tool_input)
        # limit is set - no "requires offset/limit" block
        size_blocks = [b for b in blocks if "50KB" in b]
        assert not size_blocks

    def test_no_block_for_small_file(self, tmp_path):
        small_file = tmp_path / "small.py"
        small_file.write_text("x = 1\n", encoding="utf-8")
        tool_input = {"file_path": str(small_file)}
        hints, blocks = pte.check_read(tool_input)
        assert not blocks, "Small file without limit should not be blocked"

    def test_blocks_limit_exceeding_max(self, tmp_path):
        tool_input = {"file_path": str(tmp_path / "any.py"), "limit": 9999}
        hints, blocks = pte.check_read(tool_input)
        assert blocks, "Expected block when limit exceeds max (500)"
        assert "exceeds max" in blocks[0]


# ===========================================================================
# check_checkpoint_pending
# ===========================================================================


class TestCheckCheckpointPending:
    def test_blocks_write_when_flag_exists(self, tmp_path):
        session_id = "SESSION-TEST-CKP-001"
        flag_file = _make_flag(tmp_path, ".checkpoint-pending", session_id)

        with (
            patch.object(pte, "get_current_session_id", return_value=session_id),
            patch.object(
                pte,
                "find_session_flag",
                return_value=(
                    flag_file,
                    {
                        "session_id": session_id,
                        "prompt_preview": "test task",
                        "created_at": datetime.now().isoformat(),
                    },
                ),
            ),
        ):
            hints, blocks = pte.check_checkpoint_pending("Write")
        assert blocks, "Write should be blocked when checkpoint flag exists"
        assert "BLOCKED" in blocks[0]

    def test_allows_bash_when_flag_exists(self, tmp_path):
        session_id = "SESSION-TEST-CKP-002"
        # Bash is in ALWAYS_ALLOWED, not in BLOCKED_WHILE_CHECKPOINT_PENDING
        with patch.object(pte, "get_current_session_id", return_value=session_id):
            hints, blocks = pte.check_checkpoint_pending("Bash")
        assert not blocks, "Bash should not be blocked even when checkpoint flag exists"

    def test_no_block_when_no_session(self):
        with patch.object(pte, "get_current_session_id", return_value=""):
            hints, blocks = pte.check_checkpoint_pending("Write")
        assert not blocks


# ===========================================================================
# check_task_breakdown_pending
# ===========================================================================


class TestCheckTaskBreakdownPending:
    def test_blocks_edit_when_flag_exists(self, tmp_path):
        session_id = "SESSION-TEST-TBD-001"
        flag_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "prompt_preview": "add feature",
        }
        flag_path = tmp_path / "flag.json"
        flag_path.write_text(json.dumps(flag_data), encoding="utf-8")

        with (
            patch.object(pte, "get_current_session_id", return_value=session_id),
            patch.object(pte, "find_session_flag", return_value=(flag_path, flag_data)),
        ):
            hints, blocks = pte.check_task_breakdown_pending("Edit")
        assert blocks, "Edit should be blocked when task-breakdown-pending flag exists"
        assert "BLOCKED" in blocks[0] or "Step 3.1" in blocks[0]

    def test_does_not_block_bash_when_flag_exists(self, tmp_path):
        session_id = "SESSION-TEST-TBD-002"
        with patch.object(pte, "get_current_session_id", return_value=session_id):
            # Bash is not in BLOCKED_WHILE_TASK_PENDING
            hints, blocks = pte.check_task_breakdown_pending("Bash")
        assert not blocks

    def test_no_block_when_no_session(self):
        with patch.object(pte, "get_current_session_id", return_value=""):
            hints, blocks = pte.check_task_breakdown_pending("Edit")
        assert not blocks


# ===========================================================================
# check_skill_selection_pending
# ===========================================================================


class TestCheckSkillSelectionPending:
    def test_blocks_write_when_flag_exists(self, tmp_path):
        session_id = "SESSION-TEST-SSP-001"
        flag_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "required_skill": "python-core",
            "required_type": "skill",
        }
        flag_path = tmp_path / "skill-flag.json"
        flag_path.write_text(json.dumps(flag_data), encoding="utf-8")

        with (
            patch.object(pte, "get_current_session_id", return_value=session_id),
            patch.object(pte, "find_session_flag", return_value=(flag_path, flag_data)),
        ):
            hints, blocks = pte.check_skill_selection_pending("Write")
        assert blocks, "Write should be blocked when skill-selection-pending flag exists"
        assert "BLOCKED" in blocks[0] or "Step 3.5" in blocks[0]

    def test_no_block_for_bash(self, tmp_path):
        session_id = "SESSION-TEST-SSP-002"
        with patch.object(pte, "get_current_session_id", return_value=session_id):
            hints, blocks = pte.check_skill_selection_pending("Bash")
        assert not blocks


# ===========================================================================
# check_level1_sync_complete
# ===========================================================================


class TestCheckLevel1SyncComplete:
    def test_blocks_write_when_level1_missing(self):
        session_id = "SESSION-TEST-L1-001"
        # Trace exists but does NOT contain LEVEL_1_CONTEXT or LEVEL_1_SESSION
        raw_trace = {"pipeline": [{"step": "LEVEL_2_STANDARDS"}]}

        with (
            patch.object(pte, "get_current_session_id", return_value=session_id),
            patch.object(pte, "_load_raw_flow_trace", return_value=raw_trace),
            patch("os.path.getmtime", return_value=time.time()),  # fresh trace
        ):
            hints, blocks = pte.check_level1_sync_complete("Write")
        assert blocks, "Write should be blocked when Level 1 steps are missing from trace"
        assert "Level 1" in blocks[0]

    def test_allows_write_when_level1_complete(self):
        session_id = "SESSION-TEST-L1-002"
        raw_trace = {
            "pipeline": [
                {"step": "LEVEL_1_CONTEXT"},
                {"step": "LEVEL_1_SESSION"},
            ]
        }

        with (
            patch.object(pte, "get_current_session_id", return_value=session_id),
            patch.object(pte, "_load_raw_flow_trace", return_value=raw_trace),
        ):
            hints, blocks = pte.check_level1_sync_complete("Write")
        assert not blocks

    def test_fail_open_when_no_trace(self):
        session_id = "SESSION-TEST-L1-003"
        with (
            patch.object(pte, "get_current_session_id", return_value=session_id),
            patch.object(pte, "_load_raw_flow_trace", return_value=None),
        ):
            hints, blocks = pte.check_level1_sync_complete("Write")
        # Fail-open: no trace = no block
        assert not blocks

    def test_read_tool_not_blocked(self):
        # Read is not in BLOCKED_TOOLS for level1
        hints, blocks = pte.check_level1_sync_complete("Read")
        assert not blocks


# ===========================================================================
# check_level2_standards_complete -- REMOVED
# ===========================================================================
# Level 2 standards enforcement was purged in v1.16.0 (commit 937c9ee).
# Level 2 policies are now data-only files under policies/02-standards-system/
# with no runtime enforcer. See GitHub issue #206 for the purge history; the
# TestCheckLevel2StandardsComplete class and its 2 tests were removed.


# ===========================================================================
# check_write_edit (calls check_python_unicode for .py files)
# ===========================================================================


class TestCheckWriteEdit:
    def test_calls_unicode_check_for_py_file(self):
        tool_input = {
            "file_path": "scripts/test_file.py",
            "content": "x = " + "\u2705",  # emoji char in Python file
        }
        hints, blocks = pte.check_write_edit("Write", tool_input)
        assert blocks, "Writing Unicode to .py file should be blocked"
        assert "unicode" in blocks[0].lower() or "BLOCKED" in blocks[0]

    def test_no_block_for_ascii_py_file(self):
        tool_input = {
            "file_path": "scripts/helper.py",
            "content": "def foo():\n    return 42\n",
        }
        hints, blocks = pte.check_write_edit("Write", tool_input)
        assert not blocks, "Pure ASCII .py content should not be blocked"

    def test_no_unicode_check_for_non_py_file(self):
        tool_input = {
            "file_path": "data/report.txt",
            "content": "hello " + "\u2705",
        }
        hints, blocks = pte.check_write_edit("Write", tool_input)
        # .txt file does not trigger unicode check
        unicode_blocks = [b for b in blocks if "unicode" in b.lower()]
        assert not unicode_blocks


# ===========================================================================
# Dynamic skill context detection
# ===========================================================================


class TestCheckDynamicSkillContext:
    """
    check_dynamic_skill_context is called from main() and returns hints
    based on file extension. We test the FILE_EXT_SKILL_MAP directly
    because the function reads from tool_input and _load_flow_trace_context.
    """

    def test_py_extension_in_skill_map(self):
        assert ".py" in pte.FILE_EXT_SKILL_MAP
        skill_name, skill_type, context = pte.FILE_EXT_SKILL_MAP[".py"]
        assert skill_name  # should map to a non-empty skill

    def test_java_extension_in_skill_map(self):
        assert ".java" in pte.FILE_EXT_SKILL_MAP

    def test_ts_extension_in_skill_map(self):
        assert ".ts" in pte.FILE_EXT_SKILL_MAP


# ===========================================================================
# _load_flow_trace_context: missing file returns empty dict
# ===========================================================================


class TestLoadFlowTraceContext:
    def test_returns_empty_dict_when_session_missing(self):
        with patch.object(pte, "get_current_session_id", return_value=""):
            # Reset cache so function re-runs
            pte._flow_trace_cache = None
            result = pte._load_flow_trace_context()
        assert isinstance(result, dict)

    def test_returns_empty_dict_when_trace_file_missing(self, tmp_path):
        session_id = "SESSION-MISSING-001"
        with (
            patch.object(pte, "get_current_session_id", return_value=session_id),
            patch("pathlib.Path.home", return_value=tmp_path),
        ):
            pte._flow_trace_cache = None
            result = pte._load_flow_trace_context()
        assert isinstance(result, dict)


# ===========================================================================
# find_session_flag: expired flags
# ===========================================================================


class TestFindSessionFlag:
    def test_expired_flag_returns_none(self, tmp_path):
        session_id = "SESSION-EXPIRE-001"
        # Create flag with created_at > 60 min ago
        old_time = datetime.now() - timedelta(minutes=70)
        flag_data = {
            "session_id": session_id,
            "created_at": old_time.isoformat(),
            "prompt_preview": "old task",
        }
        flag_dir = tmp_path / ".claude" / "memory" / "logs" / "sessions" / session_id / "flags"
        flag_dir.mkdir(parents=True, exist_ok=True)
        flag_file = flag_dir / "checkpoint-pending.json"
        flag_file.write_text(json.dumps(flag_data), encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            # Also patch FLAG_DIR to tmp_path / '.claude'
            with patch.object(pte, "FLAG_DIR", tmp_path / ".claude"):
                flag_path, data = pte.find_session_flag(".checkpoint-pending", session_id)

        assert flag_path is None, "Expired flag (>60 min) should return None"
        assert data is None

    def test_fresh_flag_returns_data(self, tmp_path):
        session_id = "SESSION-FRESH-001"
        flag_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "prompt_preview": "fresh task",
        }
        flag_dir = tmp_path / ".claude" / "memory" / "logs" / "sessions" / session_id / "flags"
        flag_dir.mkdir(parents=True, exist_ok=True)
        flag_file = flag_dir / "checkpoint-pending.json"
        flag_file.write_text(json.dumps(flag_data), encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.object(pte, "FLAG_DIR", tmp_path / ".claude"):
                flag_path, data = pte.find_session_flag(".checkpoint-pending", session_id)

        assert flag_path is not None, "Fresh flag should be found"
        assert data is not None
        assert data["session_id"] == session_id
