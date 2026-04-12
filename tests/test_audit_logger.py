"""Unit tests for audit_logger.py.

Tests:
  - test_audit_log_writes_json_line
  - test_audit_log_redacts_sensitive_metadata_keys
  - test_audit_log_skips_unknown_operation
  - test_audit_log_thread_safe (5 threads writing concurrently, all lines valid JSON)

ASCII-safe, UTF-8 encoded. Python 3.8+ compatible. No external services required.
"""

import json
import logging
import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------

try:
    from langgraph_engine.audit_logger import AUDITABLE_OPERATIONS, _redact_metadata, audit_log

    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="langgraph_engine.audit_logger not importable")

# ---------------------------------------------------------------------------
# Helper: capture what is actually written to the audit logger
# ---------------------------------------------------------------------------


class _CapturingHandler(logging.Handler):
    """Accumulates log records for assertion in tests."""

    def __init__(self):
        super(_CapturingHandler, self).__init__()
        self.lines = []
        self._lock = threading.Lock()

    def emit(self, record):
        with self._lock:
            self.lines.append(self.format(record))


def _attach_capturing_handler():
    """Attach a capturing handler to the audit logger and return it.

    The handler is set on the 'claude_workflow_engine.audit' logger which is
    the same logger used by audit_log().
    """
    import langgraph_engine.audit_logger as _al_mod

    # Reset the module-level singleton so a fresh logger is created
    _al_mod._audit_logger = None

    handler = _CapturingHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


# ---------------------------------------------------------------------------
# test_audit_log_writes_json_line
# ---------------------------------------------------------------------------


class TestAuditLogWritesJsonLine:
    """audit_log() must write a valid JSON line for known operations."""

    def test_pipeline_start_produces_json_line(self, tmp_path):
        """audit_log('pipeline_start', ...) must emit exactly one JSON line."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        captured = []

        def _fake_info(msg, *args, **kwargs):
            captured.append(msg)

        with patch.dict(os.environ, {"AUDIT_LOG_PATH": str(tmp_path / "audit.log")}):
            logger_mock = MagicMock()
            logger_mock.info.side_effect = _fake_info

            with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
                audit_log(
                    "pipeline_start",
                    actor="session-abc",
                    resource="pipeline",
                    outcome="success",
                    metadata={"task": "add auth"},
                )

        assert len(captured) == 1, "Expected exactly one log line, got {}".format(len(captured))
        parsed = json.loads(captured[0])
        assert parsed["operation"] == "pipeline_start"
        assert parsed["actor"] == "session-abc"
        assert parsed["resource"] == "pipeline"
        assert parsed["outcome"] == "success"

    def test_json_line_has_required_fields(self, tmp_path):
        """Each audit JSON line must contain timestamp, operation, actor, resource, outcome."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        captured = []

        def _fake_info(msg, *args, **kwargs):
            captured.append(msg)

        logger_mock = MagicMock()
        logger_mock.info.side_effect = _fake_info

        with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
            audit_log(
                "llm_call_made",
                actor="session-xyz",
                resource="anthropic-claude",
                outcome="success",
            )

        assert len(captured) >= 1
        parsed = json.loads(captured[0])
        for field in ("timestamp", "operation", "actor", "resource", "outcome", "metadata"):
            assert field in parsed, "Missing field '{}' in audit record".format(field)

    def test_json_line_is_valid_json(self, tmp_path):
        """The emitted line must be deserializable by json.loads without errors."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        captured = []

        logger_mock = MagicMock()
        logger_mock.info.side_effect = lambda msg, *a, **k: captured.append(msg)

        with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
            audit_log(
                "secrets_validated",
                actor="startup",
                resource="env",
                outcome="success",
                metadata={"keys_checked": 2},
            )

        assert len(captured) == 1
        # Must not raise
        parsed = json.loads(captured[0])
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# test_audit_log_redacts_sensitive_metadata_keys
# ---------------------------------------------------------------------------


class TestAuditLogRedactsSensitiveMetadataKeys:
    """Metadata values whose keys contain 'key', 'token', 'secret', or 'password'
    must be replaced with '[REDACTED]' in the written JSON line.
    """

    def test_api_key_in_metadata_is_redacted(self):
        """A metadata key named 'api_key' must produce '[REDACTED]' in output."""
        result = _redact_metadata({"api_key": "sk-real-secret-value", "task": "fix bug"})
        assert result["api_key"] == "[REDACTED]"
        assert result["task"] == "fix bug"

    def test_github_token_in_metadata_is_redacted(self):
        """A metadata key named 'github_token' must produce '[REDACTED]'."""
        result = _redact_metadata({"github_token": "ghp_realvalue", "repo": "my-repo"})
        assert result["github_token"] == "[REDACTED]"
        assert result["repo"] == "my-repo"

    def test_password_in_metadata_is_redacted(self):
        """A metadata key named 'password' must produce '[REDACTED]'."""
        result = _redact_metadata({"password": "s3cr3t!", "username": "alice"})
        assert result["password"] == "[REDACTED]"
        assert result["username"] == "alice"

    def test_secret_in_metadata_is_redacted(self):
        """A metadata key named 'db_secret' must produce '[REDACTED]'."""
        result = _redact_metadata({"db_secret": "hunter2", "host": "localhost"})
        assert result["db_secret"] == "[REDACTED]"
        assert result["host"] == "localhost"

    def test_non_sensitive_keys_pass_through(self):
        """Non-sensitive keys must retain their original values."""
        result = _redact_metadata(
            {
                "session_id": "ses-001",
                "step": "step0",
                "complexity": 7,
            }
        )
        assert result["session_id"] == "ses-001"
        assert result["step"] == "step0"
        assert result["complexity"] == 7

    def test_empty_metadata_returns_empty_dict(self):
        """_redact_metadata({}) must return an empty dict."""
        result = _redact_metadata({})
        assert result == {}

    def test_audit_log_redacts_in_written_line(self, tmp_path):
        """The JSON line emitted by audit_log must contain [REDACTED] for token keys."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        captured = []
        logger_mock = MagicMock()
        logger_mock.info.side_effect = lambda msg, *a, **k: captured.append(msg)

        with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
            audit_log(
                "github_issue_created",
                actor="session-001",
                resource="issue/42",
                outcome="success",
                metadata={"github_token": "ghp_real_value", "issue_title": "Fix login"},
            )

        assert len(captured) == 1
        parsed = json.loads(captured[0])
        assert parsed["metadata"]["github_token"] == "[REDACTED]"
        assert parsed["metadata"]["issue_title"] == "Fix login"


