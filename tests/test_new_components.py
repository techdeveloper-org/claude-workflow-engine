# -*- coding: utf-8 -*-
"""
test_new_components.py - Tests for new components added to the Claude Workflow Engine.

Covers:
  1. Code Graph Analyzer (scripts/architecture/03-execution-system/00-code-graph-analysis/)
  2. Level 1 Sync System scripts (scripts/architecture/01-sync-system/)
  3. Pre-tool Enforcer Level 1 / Level 2 blocking functions (scripts/pre-tool-enforcer.py)

All tests are designed to pass without external dependencies (networkx, etc.).
Uses importlib.util for dynamic imports since the scripts are not proper packages.
ASCII-only source (cp1252-safe for Windows). UTF-8 encoding.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SYNC_SYSTEM_DIR = REPO_ROOT / "scripts" / "architecture" / "01-sync-system"
CODE_GRAPH_DIR = REPO_ROOT / "scripts" / "architecture" / "03-execution-system" / "00-code-graph-analysis"
SCRIPTS_DIR = REPO_ROOT / "scripts"
HOOKS_DIR = REPO_ROOT / "hooks"


def _load_module(script_path: Path, module_name: str) -> Any:
    """Dynamically load a Python script as a module by absolute path."""
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None, "Could not create module spec for {}".format(script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, "Spec has no loader for {}".format(script_path)
    spec.loader.exec_module(module)
    return module


# ===========================================================================
# 1. Code Graph Analyzer
# ===========================================================================


class TestCodeGraphAnalyzerImport:
    """Can import the code-graph-analyzer and verify the HAS_NETWORKX flag."""

    def test_code_graph_analyzer_import(self):
        """test_code_graph_analyzer_import: module loads and HAS_NETWORKX flag is defined."""
        script_path = CODE_GRAPH_DIR / "code-graph-analyzer.py"
        assert script_path.exists(), "code-graph-analyzer.py not found at {}".format(script_path)

        mod = _load_module(script_path, "code_graph_analyzer_test_import")
        assert hasattr(mod, "HAS_NETWORKX"), "HAS_NETWORKX flag not found in module"
        # The value must be a boolean regardless of whether networkx is installed
        assert isinstance(mod.HAS_NETWORKX, bool)


class TestCodeGraphAnalyzerInterface:
    """CodeGraphAnalyzer class exposes the expected interface."""

    def test_code_graph_analyzer_interface(self, tmp_path):
        """test_code_graph_analyzer_interface: run(), save(), metrics, files attributes exist."""
        script_path = CODE_GRAPH_DIR / "code-graph-analyzer.py"
        mod = _load_module(script_path, "code_graph_analyzer_test_interface")

        analyzer = mod.CodeGraphAnalyzer(str(tmp_path), tech_stack=["python"], session_id="test-iface")

        # Attribute presence checks (before run() is called)
        assert hasattr(analyzer, "run"), "CodeGraphAnalyzer missing run() method"
        assert hasattr(analyzer, "save"), "CodeGraphAnalyzer missing save() method"
        assert hasattr(analyzer, "metrics"), "CodeGraphAnalyzer missing metrics attribute"
        assert hasattr(analyzer, "files"), "CodeGraphAnalyzer missing files attribute"

        # metrics and files must be dict and list respectively after construction
        assert isinstance(analyzer.metrics, dict)
        assert isinstance(analyzer.files, list)


class TestCodeGraphAnalyzerGracefulFailure:
    """CodeGraphAnalyzer returns 0 on an invalid project path."""

    def test_code_graph_analyzer_graceful_failure(self, tmp_path):
        """test_code_graph_analyzer_graceful_failure: run() returns 0 for non-existent path."""
        script_path = CODE_GRAPH_DIR / "code-graph-analyzer.py"
        mod = _load_module(script_path, "code_graph_analyzer_test_failure")

        non_existent = tmp_path / "does_not_exist_xyz"
        analyzer = mod.CodeGraphAnalyzer(str(non_existent))
        result = analyzer.run()

        # Must not raise; must return 0 when the path does not exist
        assert result == 0, "Expected 0 for missing project path, got {}".format(result)


class TestCodeGraphAnalyzerScoringRange:
    """score_from_metrics always returns a value in the 0-25 range."""

    def test_code_graph_analyzer_scoring_range(self):
        """test_code_graph_analyzer_scoring_range: score_from_metrics output is 0-25."""
        script_path = CODE_GRAPH_DIR / "code-graph-analyzer.py"
        mod = _load_module(script_path, "code_graph_analyzer_test_scoring")

        # Test with all-zero metrics (degenerate case)
        zero_metrics: Dict[str, Any] = {
            "total_nodes": 0,
            "density": 0.0,
            "max_betweenness": 0.0,
            "avg_fan_out": 0.0,
            "longest_path": 0,
        }
        score_zero = mod.score_from_metrics(zero_metrics)
        assert 0 <= score_zero <= 25, "Score {} out of 0-25 range for zero metrics".format(score_zero)

        # Test with maximum-stress metrics
        max_metrics: Dict[str, Any] = {
            "total_nodes": 9999,
            "density": 1.0,
            "max_betweenness": 1.0,
            "avg_fan_out": 100.0,
            "longest_path": 100,
        }
        score_max = mod.score_from_metrics(max_metrics)
        assert 0 <= score_max <= 25, "Score {} out of 0-25 range for max metrics".format(score_max)

        # Test with mid-range metrics
        mid_metrics: Dict[str, Any] = {
            "total_nodes": 30,
            "density": 0.08,
            "max_betweenness": 0.15,
            "avg_fan_out": 4.0,
            "longest_path": 4,
        }
        score_mid = mod.score_from_metrics(mid_metrics)
        assert 0 <= score_mid <= 25, "Score {} out of 0-25 range for mid metrics".format(score_mid)


# ===========================================================================
# 2. Level 1 Sync System Scripts
# ===========================================================================


# ---------------------------------------------------------------------------
# session-pruner.py
# ---------------------------------------------------------------------------


class TestSessionPrunerImport:
    """Can import the prune_sessions function from session-pruner.py."""

    def test_session_pruner_import(self):
        """test_session_pruner_import: prune_sessions is importable and callable."""
        script_path = SYNC_SYSTEM_DIR / "session-pruner.py"
        assert script_path.exists(), "session-pruner.py not found at {}".format(script_path)

        mod = _load_module(script_path, "session_pruner_test_import")
        assert hasattr(mod, "prune_sessions"), "prune_sessions function not found in module"
        assert callable(mod.prune_sessions)


class TestSessionPrunerEmptyDir:
    """prune_sessions handles an empty directory gracefully."""

    def test_session_pruner_empty_dir(self, tmp_path):
        """test_session_pruner_empty_dir: empty dir returns valid result dict without error."""
        script_path = SYNC_SYSTEM_DIR / "session-pruner.py"
        mod = _load_module(script_path, "session_pruner_test_empty")

        result = mod.prune_sessions(tmp_path)

        # Must return a dict with the expected keys
        assert isinstance(result, dict)
        assert "total_sessions" in result
        assert "kept_active" in result
        assert "archived" in result
        assert "errors" in result

        # Empty directory: no sessions found, no errors
        assert result["total_sessions"] == 0
        assert result["archived"] == 0
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# context-monitor.py
# ---------------------------------------------------------------------------


class TestContextMonitorImport:
    """Can import the estimate_context_usage function from context-monitor.py."""

    def test_context_monitor_import(self):
        """test_context_monitor_import: estimate_context_usage is importable and callable."""
        script_path = SYNC_SYSTEM_DIR / "context-monitor.py"
        assert script_path.exists(), "context-monitor.py not found at {}".format(script_path)

        mod = _load_module(script_path, "context_monitor_test_import")
        assert hasattr(mod, "estimate_context_usage"), "estimate_context_usage not found in module"
        assert callable(mod.estimate_context_usage)


class TestContextMonitorEmptySession:
    """estimate_context_usage returns a valid dict with 0 tokens for an empty directory."""

    def test_context_monitor_empty_session(self, tmp_path):
        """test_context_monitor_empty_session: returns valid dict with 0 tokens for empty dir."""
        script_path = SYNC_SYSTEM_DIR / "context-monitor.py"
        mod = _load_module(script_path, "context_monitor_test_empty")

        info = mod.estimate_context_usage(session_dir=tmp_path)

        # Must return a dict
        assert isinstance(info, dict)

        # Required keys
        required_keys = [
            "estimated_tokens",
            "max_tokens",
            "usable_tokens",
            "percentage",
            "percentage_display",
            "threshold_zone",
            "recommendation",
            "files_analysed",
            "session_dir",
            "timestamp",
        ]
        for key in required_keys:
            assert key in info, "Missing key '{}' in estimate_context_usage result".format(key)

        # Empty directory: 0 tokens, 0 files
        assert info["estimated_tokens"] == 0
        assert info["files_analysed"] == 0

        # Percentage must be 0.0 for empty dir
        assert info["percentage"] == 0.0

        # Zone must be a string (GREEN for 0% usage)
        assert isinstance(info["threshold_zone"], str)
        assert info["threshold_zone"] == "GREEN"


# ---------------------------------------------------------------------------
# pattern-detector.py
# ---------------------------------------------------------------------------


class TestPatternDetectorImport:
    """Can import the detect_patterns function from pattern-detector.py."""

    def test_pattern_detector_import(self):
        """test_pattern_detector_import: detect_patterns is importable and callable."""
        script_path = SYNC_SYSTEM_DIR / "pattern-detector.py"
        assert script_path.exists(), "pattern-detector.py not found at {}".format(script_path)

        mod = _load_module(script_path, "pattern_detector_test_import")
        assert hasattr(mod, "detect_patterns"), "detect_patterns not found in module"
        assert callable(mod.detect_patterns)


class TestPatternDetectorCurrentProject:
    """detect_patterns identifies 'python' pattern in the current project."""

    def test_pattern_detector_current_project(self):
        """test_pattern_detector_current_project: detects 'python' for this Python project."""
        script_path = SYNC_SYSTEM_DIR / "pattern-detector.py"
        mod = _load_module(script_path, "pattern_detector_test_project")

        # Point the detector at the repo root which has pyproject.toml / requirements files
        patterns = mod.detect_patterns(REPO_ROOT)

        assert isinstance(patterns, list)
        # The project has Python files and/or pyproject.toml/requirements.txt
        assert "python" in patterns, "Expected 'python' in detected patterns for this Python project, got: {}".format(
            patterns
        )


# ---------------------------------------------------------------------------
# preference-tracker.py
# ---------------------------------------------------------------------------


class TestPreferenceTrackerImport:
    """Can import the track_preferences function from preference-tracker.py."""

    def test_preference_tracker_import(self):
        """test_preference_tracker_import: track_preferences is importable and callable."""
        script_path = SYNC_SYSTEM_DIR / "preference-tracker.py"
        assert script_path.exists(), "preference-tracker.py not found at {}".format(script_path)

        mod = _load_module(script_path, "preference_tracker_test_import")
        assert hasattr(mod, "track_preferences"), "track_preferences not found in module"
        assert callable(mod.track_preferences)


class TestPreferenceTrackerEmpty:
    """track_preferences returns a valid dict for an empty sessions directory."""

    def test_preference_tracker_empty(self, tmp_path):
        """test_preference_tracker_empty: returns valid dict for empty sessions dir."""
        script_path = SYNC_SYSTEM_DIR / "preference-tracker.py"
        mod = _load_module(script_path, "preference_tracker_test_empty")

        result = mod.track_preferences(sessions_dir=tmp_path)

        assert isinstance(result, dict)

        # Required keys must be present
        required_keys = [
            "preferred_skills",
            "preferred_agents",
            "common_task_types",
            "sessions_analysed",
            "sessions_dir",
            "timestamp",
            "learning_threshold",
        ]
        for key in required_keys:
            assert key in result, "Missing key '{}' in track_preferences result".format(key)

        # Empty dir: no sessions analysed, all lists empty
        assert result["sessions_analysed"] == 0
        assert result["preferred_skills"] == []
        assert result["preferred_agents"] == []
        assert result["common_task_types"] == []

        # learning_threshold must be a positive integer
        assert isinstance(result["learning_threshold"], int)
        assert result["learning_threshold"] > 0


# ===========================================================================
# 3. Pre-tool Enforcer Level 1 / Level 2 Blocking
# ===========================================================================


def _load_pre_tool_enforcer():
    """Load pre-tool-enforcer.py as a module (cached in sys.modules under test key)."""
    module_key = "_pre_tool_enforcer_under_test"
    if module_key in sys.modules:
        return sys.modules[module_key]

    script_path = HOOKS_DIR / "pre-tool-enforcer.py"
    assert script_path.exists(), "pre-tool-enforcer.py not found at {}".format(script_path)
    mod = _load_module(script_path, module_key)
    sys.modules[module_key] = mod
    return mod


class TestLevel1CheckReturnsTuple:
    """check_level1_sync_complete returns a (hints, blocks) tuple."""

    def test_level1_check_returns_tuple(self):
        """test_level1_check_returns_tuple: returns (hints, blocks) tuple for any tool."""
        mod = _load_pre_tool_enforcer()
        result = mod.check_level1_sync_complete("Read")
        assert isinstance(result, tuple), "Expected tuple, got {}".format(type(result))
        assert len(result) == 2, "Expected 2-element tuple, got length {}".format(len(result))
        hints, blocks = result
        assert isinstance(hints, list), "hints must be a list"
        assert isinstance(blocks, list), "blocks must be a list"


# NOTE: TestLevel2CheckReturnsTuple removed in v1.16.0 -- Level 2 standards
# enforcement was purged (commit 937c9ee). Level 2 policies are now data-only
# files under policies/02-standards-system/ and no longer have a pipeline
# enforcer. See GitHub issue #206 for the purge history.


class TestLevel1CheckNoTrace:
    """check_level1_sync_complete fails open when no flow-trace exists."""

    def test_level1_check_no_trace(self, monkeypatch):
        """test_level1_check_no_trace: returns empty (hints, blocks) when flow-trace unavailable."""
        mod = _load_pre_tool_enforcer()

        # Simulate: no session ID is available (flow-trace cannot be located)
        monkeypatch.setattr(mod, "get_current_session_id", lambda: "")

        hints, blocks = mod.check_level1_sync_complete("Write")

        # Fail-open: when session ID is missing, nothing should be blocked
        assert blocks == [], "Expected no blocks when session ID is empty, got: {}".format(blocks)

    def test_level1_check_no_trace_via_none_trace(self, monkeypatch):
        """check_level1_sync_complete with valid session but None trace still fails open."""
        mod = _load_pre_tool_enforcer()

        # Simulate a session ID but no readable flow-trace
        monkeypatch.setattr(mod, "get_current_session_id", lambda: "test-session-001")
        monkeypatch.setattr(mod, "_load_raw_flow_trace", lambda: None)

        hints, blocks = mod.check_level1_sync_complete("Write")

        # Fail-open: None trace must not block
        assert blocks == [], "Expected no blocks when flow-trace is None, got: {}".format(blocks)


# NOTE: TestLevel2CheckNoTrace removed in v1.16.0 -- Level 2 standards
# enforcement was purged (commit 937c9ee). See GitHub issue #206.
