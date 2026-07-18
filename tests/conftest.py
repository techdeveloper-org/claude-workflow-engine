"""
Pytest configuration and shared fixtures
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Set env vars at module level so SecurityConfig() doesn't fail during collection
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-12345678901234567890")
os.environ.setdefault("DEVELOPMENT_MODE", "True")
os.environ.setdefault("TESTING", "True")

# Add project root (for langgraph_engine/) and src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables"""
    os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-12345678901234567890"
    os.environ["DEVELOPMENT_MODE"] = "True"
    os.environ["TESTING"] = "True"
    yield
    # Cleanup
    for key in ["SECRET_KEY", "DEVELOPMENT_MODE", "TESTING"]:
        if key in os.environ:
            del os.environ[key]


@pytest.fixture(autouse=True)
def _neutralize_llm_provider_chain(monkeypatch):
    """Stop unit tests from spawning a real ``claude`` CLI subprocess.

    ``llm_call()`` iterates ``langgraph_engine.llm_call._provider_chain`` and returns
    the first non-empty provider response, else None. On a machine where the claude
    CLI is on PATH, the ClaudeCLIProvider blocks on a real subprocess for up to the
    call's timeout; several pipeline nodes call ``llm_call()`` transitively (Step 10
    implementation, UML LLM enrichment, ...), which stalled the suite. Emptying the
    provider chain makes ``llm_call()`` return None instantly -- the same result CI
    sees with no provider configured -- so tests stay hermetic and fast. Tests that
    need a specific LLM response patch ``llm_call`` themselves and are unaffected.
    """
    # Import the submodule explicitly and patch the module object -- a dotted string
    # target would fail with AttributeError for a test that runs before anything else
    # has imported langgraph_engine.llm_call (getattr on the not-yet-bound submodule).
    import langgraph_engine.llm_call as _llm_call_mod

    monkeypatch.setattr(_llm_call_mod, "_provider_chain", [], raising=False)


@pytest.fixture
def mock_services():
    """Mock all service classes with flexible MagicMock"""
    mocks = {
        "memory_system_monitor": MagicMock(),
        "log_parser": MagicMock(),
        "anomaly_detector": MagicMock(),
        "predictive_analytics": MagicMock(),
        "bottleneck_analyzer": MagicMock(),
        "alert_sender": MagicMock(),
        "notification_integration": MagicMock(),
    }

    # Configure mock return values
    mocks["memory_system_monitor"].get_system_info.return_value = {"version": "2.5.0", "uptime": "5 days"}
    mocks["log_parser"].get_recent_logs.return_value = []
    mocks["anomaly_detector"].detect_anomalies.return_value = []
    mocks["predictive_analytics"].predict_future_usage.return_value = {}
    mocks["bottleneck_analyzer"].analyze_performance.return_value = {}

    return mocks


@pytest.fixture
def temp_widget_dir(tmp_path):
    """Create temporary widget directory structure"""
    widget_dir = tmp_path / "widgets"
    widget_dir.mkdir()

    # Create subdirectories
    (widget_dir / "community").mkdir()
    (widget_dir / "installed").mkdir()
    (widget_dir / "versions").mkdir()

    return widget_dir


@pytest.fixture
def mock_widget_data():
    """Mock widget data for testing"""
    return {
        "widget-1": {
            "id": "widget-1",
            "name": "Test Widget",
            "version": "1.0.0",
            "author": "Test Author",
            "description": "Test widget for testing",
        }
    }


def pytest_collection_modifyitems(config, items):
    """Mark integration tests as xfail (require full service setup)"""
    for item in items:
        if "test_integration.py" in item.nodeid:
            item.add_marker(
                pytest.mark.xfail(reason="Integration tests require full service initialization", strict=False)
            )
