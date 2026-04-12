"""Unit tests for secrets_manager.py.

Tests validate_secrets(), SecretsMissingError, and rotate_key_hint().

ASCII-safe, UTF-8 encoded. Python 3.8+ compatible. No external services required.
"""

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

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
    from langgraph_engine.secrets_manager import (
        REQUIRED_SECRETS,
        SecretsMissingError,
        rotate_key_hint,
        validate_secrets,
    )

    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="langgraph_engine.secrets_manager not importable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_required_secrets():
    """Remove all REQUIRED_SECRETS from os.environ; return saved values."""
    saved = {}
    for key in REQUIRED_SECRETS:
        saved[key] = os.environ.pop(key, None)
    return saved


def _restore_secrets(saved):
    """Restore previously saved env var values."""
    for key, value in saved.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# test_validate_secrets_raises_when_key_missing
# ---------------------------------------------------------------------------


class TestValidateSecretsRaisesWhenKeyMissing:
    """validate_secrets() must raise SecretsMissingError if any required key is absent."""

    def test_raises_when_anthropic_key_absent(self):
        """Removing ANTHROPIC_API_KEY must trigger SecretsMissingError."""
        saved = _clear_required_secrets()
        try:
            with pytest.raises(SecretsMissingError) as exc_info:
                validate_secrets()
            assert "ANTHROPIC_API_KEY" in exc_info.value.missing_keys
        finally:
            _restore_secrets(saved)

    def test_missing_keys_list_is_non_empty(self):
        """The missing_keys attribute must contain at least one entry."""
        saved = _clear_required_secrets()
        try:
            with pytest.raises(SecretsMissingError) as exc_info:
                validate_secrets()
            assert len(exc_info.value.missing_keys) > 0
        finally:
            _restore_secrets(saved)

    def test_exception_message_contains_missing_key_name(self):
        """The exception string must include the missing key name."""
        saved = _clear_required_secrets()
        try:
            with pytest.raises(SecretsMissingError) as exc_info:
                validate_secrets()
            error_text = str(exc_info.value)
            # At least one required key name must appear in the message
            found = any(k in error_text for k in REQUIRED_SECRETS)
            assert found, "Exception message did not mention any required key: {}".format(error_text)
        finally:
            _restore_secrets(saved)

    def test_empty_string_value_is_treated_as_missing(self):
        """A key set to an empty string must also trigger SecretsMissingError."""
        saved = _clear_required_secrets()
        try:
            os.environ["ANTHROPIC_API_KEY"] = ""
            os.environ["GITHUB_TOKEN"] = ""
            with pytest.raises(SecretsMissingError):
                validate_secrets()
        finally:
            _restore_secrets(saved)


# ---------------------------------------------------------------------------
# test_validate_secrets_passes_when_all_set
# ---------------------------------------------------------------------------


class TestValidateSecretsPassesWhenAllSet:
    """validate_secrets() must not raise when all required secrets are present."""

    def test_no_exception_when_all_required_set(self):
        """All required keys set to non-empty values must pass validation."""
        saved = {}
        for key in REQUIRED_SECRETS:
            saved[key] = os.environ.get(key)
        try:
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-1234567890"
            os.environ["GITHUB_TOKEN"] = "ghp_test-github-token-xyz"
            validate_secrets()  # must not raise
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

    def test_return_value_is_none(self):
        """validate_secrets() must return None (no meaningful return value)."""
        saved = {}
        for key in REQUIRED_SECRETS:
            saved[key] = os.environ.get(key)
        try:
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-1234567890"
            os.environ["GITHUB_TOKEN"] = "ghp_test-github-token-xyz"
            result = validate_secrets()
            assert result is None
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# test_rotate_key_hint_warns_within_7_days
# ---------------------------------------------------------------------------


