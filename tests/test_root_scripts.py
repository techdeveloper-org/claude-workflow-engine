"""
Tests for key root scripts in the Claude Workflow Engine.

Covers:
- SessionIDGenerator (session-id-generator.py)
- metrics-emitter.py emit/read functions
- policy_tracking_helper.py record/read functions
- project_session.py get/read session functions
- ide_paths.py path resolution functions
- release.py bump_version / read_version
- PipelineBenchmark (performance_benchmarks.py)
- MetricsDashboard (metrics_dashboard.py)

Windows-safe: ASCII only (cp1252 compatible).
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root, scripts/, scripts/tools/, and hooks/ to sys.path so source
# modules are importable. Commit 69dab0f (v1.16.x) moved hook helpers from
# scripts/ to hooks/ at project root, and commit 4a835a6 moved dev tools from
# scripts/ to scripts/tools/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))


# ===========================================================================
# Helpers
# ===========================================================================


def _write_json(path, data):
    """Write dict as JSON to path."""
    path.write_text(json.dumps(data), encoding="utf-8")


# ===========================================================================
# SessionIDGenerator tests -- REMOVED
# ===========================================================================
# The Python-based session-id-generator.py was removed. Session ID generation
# is now handled by the shell script scripts/tools/session-id-generator.sh
# which has no unit-test surface (it is a one-liner invoked by hooks). See
# GitHub issue #203 for the purge history.


# ===========================================================================
# MetricsEmitter tests
# ===========================================================================


class TestMetricsEmitter:
    """Tests for metrics-emitter.py emit/read functions."""

    @pytest.fixture(autouse=True)
    def _import_module(self, tmp_path):
        """Import metrics_emitter with metrics file redirected to tmp_path."""
        self.metrics_file = tmp_path / "metrics.jsonl"

        # Patch _metrics_file() to return our tmp file
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "metrics_emitter",
            Path(__file__).resolve().parent.parent / "scripts" / "tools" / "metrics-emitter.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.mod = mod
        # Redirect the private helper
        mod._metrics_file = lambda: self.metrics_file
        self.tmp_path = tmp_path
        yield

    def _read_records(self):
        """Return list of parsed JSONL records from metrics file."""
        if not self.metrics_file.exists():
            return []
        lines = self.metrics_file.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def test_emit_hook_execution(self):
        """emit_hook_execution writes a record to the metrics file."""
        self.mod.emit_hook_execution(
            hook_name="test-hook.py",
            duration_ms=100,
            session_id="SESSION-TEST-001",
            exit_code=0,
        )
        records = self._read_records()
        assert len(records) >= 1
        rec = records[-1]
        assert rec["type"] == "hook_execution"
        assert rec["hook"] == "test-hook.py"
        assert rec["duration_ms"] == 100
        assert rec["exit_code"] == 0

    def test_read_metrics_after_emit(self):
        """Records emitted are readable as valid JSON lines."""
        self.mod.emit_hook_execution("hook-a.py", 50, session_id="S1")
        self.mod.emit_hook_execution("hook-b.py", 75, session_id="S2")
        records = self._read_records()
        assert len(records) == 2
        hooks = [r["hook"] for r in records]
        assert "hook-a.py" in hooks
        assert "hook-b.py" in hooks

    def test_emit_enforcement_event(self):
        """emit_enforcement_event writes an enforcement_event record."""
        self.mod.emit_enforcement_event(
            hook_name="pre-tool-enforcer.py",
            event_type="checkpoint_block",
            tool_name="Write",
            reason="checkpoint pending",
            blocked=True,
            session_id="SESSION-001",
        )
        records = self._read_records()
        rec = records[-1]
        assert rec["type"] == "enforcement_event"
        assert rec["blocked"] is True
        assert rec["event_type"] == "checkpoint_block"

    def test_emit_policy_step(self):
        """emit_policy_step writes a policy_step record with correct fields."""
        self.mod.emit_policy_step(
            step_name="LEVEL_3_STEP_4",
            level=3,
            passed=True,
            duration_ms=42,
            session_id="SESSION-001",
        )
        records = self._read_records()
        rec = records[-1]
        assert rec["type"] == "policy_step"
        assert rec["step"] == "LEVEL_3_STEP_4"
        assert rec["level"] == 3
        assert rec["passed"] is True

    def test_emit_never_raises(self):
        """Emit functions swallow exceptions and never raise to the caller."""
        # Force an I/O error by making the metrics file a directory
        self.mod._metrics_file = lambda: self.tmp_path  # directory, not file
        try:
            self.mod.emit_hook_execution("bad.py", 0)
        except Exception as exc:
            pytest.fail("emit_hook_execution raised unexpectedly: %s" % exc)


# ===========================================================================
# PolicyTrackingHelper tests
# ===========================================================================


class TestPolicyTrackingHelper:
    """Tests for policy_tracking_helper.py record/read functions."""

    @pytest.fixture(autouse=True)
    def _import_module(self, tmp_path):
        """Import policy_tracking_helper; redirect home to tmp_path."""
        self.tmp_path = tmp_path
        with patch("pathlib.Path.home", return_value=tmp_path):
            # Re-bind home in the module's namespace
            import importlib

            import policy_tracking_helper as pth

            importlib.reload(pth)
        self.pth = pth
        yield

    def _session_dir(self, session_id):
        return self.tmp_path / ".claude" / "memory" / "logs" / "sessions" / session_id

    def test_record_policy_execution_returns_true(self):
        """record_policy_execution returns True on success."""
        with patch("pathlib.Path.home", return_value=self.tmp_path):
            result = self.pth.record_policy_execution(
                session_id="SESSION-20260101-120000-ABCD",
                policy_name="test-policy",
                policy_script="test-policy.py",
                policy_type="Test",
                input_params={"key": "value"},
                output_results={"status": "OK"},
                decision="Test decision",
                duration_ms=10,
            )
        assert result is True

    def test_record_policy_execution_writes_file(self):
        """record_policy_execution persists a flow-trace.json file."""
        sid = "SESSION-20260101-120000-TEST"
        with patch("pathlib.Path.home", return_value=self.tmp_path):
            self.pth.record_policy_execution(
                session_id=sid,
                policy_name="my-policy",
                policy_script="my-policy.py",
                policy_type="Policy Script",
                input_params={},
                output_results={},
                decision="did something",
                duration_ms=5,
            )
        flow_trace_file = self._session_dir(sid) / "flow-trace.json"
        assert flow_trace_file.exists(), "flow-trace.json must be created"

    def test_read_policy_history_from_flow_trace(self):
        """Recorded policy execution is readable from flow-trace.json."""
        sid = "SESSION-20260101-120001-HIST"
        with patch("pathlib.Path.home", return_value=self.tmp_path):
            self.pth.record_policy_execution(
                session_id=sid,
                policy_name="history-policy",
                policy_script="history-policy.py",
                policy_type="Utility Hook",
                input_params={"x": 1},
                output_results={"y": 2},
                decision="recorded",
                duration_ms=20,
            )
        flow_trace_file = self._session_dir(sid) / "flow-trace.json"
        data = json.loads(flow_trace_file.read_text(encoding="utf-8"))
        policies = data.get("all_policies_executed", [])
        assert len(policies) == 1
        assert policies[0]["policy_name"] == "history-policy"

    def test_record_sub_operation_returns_dict(self):
        """record_sub_operation returns a dict with expected keys."""
        result = self.pth.record_sub_operation(
            session_id="SESSION-TEST",
            policy_name="parent-policy",
            operation_name="check_something",
            input_params={"required": "3.8+"},
            output_results={"found": True},
            duration_ms=5,
        )
        assert isinstance(result, dict)
        assert result["operation"] == "check_something"
        assert result["duration_ms"] == 5

    def test_get_session_id_returns_unknown_when_missing(self, tmp_path):
        """get_session_id returns 'unknown' when session file is absent."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            sid = self.pth.get_session_id()
        assert sid == "unknown"


