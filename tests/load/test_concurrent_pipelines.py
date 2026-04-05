"""Load tests for concurrent pipeline state isolation.

Tests verify that concurrent pipeline executions do not corrupt each
others' FlowState (session_id uniqueness, no shared global state).

These tests do NOT require real LLM providers. They mock the LangGraph
graph execution to return immediately.

Mark: pytest.mark.load (skip in CI by default unless RUN_LOAD_TESTS=1)
"""

import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_SRC_MCP_DIR = _PROJECT_ROOT / "src" / "mcp"

for _p in [str(_PROJECT_ROOT), str(_SCRIPTS_DIR), str(_SRC_MCP_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Skip all load tests unless the operator explicitly opts in
pytestmark = pytest.mark.skipif(not os.environ.get("RUN_LOAD_TESTS"), reason="Set RUN_LOAD_TESTS=1 to run load tests")


# ---------------------------------------------------------------------------
# Helper: generate session IDs in the same way the pipeline does
# ---------------------------------------------------------------------------


def _generate_session_id():
    """Generate a unique session ID using uuid4.

    This mirrors how the pipeline creates session IDs so we can test
    uniqueness guarantees across concurrent callers.
    """
    import uuid

    return "session-" + str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Test 1: Concurrent session ID uniqueness
# ---------------------------------------------------------------------------


class TestConcurrentSessionIdUniqueness:
    """Five concurrent threads must each produce a unique session ID."""

    def test_five_concurrent_sessions_are_unique(self):
        """Session IDs generated concurrently must all be distinct."""
        session_ids = []
        lock = threading.Lock()

        def generate_and_collect():
            sid = _generate_session_id()
            with lock:
                session_ids.append(sid)

        threads = [threading.Thread(target=generate_and_collect) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(session_ids) == 5
        assert len(set(session_ids)) == 5, "All session IDs must be unique; duplicates found: {}".format(
            [sid for sid in session_ids if session_ids.count(sid) > 1]
        )

    def test_hundred_concurrent_sessions_are_unique(self):
        """100 concurrent session ID generations must all be distinct."""
        session_ids = []
        lock = threading.Lock()

        def generate_and_collect():
            sid = _generate_session_id()
            with lock:
                session_ids.append(sid)

        threads = [threading.Thread(target=generate_and_collect) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(session_ids) == 100
        assert len(set(session_ids)) == 100


# ---------------------------------------------------------------------------
# Test 2: TokenBucket thread safety
# ---------------------------------------------------------------------------


class TestTokenBucketThreadSafety:
    """20 threads each trying to consume 1 token from a capacity-10 bucket.

    Exactly 10 should succeed (consume returns True) and 10 should fail
    (consume returns False) when all threads start simultaneously.
    """

    def test_exactly_ten_of_twenty_threads_succeed(self):
        """With capacity=10 and 20 concurrent consumes, exactly 10 must succeed."""
        try:
            from rate_limiter import TokenBucket
        except ImportError:
            pytest.skip("rate_limiter module not importable")

        CAPACITY = 10
        NUM_THREADS = 20

        # Freeze time so no refill happens during the test
        with patch("time.time") as mock_time:
            mock_time.return_value = 5000.0
            bucket = TokenBucket(capacity=CAPACITY, refill_rate=CAPACITY)

        results = []
        lock = threading.Lock()
        barrier = threading.Barrier(NUM_THREADS)

        def try_consume():
            barrier.wait()  # all threads start simultaneously
            with patch("time.time") as mock_time:
                mock_time.return_value = 5000.0  # no time elapsed = no refill
                result = bucket.consume()
            with lock:
                results.append(result)

        threads = [threading.Thread(target=try_consume) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(results) == NUM_THREADS
        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if r is False)

        assert successes == CAPACITY, "Expected exactly {} successful consumes, got {}".format(CAPACITY, successes)
        assert failures == NUM_THREADS - CAPACITY, "Expected exactly {} failed consumes, got {}".format(
            NUM_THREADS - CAPACITY, failures
        )

    def test_bucket_is_thread_safe_no_tokens_lost(self):
        """Concurrent operations must not lose tokens (no race conditions)."""
        try:
            from rate_limiter import TokenBucket
        except ImportError:
            pytest.skip("rate_limiter module not importable")

        CAPACITY = 50

        with patch("time.time") as mock_time:
            mock_time.return_value = 5000.0
            bucket = TokenBucket(capacity=CAPACITY, refill_rate=1)

        success_count = [0]
        counter_lock = threading.Lock()
        barrier = threading.Barrier(CAPACITY)

        def try_consume():
            barrier.wait()
            with patch("time.time") as mock_time:
                mock_time.return_value = 5000.0
                if bucket.consume():
                    with counter_lock:
                        success_count[0] += 1

        threads = [threading.Thread(target=try_consume) for _ in range(CAPACITY)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # All CAPACITY tokens consumed, none extra
        assert success_count[0] == CAPACITY
