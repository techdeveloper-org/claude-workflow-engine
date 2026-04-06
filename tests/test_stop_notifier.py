#!/usr/bin/env python3
"""
Test Suite: test_stop_notifier.py
Target: stop-notifier.py v4.3.0 (static messages only, Ollama removed)
Author: qa-testing-agent
Date: 2026-04-06

Coverage:
  - Unit Tests: read_flag, delete_flag, increment_retry,
                get_session_start_default, get_work_done_default
  - Integration Tests: full flag-to-speak flow, retry flow,
                       max retries, work-done priority
  - Logging Tests: error messages, retry counters, flag lifecycle
  - Speak Tests: Popen fire-and-forget launcher

Windows-Safe: ASCII only (no Unicode/emojis)
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Bootstrap: load stop-notifier.py as a module and register in sys.modules
# so that patch('stop_notifier.X') works correctly.
# ---------------------------------------------------------------------------
_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "stop-notifier.py"

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("stop_notifier", str(_SCRIPT_PATH))
_mod = importlib.util.module_from_spec(_spec)
# Register BEFORE exec so internal imports land on the right object
sys.modules["stop_notifier"] = _mod
_mod.__name__ = "stop_notifier"
_spec.loader.exec_module(_mod)

# Convenience aliases
read_flag = _mod.read_flag
delete_flag = _mod.delete_flag
increment_retry = _mod.increment_retry
get_session_start_default = _mod.get_session_start_default
get_task_complete_default = _mod.get_task_complete_default
get_work_done_default = _mod.get_work_done_default
speak = _mod.speak
log_s = _mod.log_s
STOP_LOG = _mod.STOP_LOG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tmp_flag(tmp_dir, filename, content="hello context"):
    """Create a plain-text flag file and return its Path."""
    p = Path(tmp_dir) / filename
    p.write_text(content, encoding="utf-8")
    return p


def _tmp_json_flag(tmp_dir, filename, data):
    """Create a JSON flag file and return its Path."""
    p = Path(tmp_dir) / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ===========================================================================
# SECTION 1: UNIT TESTS
# ===========================================================================


class TestReadFlag(unittest.TestCase):
    """Unit tests for read_flag()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reads_existing_file_content(self):
        p = _tmp_flag(self.tmp, ".session-start-voice", "Good morning context")
        result = read_flag(p)
        self.assertEqual(result, "Good morning context")

    def test_returns_empty_string_when_file_missing(self):
        p = Path(self.tmp) / ".nonexistent-flag"
        result = read_flag(p)
        self.assertEqual(result, "")

    def test_strips_whitespace(self):
        p = _tmp_flag(self.tmp, ".flag", "  context with spaces  \n")
        result = read_flag(p)
        self.assertEqual(result, "context with spaces")

    def test_does_NOT_delete_flag_after_read(self):
        """read_flag must be non-destructive - file must still exist after call."""
        p = _tmp_flag(self.tmp, ".session-start-voice", "context")
        read_flag(p)
        self.assertTrue(p.exists(), "read_flag() must not delete the flag file")

    def test_empty_file_returns_empty_string(self):
        p = Path(self.tmp) / ".flag"
        p.write_text("", encoding="utf-8")
        result = read_flag(p)
        self.assertEqual(result, "")

    def test_plain_ascii_content_preserved(self):
        p = _tmp_flag(self.tmp, ".flag", "Session with plain details")
        result = read_flag(p)
        self.assertEqual(result, "Session with plain details")


