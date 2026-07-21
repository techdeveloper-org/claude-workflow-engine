"""Unit tests for scripts/tools/sync-library.py -- the ADR-2 verify+pull
wrapper that replaces the removed hook-downloader.py sync flow.

Covers:
- Sibling present, no --pull -> verify-only success, zero subprocess calls
- Sibling present, --pull -> runs `git pull --ff-only` in the sibling dir
  with the exact expected command/cwd
- Sibling absent -> exit 2 with the LibrarySetupError-style actionable message
- --pull against a non-fast-forwardable sibling -> exit 3
- CLI argument parsing wires --pull through to verify_and_pull()
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langgraph_engine.library.resolver import _reset_library_root_cache  # noqa: E402

_SYNC_LIBRARY_PATH = _PROJECT_ROOT / "scripts" / "tools" / "sync-library.py"
_spec = importlib.util.spec_from_file_location("sync_library", _SYNC_LIBRARY_PATH)
sync_library = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_library)


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    """Every test starts with a clean locate_library_root() memoization cache
    and no CLAUDE_GLOBAL_LIB_PATH override leaking from the real environment.
    """
    monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
    _reset_library_root_cache()
    yield
    _reset_library_root_cache()


@pytest.fixture
def engine_and_sibling(tmp_path):
    """A fake engine checkout with a sibling claude-global-library next to it."""
    engine_root = tmp_path / "claude-workflow-engine"
    sibling_root = tmp_path / "claude-global-library"
    engine_root.mkdir()
    sibling_root.mkdir()
    return engine_root, sibling_root


class FakeRunner:
    """Records every subprocess.run-shaped call and returns a canned result."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: List[Tuple[list, dict]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr=self.stderr)


class TestVerifyOnly:
    def test_sibling_present_no_pull_flag_succeeds_with_zero_subprocess_calls(self, engine_and_sibling):
        engine_root, _sibling_root = engine_and_sibling
        runner = FakeRunner()

        exit_code = sync_library.verify_and_pull(do_pull=False, engine_root=engine_root, runner=runner)

        assert exit_code == sync_library.EXIT_OK
        assert runner.calls == []


class TestPullSuccess:
    def test_sibling_present_with_pull_runs_git_pull_ff_only_in_sibling_dir(self, engine_and_sibling):
        engine_root, sibling_root = engine_and_sibling
        runner = FakeRunner(returncode=0, stdout="Already up to date.")

        exit_code = sync_library.verify_and_pull(do_pull=True, engine_root=engine_root, runner=runner)

        assert exit_code == sync_library.EXIT_OK
        assert len(runner.calls) == 1
        cmd, kwargs = runner.calls[0]
        assert cmd == ["git", "pull", "--ff-only"]
        assert kwargs["cwd"] == str(sibling_root)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False


class TestSiblingAbsent:
    def test_sibling_absent_exits_2_with_actionable_message(self, tmp_path, capsys):
        engine_root = tmp_path / "claude-workflow-engine"
        engine_root.mkdir()
        runner = FakeRunner()

        exit_code = sync_library.verify_and_pull(do_pull=False, engine_root=engine_root, runner=runner)

        assert exit_code == sync_library.EXIT_SIBLING_NOT_FOUND
        assert runner.calls == []
        captured = capsys.readouterr()
        expected_path = str(tmp_path / "claude-global-library")
        assert "claude-global-library not found" in captured.err
        assert expected_path in captured.err
        assert sync_library.ENV_LIBRARY_PATH in captured.err

    def test_sibling_absent_with_pull_flag_still_exits_2_without_attempting_pull(self, tmp_path):
        engine_root = tmp_path / "claude-workflow-engine"
        engine_root.mkdir()
        runner = FakeRunner()

        exit_code = sync_library.verify_and_pull(do_pull=True, engine_root=engine_root, runner=runner)

        assert exit_code == sync_library.EXIT_SIBLING_NOT_FOUND
        assert runner.calls == []


class TestPullFailure:
    def test_non_fast_forward_pull_exits_3(self, engine_and_sibling, capsys):
        engine_root, sibling_root = engine_and_sibling
        runner = FakeRunner(returncode=1, stderr="fatal: Not possible to fast-forward, aborting.")

        exit_code = sync_library.verify_and_pull(do_pull=True, engine_root=engine_root, runner=runner)

        assert exit_code == sync_library.EXIT_PULL_FAILED
        assert len(runner.calls) == 1
        captured = capsys.readouterr()
        assert "git pull --ff-only failed" in captured.err
        assert str(sibling_root) in captured.err
        assert "Not possible to fast-forward" in captured.err

    def test_generic_git_failure_also_exits_3(self, engine_and_sibling):
        engine_root, _sibling_root = engine_and_sibling
        runner = FakeRunner(returncode=128, stderr="fatal: not a git repository")

        exit_code = sync_library.verify_and_pull(do_pull=True, engine_root=engine_root, runner=runner)

        assert exit_code == sync_library.EXIT_PULL_FAILED


class TestCliArgumentParsing:
    def test_no_args_defaults_to_verify_only(self, monkeypatch):
        captured_kwargs = {}

        def fake_verify_and_pull(do_pull, **kwargs):
            captured_kwargs["do_pull"] = do_pull
            return sync_library.EXIT_OK

        monkeypatch.setattr(sync_library, "verify_and_pull", fake_verify_and_pull)

        exit_code = sync_library.main([])

        assert exit_code == sync_library.EXIT_OK
        assert captured_kwargs["do_pull"] is False

    def test_pull_flag_is_forwarded(self, monkeypatch):
        captured_kwargs = {}

        def fake_verify_and_pull(do_pull, **kwargs):
            captured_kwargs["do_pull"] = do_pull
            return sync_library.EXIT_OK

        monkeypatch.setattr(sync_library, "verify_and_pull", fake_verify_and_pull)

        exit_code = sync_library.main(["--pull"])

        assert exit_code == sync_library.EXIT_OK
        assert captured_kwargs["do_pull"] is True
