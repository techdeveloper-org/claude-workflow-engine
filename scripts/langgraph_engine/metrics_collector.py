"""
Metrics Collector - Real-time execution metrics for pipeline steps.

Records:
- Per-step duration, status, token usage
- Files created/modified/deleted per step
- Error occurrences and recovery actions
- Session-level summary statistics

Metrics are written to:
    ~/.claude/logs/sessions/{session_id}/metrics.json

Usage:
    from .metrics_collector import MetricsCollector

    metrics = MetricsCollector(session_id)
    metrics.record_step(step=3, duration=1.4, status="SUCCESS", tokens=820)
    metrics.record_error(step=3, error_type="NetworkError", recovery="RetryWithBackoff")
    metrics.record_files_modified(step=3, files=["src/app.py", "tests/test_app.py"])

    summary = metrics.summary()
    print(summary)
"""

import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"
STATUS_PARTIAL = "PARTIAL"


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Collect and persist execution metrics across all pipeline steps."""

    def __init__(self, session_id: str, base_log_dir: str = "~/.claude/logs"):
        """
        Initialise metrics collector.

        Args:
            session_id:   Unique session identifier.
            base_log_dir: Base directory for log files.
        """
        self.session_id = session_id
        session_dir = Path(base_log_dir).expanduser() / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        self.metrics_file = session_dir / "metrics.json"
        self._start_time = time.time()

        # In-memory store
        # Key: "step_{n}"  Value: step-level metrics dict
        self._step_metrics: Dict[str, Dict[str, Any]] = {}
        self._error_records: List[Dict[str, Any]] = []
        # Aggregate set of all files touched across all steps
        self._all_files_modified: Set[str] = set()

        # Load existing data if we are resuming
        self._load()

    # ------------------------------------------------------------------
    # Core recording methods
    # ------------------------------------------------------------------

    def record_step(
        self,
        step: int,
        duration: float,
        status: str,
        tokens: int = 0,
        model: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record metrics for a completed step.

        Args:
            step:     Step number (0-14).
            duration: Execution time in seconds.
            status:   One of SUCCESS / FAILED / SKIPPED / PARTIAL.
            tokens:   LLM tokens consumed during the step (0 if unknown).
            model:    Model name used (e.g. "claude-sonnet-4-6").
            extra:    Additional key-value pairs to store with the metric.
        """
        key = f"step_{step}"
        entry: Dict[str, Any] = {
            "step": step,
            "duration_seconds": round(duration, 3),
            "status": status,
            "tokens_used": tokens,
            "timestamp": datetime.now().isoformat(),
        }
        if model:
            entry["model"] = model
        if extra:
            entry.update(extra)

        self._step_metrics[key] = entry
        self._save()

        icon = "OK" if status == STATUS_SUCCESS else status
        logger.info(f"[Metrics] Step {step:02d} | {icon} | {duration:.2f}s | {tokens} tokens")

    def record_files_modified(
        self,
        step: int,
        files: List[str],
        operation: str = "modified",
    ) -> None:
        """
        Record files that were created, modified, or deleted during a step.

        Args:
            step:      Step number where files were changed.
            files:     List of file paths (absolute or relative).
            operation: One of "created", "modified", "deleted" (default "modified").
        """
        if not files:
            return

        key = f"step_{step}"
        step_entry = self._step_metrics.setdefault(key, {"step": step})
        file_ops = step_entry.setdefault("files_modified", [])

        timestamp = datetime.now().isoformat()
        for filepath in files:
            entry: Dict[str, Any] = {
                "path": filepath,
                "operation": operation,
                "timestamp": timestamp,
            }
            file_ops.append(entry)
            self._all_files_modified.add(filepath)

        self._save()
        logger.info(f"[Metrics] Step {step:02d} | {operation} {len(files)} file(s)")

    def record_error(
        self,
        step: int,
        error_type: str,
        recovery: str,
        message: Optional[str] = None,
    ) -> None:
        """
        Record an error occurrence.

        Args:
            step:       Step where the error occurred.
            error_type: Short error class name (e.g. "NetworkError").
            recovery:   Recovery action taken (e.g. "Fallback to Claude API").
            message:    Optional detailed error message.
        """
        entry: Dict[str, Any] = {
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "recovery": recovery,
        }
        if message:
            entry["message"] = message

        self._error_records.append(entry)

        # Merge into the step entry if it exists
        key = f"step_{step}"
        step_entry = self._step_metrics.setdefault(key, {"step": step})
        errors = step_entry.setdefault("errors", [])
        errors.append(entry)

        self._save()
        logger.warning(f"[Metrics] Error at step {step}: {error_type} | recovery={recovery}")

    # ------------------------------------------------------------------
    # Timing helpers
    # ------------------------------------------------------------------

    @contextmanager
    def timed_step(self, step: int, tokens: int = 0, model: Optional[str] = None):
        """
        Context manager that automatically records step duration.

        Usage:
            with metrics.timed_step(step=5) as ctx:
                result = do_work()
                ctx["tokens"] = estimate_tokens(result)

        The context dict supports:
            ctx["tokens"]  - override token count (default 0)
            ctx["status"]  - override status  (default SUCCESS)
            ctx["extra"]   - dict of additional fields

        Exceptions are caught, status is set to FAILED, then re-raised.
        """
        ctx: Dict[str, Any] = {
            "tokens": tokens,
            "status": STATUS_SUCCESS,
            "extra": {},
        }
        start = time.time()
        try:
            yield ctx
        except Exception as e:
            ctx["status"] = STATUS_FAILED
            self.record_error(step, type(e).__name__, "Exception propagated", str(e))
            raise
        finally:
            duration = time.time() - start
            self.record_step(
                step=step,
                duration=duration,
                status=ctx["status"],
                tokens=ctx.get("tokens", 0),
                model=model,
                extra=ctx.get("extra") or None,
            )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """
        Build a session-level summary of all recorded metrics.

        Returns:
            Dict with:
              total_time_hours, total_tokens, successful_steps,
              failed_steps, skipped_steps, total_steps, success_rate,
              total_errors, by_step (raw metrics per step)
        """
        values = list(self._step_metrics.values())
        total_time_s = sum(m.get("duration_seconds", 0.0) for m in values)
        total_tokens = sum(m.get("tokens_used", 0) for m in values)

        successful = sum(1 for m in values if m.get("status") == STATUS_SUCCESS)
        failed = sum(1 for m in values if m.get("status") == STATUS_FAILED)
        skipped = sum(1 for m in values if m.get("status") == STATUS_SKIPPED)
        total = len(values)

        # Collect all files modified across steps
        all_files: Set[str] = set(self._all_files_modified)
        for m in values:
            for fop in m.get("files_modified", []):
                all_files.add(fop.get("path", ""))
        all_files.discard("")

        return {
            "session_id": self.session_id,
            "total_time_hours": round(total_time_s / 3600, 4),
            "total_time_seconds": round(total_time_s, 2),
            "total_tokens": total_tokens,
            "successful_steps": successful,
            "failed_steps": failed,
            "skipped_steps": skipped,
            "total_steps": total,
            "success_rate": round(successful / total, 4) if total else 0.0,
            "total_errors": len(self._error_records),
            "total_files_modified": len(all_files),
            "files_modified": sorted(all_files),
            "by_step": self._step_metrics,
        }

    def print_summary(self) -> None:
        """Print a human-readable summary to stderr (hooks use stdout for JSON)."""
        import sys

        out = sys.stderr
        s = self.summary()
        print("\n" + "=" * 55, file=out)
        print(f"  SESSION METRICS  ({self.session_id})", file=out)
        print("=" * 55, file=out)
        print(f"  Steps completed  : {s['total_steps']}", file=out)
        print(f"  Successful       : {s['successful_steps']}", file=out)
        print(f"  Failed           : {s['failed_steps']}", file=out)
        print(f"  Skipped          : {s['skipped_steps']}", file=out)
        print(f"  Success rate     : {s['success_rate']*100:.1f}%", file=out)
        print(f"  Total time       : {s['total_time_seconds']:.1f}s", file=out)
        print(f"  Total tokens     : {s['total_tokens']}", file=out)
        print(f"  Total errors     : {s['total_errors']}", file=out)
        print(f"  Files modified   : {s['total_files_modified']}", file=out)
        print("=" * 55, file=out)

        if s["by_step"]:
            print("  Per-step breakdown:", file=out)
            for key in sorted(s["by_step"].keys(), key=lambda k: int(k.split("_")[1])):
                m = s["by_step"][key]
                status_icon = "OK" if m["status"] == STATUS_SUCCESS else m["status"]
                model_info = f"  [{m.get('model', '')}]" if m.get("model") else ""
                print(
                    f"    Step {m['step']:02d}  {status_icon:<10}"
                    f"  {m.get('duration_seconds', 0):.2f}s"
                    f"  {m.get('tokens_used', 0)} tokens"
                    f"{model_info}",
                    file=out,
                )
        print(file=out)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Write current metrics to disk (atomic via temp-file + os.replace)."""
        payload = {
            "session_id": self.session_id,
            "saved_at": datetime.now().isoformat(),
            "step_metrics": self._step_metrics,
            "error_records": self._error_records,
            "all_files_modified": sorted(self._all_files_modified),
        }
        content = json.dumps(payload, indent=2)
        dir_path = self.metrics_file.parent
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                os.replace(tmp_path, str(self.metrics_file))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except (IOError, OSError, PermissionError) as e:
            # Fallback: direct write
            try:
                self.metrics_file.write_text(content, encoding="utf-8")
            except Exception as fallback_err:
                logger.error(f"[Metrics] Failed to save metrics: {e} / {fallback_err}")

    def _load(self) -> None:
        """Load persisted metrics from disk (used when resuming)."""
        if not self.metrics_file.exists():
            return
        try:
            data = json.loads(self.metrics_file.read_text(encoding="utf-8"))
            self._step_metrics = data.get("step_metrics", {})
            self._error_records = data.get("error_records", [])
            # Restore aggregate files set
            saved_files = data.get("all_files_modified", [])
            self._all_files_modified = set(saved_files)
            logger.debug(f"[Metrics] Loaded existing metrics from {self.metrics_file}")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"[Metrics] Could not load existing metrics: {e}")


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def create_metrics_collector(session_id: str) -> MetricsCollector:
    """Create a MetricsCollector for the given session."""
    return MetricsCollector(session_id)


# ---------------------------------------------------------------------------
# CLI / smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    sid = sys.argv[1] if len(sys.argv) > 1 else "test-session-metrics"
    mc = MetricsCollector(sid)

    # Simulate step recording
    for i in range(1, 6):
        mc.record_step(
            step=i,
            duration=0.5 * i,
            status=STATUS_SUCCESS if i != 3 else STATUS_FAILED,
            tokens=100 * i,
            model="claude-sonnet-4-6",
        )
        if i == 3:
            mc.record_error(i, "NetworkError", "Retried with backoff", "Connection refused")

    mc.print_summary()