class TestDeleteFlag(unittest.TestCase):
    """Unit tests for delete_flag()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deletes_existing_flag(self):
        p = _tmp_flag(self.tmp, ".session-start-voice", "context")
        delete_flag(p)
        self.assertFalse(p.exists(), "Flag must be deleted after delete_flag()")

    def test_does_not_raise_when_flag_missing(self):
        """delete_flag on a non-existent path must be a no-op."""
        p = Path(self.tmp) / ".nonexistent"
        try:
            delete_flag(p)
        except Exception as exc:
            self.fail(f"delete_flag raised on missing file: {exc}")

    def test_idempotent_second_call(self):
        """Calling delete_flag twice on same path must not raise."""
        p = _tmp_flag(self.tmp, ".flag", "ctx")
        delete_flag(p)
        try:
            delete_flag(p)
        except Exception as exc:
            self.fail(f"Second delete_flag call raised: {exc}")


class TestIncrementRetry(unittest.TestCase):
    """Unit tests for increment_retry()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_retry_on_plain_text_flag_returns_true(self):
        """
        Plain-text flag (no .json suffix): treated as retries=0 -> incremented
        to 1, returns True.
        Note: the function reads JSON only when suffix=='.json'.
        Plain files get a fresh dict({'retries': 0}).
        """
        p = _tmp_flag(self.tmp, ".session-start-voice", "plain context")
        result = increment_retry(p)
        self.assertTrue(result, "First retry should return True (still has retries)")

    def test_retry_counter_written_to_file(self):
        """After increment on a plain flag, file must contain JSON with retries=1."""
        p = _tmp_flag(self.tmp, ".flag", "context")
        increment_retry(p)
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("retries"), 1)

    def test_second_retry_returns_true(self):
        p = _tmp_json_flag(self.tmp, ".flag.json", {"content": "ctx", "retries": 1})
        result = increment_retry(p)
        self.assertTrue(result)

    def test_third_retry_returns_true(self):
        """retries=2 -> 3, still below max, returns True."""
        p = _tmp_json_flag(self.tmp, ".flag.json", {"content": "ctx", "retries": 2})
        result = increment_retry(p)
        self.assertTrue(result)

    def test_max_retries_exceeded_returns_false(self):
        """When retries is already 3, next call must return False."""
        p = _tmp_json_flag(self.tmp, ".flag.json", {"content": "ctx", "retries": 3})
        result = increment_retry(p)
        self.assertFalse(result, "Max retries (3) exceeded -> must return False")

    def test_non_json_suffix_handled_as_plain(self):
        """Files without .json suffix treated as plain text; retries field added."""
        p = _tmp_flag(self.tmp, ".session-start-voice", "session context")
        increment_retry(p)
        content = p.read_text(encoding="utf-8")
        data = json.loads(content)
        self.assertIn("retries", data)
        self.assertEqual(data["retries"], 1)

    def test_missing_file_returns_false(self):
        """
        increment_retry on a missing file:
        - For .json suffix: flag_path.read_text() raises FileNotFoundError
          -> caught by except -> returns False
        - For non-.json suffix: dict initialized from scratch (retries=0 -> 1)
          -> write_text raises FileNotFoundError on missing dir? No - the parent
          dir exists (tmp_dir exists but we chose a ghost filename in tmp).

        Use a ghost JSON file so the read path throws.
        """
        p = Path(self.tmp) / "ghost.json"
        result = increment_retry(p)
        self.assertFalse(result, "Missing .json flag -> read fails -> return False")