# ===========================================================================
# ProjectSession tests
# ===========================================================================


class TestProjectSession:
    """Tests for project_session.py get/read session functions."""

    @pytest.fixture(autouse=True)
    def _import_module(self, tmp_path):
        """Import project_session; redirect home to tmp_path."""
        self.tmp_path = tmp_path
        import importlib

        import project_session as ps

        with patch("pathlib.Path.home", return_value=tmp_path):
            importlib.reload(ps)
        self.ps = ps
        yield

    def test_get_project_session_file_returns_path(self):
        """get_project_session_file returns a Path instance."""
        with patch("pathlib.Path.home", return_value=self.tmp_path):
            result = self.ps.get_project_session_file()
        assert isinstance(result, Path)

    def test_get_project_session_file_name(self):
        """get_project_session_file path ends with .current-session.json."""
        with patch("pathlib.Path.home", return_value=self.tmp_path):
            result = self.ps.get_project_session_file()
        assert result.name == ".current-session.json"

    def test_read_session_id_from_mock_file(self, tmp_path):
        """read_session_id returns the stored session ID from a JSON file."""
        session_file = tmp_path / ".claude" / "memory" / ".current-session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(session_file, {"current_session_id": "SESSION-20260101-080000-WXYZ"})
        with patch("pathlib.Path.home", return_value=tmp_path):
            import importlib

            importlib.reload(self.ps)
            sid = self.ps.read_session_id()
        assert sid == "SESSION-20260101-080000-WXYZ"

    def test_read_session_id_returns_empty_when_missing(self, tmp_path):
        """read_session_id returns empty string when session file is absent."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            import importlib

            importlib.reload(self.ps)
            sid = self.ps.read_session_id()
        assert sid == ""

    def test_read_session_id_returns_empty_for_non_session_prefix(self, tmp_path):
        """read_session_id returns empty for IDs not starting with SESSION-."""
        session_file = tmp_path / ".claude" / "memory" / ".current-session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(session_file, {"current_session_id": "TASK-20260101-080000-WXYZ"})
        with patch("pathlib.Path.home", return_value=tmp_path):
            import importlib

            importlib.reload(self.ps)
            sid = self.ps.read_session_id()
        assert sid == ""


# ===========================================================================
# IdePaths tests
# ===========================================================================


class TestIdePaths:
    """Tests for ide_paths.py path resolution functions."""

    @pytest.fixture(autouse=True)
    def _import_module(self, tmp_path):
        """Import ide_paths in standalone mode (no IDE env vars)."""
        self.tmp_path = tmp_path
        # Ensure IDE env vars are absent
        env_patch = {
            "CLAUDE_IDE_INSTALL_DIR": "",
            "CLAUDE_IDE_DATA_DIR": "",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            import importlib

            import ide_paths as ip

            importlib.reload(ip)
            self.ip = ip
        yield

    def test_get_claude_dir_returns_path(self):
        """get_install_base returns a Path instance."""
        result = self.ip.get_install_base()
        assert isinstance(result, Path)

    def test_get_install_base_standalone_mode(self):
        """In standalone mode, install base is ~/.claude."""
        result = self.ip.get_install_base()
        assert result.name == ".claude", "Standalone install base must end in .claude, got %s" % result

    def test_get_data_base_standalone_mode(self):
        """In standalone mode, data base is ~/.claude."""
        result = self.ip.get_data_base()
        assert result.name == ".claude"

    def test_is_ide_mode_false_in_standalone(self):
        """is_ide_mode returns False when CLAUDE_IDE_INSTALL_DIR is not set."""
        assert self.ip.is_ide_mode() is False

    def test_is_ide_mode_true_with_env_var(self, tmp_path):
        """is_ide_mode returns True when CLAUDE_IDE_INSTALL_DIR is set."""
        with patch.dict(os.environ, {"CLAUDE_IDE_INSTALL_DIR": str(tmp_path)}):
            import importlib

            import ide_paths as ip2

            importlib.reload(ip2)
            assert ip2.is_ide_mode() is True

    def test_memory_base_is_under_data_base(self):
        """MEMORY_BASE is a subdirectory of the data base."""
        data_base = self.ip.get_data_base()
        assert str(self.ip.MEMORY_BASE).startswith(str(data_base))


# ===========================================================================
# Release tests
# ===========================================================================


class TestRelease:
    """Tests for release.py bump_version and read_version."""

    @pytest.fixture(autouse=True)
    def _import_module(self, tmp_path):
        """Import release module with PROJECT_ROOT redirected to tmp_path."""
        self.tmp_path = tmp_path
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "release",
            Path(__file__).resolve().parent.parent / "scripts" / "tools" / "release.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.mod = mod
        # Redirect VERSION_FILE to tmp_path so tests do not touch production
        self.version_file = tmp_path / "VERSION"
        mod.VERSION_FILE = self.version_file
        yield

    def test_read_version(self):
        """read_version reads the version string from VERSION file."""
        self.version_file.write_text("7.5.0\n", encoding="utf-8")
        assert self.mod.read_version() == "7.5.0"

    def test_read_version_missing_file_exits(self):
        """read_version calls sys.exit(1) when VERSION file is absent."""
        with pytest.raises(SystemExit) as exc_info:
            self.mod.read_version()
        assert exc_info.value.code == 1

    def test_bump_version_patch(self):
        """bump_version with 'patch' increments the patch component."""
        result = self.mod.bump_version("7.5.0", "patch")
        assert result == "7.5.1"

    def test_bump_version_minor(self):
        """bump_version with 'minor' increments minor and resets patch."""
        result = self.mod.bump_version("7.5.0", "minor")
        assert result == "7.6.0"

    def test_bump_version_major(self):
        """bump_version with 'major' increments major and resets minor/patch."""
        result = self.mod.bump_version("7.5.0", "major")
        assert result == "8.0.0"

    def test_bump_version_invalid_format_exits(self):
        """bump_version calls sys.exit(1) for a non-X.Y.Z version string."""
        with pytest.raises(SystemExit) as exc_info:
            self.mod.bump_version("notaversion", "patch")
        assert exc_info.value.code == 1

    def test_bump_version_invalid_type_exits(self):
        """bump_version calls sys.exit(1) for an unknown bump type."""
        with pytest.raises(SystemExit) as exc_info:
            self.mod.bump_version("7.5.0", "invalid_type")
        assert exc_info.value.code == 1


# ===========================================================================
# PipelineBenchmark tests
# ===========================================================================


class TestPipelineBenchmark:
    """Tests for PipelineBenchmark in performance_benchmarks.py."""

    @pytest.fixture(autouse=True)
    def _import_module(self, tmp_path):
        """Import PipelineBenchmark with benchmark_dir in tmp_path."""
        self.tmp_path = tmp_path
        sys.path.insert(
            0,
            str(Path(__file__).resolve().parent.parent / "langgraph_engine"),
        )
        try:
            import importlib

            import performance_benchmarks as pb

            importlib.reload(pb)
            self.pb = pb
        finally:
            pass
        yield

    def _make_bench(self):
        return self.pb.PipelineBenchmark(
            session_id="TEST-SESSION",
            benchmark_dir=self.tmp_path,
        )

    def test_record_step_stores_data(self):
        """record_step stores step data in the steps dict."""
        bench = self._make_bench()
        bench.record_step(step=3, duration=0.5, status="SUCCESS")
        assert 3 in bench.steps
        assert bench.steps[3]["status"] == "SUCCESS"
        assert bench.steps[3]["duration_ms"] == pytest.approx(500.0, abs=1)

    def test_record_step_duration_ms(self):
        """duration is converted to milliseconds correctly."""
        bench = self._make_bench()
        bench.record_step(step=0, duration=1.0, status="SUCCESS")
        assert bench.steps[0]["duration_ms"] == pytest.approx(1000.0, abs=1)

    def test_get_summary_returns_dict(self):
        """get_summary returns a dict with required aggregate keys."""
        bench = self._make_bench()
        bench.record_step(step=0, duration=1.0, status="SUCCESS")
        bench.record_step(step=1, duration=0.5, status="SUCCESS")
        summary = bench.get_summary()
        assert isinstance(summary, dict)
        for key in (
            "step_count",
            "success_count",
            "success_rate",
            "avg_step_ms",
            "max_step_ms",
            "total_llm_calls",
        ):
            assert key in summary, "Missing key: %s" % key

    def test_get_summary_step_count(self):
        """get_summary step_count matches the number of recorded steps."""
        bench = self._make_bench()
        bench.record_step(step=0, duration=0.1)
        bench.record_step(step=1, duration=0.2)
        bench.record_step(step=2, duration=0.3)
        summary = bench.get_summary()
        assert summary["step_count"] == 3

    def test_format_summary_table_returns_string(self):
        """format_summary_table returns a non-empty string."""
        bench = self._make_bench()
        bench.record_step(step=0, duration=0.2, status="SUCCESS")
        table = bench.format_summary_table()
        assert isinstance(table, str)
        assert len(table) > 0

    def test_format_summary_table_contains_header(self):
        """format_summary_table output contains the expected header text."""
        bench = self._make_bench()
        bench.record_step(step=5, duration=0.4, status="SUCCESS")
        table = bench.format_summary_table()
        assert "PIPELINE PERFORMANCE SUMMARY" in table

    def test_save_benchmark_writes_json(self):
        """save() writes a benchmark JSON file to benchmark_dir."""
        bench = self._make_bench()
        bench.record_step(step=0, duration=0.1, status="SUCCESS")
        saved_path = bench.save()
        assert saved_path is not None
        path_obj = Path(saved_path)
        assert path_obj.exists()
        data = json.loads(path_obj.read_text(encoding="utf-8"))
        assert data["session_id"] == "TEST-SESSION"

    def test_load_history_returns_list(self):
        """load_history returns a list (empty or populated)."""
        bench = self._make_bench()
        bench.record_step(step=0, duration=0.1, status="SUCCESS")
        bench.save()
        history = self.pb.PipelineBenchmark.load_history(benchmark_dir=self.tmp_path)
        assert isinstance(history, list)
        assert len(history) >= 1

    def test_load_history_empty_for_missing_dir(self, tmp_path):
        """load_history returns empty list when directory does not exist."""
        missing = tmp_path / "nonexistent"
        history = self.pb.PipelineBenchmark.load_history(benchmark_dir=missing)
        assert history == []


# ===========================================================================
# MetricsDashboard tests
# ===========================================================================


class TestMetricsDashboard:
    """Tests for MetricsDashboard in metrics_dashboard.py."""

    @pytest.fixture(autouse=True)
    def _import_module(self, tmp_path):
        """Import MetricsDashboard with dirs in tmp_path."""
        self.tmp_path = tmp_path
        sys.path.insert(
            0,
            str(Path(__file__).resolve().parent.parent / "langgraph_engine"),
        )
        import importlib

        import metrics_dashboard as md

        importlib.reload(md)
        self.md = md
        yield

    def _make_dashboard(self):
        return self.md.MetricsDashboard(
            benchmark_dir=self.tmp_path,
            output_dir=self.tmp_path,
        )

    def _write_benchmark(self, filename, data):
        path = self.tmp_path / filename
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def test_aggregate_empty_returns_zero_run_count(self):
        """aggregate returns run_count=0 when no benchmark files exist."""
        dashboard = self._make_dashboard()
        result = dashboard.aggregate(benchmarks=[])
        assert result["run_count"] == 0

    def test_aggregate_with_single_run(self):
        """aggregate correctly aggregates a single benchmark run."""
        benchmarks = [
            {
                "session_id": "S1",
                "total_time_s": 12.5,
                "total_llm_calls": 3,
                "steps": {
                    "0": {
                        "step": 0,
                        "duration_ms": 200.0,
                        "status": "SUCCESS",
                    },
                    "1": {
                        "step": 1,
                        "duration_ms": 300.0,
                        "status": "SUCCESS",
                    },
                },
            }
        ]
        dashboard = self._make_dashboard()
        result = dashboard.aggregate(benchmarks=benchmarks)
        assert result["run_count"] == 1
        assert result["avg_total_time_s"] == pytest.approx(12.5, abs=0.1)
        assert "per_step" in result
        per_step = result["per_step"]
        assert 0 in per_step
        assert per_step[0]["avg_duration_ms"] == pytest.approx(200.0, abs=0.5)
        assert per_step[0]["success_rate"] == pytest.approx(100.0, abs=0.1)

    def test_aggregate_with_multiple_runs(self):
        """aggregate combines multiple runs into averaged stats."""
        benchmarks = [
            {
                "total_time_s": 10.0,
                "total_llm_calls": 2,
                "steps": {
                    "0": {
                        "step": 0,
                        "duration_ms": 100.0,
                        "status": "SUCCESS",
                    }
                },
            },
            {
                "total_time_s": 20.0,
                "total_llm_calls": 4,
                "steps": {
                    "0": {
                        "step": 0,
                        "duration_ms": 200.0,
                        "status": "SUCCESS",
                    }
                },
            },
        ]
        dashboard = self._make_dashboard()
        result = dashboard.aggregate(benchmarks=benchmarks)
        assert result["run_count"] == 2
        assert result["avg_total_time_s"] == pytest.approx(15.0, abs=0.1)
        assert result["per_step"][0]["avg_duration_ms"] == pytest.approx(150.0, abs=0.5)

    def test_aggregate_success_rate_calculation(self):
        """overall_success_rate is computed correctly across mixed statuses."""
        benchmarks = [
            {
                "total_time_s": 5.0,
                "total_llm_calls": 1,
                "steps": {
                    "0": {
                        "step": 0,
                        "duration_ms": 50.0,
                        "status": "SUCCESS",
                    },
                    "1": {
                        "step": 1,
                        "duration_ms": 50.0,
                        "status": "FAILED",
                    },
                },
            }
        ]
        dashboard = self._make_dashboard()
        result = dashboard.aggregate(benchmarks=benchmarks)
        assert result["overall_success_rate"] == pytest.approx(50.0, abs=0.1)

    def test_save_summary_creates_file(self):
        """save_summary writes metrics-summary.json to output_dir."""
        dashboard = self._make_dashboard()
        metrics = dashboard.aggregate(benchmarks=[])
        saved_path = dashboard.save_summary(metrics=metrics)
        assert saved_path is not None
        path_obj = Path(saved_path)
        assert path_obj.name == "metrics-summary.json"
        assert path_obj.exists()

    def test_save_summary_content_is_valid_json(self):
        """metrics-summary.json contains valid JSON after save_summary."""
        dashboard = self._make_dashboard()
        metrics = {"run_count": 0, "message": "test"}
        saved_path = dashboard.save_summary(metrics=metrics)
        data = json.loads(Path(saved_path).read_text(encoding="utf-8"))
        assert data["run_count"] == 0

    def test_format_report_empty_data_message(self):
        """format_report for empty data returns a descriptive string."""
        dashboard = self._make_dashboard()
        report = dashboard.format_report(metrics={"run_count": 0})
        assert isinstance(report, str)
        assert len(report) > 0

    def test_format_report_with_data_contains_header(self):
        """format_report with run data contains the dashboard header."""
        benchmarks = [
            {
                "total_time_s": 8.0,
                "total_llm_calls": 2,
                "steps": {
                    "0": {
                        "step": 0,
                        "duration_ms": 120.0,
                        "status": "SUCCESS",
                    }
                },
            }
        ]
        dashboard = self._make_dashboard()
        metrics = dashboard.aggregate(benchmarks=benchmarks)
        report = dashboard.format_report(metrics=metrics)
        assert "PIPELINE METRICS DASHBOARD" in report

    def test_format_report_with_data_shows_run_count(self):
        """format_report includes run count in the formatted text."""
        benchmarks = [
            {
                "total_time_s": 5.0,
                "total_llm_calls": 1,
                "steps": {
                    "0": {
                        "step": 0,
                        "duration_ms": 80.0,
                        "status": "SUCCESS",
                    }
                },
            }
        ]
        dashboard = self._make_dashboard()
        metrics = dashboard.aggregate(benchmarks=benchmarks)
        report = dashboard.format_report(metrics=metrics)
        assert "1" in report  # run count appears somewhere in report