class TestRotateKeyHintWarnsWithin7Days:
    """rotate_key_hint() must emit a WARNING when expiry is within 7 days."""

    def test_warning_emitted_when_expiry_in_3_days(self, caplog):
        """A key expiring 3 days from now must trigger a WARNING log."""
        expiry = (date.today() + timedelta(days=3)).isoformat()
        saved = os.environ.get("ANTHROPIC_KEY_EXPIRY")
        try:
            os.environ["ANTHROPIC_KEY_EXPIRY"] = expiry
            with caplog.at_level(logging.WARNING, logger="langgraph_engine.secrets_manager"):
                rotate_key_hint()
            warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
            assert len(warning_records) > 0, "Expected WARNING log for key expiring in 3 days"
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_KEY_EXPIRY"] = saved
            else:
                os.environ.pop("ANTHROPIC_KEY_EXPIRY", None)

    def test_warning_emitted_when_expiry_is_today(self, caplog):
        """A key expiring today (0 days remaining) must trigger a WARNING log."""
        expiry = date.today().isoformat()
        saved = os.environ.get("ANTHROPIC_KEY_EXPIRY")
        try:
            os.environ["ANTHROPIC_KEY_EXPIRY"] = expiry
            with caplog.at_level(logging.WARNING, logger="langgraph_engine.secrets_manager"):
                rotate_key_hint()
            warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
            assert len(warning_records) > 0
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_KEY_EXPIRY"] = saved
            else:
                os.environ.pop("ANTHROPIC_KEY_EXPIRY", None)

    def test_warning_emitted_when_expiry_in_exactly_7_days(self, caplog):
        """A key expiring in exactly 7 days must trigger a WARNING log."""
        expiry = (date.today() + timedelta(days=7)).isoformat()
        saved = os.environ.get("ANTHROPIC_KEY_EXPIRY")
        try:
            os.environ["ANTHROPIC_KEY_EXPIRY"] = expiry
            with caplog.at_level(logging.WARNING, logger="langgraph_engine.secrets_manager"):
                rotate_key_hint()
            warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
            assert len(warning_records) > 0
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_KEY_EXPIRY"] = saved
            else:
                os.environ.pop("ANTHROPIC_KEY_EXPIRY", None)


# ---------------------------------------------------------------------------
# test_rotate_key_hint_silent_when_far_future
# ---------------------------------------------------------------------------


class TestRotateKeyHintSilentWhenFarFuture:
    """rotate_key_hint() must NOT emit a WARNING when expiry is far in the future."""

    def test_no_warning_when_expiry_in_30_days(self, caplog):
        """A key expiring 30 days from now must not trigger a WARNING log."""
        expiry = (date.today() + timedelta(days=30)).isoformat()
        saved = os.environ.get("ANTHROPIC_KEY_EXPIRY")
        try:
            os.environ["ANTHROPIC_KEY_EXPIRY"] = expiry
            with caplog.at_level(logging.WARNING, logger="langgraph_engine.secrets_manager"):
                rotate_key_hint()
            warning_records = [
                r
                for r in caplog.records
                if r.levelno >= logging.WARNING and "langgraph_engine.secrets_manager" in (r.name or "")
            ]
            assert len(warning_records) == 0, "Unexpected WARNING for key expiring in 30 days: {}".format(
                [r.message for r in warning_records]
            )
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_KEY_EXPIRY"] = saved
            else:
                os.environ.pop("ANTHROPIC_KEY_EXPIRY", None)

    def test_no_warning_when_expiry_env_not_set(self, caplog):
        """When ANTHROPIC_KEY_EXPIRY is not set, no WARNING must be emitted."""
        saved = os.environ.pop("ANTHROPIC_KEY_EXPIRY", None)
        try:
            with caplog.at_level(logging.WARNING, logger="langgraph_engine.secrets_manager"):
                rotate_key_hint()
            warning_records = [
                r for r in caplog.records if r.levelno >= logging.WARNING and "rotation" in r.getMessage().lower()
            ]
            assert len(warning_records) == 0
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_KEY_EXPIRY"] = saved

    def test_invalid_date_format_does_not_raise(self):
        """An invalid date string in ANTHROPIC_KEY_EXPIRY must not cause an exception."""
        saved = os.environ.get("ANTHROPIC_KEY_EXPIRY")
        try:
            os.environ["ANTHROPIC_KEY_EXPIRY"] = "not-a-date"
            rotate_key_hint()  # must not raise
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_KEY_EXPIRY"] = saved
            else:
                os.environ.pop("ANTHROPIC_KEY_EXPIRY", None)
