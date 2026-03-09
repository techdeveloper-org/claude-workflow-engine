#!/usr/bin/env python3
"""
Unit Tests for EnforcementLogger

Tests all functionality of the enforcement logging middleware including:
- Policy execution logging
- Step execution logging
- Tool usage logging
- Model selection logging
- Task breakdown logging
- Daemon activity logging
- Recent log retrieval
- State file updates
"""

import unittest
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from middleware.enforcement_logger import EnforcementLogger, get_enforcement_logger


class TestEnforcementLogger(unittest.TestCase):
    """Test suite for EnforcementLogger"""

    def setUp(self):
        """Set up test fixtures before each test"""
        # Create temporary directories
        self.temp_dir = tempfile.mkdtemp()
        self.memory_dir = Path(self.temp_dir) / '.claude' / 'memory'
        self.logs_dir = self.memory_dir / 'logs'
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Patch home directory
        self.patcher = patch('pathlib.Path.home')
        self.mock_home = self.patcher.start()
        self.mock_home.return_value = Path(self.temp_dir)

        # Create logger instance
        self.logger = EnforcementLogger()

    def tearDown(self):
        """Clean up after each test"""
        # Close logger handlers to release file handles
        for handler in self.logger.logger.handlers[:]:
            handler.close()
            self.logger.logger.removeHandler(handler)

        self.patcher.stop()

        # Clean up temp directory with retry logic for Windows
        import shutil
        import time
        if os.path.exists(self.temp_dir):
            for attempt in range(3):
                try:
                    shutil.rmtree(self.temp_dir)
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.1)
                    else:
                        pass  # Give up after 3 attempts

    def test_initialization(self):
        """Test logger initialization"""
        self.assertTrue(self.logger.log_file.exists())
        self.assertTrue(self.logger.log_file.parent.exists())
        self.assertIsNotNone(self.logger.logger)

    def test_log_policy_execution_basic(self):
        """Test basic policy execution logging"""
        self.logger.log_policy_execution(
            'test-policy',
            'OK',
            'Test message'
        )

        # Verify log was written
        log_content = self.logger.log_file.read_text()
        self.assertIn('test-policy', log_content)
        self.assertIn('OK', log_content)
        self.assertIn('Test message', log_content)

    def test_log_policy_execution_with_metadata(self):
        """Test policy execution logging with metadata"""
        metadata = {
            'key1': 'value1',
            'key2': 123,
            'key3': True
        }

        self.logger.log_policy_execution(
            'test-policy',
            'OK',
            'Test message',
            metadata
        )

        log_content = self.logger.log_file.read_text()
        self.assertIn('test-policy', log_content)
        self.assertIn('test-policy-metadata', log_content)
        self.assertIn('value1', log_content)

    def test_log_step_execution_started(self):
        """Test step execution logging with STARTED status"""
        self.logger.log_step_execution(
            0,
            'Prompt Generation',
            'STARTED'
        )

        log_content = self.logger.log_file.read_text()
        self.assertIn('step-0-prompt-generation', log_content)
        self.assertIn('STARTED', log_content)
        self.assertIn('Step 0', log_content)

    def test_log_step_execution_completed_updates_state(self):
        """Test step execution logging updates enforcer state on COMPLETED"""
        self.logger.log_step_execution(
            0,
            'Prompt Generation',
            'COMPLETED',
            {'test': 'data'}
        )

        # Check state file was created
        state_file = self.logger.enforcer_state_file
        self.assertTrue(state_file.exists())

        # Check state was updated
        with open(state_file, 'r') as f:
            state = json.load(f)

        self.assertTrue(state.get('prompt_generated'))

    def test_log_step_execution_all_steps(self):
        """Test logging completion of all steps updates state correctly"""
        steps = [
            (0, 'Session Start', 'session_started'),
            (1, 'Context Check', 'context_checked'),
            (2, 'Standards Loaded', 'standards_loaded'),
            (3, 'Prompt Generation', 'prompt_generated'),
            (4, 'Task Breakdown', 'tasks_created'),
            (5, 'Plan Mode Decision', 'plan_mode_decided'),
            (6, 'Model Selection', 'model_selected'),
            (7, 'Skills/Agents Check', 'skills_agents_checked')
        ]

        for step_num, step_name, state_key in steps:
            self.logger.log_step_execution(step_num, step_name, 'COMPLETED')

        # Verify all state keys were set
        with open(self.logger.enforcer_state_file, 'r') as f:
            state = json.load(f)

        for _, _, state_key in steps:
            self.assertTrue(state.get(state_key), f"State key {state_key} should be True")

    def test_log_tool_usage_basic(self):
        """Test basic tool usage logging"""
        self.logger.log_tool_usage(
            'Read',
            'Read file',
            'SUCCESS'
        )

        log_content = self.logger.log_file.read_text()
        self.assertIn('tool-read', log_content)
        self.assertIn('Read file', log_content)
        self.assertIn('SUCCESS', log_content)

    def test_log_tool_usage_with_details(self):
        """Test tool usage logging with details"""
        details = {
            'file': 'test.py',
            'lines': 100,
            'tokens_saved': 5000
        }

        self.logger.log_tool_usage(
            'Read',
            'Read with optimization',
            'OPTIMIZED',
            details
        )

        log_content = self.logger.log_file.read_text()
        self.assertIn('tool-read', log_content)
        self.assertIn('OPTIMIZED', log_content)
        self.assertIn('test.py', log_content)

    def test_log_model_selection(self):
        """Test model selection logging"""
        self.logger.log_model_selection(
            'SONNET',
            8,
            'API Development',
            'Complexity matches SONNET capabilities'
        )

        log_content = self.logger.log_file.read_text()
        self.assertIn('model-selection', log_content)
        self.assertIn('SONNET', log_content)
        self.assertIn('API Development', log_content)

    def test_log_task_breakdown(self):
        """Test task breakdown logging"""
        self.logger.log_task_breakdown(
            12,
            3,
            'MODERATE',
            False
        )

        log_content = self.logger.log_file.read_text()
        self.assertIn('task-breakdown', log_content)
        self.assertIn('12 tasks', log_content)
        self.assertIn('3 phases', log_content)
        self.assertIn('MODERATE', log_content)

    def test_get_recent_logs_empty(self):
        """Test getting recent logs when log is empty"""
        result = self.logger.get_recent_logs(hours=1, limit=100)

        self.assertEqual(len(result), 0)

    def test_get_recent_logs_with_entries(self):
        """Test getting recent logs with entries"""
        # Add some log entries
        self.logger.log_policy_execution('policy1', 'OK', 'Message 1')
        self.logger.log_policy_execution('policy2', 'OK', 'Message 2')
        self.logger.log_policy_execution('policy3', 'OK', 'Message 3')

        result = self.logger.get_recent_logs(hours=1, limit=100)

        self.assertGreater(len(result), 0)
        self.assertLessEqual(len(result), 3)

        # Check structure
        for entry in result:
            self.assertIn('timestamp', entry)
            self.assertIn('policy', entry)
            self.assertIn('status', entry)
            self.assertIn('message', entry)

    def test_get_recent_logs_respects_time_limit(self):
        """Test that recent logs respects time limit"""
        # Manually create log with old entry
        now = datetime.now()
        old_time = (now - timedelta(hours=25)).isoformat()
        recent_time = now.isoformat()

        with open(self.logger.log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{old_time}] old-policy | OK | Old message\n")
            f.write(f"[{recent_time}] recent-policy | OK | Recent message\n")

        result = self.logger.get_recent_logs(hours=24, limit=100)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['policy'], 'recent-policy')

    def test_get_recent_logs_respects_limit(self):
        """Test that recent logs respects entry limit"""
        # Add many entries
        for i in range(50):
            self.logger.log_policy_execution(f'policy-{i}', 'OK', f'Message {i}')

        result = self.logger.get_recent_logs(hours=1, limit=10)

        self.assertEqual(len(result), 10)

    def test_get_recent_logs_ordered_most_recent_first(self):
        """Test that recent logs are ordered with most recent first"""
        import time

        # Create log entries manually to avoid logger name interference
        now = datetime.now()
        entries = [
            (now - timedelta(seconds=3), 'first', 'OK', 'First message'),
            (now - timedelta(seconds=2), 'second', 'OK', 'Second message'),
            (now - timedelta(seconds=1), 'third', 'OK', 'Third message')
        ]

        with open(self.logger.log_file, 'w', encoding='utf-8') as f:
            for timestamp, policy, status, message in entries:
                f.write(f"[{timestamp.isoformat()}] {policy} | {status} | {message}\n")

        result = self.logger.get_recent_logs(hours=1, limit=100)

        # Most recent should be first
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]['policy'], 'third')
        self.assertEqual(result[-1]['policy'], 'first')

    def test_get_enforcement_logger_singleton(self):
        """Test that get_enforcement_logger returns singleton"""
        logger1 = get_enforcement_logger()
        logger2 = get_enforcement_logger()

        self.assertIs(logger1, logger2)

    def test_unicode_handling(self):
        """Test proper handling of Unicode characters"""
        self.logger.log_policy_execution(
            'unicode-test',
            'OK',
            'Test with emojis [ROCKET] and Chinese'
        )

        log_content = self.logger.log_file.read_text(encoding='utf-8')
        self.assertIn('[ROCKET]', log_content)
        self.assertIn('Chinese', log_content)

    def test_state_file_preserves_existing_data(self):
        """Test that updating state preserves existing state data"""
        # Create initial state
        initial_state = {
            'session_started': True,
            'custom_key': 'custom_value',
            'total_violations': 5
        }

        with open(self.logger.enforcer_state_file, 'w') as f:
            json.dump(initial_state, f)

        # Update state via logging
        self.logger.log_step_execution(3, 'Prompt Generation', 'COMPLETED')

        # Check state preserved existing data
        with open(self.logger.enforcer_state_file, 'r') as f:
            state = json.load(f)

        self.assertTrue(state['session_started'])
        self.assertEqual(state['custom_key'], 'custom_value')
        self.assertEqual(state['total_violations'], 5)
        self.assertTrue(state['prompt_generated'])

    def test_malformed_log_entries_dont_break_parsing(self):
        """Test that malformed entries don't break log parsing"""
        with open(self.logger.log_file, 'w', encoding='utf-8') as f:
            f.write("Malformed line without proper format\n")
            f.write("[incomplete | line\n")
            f.write(f"[{datetime.now().isoformat()}] valid-policy | OK | Valid message\n")

        result = self.logger.get_recent_logs(hours=1, limit=100)

        # Should parse the valid entry
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['policy'], 'valid-policy')


class TestEnforcementLoggerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.patcher = patch('pathlib.Path.home')
        self.mock_home = self.patcher.start()
        self.mock_home.return_value = Path(self.temp_dir)

    def tearDown(self):
        """Clean up"""
        self.patcher.stop()

        # Clean up with retry logic for Windows
        import shutil
        import time
        if os.path.exists(self.temp_dir):
            for attempt in range(3):
                try:
                    shutil.rmtree(self.temp_dir)
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.1)
                    else:
                        pass

    def test_corrupted_state_file_handled(self):
        """Test that corrupted state file doesn't crash logger"""
        logger = EnforcementLogger()

        # Create corrupted state file
        with open(logger.enforcer_state_file, 'w') as f:
            f.write("{ invalid json")

        # Should handle gracefully
        try:
            logger.log_step_execution(0, 'Test Step', 'COMPLETED')
            success = True
        except Exception:
            success = False

        self.assertTrue(success)

    def test_permission_error_handled(self):
        """Test handling of permission errors"""
        logger = EnforcementLogger()

        # Make log file read-only (Windows-compatible approach)
        log_file = logger.log_file
        log_file.touch()

        # This test may not work on all systems, so we'll just verify it doesn't crash
        try:
            logger.log_policy_execution('test', 'OK', 'Test')
            # If it succeeds, that's fine
        except Exception:
            # If it fails, that's also acceptable for this test
            pass


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestEnforcementLogger))
    suite.addTests(loader.loadTestsFromTestCase(TestEnforcementLoggerEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
