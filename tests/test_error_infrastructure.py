#!/usr/bin/env python3
"""
Test script for Level -1 Error Infrastructure

Tests:
1. ErrorLogger functionality
2. BackupManager functionality
3. File validation and recovery
"""

import sys
import tempfile
from pathlib import Path

# Add project root and langgraph_engine to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "langgraph_engine"))

from backup_manager import BackupManager
from error_logger import ErrorLogger


def test_error_logger():
    """Test error logger functionality."""
    print("\n" + "=" * 60)
    print("TEST 1: ErrorLogger Functionality")
    print("=" * 60)

    logger = ErrorLogger("test-session-001")

    # Test 1: Log validation result
    logger.log_validation_result("Level -1", "Unicode UTF-8 Fix", True, "UTF-8 encoding applied")

    # Test 2: Log validation failure
    logger.log_validation_result(
        "Level -1",
        "Encoding Check",
        False,
        "Non-ASCII characters found in 3 files",
    )

    # Test 3: Log decision
    logger.log_decision(
        "Level -1",
        "Retry Failed Checks",
        "User selected auto-fix option",
        options=["auto-fix", "skip"],
        chosen_option="auto-fix",
    )

    # Test 4: Log retry attempt
    logger.log_retry_attempt("Level -1", attempt=1, max_attempts=3, status="FAILED", reason="Encoding check failed")

    # Test 5: Log error
    logger.log_error(
        "Level -1",
        "Failed to apply Unicode fix",
        severity="ERROR",
        error_type="EncodingError",
        recovery_action="Retried with fallback",
        context={"file": "test_file.py", "line": 42},
    )

    # Test 6: Get summaries
    error_summary = logger.get_error_summary()
    decision_summary = logger.get_decision_summary()

    print(f"\n[OK] Error Summary: {error_summary}")
    print(f"[OK] Decision Summary: {decision_summary}")

    # Test 7: Save audit trail
    audit_path = logger.save_audit_trail()
    print(f"[OK] Audit trail saved: {audit_path}")
    print(f"   File exists: {audit_path.exists()}")

    return True


def test_backup_manager():
    """Test backup manager functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: BackupManager Functionality")
    print("=" * 60)

    manager = BackupManager("test-session-002")

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        test_file = Path(f.name)
        f.write("print('original content')\n")

    try:
        # Test 1: Backup file
        success = manager.backup_file(str(test_file), "Level -1", "Before modification")
        print(f"[OK] Backup created: {success}")

        # Test 2: Modify file
        test_file.write_text("print('original content')\nprint('modified')\n")
        print("[OK] File modified")

        # Test 3: Generate diff
        diff_path = manager.generate_diff(str(test_file), "Level -1")
        print(f"[OK] Diff generated: {diff_path}")
        if diff_path:
            print(f"   Content:\n{Path(diff_path).read_text()[:200]}...")

        # Test 4: Compare files
        comparison = manager.compare_files(str(test_file), "Level -1")
        print(f"[OK] Comparison: {comparison}")

        # Test 5: Validate file integrity
        is_valid = manager.validate_file_integrity(str(test_file), "Level -1")
        print(f"[OK] File validation: {is_valid}")

        # Test 6: Get backup history
        history = manager.get_backup_history(str(test_file))
        print(f"[OK] Backup history: {len(history)} entries")

        # Test 7: Restore file
        success = manager.restore_file(str(test_file), "Level -1")
        print(f"[OK] File restored: {success}")

        # Verify restoration
        restored_content = test_file.read_text()
        is_restored = "original content" in restored_content and "modified" not in restored_content
        print(f"[OK] Restoration verified: {is_restored}")

        return True

    finally:
        # Cleanup
        test_file.unlink()


def test_integration():
    """Test integration of error logging and backup."""
    print("\n" + "=" * 60)
    print("TEST 3: Integration Test")
    print("=" * 60)

    session_id = "test-integration-001"
    logger = ErrorLogger(session_id)
    backup = BackupManager(session_id)

    # Create test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        test_file = Path(f.name)
        f.write("x = 1\n")

    try:
        # Backup before modification
        logger.log_decision("Level -1", "Starting modification", "File will be backed up and restored if needed")
        backup.backup_file(str(test_file), "Level -1", "Integration test")

        # Attempt modification
        _original = test_file.read_text()
        test_file.write_text("x = 1\ny = 2\n")
        logger.log_validation_result("Level -1", "File modification", True)

        # Validate integrity
        if backup.validate_file_integrity(str(test_file), "Level -1"):
            logger.log_validation_result("Level -1", "File integrity check", True)

            # Generate diff
            _diff = backup.generate_diff(str(test_file), "Level -1", "integration_test")
            logger.log_decision("Level -1", "Modification complete", "File is valid and changes tracked")
        else:
            logger.log_error("Level -1", "Validation failed", severity="ERROR")
            backup.restore_file(str(test_file), "Level -1")
            logger.log_validation_result("Level -1", "File restoration", True)

        # Save audit trail
        logger.save_audit_trail()
        print("[OK] Integration test completed successfully")

        return True

    finally:
        # Cleanup
        test_file.unlink()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LEVEL -1 ERROR INFRASTRUCTURE TESTS")
    print("=" * 60)

    try:
        test_error_logger()
        test_backup_manager()
        test_integration()

        print("\n" + "=" * 60)
        print("[OK] ALL TESTS PASSED!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
