"""
Metrics Dashboard Data Collector - Aggregates pipeline execution history.

Collects from benchmark files and produces:
- Average step duration across runs
- Success rate per step
- RAG hit rate trends
- Cache hit rate trends
- Error distribution
- metrics-summary.json for future dashboard consumption

CLI usage:
    python scripts/langgraph_engine/metrics_dashboard.py --report

Windows-safe: ASCII only (cp1252 compatible).
"""

import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class MetricsDashboard:
    """Aggregates pipeline execution history into dashboard metrics."""

    def __init__(self, benchmark_dir=None, output_dir=None):
        if benchmark_dir:
            self.benchmark_dir = Path(benchmark_dir)
        else:
            self.benchmark_dir = (
                Path.home() / ".claude" / "logs" / "benchmarks"
            )

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = self.benchmark_dir

    def load_benchmarks(self, limit=100):
        """Load benchmark history files.

        Returns list of benchmark summary dicts, newest first.
        """
        if not self.benchmark_dir.is_dir():
            return []

        files = sorted(
            self.benchmark_dir.glob("benchmark_*.json"), reverse=True
        )
        results = []

        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:
                continue

        return results

    def aggregate(self, benchmarks=None):
        """Aggregate metrics across multiple pipeline runs.

        Returns dict with avg_total_time, per_step_avg, success_rates,
        rag_hit_rate_trend, error_distribution, etc.
        """
        if benchmarks is None:
            benchmarks = self.load_benchmarks()

        if not benchmarks:
            return {
                "run_count": 0,
                "message": "No benchmark data found",
            }

        run_count = len(benchmarks)

        # Total time stats
        total_times = [b.get("total_time_s", 0) for b in benchmarks]
        avg_total = sum(total_times) / len(total_times) if total_times else 0
        min_total = min(total_times) if total_times else 0
        max_total = max(total_times) if total_times else 0

        # Per-step aggregation
        step_stats = {}  # step_number -> {durations: [], successes: int, ...}
        for b in benchmarks:
            steps = b.get("steps", {})
            for step_key, step_data in steps.items():
                step_num = step_data.get("step", step_key)
                if step_num not in step_stats:
                    step_stats[step_num] = {
                        "durations": [],
                        "successes": 0,
                        "failures": 0,
                        "timeouts": 0,
                        "rag_hits": 0,
                        "total": 0,
                    }
                stats = step_stats[step_num]
                stats["durations"].append(step_data.get("duration_ms", 0))
                stats["total"] += 1
                status = step_data.get("status", "")
                if status == "SUCCESS":
                    stats["successes"] += 1
                elif status == "TIMEOUT":
                    stats["timeouts"] += 1
                elif status in ("FAILED", "ERROR"):
                    stats["failures"] += 1
                if step_data.get("rag_hit"):
                    stats["rag_hits"] += 1

        # Compute per-step averages
        per_step = {}
        for step_num, stats in sorted(step_stats.items()):
            durations = stats["durations"]
            per_step[step_num] = {
                "avg_duration_ms": round(
                    sum(durations) / len(durations), 1
                ) if durations else 0,
                "min_duration_ms": round(min(durations), 1) if durations else 0,
                "max_duration_ms": round(max(durations), 1) if durations else 0,
                "success_rate": round(
                    stats["successes"] / stats["total"] * 100, 1
                ) if stats["total"] > 0 else 0,
                "failure_count": stats["failures"],
                "timeout_count": stats["timeouts"],
                "rag_hit_rate": round(
                    stats["rag_hits"] / stats["total"] * 100, 1
                ) if stats["total"] > 0 else 0,
                "run_count": stats["total"],
            }

        # Overall success rate
        total_steps_run = sum(s["total"] for s in step_stats.values())
        total_successes = sum(s["successes"] for s in step_stats.values())
        overall_success_rate = round(
            total_successes / total_steps_run * 100, 1
        ) if total_steps_run > 0 else 0

        # RAG hit rate trend (last N runs)
        rag_rates = [
            b.get("rag_hit_rate", 0) for b in benchmarks
        ]

        # LLM call stats
        llm_calls = [b.get("total_llm_calls", 0) for b in benchmarks]

        # Error distribution
        error_dist = {}
        for b in benchmarks:
            for step_data in b.get("steps", {}).values():
                status = step_data.get("status", "")
                if status not in ("SUCCESS", "RAG_HIT"):
                    error_dist[status] = error_dist.get(status, 0) + 1

        return {
            "run_count": run_count,
            "avg_total_time_s": round(avg_total, 2),
            "min_total_time_s": round(min_total, 2),
            "max_total_time_s": round(max_total, 2),
            "overall_success_rate": overall_success_rate,
            "avg_rag_hit_rate": round(
                sum(rag_rates) / len(rag_rates), 1
            ) if rag_rates else 0,
            "avg_llm_calls": round(
                sum(llm_calls) / len(llm_calls), 1
            ) if llm_calls else 0,
            "per_step": per_step,
            "error_distribution": error_dist,
            "generated_at": datetime.now().isoformat(),
        }

    def save_summary(self, metrics=None):
        """Save aggregated metrics to metrics-summary.json.

        Returns saved file path.
        """
        if metrics is None:
            metrics = self.aggregate()

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            filepath = self.output_dir / "metrics-summary.json"
            filepath.write_text(
                json.dumps(metrics, indent=2), encoding="utf-8"
            )
            return str(filepath)
        except Exception as e:
            logger.warning("Failed to save metrics summary: %s", e)
            return None

    def format_report(self, metrics=None):
        """Format metrics as human-readable text report.

        Returns multi-line string.
        """
        if metrics is None:
            metrics = self.aggregate()

        if metrics.get("run_count", 0) == 0:
            return "No benchmark data found. Run the pipeline first."

        lines = [
            "",
            "=" * 65,
            "  PIPELINE METRICS DASHBOARD",
            "  Generated: %s" % metrics.get("generated_at", "")[:19],
            "=" * 65,
            "",
            "  Total Runs:         %d" % metrics["run_count"],
            "  Avg Pipeline Time:  %.1f s" % metrics["avg_total_time_s"],
            "  Min/Max Time:       %.1f / %.1f s" % (
                metrics["min_total_time_s"], metrics["max_total_time_s"]
            ),
            "  Overall Success:    %.1f%%" % metrics["overall_success_rate"],
            "  Avg RAG Hit Rate:   %.1f%%" % metrics["avg_rag_hit_rate"],
            "  Avg LLM Calls:      %.1f" % metrics["avg_llm_calls"],
            "",
            "-" * 65,
            "  Step | Avg Time  | Success | RAG Hit | Failures | Runs",
            "-" * 65,
        ]

        for step_num in sorted(metrics.get("per_step", {}).keys()):
            data = metrics["per_step"][step_num]
            lines.append(
                "  %4s | %7.0f ms | %5.1f%%  | %5.1f%%  | %8d | %4d" % (
                    step_num,
                    data["avg_duration_ms"],
                    data["success_rate"],
                    data["rag_hit_rate"],
                    data["failure_count"],
                    data["run_count"],
                )
            )

        lines.append("-" * 65)

        # Error distribution
        errors = metrics.get("error_distribution", {})
        if errors:
            lines.append("")
            lines.append("  Error Distribution:")
            for err_type, count in sorted(
                errors.items(), key=lambda x: -x[1]
            ):
                lines.append("    %-20s : %d" % (err_type, count))

        lines.append("")
        return "\n".join(lines)


