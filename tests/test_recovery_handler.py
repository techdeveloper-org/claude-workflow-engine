"""
Tests for recovery_handler.py - Graceful interrupt handling and execution resume.

ASCII-safe, UTF-8 encoded - Windows cp1252 compatible.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Pre-import stubs: heavy transitive dependencies stubbed before any load
# ---------------------------------------------------------------------------


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


_stub("loguru", logger=MagicMock())

# scripts/ on sys.path so relative imports inside the package can resolve
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
for _p in [_REPO_ROOT, _SCRIPTS]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Stub langgraph_engine as a bare module so the package __init__ is skipped.
# We load individual sub-modules directly via spec_from_file_location below.
_LE_ROOT = Path(_REPO_ROOT) / "langgraph_engine"

_le = types.ModuleType("langgraph_engine")
_le.__path__ = [str(_LE_ROOT)]
_le.__package__ = "langgraph_engine"
sys.modules["langgraph_engine"] = _le


def _load_module(name, rel_path):
    """Load a module from an absolute path and register it in sys.modules."""
    full_path = _LE_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(full_path))
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "langgraph_engine"
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub checkpoint_manager (provides CheckpointManager)
_mock_cp_mod = _stub(
    "langgraph_engine.checkpoint_manager", CheckpointManager=MagicMock(), create_checkpoint_manager=MagicMock()
)

# Stub error_logger (provides ErrorLogger)
_mock_el_mod = _stub("langgraph_engine.error_logger", ErrorLogger=MagicMock(), create_logger=MagicMock())

# Also stub the plain-name fallback used inside recovery_handler
sys.modules.setdefault("checkpoint_manager", _mock_cp_mod)
sys.modules.setdefault("error_logger", _mock_el_mod)

# Now load recovery_handler directly
_rh_mod = _load_module("langgraph_engine.recovery_handler", "recovery_handler.py")

# Bind to module-level names for tests
RecoveryHandler = _rh_mod.RecoveryHandler
resume_from_checkpoint = _rh_mod.resume_from_checkpoint
_backoff_delay = _rh_mod._backoff_delay
_is_transient_error = _rh_mod._is_transient_error
_BACKOFF_DELAYS = _rh_mod._BACKOFF_DELAYS
_MAX_STEP_RETRIES = _rh_mod._MAX_STEP_RETRIES


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_handler(tmp_path, session_id="test-session"):
    return RecoveryHandler(session_id=session_id, base_log_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecoveryHandlerInit:
    """test_recovery_handler_init - Creates with session_id, initializes components."""

    def test_recovery_handler_init(self, tmp_path):
        handler = _make_handler(tmp_path, "session-abc")
        assert handler.session_id == "session-abc"
        assert handler.checkpoint_manager is not None
        assert handler.error_logger is not None


class TestInstallSignalHandlers:
    """test_install_signal_handlers - Installs SIGINT/SIGTERM handlers."""

    def test_install_signal_handlers_main_thread(self, tmp_path):
        import signal as _signal

        handler = _make_handler(tmp_path)
        with patch.object(_rh_mod, "signal") as mock_signal:
            mock_signal.SIGINT = _signal.SIGINT
            mock_signal.SIGTERM = _signal.SIGTERM
            with patch("threading.current_thread") as mock_ct, patch("threading.main_thread") as mock_mt:
                same = object()
                mock_ct.return_value = same
                mock_mt.return_value = same
                handler.install_signal_handlers()
            assert mock_signal.signal.called

    def test_install_signal_handlers_non_main_thread_skips(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch("threading.current_thread", return_value=object()), patch(
            "threading.main_thread", return_value=object()
        ), patch.object(_rh_mod, "signal") as mock_signal:
            handler.install_signal_handlers()
            mock_signal.signal.assert_not_called()


class TestUpdateState:
    """test_update_state - Updates module-level globals."""

    def test_update_state(self, tmp_path):
        handler = _make_handler(tmp_path)
        state = {"session_id": "s1", "user_message": "do something"}
        with patch.object(_rh_mod, "_register_globals") as mock_reg:
            handler.update_state(step=3, state=state)
            mock_reg.assert_called_once_with(3, state, handler.checkpoint_manager, handler.error_logger)


class TestSaveStepCheckpoint:
    """test_save_step_checkpoint - Delegates to CheckpointManager."""

    def test_save_step_checkpoint_success(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.checkpoint_manager.save_checkpoint.return_value = True
        result = handler.save_step_checkpoint(step=5, state={"x": 1}, success_status=True)
        assert result is True
        handler.checkpoint_manager.save_checkpoint.assert_called_once_with(
            5, {"x": 1}, success_status=True, error_message=None
        )

    def test_save_step_checkpoint_failure_logs_error(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.checkpoint_manager.save_checkpoint.return_value = False
        result = handler.save_step_checkpoint(step=5, state={}, success_status=False)
        assert result is False
        handler.error_logger.log_error.assert_called()


class TestIsTransientError:
    """Tests for _is_transient_error heuristic."""

    def test_is_transient_error_timeout(self):
        assert _is_transient_error(RuntimeError("Connection timeout after 30s")) is True

    def test_is_transient_error_connection(self):
        assert _is_transient_error(OSError("connection refused by server")) is True

    def test_is_transient_error_rate_limit(self):
        assert _is_transient_error(ValueError("rate limit exceeded")) is True

    def test_is_transient_error_permanent(self):
        assert _is_transient_error(SyntaxError("invalid syntax")) is False

    def test_is_transient_error_file_not_found(self):
        assert _is_transient_error(FileNotFoundError("config.yaml missing")) is False


class TestBackoffDelay:
    """test_backoff_delay_exponential - 1s, 2s, 4s, 8s (max)."""

    def test_backoff_delay_attempt_0(self):
        assert _backoff_delay(0) == 1.0

    def test_backoff_delay_attempt_1(self):
        assert _backoff_delay(1) == 2.0

    def test_backoff_delay_attempt_2(self):
        assert _backoff_delay(2) == 4.0

    def test_backoff_delay_attempt_3(self):
        assert _backoff_delay(3) == 8.0

    def test_backoff_delay_capped_at_max(self):
        assert _backoff_delay(99) == _BACKOFF_DELAYS[-1]


class TestResumeSession:
    """Tests for RecoveryHandler.resume_session."""

    def test_resume_session_no_checkpoint(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.checkpoint_manager.get_last_checkpoint.return_value = (None, None)
        handler.step_executor = MagicMock()
        result = handler.resume_session()
        assert result is False

    def test_resume_session_from_checkpoint(self, tmp_path):
        handler = _make_handler(tmp_path)
        saved_state = {"session_id": "test-session"}
        handler.checkpoint_manager.get_last_checkpoint.return_value = (13, saved_state)
        handler.checkpoint_manager.save_checkpoint.return_value = True

        def _executor(step, state):
            return {}

        handler.step_executor = _executor
        with patch.object(_rh_mod, "time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.time = MagicMock(return_value=0.0)
            result = handler.resume_session()

        assert result is True

    def test_resume_session_no_executor(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.step_executor = None
        result = handler.resume_session()
        assert result is False


class TestResumeFromCheckpointPublicApi:
    """test_resume_from_checkpoint_public_api - Public function creates handler and resumes."""

    def test_resume_from_checkpoint_creates_handler_and_resumes(self, tmp_path):
        with patch.object(_rh_mod, "RecoveryHandler") as MockHandler:
            mock_instance = MagicMock()
            mock_instance.resume_session.return_value = True
            MockHandler.return_value = mock_instance

            result = resume_from_checkpoint(session_id="my-session")

        MockHandler.assert_called_once()
        mock_instance.resume_session.assert_called_once()
        assert result is True

    def test_resume_from_checkpoint_passes_checkpoint_id(self, tmp_path):
        with patch.object(_rh_mod, "RecoveryHandler") as MockHandler:
            mock_instance = MagicMock()
            mock_instance.resume_session.return_value = False
            MockHandler.return_value = mock_instance

            result = resume_from_checkpoint(
                session_id="my-session",
                checkpoint_id="my-session:step-05",
            )

        mock_instance.resume_session.assert_called_once_with(checkpoint_id="my-session:step-05")
        assert result is False
