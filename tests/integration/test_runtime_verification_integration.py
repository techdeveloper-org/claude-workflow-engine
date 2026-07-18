"""Integration tests: ENABLE_RUNTIME_VERIFICATION=1 cross-boundary checks.

Tests exercise the full path from verifier singleton through the health
endpoint JSON, Prometheus counter, and OTel spans.  Each test is marked
@pytest.mark.integration and is fully offline -- no live network calls,
no .env reads, no real claude CLI subprocess (ADR-1 / ADR-2).

Prometheus and OTel tests skip gracefully when the optional packages are
not installed (prometheus_client, opentelemetry-sdk).

Run:
    pytest tests/integration/test_runtime_verification_integration.py -m integration -v
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_SRC_MCP_DIR = _PROJECT_ROOT / "src" / "mcp"

for _p in [str(_PROJECT_ROOT), str(_SCRIPTS_DIR), str(_SRC_MCP_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Singleton isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_verifier():
    """Guarantee singleton isolation between every integration test."""
    from langgraph_engine.runtime_verification.verifier import RuntimeVerifier

    RuntimeVerifier.reset_for_tests()
    yield
    RuntimeVerifier.reset_for_tests()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LONG_PROMPT = "A" * 250


def _free_port():
    """Find a free TCP port on the loopback interface."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ===========================================================================
# Test 1: health endpoint includes "verification" key when RV enabled
# ===========================================================================


@pytest.mark.integration
def test_health_endpoint_contains_verification_key(monkeypatch):
    """GET /health returns JSON with a 'verification' key when ENABLE_RUNTIME_VERIFICATION=1.

    The health server is started on a free port, queried once, then discarded.
    The server thread is daemon so it does not block test process exit.
    """
    port = _free_port()
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    monkeypatch.setenv("ENABLE_HEALTH_SERVER", "1")

    from scripts.health_server import start_health_server

    start_health_server(port=port)

    # Give the daemon thread time to bind
    import time

    time.sleep(0.3)

    url = "http://127.0.0.1:{}/health".format(port)
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        pytest.fail("Health server did not respond: {}".format(exc))

    assert "verification" in body, "Health endpoint must include 'verification' key"
    verification = body["verification"]
    assert "enabled" in verification
    assert "violations_total" in verification
    assert "contracts_registered" in verification


# ===========================================================================
# Test 2: verification.enabled=True when RV enabled in health response
# ===========================================================================


@pytest.mark.integration
def test_health_endpoint_verification_enabled_true(monkeypatch):
    """verification.enabled is True in /health response when ENABLE_RUNTIME_VERIFICATION=1."""
    port = _free_port()
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    monkeypatch.setenv("ENABLE_HEALTH_SERVER", "1")

    from scripts.health_server import start_health_server

    start_health_server(port=port)

    import time

    time.sleep(0.3)

    url = "http://127.0.0.1:{}/health".format(port)
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        pytest.fail("Health server did not respond: {}".format(exc))

    assert body["verification"]["enabled"] is True


# ===========================================================================
# Test 3: verification.violations_total reflects accumulated violations
# ===========================================================================


@pytest.mark.integration
def test_health_endpoint_violations_total_reflects_accumulated_violations(monkeypatch):
    """After triggering a violation, health /health shows violations_total >= 1."""
    port = _free_port()
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    monkeypatch.setenv("ENABLE_HEALTH_SERVER", "1")

    from langgraph_engine.runtime_verification.contracts import NodeContract, PreconditionSpec
    from langgraph_engine.runtime_verification.verifier import RuntimeVerifier
    from scripts.health_server import start_health_server

    # Trigger a violation before starting health server
    verifier = RuntimeVerifier.get_instance()
    contract = NodeContract(
        node_name="integration_violation_node",
        preconditions=[PreconditionSpec(key="required_key", expected_type=str, required=True)],
    )
    verifier.register(contract)
    verifier.check_preconditions("integration_violation_node", {})  # triggers CRITICAL

    start_health_server(port=port)

    import time

    time.sleep(0.3)

    url = "http://127.0.0.1:{}/health".format(port)
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        pytest.fail("Health server did not respond: {}".format(exc))

    assert body["verification"]["violations_total"] >= 1


# ===========================================================================
# Test 4: Prometheus counter increments on violation (ADR-5)
# ===========================================================================


