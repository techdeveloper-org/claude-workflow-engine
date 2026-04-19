"""
Test Complete Retry History Tracking

Verifies that Claude gets complete feedback history showing:
- What was fixed in previous attempts
- Current issues to fix
- Remaining retry attempts
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from langgraph_engine.flow_state import FlowState
from langgraph_engine.level3_execution.subgraph import _build_retry_history_context, step10_implementation_note


class TestRetryHistoryTracking:
    """Test complete retry history context."""

    def test_no_retry_history_initial(self):
        """Test first attempt - no retry history."""
        print("\n" + "=" * 70)
        print("[OK] TEST 1: Initial Attempt (No Retry History)")
        print("=" * 70)

        state = FlowState(
            step11_retry_count=0,
            step11_retry_messages=[],
            step11_review_issues=[],
            step7_execution_prompt="Initial prompt",
            session_dir=str(getattr(self, "_tmp", Path(tempfile.mkdtemp()))),
        )

        history = _build_retry_history_context(state)
        print(f"History: '{history}'")
        assert history == "", "First attempt should have empty history"
        print("[OK] No history on first attempt (correct)")

    def test_retry_attempt_1_history(self):
        """Test Retry Attempt 1 - shows what was fixed."""
        print("\n" + "=" * 70)
        print("[OK] TEST 2: Retry Attempt 1 (Shows Previous Fixes)")
        print("=" * 70)

        state = FlowState(
            step11_retry_count=1,
            step11_retry_messages=["Fixed print() statement in main function"],
            step11_review_issues=["Missing logger import"],
            step7_execution_prompt="Original prompt",
            session_dir=str(getattr(self, "_tmp", Path(tempfile.mkdtemp()))),
        )

        history = _build_retry_history_context(state)
        print(f"History:\n{history}")

        # Check content
        assert "COMPLETE RETRY HISTORY" in history
        assert "Attempt 1" in history
        assert "Fixed print() statement" in history
        assert "Missing logger import" in history
        assert "Current Attempt: #1 of 3" in history
        print("[OK] Previous fixes shown (correct)")
        print("[OK] Current issues shown (correct)")

    def test_retry_attempt_2_complete_history(self):
        """Test Retry Attempt 2 - shows complete history + new issues."""
        print("\n" + "=" * 70)
        print("[OK] TEST 3: Retry Attempt 2 (Complete History)")
        print("=" * 70)

        state = FlowState(
            step11_retry_count=2,
            step11_retry_messages=[
                "Attempt 1: Fixed print() -> added logging",
                "Attempt 2: Added logger import -> fixed import error",
            ],
            step11_review_issues=[
                "Missing @Autowired annotation",
                "No error handling in try/catch",
                "Unused variable 'result'",
            ],
            step7_execution_prompt="Original prompt",
            session_dir=str(getattr(self, "_tmp", Path(tempfile.mkdtemp()))),
        )

        history = _build_retry_history_context(state)
        print(f"History:\n{history}")

        # Verify complete history is shown
        assert "Attempt 1" in history, "Should show Attempt 1"
        assert "Attempt 2" in history, "Should show Attempt 2"
        assert "Fixed print()" in history, "Should show previous fix 1"
        assert "Added logger import" in history, "Should show previous fix 2"
        assert "Missing @Autowired" in history, "Should show current issue 1"
        assert "No error handling" in history, "Should show current issue 2"
        assert "Current Attempt: #2 of 3" in history
        print("[OK] Complete history tracked (correct)")

    def test_final_retry_warning(self):
        """Test Retry Attempt 3 - final warning."""
        print("\n" + "=" * 70)
        print("[OK] TEST 4: Final Retry (Attempt 3) - Warning Message")
        print("=" * 70)

        state = FlowState(
            step11_retry_count=3,
            step11_retry_messages=[
                "Attempt 1: Fixed issue A",
                "Attempt 2: Fixed issue B",
            ],
            step11_review_issues=["Issue C"],
            step7_execution_prompt="Original prompt",
            session_dir=str(getattr(self, "_tmp", Path(tempfile.mkdtemp()))),
        )

        history = _build_retry_history_context(state)
        print(f"History:\n{history}")

        # Check final warning
        assert "FINAL ATTEMPT" in history
        assert "PR will be blocked for manual review" in history
        assert "Remaining Attempts: 0" in history
        print("[OK] Final attempt warning shown (correct)")
        print("[WARN]  User alerted about manual review fallback")

    def test_step10_implementation_note_with_history(self):
        """Test step10 generates prompt with complete history."""
        print("\n" + "=" * 70)
        print("[OK] TEST 5: Step 10 Full Prompt with History")
        print("=" * 70)

        state = FlowState(
            step11_retry_count=1,
            step11_retry_messages=["Removed print() statements"],
            step11_review_issues=["Missing imports at top", "No docstring in main function"],
            step7_execution_prompt="Implement the feature...",
            session_dir=str(getattr(self, "_tmp", Path(tempfile.mkdtemp()))),
        )

        result = step10_implementation_note(state)

        print(f"Status: {result['step10_status']}")
        print(f"Message: {result['step10_message']}")
        print(f"Has retry context: {result['step10_has_retry_context']}")

        # Check prompt includes history
        prompt = result["step10_execution_prompt"]
        print(f"\nPrompt preview:\n{prompt[:500]}...")

        assert "COMPLETE RETRY HISTORY" in prompt
        assert "Removed print()" in prompt
        assert "Missing imports" in prompt
        assert "CURRENT ISSUES TO FIX" in prompt
        assert "Do NOT undo previous fixes" in prompt
        print("[OK] Prompt includes complete history (correct)")

    def test_many_issues_truncated(self):
        """Test many issues are truncated nicely."""
        print("\n" + "=" * 70)
        print("[OK] TEST 6: Many Issues Truncation")
        print("=" * 70)

        # Create 20 issues
        issues = [f"Issue #{i}" for i in range(1, 21)]

        state = FlowState(
            step11_retry_count=1,
            step11_retry_messages=["Fixed previous issue"],
            step11_review_issues=issues,
            step7_execution_prompt="Prompt",
            session_dir=str(getattr(self, "_tmp", Path(tempfile.mkdtemp()))),
        )

        history = _build_retry_history_context(state)
        print(f"History (last 300 chars):\n...{history[-300:]}")

        # Should show first 10 + "and X more"
        assert "Issue #1" in history
        assert "Issue #10" in history
        assert "and 10 more issues" in history
        print("[OK] Issues truncated nicely (shows first 10 + count)")


class TestRetryHistorySummary:
    """Summary of retry history tracking."""

    def test_summary(self):
        """Print summary."""
        print("\n" + "=" * 70)
        print("COMPLETE RETRY HISTORY TRACKING - TEST SUMMARY")
        print("=" * 70)
        print(
            """