class TestGetSessionStartDefault(unittest.TestCase):
    """Unit tests for get_session_start_default() fallback messages."""

    def test_morning_greeting(self):
        """hour < 12 -> 'Good morning'"""
        with patch.object(_mod, "datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=9)
            msg = get_session_start_default()
        self.assertIn("Good morning", msg)
        self.assertIn("Sir", msg)

    def test_afternoon_greeting(self):
        """12 <= hour < 17 -> 'Good afternoon'"""
        with patch.object(_mod, "datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=14)
            msg = get_session_start_default()
        self.assertIn("Good afternoon", msg)

    def test_evening_greeting(self):
        """hour >= 17 -> 'Good evening'"""
        with patch.object(_mod, "datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=20)
            msg = get_session_start_default()
        self.assertIn("Good evening", msg)

    def test_boundary_noon_is_afternoon(self):
        """hour=12 should be 'Good afternoon', not morning."""
        with patch.object(_mod, "datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=12)
            msg = get_session_start_default()
        self.assertIn("Good afternoon", msg)

    def test_boundary_17_is_evening(self):
        """hour=17 should be 'Good evening', not afternoon."""
        with patch.object(_mod, "datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=17)
            msg = get_session_start_default()
        self.assertIn("Good evening", msg)

    def test_returns_non_empty_string(self):
        msg = get_session_start_default()
        self.assertIsInstance(msg, str)
        self.assertGreater(len(msg.strip()), 0)

    def test_mentions_session_started(self):
        msg = get_session_start_default()
        self.assertIn("session started", msg.lower())

    def test_mentions_ready(self):
        msg = get_session_start_default()
        self.assertIn("ready", msg.lower())


class TestGetWorkDoneDefault(unittest.TestCase):
    """Unit tests for get_work_done_default() fallback messages."""

    def test_returns_string(self):
        msg = get_work_done_default()
        self.assertIsInstance(msg, str)

    def test_contains_sir(self):
        msg = get_work_done_default()
        self.assertIn("Sir", msg)

    def test_mentions_completion(self):
        msg = get_work_done_default()
        msg_lower = msg.lower()
        self.assertTrue("complet" in msg_lower or "done" in msg_lower, f"Expected completion keyword in: {msg}")

    def test_non_empty(self):
        msg = get_work_done_default()
        self.assertGreater(len(msg.strip()), 10)


class TestGetTaskCompleteDefault(unittest.TestCase):
    """Unit tests for get_task_complete_default() fallback."""

    def test_returns_string_with_sir(self):
        msg = get_task_complete_default()
        self.assertIsInstance(msg, str)
        self.assertIn("Sir", msg)

    def test_mentions_task(self):
        msg = get_task_complete_default()
        self.assertIn("task", msg.lower())


# ===========================================================================
# SECTION 2: INTEGRATION TESTS
# ===========================================================================


class TestCompleteFlow(unittest.TestCase):
    """
    Integration Tests: flag exists -> LLM call -> speak -> delete.
    All external I/O (LLM, speak, delete) is mocked.
    Uses patch.object() which targets the already-loaded module object directly.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _absent(self, name):
        """Return path to a file that does not exist."""
        return Path(self.tmp) / name

    def test_session_start_speaks_and_deletes(self):
        """
        Flow: SESSION_START flag exists ->
              speak() called with static default, delete_flag() called once.
        """
        flag = _tmp_flag(self.tmp, ".session-start-voice", "morning context")

        with patch.object(_mod, "SESSION_START_FLAG", flag), patch.object(
            _mod, "TASK_COMPLETE_FLAG", self._absent(".tc")
        ), patch.object(_mod, "WORK_DONE_FLAG", self._absent(".wd")), patch.object(
            _mod, "speak"
        ) as mock_speak, patch.object(
            _mod, "delete_flag"
        ) as mock_delete:
            with self.assertRaises(SystemExit):
                _mod.main()

        mock_speak.assert_called_once()
        spoken = mock_speak.call_args[0][0]
        self.assertIn("Sir", spoken)
        mock_delete.assert_called_once_with(flag)

    def test_work_done_speaks_and_deletes(self):
        """
        Flow: WORK_DONE flag exists ->
              speak() called with static default, delete_flag() called.
        """
        flag = _tmp_flag(self.tmp, ".session-work-done", "All tests passed")

        with patch.object(_mod, "SESSION_START_FLAG", self._absent(".ss")), patch.object(
            _mod, "SESSION_START_FLAG_PID", self._absent(".ss-pid")
        ), patch.object(_mod, "TASK_COMPLETE_FLAG", self._absent(".tc")), patch.object(
            _mod, "TASK_COMPLETE_FLAG_PID", self._absent(".tc-pid")
        ), patch.object(
            _mod, "WORK_DONE_FLAG", flag
        ), patch.object(
            _mod, "WORK_DONE_FLAG_PID", self._absent(".wd-pid")
        ), patch.object(
            _mod, "speak"
        ) as mock_speak, patch.object(
            _mod, "delete_flag"
        ) as mock_delete:
            with self.assertRaises(SystemExit):
                _mod.main()

        mock_speak.assert_called_once()
        spoken = mock_speak.call_args[0][0]
        self.assertIn("Sir", spoken)
        mock_delete.assert_called_once_with(flag)

    def test_task_complete_flow(self):
        """TASK_COMPLETE flag: static default spoken and flag deleted."""
        flag = _tmp_flag(self.tmp, ".task-complete-voice", "task info")

        with patch.object(_mod, "SESSION_START_FLAG", self._absent(".ss")), patch.object(
            _mod, "SESSION_START_FLAG_PID", self._absent(".ss-pid")
        ), patch.object(_mod, "TASK_COMPLETE_FLAG", flag), patch.object(
            _mod, "TASK_COMPLETE_FLAG_PID", self._absent(".tc-pid")
        ), patch.object(
            _mod, "WORK_DONE_FLAG", self._absent(".wd")
        ), patch.object(
            _mod, "WORK_DONE_FLAG_PID", self._absent(".wd-pid")
        ), patch.object(
            _mod, "speak"
        ) as mock_speak, patch.object(
            _mod, "delete_flag"
        ) as mock_delete:
            with self.assertRaises(SystemExit):
                _mod.main()

        mock_speak.assert_called_once()
        spoken = mock_speak.call_args[0][0]
        self.assertIn("Sir", spoken)
        mock_delete.assert_called_once_with(flag)

    def test_static_message_spoken_and_flag_deleted(self):
        """
        v4.3.0: Static default is always spoken, flag always deleted.
        """
        flag = _tmp_flag(self.tmp, ".session-start-voice", "context")

        with patch.object(_mod, "SESSION_START_FLAG", flag), patch.object(
            _mod, "SESSION_START_FLAG_PID", self._absent(".ss-pid")
        ), patch.object(_mod, "TASK_COMPLETE_FLAG", self._absent(".tc")), patch.object(
            _mod, "TASK_COMPLETE_FLAG_PID", self._absent(".tc-pid")
        ), patch.object(
            _mod, "WORK_DONE_FLAG", self._absent(".wd")
        ), patch.object(
            _mod, "WORK_DONE_FLAG_PID", self._absent(".wd-pid")
        ), patch.object(
            _mod, "speak"
        ) as mock_speak, patch.object(
            _mod, "delete_flag"
        ) as mock_delete:
            with self.assertRaises(SystemExit):
                _mod.main()

        mock_speak.assert_called()
        mock_delete.assert_called_with(flag)

    def test_static_fallback_always_speaks_and_deletes_flag(self):
        """
        Flow: flag exists -> speak static default, delete flag.
        """
        flag = _tmp_flag(self.tmp, ".session-start-voice", "ctx")

        with patch.object(_mod, "SESSION_START_FLAG", flag), patch.object(
            _mod, "TASK_COMPLETE_FLAG", self._absent(".tc")
        ), patch.object(_mod, "WORK_DONE_FLAG", self._absent(".wd")), patch.object(
            _mod, "speak"
        ) as mock_speak, patch.object(
            _mod, "delete_flag"
        ) as mock_delete:
            with self.assertRaises(SystemExit):
                _mod.main()

        mock_speak.assert_called()
        mock_delete.assert_called_with(flag)

    def test_work_done_always_speaks(self):
        """
        CRITICAL: work-done flag must ALWAYS trigger speak.
        This is the most important notification in the system.
        """
        flag = _tmp_flag(self.tmp, ".session-work-done", "all done")

        with patch.object(_mod, "SESSION_START_FLAG", self._absent(".ss")), patch.object(
            _mod, "TASK_COMPLETE_FLAG", self._absent(".tc")
        ), patch.object(_mod, "WORK_DONE_FLAG", flag), patch.object(_mod, "speak") as mock_speak, patch.object(
            _mod, "delete_flag"
        ) as mock_delete:
            with self.assertRaises(SystemExit):
                _mod.main()

        self.assertTrue(mock_speak.called, "work-done MUST call speak()")
        mock_delete.assert_called_with(flag)

    def test_no_flags_no_speak(self):
        """No flag files present -> speak must never be called."""
        with patch.object(_mod, "SESSION_START_FLAG", self._absent(".ss")), patch.object(
            _mod, "TASK_COMPLETE_FLAG", self._absent(".tc")
        ), patch.object(_mod, "WORK_DONE_FLAG", self._absent(".wd")), patch.object(_mod, "speak") as mock_speak:
            with self.assertRaises(SystemExit):
                _mod.main()

        mock_speak.assert_not_called()

    def test_static_default_is_spoken_not_raw_flag_content(self):
        """
        v4.3.0: Static default is always spoken (NEVER the raw flag content string).
        """
        flag = _tmp_flag(self.tmp, ".session-start-voice", "My custom context message")

        with patch.object(_mod, "SESSION_START_FLAG", flag), patch.object(
            _mod, "SESSION_START_FLAG_PID", self._absent(".ss-pid")
        ), patch.object(_mod, "TASK_COMPLETE_FLAG", self._absent(".tc")), patch.object(
            _mod, "TASK_COMPLETE_FLAG_PID", self._absent(".tc-pid")
        ), patch.object(
            _mod, "WORK_DONE_FLAG", self._absent(".wd")
        ), patch.object(
            _mod, "WORK_DONE_FLAG_PID", self._absent(".wd-pid")
        ), patch.object(
            _mod, "speak"
        ) as mock_speak, patch.object(
            _mod, "delete_flag"
        ):
            with self.assertRaises(SystemExit):
                _mod.main()

        # v4.3.0: static default is spoken, not raw flag content
        mock_speak.assert_called_once()
        spoken = mock_speak.call_args[0][0]
        self.assertIn("Sir", spoken)
        self.assertNotEqual(spoken, "My custom context message", "v4.3.0 must not speak raw flag content")


class TestPriorityOrder(unittest.TestCase):
    """All three flags are processed independently when they all exist."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_three_flags_processed(self):
        """When all 3 flags exist, all 3 must speak and delete."""
        f1 = _tmp_flag(self.tmp, ".session-start-voice", "ctx1")
        f2 = _tmp_flag(self.tmp, ".task-complete-voice", "ctx2")
        f3 = _tmp_flag(self.tmp, ".session-work-done", "ctx3")

        with patch.object(_mod, "SESSION_START_FLAG", f1), patch.object(_mod, "TASK_COMPLETE_FLAG", f2), patch.object(
            _mod, "WORK_DONE_FLAG", f3
        ), patch.object(_mod, "speak") as mock_speak, patch.object(_mod, "delete_flag") as mock_delete:
            with self.assertRaises(SystemExit):
                _mod.main()

        self.assertEqual(mock_speak.call_count, 3, "All 3 flags must trigger speak")
        self.assertEqual(mock_delete.call_count, 3, "All 3 flags must be deleted")


# ===========================================================================
# SECTION 3: LOGGING TESTS
# ===========================================================================


class TestLogging(unittest.TestCase):
    """
    Verify that log_s() writes entries and that key flow events produce
    the correct log entries (retry counters, flag lifecycle events).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log_file = Path(self.tmp) / "test-stop-notifier.log"
        self.log_patcher = patch.object(_mod, "STOP_LOG", self.log_file)
        self.log_patcher.start()

    def tearDown(self):
        self.log_patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read_log(self):
        if not self.log_file.exists():
            return ""
        return self.log_file.read_text(encoding="utf-8")

    def test_log_s_writes_timestamped_entry(self):
        log_s("TEST ENTRY")
        content = self._read_log()
        self.assertIn("TEST ENTRY", content)
        self.assertRegex(content, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_log_s_appends_multiple_entries(self):
        log_s("FIRST")
        log_s("SECOND")
        log_s("THIRD")
        content = self._read_log()
        self.assertIn("FIRST", content)
        self.assertIn("SECOND", content)
        self.assertIn("THIRD", content)

    def test_delete_flag_logs_flag_name(self):
        p = Path(self.tmp) / ".my-flag"
        p.write_text("x", encoding="utf-8")
        delete_flag(p)
        content = self._read_log()
        self.assertIn(".my-flag", content)
        self.assertIn("deleted", content.lower())

    def test_increment_retry_writes_json_to_flag(self):
        """
        v4.2.0: increment_retry() does not log - it only updates the flag file.
        Verify the retry counter is written correctly to the flag file.
        """
        p = _tmp_flag(self.tmp, ".flag", "ctx")
        result = increment_retry(p)
        self.assertTrue(result)
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("retries"), 1)

    def test_increment_retry_max_returns_false(self):
        """
        v4.3.0: increment_retry() at max_retries returns False without logging.
        """
        p = _tmp_json_flag(self.tmp, ".flag.json", {"content": "x", "retries": 3})
        result = increment_retry(p)
        self.assertFalse(result)

    def test_voice_flag_logs_static_message(self):
        """v4.3.0: handle_voice_flag logs the static message being used."""
        from scripts.stop_notifier.voice import get_session_start_default, handle_voice_flag

        p = Path(self.tmp) / ".session-start-voice"
        p.write_text("ctx", encoding="utf-8")

        with patch("scripts.stop_notifier.voice.speak"), patch("scripts.stop_notifier.voice.delete_flag"):
            handle_voice_flag(p, "session_start", get_session_start_default)

        content = self._read_log()
        self.assertIn("session_start", content)
        self.assertIn("static message", content)

    def test_stop_hook_logs_silence_when_no_flags(self):
        """When no flags exist, main() must log the 'No voice flags found' message."""
        tmp = tempfile.mkdtemp()
        try:
            with patch.object(_mod, "SESSION_START_FLAG", Path(tmp) / ".ss"), patch.object(
                _mod, "TASK_COMPLETE_FLAG", Path(tmp) / ".tc"
            ), patch.object(_mod, "WORK_DONE_FLAG", Path(tmp) / ".wd"):
                with self.assertRaises(SystemExit):
                    _mod.main()

            content = self._read_log()
            self.assertIn("No voice flags found", content)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# SECTION 4: SPEAK FUNCTION TESTS
# ===========================================================================


class TestSpeak(unittest.TestCase):
    """Tests for the speak() non-blocking Popen launcher."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.voice_script = Path(self.tmp) / "voice-notifier.py"
        self.voice_script.write_text("# fake voice script", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_text_does_not_launch_popen(self):
        with patch.object(_mod, "VOICE_SCRIPT", self.voice_script), patch.object(
            _mod.subprocess, "Popen"
        ) as mock_popen:
            speak("")
        mock_popen.assert_not_called()

    def test_whitespace_only_does_not_launch_popen(self):
        with patch.object(_mod, "VOICE_SCRIPT", self.voice_script), patch.object(
            _mod.subprocess, "Popen"
        ) as mock_popen:
            speak("   \t\n")
        mock_popen.assert_not_called()

    def test_missing_voice_script_does_not_raise(self):
        missing = Path(self.tmp) / "no-voice.py"
        with patch.object(_mod, "VOICE_SCRIPT", missing):
            try:
                speak("Sir, test message.")
            except Exception as exc:
                self.fail(f"speak() raised on missing voice script: {exc}")

    def test_valid_text_calls_popen(self):
        with patch.object(_mod, "VOICE_SCRIPT", self.voice_script), patch.object(
            _mod, "VOICE_ENABLED", True
        ), patch.object(_mod.subprocess, "Popen") as mock_popen:
            speak("Sir, session started.")
        mock_popen.assert_called_once()

    def test_valid_text_passed_to_popen_command(self):
        with patch.object(_mod, "VOICE_SCRIPT", self.voice_script), patch.object(
            _mod, "VOICE_ENABLED", True
        ), patch.object(_mod.subprocess, "Popen") as mock_popen:
            speak("Sir, session started.")
        cmd = mock_popen.call_args[0][0]
        self.assertIn("Sir, session started.", cmd)

    def test_popen_called_with_devnull_streams(self):
        """Fire-and-forget pattern: stdout and stderr must be DEVNULL."""
        import subprocess as sp

        with patch.object(_mod, "VOICE_SCRIPT", self.voice_script), patch.object(
            _mod, "VOICE_ENABLED", True
        ), patch.object(_mod.subprocess, "Popen") as mock_popen:
            speak("Sir, hello.")
        kwargs = mock_popen.call_args[1]
        self.assertEqual(kwargs.get("stdout"), sp.DEVNULL)
        self.assertEqual(kwargs.get("stderr"), sp.DEVNULL)


# ===========================================================================
# MAIN RUNNER
# ===========================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        # Unit tests
        TestReadFlag,
        TestDeleteFlag,
        TestIncrementRetry,
        TestGetSessionStartDefault,
        TestGetWorkDoneDefault,
        TestGetTaskCompleteDefault,
        # Integration tests
        TestCompleteFlow,
        TestPriorityOrder,
        # Logging tests
        TestLogging,
        # speak() function tests
        TestSpeak,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    print("")
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"  Tests run   : {result.testsRun}")
    print(f"  Failures    : {len(result.failures)}")
    print(f"  Errors      : {len(result.errors)}")
    print(f"  Skipped     : {len(result.skipped)}")
    print(f'  Result      : {"PASS" if result.wasSuccessful() else "FAIL"}')
    print("=" * 70)

    sys.exit(0 if result.wasSuccessful() else 1)