@pytest.mark.integration
def test_prometheus_counter_increments_on_violation(monkeypatch):
    """inc_verification_violations increments verification_violations_total counter.

    Skipped when prometheus_client is not installed.
    ADR-5: use REGISTRY.get_sample_value(name, labels), compute delta from baseline.
    """
    prometheus_client = pytest.importorskip("prometheus_client")
    REGISTRY = prometheus_client.REGISTRY

    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")
    monkeypatch.setenv("ENABLE_METRICS", "1")

    from langgraph_engine.metrics.exporter import inc_verification_violations

    label_set = {"level": "ERROR", "node": "test_prometheus_node"}

    # Baseline before increment
    baseline = REGISTRY.get_sample_value("verification_violations_total", label_set) or 0.0

    inc_verification_violations(level="ERROR", node="test_prometheus_node")

    after = REGISTRY.get_sample_value("verification_violations_total", label_set) or 0.0
    delta = after - baseline

    assert delta == pytest.approx(1.0), "Counter must increment by exactly 1.0 per inc_verification_violations call"


# ===========================================================================
# Test 5: OTel span invoked by verify_node decorator (ADR-4 / B.8)
# ===========================================================================


@pytest.mark.integration
def test_otel_span_invoked_by_verify_node(monkeypatch):
    """verify_node calls create_span exactly once per node execution (ADR-4).

    The tracing module is patched at its import path inside decorators.py
    (B.8 boundary: 'langgraph_engine.runtime_verification.decorators.create_span').
    This is the correct interception point because decorators.py imports
    create_span at module level from langgraph_engine.tracing.

    Skipped when opentelemetry-sdk is not installed -- guards via importorskip
    to confirm the package dependency chain is consistent.
    """
    pytest.importorskip("opentelemetry.sdk.trace")

    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")

    from unittest.mock import MagicMock

    span_mock = MagicMock()
    span_mock.__enter__ = MagicMock(return_value=span_mock)
    span_mock.__exit__ = MagicMock(return_value=False)

    with patch(
        "langgraph_engine.runtime_verification.decorators.create_span",
        return_value=span_mock,
    ) as mock_span_factory:
        from langgraph_engine.runtime_verification.contracts import NodeContract, PreconditionSpec
        from langgraph_engine.runtime_verification.decorators import verify_node

        contract = NodeContract(
            node_name="otel_integration_node",
            preconditions=[PreconditionSpec(key="user_message", expected_type=str, required=True)],
            postconditions=[],
            invariants=[],
        )

        @verify_node(contract)
        def _node(state):
            return {"output": "otel-ok"}

        _node({"user_message": "otel integration test"})

    # create_span must have been called by the decorator wrapper
    assert mock_span_factory.called, "verify_node must call create_span (ADR-4)"

    # Span name must be the verification span name from decorators.py
    call_args = mock_span_factory.call_args
    span_name = call_args[0][0] if call_args[0] else call_args.kwargs.get("name", "")
    assert (
        "runtime_verification" in span_name or "verify_node" in span_name
    ), "create_span must be called with span name containing 'runtime_verification'; " "got: '{}'".format(span_name)


# ===========================================================================
# Test 6: check_level_transition level1->level3 violation on missing session_synced
# ===========================================================================


@pytest.mark.integration
def test_level1_to_level3_transition_violation_when_session_not_synced(monkeypatch):
    """check_level_transition("level1", "level3", state) produces violation when
    session_synced key is missing -- confirms the invariant guard is active.
    """
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")

    from langgraph_engine.runtime_verification.verifier import RuntimeVerifier

    verifier = RuntimeVerifier.get_instance()

    # combined_complexity_score valid, but session_synced missing
    state = {"combined_complexity_score": 10}
    violations = verifier.check_level_transition("level1", "level3", state)

    assert len(violations) >= 1, "Missing session_synced must produce at least one transition guard violation"
    keys = [v["key"] for v in violations]
    assert "session_synced" in keys


# ===========================================================================
# Test 7: check_level_transition level1->level3 passes with valid state
# ===========================================================================


@pytest.mark.integration
def test_level1_to_level3_transition_passes_with_valid_state(monkeypatch):
    """check_level_transition("level1", "level3", state) returns [] for valid state."""
    monkeypatch.setenv("ENABLE_RUNTIME_VERIFICATION", "1")

    from langgraph_engine.runtime_verification.verifier import RuntimeVerifier

    verifier = RuntimeVerifier.get_instance()

    # Both required keys present with valid values
    state = {
        "combined_complexity_score": 12,
        "session_synced": True,
    }
    violations = verifier.check_level_transition("level1", "level3", state)

    assert violations == [], "Valid state must produce no transition guard violations"
