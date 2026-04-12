"""
Performance Benchmarks - Step timing, aggregate metrics, and benchmark history.

Provides:
- PipelineBenchmark class for per-run metric collection
- Benchmark decorator for step timing
- Aggregate metrics per pipeline run (step durations, total time, cache hit rate)
- Benchmark results saved to ~/.claude/logs/benchmarks/
- Summary table for Step 14 output

Windows-safe: ASCII only (cp1252 compatible).
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from utils.path_resolver import get_benchmarks_dir

    _BENCHMARKS_DIR = get_benchmarks_dir()
except ImportError:
    _BENCHMARKS_DIR = Path.home() / ".claude" / "logs" / "benchmarks"


class PipelineBenchmark:
    """Collects and aggregates performance metrics for a single pipeline run."""

    def __init__(self, session_id="", benchmark_dir=None):
        self.session_id = session_id
        self.start_time = time.time()
        self.steps = {}  # step_number -> {duration, status, cache_hit, ...}
        self.total_llm_calls = 0
        self.total_cache_hits = 0

        if benchmark_dir:
            self.benchmark_dir = Path(benchmark_dir)
        else:
            self.benchmark_dir = _BENCHMARKS_DIR

    def record_step(self, step, duration, status="SUCCESS", cache_hit=False, llm_calls=0):
        """Record metrics for a completed step.

        Args:
            step: Step number (0-14).
            duration: Execution time in seconds.
            status: "SUCCESS", "FAILED", "TIMEOUT".
            cache_hit: Whether LLM cache was hit.
            llm_calls: Number of LLM calls made.
        """
        self.steps[step] = {
            "step": step,
            "duration_ms": round(duration * 1000, 1),
            "status": status,
            "cache_hit": cache_hit,
            "llm_calls": llm_calls,
            "timestamp": datetime.now().isoformat(),
        }

        if cache_hit:
            self.total_cache_hits += 1
        self.total_llm_calls += llm_calls

    def get_summary(self):
        """Generate aggregate summary of pipeline performance.

        Returns dict with total_time, step_count, avg_step_time,
        success_rate, etc.
        """
        total_time = time.time() - self.start_time
        step_count = len(self.steps)
        success_count = sum(1 for s in self.steps.values() if s["status"] == "SUCCESS")

        step_durations = [s["duration_ms"] for s in self.steps.values()]
        avg_step_ms = sum(step_durations) / len(step_durations) if step_durations else 0
        max_step = max(step_durations) if step_durations else 0
        slowest_step = None
        if step_durations:
            for step_num, data in self.steps.items():
                if data["duration_ms"] == max_step:
                    slowest_step = step_num
                    break

        return {
            "session_id": self.session_id,
            "total_time_s": round(total_time, 2),
            "total_time_ms": round(total_time * 1000, 1),
            "step_count": step_count,
            "success_count": success_count,
            "success_rate": (round(success_count / step_count * 100, 1) if step_count > 0 else 0),
            "avg_step_ms": round(avg_step_ms, 1),
            "max_step_ms": round(max_step, 1),
            "slowest_step": slowest_step,
            "total_llm_calls": self.total_llm_calls,
            "total_cache_hits": self.total_cache_hits,
            "steps": dict(self.steps),
            "timestamp": datetime.now().isoformat(),
        }

    def format_summary_table(self):
        """Format summary as a human-readable text table for Step 14.

        Returns multi-line string.
        """
        summary = self.get_summary()
        lines = [
            "",
            "=" * 60,
            "  PIPELINE PERFORMANCE SUMMARY",
            "=" * 60,
            "",
            "  Total Time:     %.1f s" % summary["total_time_s"],
            "  Steps Run:      %d" % summary["step_count"],
            "  Success Rate:   %.1f%%" % summary["success_rate"],
            "  Avg Step Time:  %.0f ms" % summary["avg_step_ms"],
            "  Slowest Step:   Step %s (%.0f ms)" % (summary["slowest_step"], summary["max_step_ms"]),
            "  LLM Calls:      %d" % summary["total_llm_calls"],
            "  Cache Hits:     %d" % summary["total_cache_hits"],
            "",
            "-" * 60,
            "  Step  | Duration  | Status   | Cache",
            "-" * 60,
        ]

        for step_num in sorted(self.steps.keys()):
            data = self.steps[step_num]
            lines.append(
                "  %2d    | %7.0f ms | %-8s | %s"
                % (
                    step_num,
                    data["duration_ms"],
                    data["status"],
                    "Y" if data["cache_hit"] else "-",
                )
            )

        lines.append("-" * 60)
        lines.append("")

        return "\n".join(lines)

    def save(self):
        """Save benchmark results to ~/.claude/logs/benchmarks/.

        Returns saved file path.
        """
        try:
            self.benchmark_dir.mkdir(parents=True, exist_ok=True)

            summary = self.get_summary()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = "benchmark_%s_%s.json" % (timestamp, self.session_id[:16] if self.session_id else "none")
            filepath = self.benchmark_dir / filename

            filepath.write_text(json.dumps(summary, indent=2), encoding="utf-8")

            logger.info("Benchmark saved: %s", filepath)
            return str(filepath)

        except Exception as e:
            logger.warning("Failed to save benchmark: %s", e)
            return None

    @classmethod
    def load_history(cls, benchmark_dir=None, limit=20):
        """Load recent benchmark history.

        Returns list of summary dicts, newest first.
        """
        if benchmark_dir:
            bdir = Path(benchmark_dir)
        else:
            bdir = _BENCHMARKS_DIR

        if not bdir.is_dir():
            return []

        files = sorted(bdir.glob("benchmark_*.json"), reverse=True)
        results = []

        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:
                continue

        return results