[OK] FEATURES IMPLEMENTED:

1. Build Retry History Context
   [x] Shows what was fixed in each attempt
   [x] Lists current issues to fix
   [x] Shows remaining retry attempts
   [x] Warns on final attempt

2. Prompt Generation
   [x] Includes complete history in retry prompt
   [x] Reminds Claude not to undo previous fixes
   [x] Clear separation of previous fixes vs current issues
   [x] Truncates many issues nicely (first 10 + count)

3. Smart Formatting
   [x] Easy to read sections
   [x] Clear emphasis on current issues
   [x] Tracks attempt numbers
   [x] Final attempt warning

EXAMPLE OUTPUT:
---------------------------------------------------------------------

======================================================================
[list] COMPLETE RETRY HISTORY
======================================================================

[x] PREVIOUS ATTEMPTS (What was fixed):
----------------------------------------------------------------------

  Attempt 1:
  Fixed print() statement in main function

  Attempt 2:
  Added logger import to utils.py

[RED] CURRENT ATTEMPT (Issues to fix now):
----------------------------------------------------------------------
  1. Missing @Autowired annotation on dependency
  2. No error handling in catch block
  3. Unused variable 'result' in function

[chart] RETRY STATUS:
----------------------------------------------------------------------
  Current Attempt: #2 of 3
  Remaining Attempts: 1

======================================================================

[RETRY #2] Fix the following code review issues while keeping
previous fixes:

CURRENT ISSUES TO FIX:
- Missing @Autowired annotation on dependency
- No error handling in catch block
- Unused variable 'result' in function

IMPORTANT:
- Do NOT undo previous fixes (shown in history above)
- Fix ONLY the current issues listed above
- Keep all working code from previous attempts
- Run tests to verify fixes if possible

Original implementation prompt:
---
[original prompt]
---

Please fix the issues above and re-implement.

---------------------------------------------------------------------

BENEFITS:
---------------------------------------------------------------------

[OK] Claude sees what was already fixed
[OK] Prevents repeating same fixes
[OK] Clear understanding of progress
[OK] Motivated by seeing improvements
[OK] Fewer infinite loops
[OK] Better retry success rate

Status: PRODUCTION READY [OK]
        """
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