# ---------------------------------------------------------------------------
# test_audit_log_skips_unknown_operation
# ---------------------------------------------------------------------------


class TestAuditLogSkipsUnknownOperation:
    """audit_log() must silently drop (not write) events with unrecognised operations."""

    def test_unknown_operation_is_not_written(self, caplog):
        """An unknown operation must result in zero calls to the audit logger info()."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        captured = []
        logger_mock = MagicMock()
        logger_mock.info.side_effect = lambda msg, *a, **k: captured.append(msg)

        with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
            with caplog.at_level(logging.WARNING):
                audit_log(
                    "not_a_real_operation",
                    actor="session-001",
                    resource="something",
                    outcome="success",
                )

        # The audit logger info() must NOT have been called
        assert len(captured) == 0, "audit_log must not write for unknown operation, but got: {}".format(captured)

    def test_unknown_operation_emits_module_warning(self, caplog):
        """An unknown operation must emit a WARNING from the module logger."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        logger_mock = MagicMock()

        with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
            with caplog.at_level(logging.WARNING):
                audit_log(
                    "completely_unknown",
                    actor="bot",
                    resource="resource",
                    outcome="unknown",
                )

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) > 0, "Expected a WARNING for unknown operation"

    def test_all_auditable_operations_are_accepted(self, tmp_path):
        """All operations listed in AUDITABLE_OPERATIONS must be written without error."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        for operation in AUDITABLE_OPERATIONS:
            captured = []
            logger_mock = MagicMock()
            logger_mock.info.side_effect = lambda msg, *a, **k: captured.append(msg)

            _al_mod._audit_logger = None
            with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
                audit_log(operation, actor="test", resource="test", outcome="success")

            assert len(captured) == 1, "Operation '{}' must produce exactly one log line".format(operation)


# ---------------------------------------------------------------------------
# test_audit_log_thread_safe
# ---------------------------------------------------------------------------


class TestAuditLogThreadSafe:
    """Five threads writing concurrently must each produce a valid JSON line."""

    def test_concurrent_writes_all_produce_valid_json(self, tmp_path):
        """5 concurrent audit_log calls must produce 5 valid JSON lines."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        written_lines = []
        write_lock = threading.Lock()

        def _fake_info(msg, *args, **kwargs):
            with write_lock:
                written_lines.append(msg)

        logger_mock = MagicMock()
        logger_mock.info.side_effect = _fake_info

        errors = []

        def write_audit_line(index):
            try:
                with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
                    audit_log(
                        "pipeline_start",
                        actor="session-{}".format(index),
                        resource="pipeline",
                        outcome="success",
                        metadata={"thread_index": index},
                    )
            except Exception as exc:
                with write_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=write_audit_line, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, "Exceptions occurred during concurrent writes: {}".format(errors)
        assert len(written_lines) == 5, "Expected 5 lines from 5 threads, got {}".format(len(written_lines))

        # Every line must be valid JSON
        for i, line in enumerate(written_lines):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                pytest.fail("Line {} is not valid JSON: {} | Error: {}".format(i, line, exc))
            assert "operation" in parsed
            assert "actor" in parsed

    def test_concurrent_writes_produce_unique_actor_values(self, tmp_path):
        """Each thread's session ID must appear exactly once across all written lines."""
        import langgraph_engine.audit_logger as _al_mod

        _al_mod._audit_logger = None

        written_lines = []
        write_lock = threading.Lock()

        def _fake_info(msg, *args, **kwargs):
            with write_lock:
                written_lines.append(msg)

        logger_mock = MagicMock()
        logger_mock.info.side_effect = _fake_info

        def write_audit_line(index):
            with patch.object(_al_mod, "_get_audit_logger", return_value=logger_mock):
                audit_log(
                    "llm_call_made",
                    actor="session-{}".format(index),
                    resource="claude",
                    outcome="success",
                )

        threads = [threading.Thread(target=write_audit_line, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        actors = [json.loads(line)["actor"] for line in written_lines]
        assert len(set(actors)) == 5, "Expected 5 unique actor values, got: {}".format(actors)
