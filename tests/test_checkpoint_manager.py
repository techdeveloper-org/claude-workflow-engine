"""
Tests for checkpoint_manager.py - State persistence between steps.

ASCII-safe, UTF-8 encoded - Windows cp1252 compatible.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Pre-import stubs
# ---------------------------------------------------------------------------


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


_stub("loguru", logger=MagicMock())

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
for _p in [_REPO_ROOT, _SCRIPTS]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

_LE_ROOT = Path(_REPO_ROOT) / "langgraph_engine"

# Stub langgraph_engine as a bare namespace (skip __init__.py)
_le = types.ModuleType("langgraph_engine")
_le.__path__ = [str(_LE_ROOT)]
_le.__package__ = "langgraph_engine"
sys.modules["langgraph_engine"] = _le


def _load_module(name, rel_path):
    full_path = _LE_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(full_path))
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "langgraph_engine"
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_cp_mod = _load_module("langgraph_engine.checkpoint_manager", "checkpoint_manager.py")
CheckpointManager = _cp_mod.CheckpointManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path, session_id="test-session"):
    return CheckpointManager(session_id=session_id, base_dir=str(tmp_path))


def _write_checkpoint(cp_dir, step, state, success=True, error_msg=None, session_id="test-session"):
    from datetime import datetime

    payload = {
        "checkpoint_id": f"{session_id}:step-{step:02d}",
        "step": step,
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "success_status": success,
        "error_message": error_msg,
        "state": state,
    }
    path = cp_dir / f"step-{step:02d}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckpointManagerInit:
    """test_init_creates_checkpoint_dir - Creates checkpoints/ subdirectory."""

    def test_init_creates_checkpoint_dir(self, tmp_path):
        mgr = _make_manager(tmp_path, "session-xyz")
        assert mgr.checkpoint_dir.exists()
        assert mgr.checkpoint_dir.is_dir()

    def test_init_sets_session_id(self, tmp_path):
        mgr = _make_manager(tmp_path, "my-session-123")
        assert mgr.session_id == "my-session-123"


class TestSaveCheckpoint:
    """Tests for CheckpointManager.save_checkpoint."""

    def test_save_checkpoint_creates_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.save_checkpoint(step=3, state={"user_message": "build"})
        assert result is True
        assert (mgr.checkpoint_dir / "step-03.json").exists()

    def test_save_checkpoint_creates_latest(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save_checkpoint(step=2, state={"x": 42})
        assert (mgr.checkpoint_dir / "latest.json").exists()

    def test_save_checkpoint_metadata(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-meta")
        mgr.save_checkpoint(step=5, state={"k": "v"}, success_status=True)
        raw = json.loads((mgr.checkpoint_dir / "step-05.json").read_text(encoding="utf-8"))
        assert raw["checkpoint_id"] == "sess-meta:step-05"
        assert "timestamp" in raw
        assert raw["success_status"] is True

    def test_save_checkpoint_failed_step(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save_checkpoint(step=7, state={}, success_status=False, error_message="LLM timeout")
        raw = json.loads((mgr.checkpoint_dir / "step-07.json").read_text(encoding="utf-8"))
        assert raw["success_status"] is False
        assert raw["error_message"] == "LLM timeout"


class TestLoadCheckpoint:
    """Tests for CheckpointManager.load_checkpoint."""

    def test_load_checkpoint(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-load")
        _write_checkpoint(mgr.checkpoint_dir, step=4, state={"user_message": "hello"}, session_id="sess-load")
        state = mgr.load_checkpoint(4)
        assert state is not None
        assert state["user_message"] == "hello"

    def test_load_checkpoint_missing(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.load_checkpoint(99) is None

    def test_load_checkpoint_corrupt(self, tmp_path):
        mgr = _make_manager(tmp_path)
        (mgr.checkpoint_dir / "step-02.json").write_text("{not valid", encoding="utf-8")
        assert mgr.load_checkpoint(2) is None

    def test_load_checkpoint_metadata_only(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-meta2")
        _write_checkpoint(mgr.checkpoint_dir, step=6, state={"data": "abc"}, session_id="sess-meta2")
        meta = mgr.load_checkpoint_metadata(6)
        assert meta is not None
        assert meta["step"] == 6
        assert meta["success_status"] is True
        # load_checkpoint_metadata must NOT include the full state blob
        assert "state" not in meta

    def test_load_checkpoint_metadata_missing(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.load_checkpoint_metadata(50) is None


class TestLoadCheckpointById:
    """test_load_checkpoint_by_id - Parses 'session:step-05' format."""

    def test_load_by_id_standard_format(self, tmp_path):
        mgr = _make_manager(tmp_path, "my-sess")
        _write_checkpoint(mgr.checkpoint_dir, step=5, state={"key": "value"}, session_id="my-sess")
        state = mgr.load_checkpoint_by_id("my-sess:step-05")
        assert state is not None
        assert state["key"] == "value"

    def test_load_by_id_step_only(self, tmp_path):
        mgr = _make_manager(tmp_path, "my-sess")
        _write_checkpoint(mgr.checkpoint_dir, step=3, state={"data": 99}, session_id="my-sess")
        assert mgr.load_checkpoint_by_id("step-03") is not None

    def test_load_by_id_invalid(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.load_checkpoint_by_id("not-a-valid-id-xyz") is None


class TestGetLastCheckpoint:
    """test_get_last_checkpoint - Finds highest step number."""

    def test_get_last_checkpoint_empty(self, tmp_path):
        mgr = _make_manager(tmp_path)
        step, state = mgr.get_last_checkpoint()
        assert step is None
        assert state is None

    def test_get_last_checkpoint_returns_highest_step(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-last")
        for s in [1, 3, 2]:
            _write_checkpoint(mgr.checkpoint_dir, step=s, state={"s": s}, session_id="sess-last")
        step, state = mgr.get_last_checkpoint()
        assert step == 3
        assert state["s"] == 3


class TestGetLastSuccessfulCheckpoint:
    """test_get_last_successful_checkpoint - Filters for success_status=True."""

    def test_skips_failed_steps(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-succ")
        _write_checkpoint(mgr.checkpoint_dir, step=2, state={"s": 2}, success=True, session_id="sess-succ")
        _write_checkpoint(mgr.checkpoint_dir, step=3, state={"s": 3}, success=False, session_id="sess-succ")
        step, state = mgr.get_last_successful_checkpoint()
        assert step == 2
        assert state["s"] == 2

    def test_returns_none_when_all_failed(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-fail")
        _write_checkpoint(mgr.checkpoint_dir, step=1, state={}, success=False, session_id="sess-fail")
        step, state = mgr.get_last_successful_checkpoint()
        assert step is None
        assert state is None


class TestListCheckpoints:
    """test_list_checkpoints - Returns metadata list."""

    def test_list_checkpoints_empty(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.list_checkpoints() == []

    def test_list_checkpoints_returns_metadata(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-list")
        _write_checkpoint(mgr.checkpoint_dir, step=1, state={"a": 1}, session_id="sess-list")
        _write_checkpoint(mgr.checkpoint_dir, step=2, state={"b": 2}, session_id="sess-list")
        items = mgr.list_checkpoints()
        assert len(items) == 2
        assert {i["step"] for i in items} == {1, 2}
        for item in items:
            assert "checkpoint_id" in item
            assert "timestamp" in item
            assert "success_status" in item


class TestDeleteCheckpoint:
    """test_delete_checkpoint - Removes step file."""

    def test_delete_removes_file(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-del")
        _write_checkpoint(mgr.checkpoint_dir, step=4, state={}, session_id="sess-del")
        assert (mgr.checkpoint_dir / "step-04.json").exists()
        assert mgr.delete_checkpoint(4) is True
        assert not (mgr.checkpoint_dir / "step-04.json").exists()

    def test_delete_missing_returns_true(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.delete_checkpoint(99) is True


class TestClearAll:
    """test_clear_all - Removes all checkpoint files."""

    def test_clear_all_removes_all_files(self, tmp_path):
        mgr = _make_manager(tmp_path, "sess-clear")
        for step in [1, 2, 3]:
            _write_checkpoint(mgr.checkpoint_dir, step=step, state={}, session_id="sess-clear")
        count = mgr.clear_all()
        assert count == 3
        assert list(mgr.checkpoint_dir.glob("*.json")) == []


class TestAtomicWriteIntegrity:
    """test_atomic_write_integrity - File content matches after write."""

    def test_content_matches_after_write(self, tmp_path):
        mgr = _make_manager(tmp_path)
        state = {"session_id": "atomic-test", "counter": 42, "flag": True}
        mgr.save_checkpoint(step=1, state=state)
        loaded = mgr.load_checkpoint(1)
        assert loaded is not None
        assert loaded["counter"] == 42
        assert loaded["flag"] is True