def get_dashboard_data(days=7):
    """Get formatted dashboard data from metrics aggregator.

    Bridge function: reads from metrics_aggregator.get_full_report()
    and formats for dashboard consumption (JSON API or template rendering).

    Args:
        days: Number of days to aggregate (default 7).

    Returns:
        Dict with summary, steps, skills, tools, task_types sections.
    """
    try:
        from .metrics_aggregator import get_full_report
        report = get_full_report(days)

        return {
            "period_days": days,
            "summary": {
                "total_sessions": report.get("sessions", {}).get("total_sessions", 0),
                "avg_complexity": report.get("sessions", {}).get("avg_complexity", 0),
                "total_llm_calls": report.get("llm_usage", {}).get("total_llm_calls", 0),
                "cache_hit_rate": report.get("llm_usage", {}).get("cache_hit_rate", 0),
            },
            "steps": report.get("step_performance", {}).get("steps", {}),
            "top_skills": report.get("sessions", {}).get("skills_used", {}),
            "top_tools": report.get("tool_usage", {}).get("tools", {}),
            "task_types": report.get("sessions", {}).get("task_types", {}),
        }
    except Exception as exc:
        logger.debug("Dashboard data unavailable: %s", exc)
        return {"error": str(exc), "period_days": days}


def format_dashboard_text(data=None, days=7):
    """Format dashboard data as ASCII text for terminal display.

    Args:
        data: Pre-fetched dashboard data dict, or None to fetch fresh.
        days: Number of days (used if data is None).

    Returns:
        Formatted string for terminal output.
    """
    if data is None:
        data = get_dashboard_data(days)

    lines = []
    lines.append("=" * 60)
    lines.append("  CLAUDE WORKFLOW ENGINE - METRICS DASHBOARD")
    lines.append("=" * 60)

    summary = data.get("summary", {})
    lines.append("")
    lines.append("  Sessions: %d | Avg Complexity: %.1f" % (
        summary.get("total_sessions", 0),
        summary.get("avg_complexity", 0),
    ))
    lines.append("  LLM Calls: %d | Cache Hit Rate: %.1f%%" % (
        summary.get("total_llm_calls", 0),
        summary.get("cache_hit_rate", 0) * 100,
    ))
    lines.append("")

    # Step performance
    steps = data.get("steps", {})
    if steps:
        lines.append("  STEP PERFORMANCE:")
        for step_name in sorted(steps.keys()):
            step_data = steps[step_name]
            if isinstance(step_data, dict):
                avg_ms = step_data.get("avg_duration_ms", 0)
                rate = step_data.get("success_rate", 1.0)
                bar_len = min(30, max(1, int(avg_ms / 100)))
                bar = "#" * bar_len
                lines.append("    %-20s  %s  %dms  %.0f%%" % (
                    step_name, bar, avg_ms, rate * 100
                ))
        lines.append("")

    # Top skills
    skills = data.get("top_skills", {})
    if skills:
        lines.append("  TOP SKILLS:")
        for skill, count in sorted(skills.items(), key=lambda x: -x[1])[:5]:
            lines.append("    %-30s  %d uses" % (skill, count))
        lines.append("")

    # Task types
    tasks = data.get("task_types", {})
    if tasks:
        lines.append("  TASK TYPES:")
        for ttype, count in sorted(tasks.items(), key=lambda x: -x[1])[:5]:
            lines.append("    %-20s  %d" % (ttype, count))
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    """CLI entry point for metrics dashboard."""
    dashboard = MetricsDashboard()

    if "--report" in sys.argv or len(sys.argv) == 1:
        report = dashboard.format_report()
        print(report)

    if "--save" in sys.argv or "--report" not in sys.argv:
        path = dashboard.save_summary()
        if path:
            print("Saved to: %s" % path)


if __name__ == "__main__":
    main()
