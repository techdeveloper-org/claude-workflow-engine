"""Metrics Aggregator - Collects and summarizes pipeline execution metrics.

Reads existing log files from the configured logs directory and produces
aggregated statistics. No UI - just data layer. Can be called via CLI.

Usage:
    python metrics_aggregator.py --last 7d
    python metrics_aggregator.py --session SESSION_ID
    python metrics_aggregator.py --all
    python metrics_aggregator.py --json

Log file locations (resolved via path_resolver):
    Sessions:         {logs_dir}/sessions/*/session.json
    Level logs:       {logs_dir}/level/*.json
    Tool optimization:{logs_dir}/tool-optimization.jsonl
    Cache stats:      {logs_dir}/cache/cache_stats.json

Windows-safe: ASCII only (cp1252 compatible).
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# sys.path setup - allows standalone execution from scripts/ directory
# ---------------------------------------------------------------------------
_here = Path(__file__).parent
_project_root = _here.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# path_resolver import with fallback
# ---------------------------------------------------------------------------
try:
    from src.utils.path_resolver import get_logs_dir

    _HAS_PATH_RESOLVER = True
except ImportError:
    _HAS_PATH_RESOLVER = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_logs_base() -> Path:
    """Return the base logs directory using path_resolver or a default fallback."""
    if _HAS_PATH_RESOLVER:
        try:
            return Path(get_logs_dir())
        except Exception:
            pass
    return Path.home() / ".claude" / "logs"


def _is_within_days(timestamp_str: Optional[str], days: int) -> bool:
    """Return True if the ISO-8601 timestamp is within the last *days* days.

    Returns True when *days* is 0 or negative (meaning 'all time').
    Returns True when *timestamp_str* is None or unparseable (lenient mode).

    Args:
        timestamp_str: ISO-8601 timestamp string to check.
        days: Number of days for the look-back window.

    Returns:
        bool: Whether the timestamp falls within the window.
    """
    if days <= 0:
        return True
    if not timestamp_str:
        return True
    try:
        ts = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        return ts >= cutoff
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# Public aggregation functions
# ---------------------------------------------------------------------------


def aggregate_sessions(days: int = 7) -> Dict[str, Any]:
    """Aggregate session-level statistics from session.json files.

    Reads all session.json files from:
        {logs_dir}/sessions/*/session.json

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            total_sessions (int)
            date_range (dict): {from: str, to: str}
            avg_complexity (float)
            task_types (dict): {task_type: count}
            skills_used (dict): {skill_name: count}
            agents_used (dict): {agent_name: count}
    """
    empty: Dict[str, Any] = {
        "total_sessions": 0,
        "date_range": {"from": None, "to": None},
        "avg_complexity": 0.0,
        "task_types": {},
        "skills_used": {},
        "agents_used": {},
    }

    try:
        sessions_dir = _get_logs_base() / "sessions"
        if not sessions_dir.is_dir():
            return empty

        total = 0
        complexities: List[float] = []
        task_types: Dict[str, int] = {}
        skills: Dict[str, int] = {}
        agents: Dict[str, int] = {}
        timestamps: List[str] = []

        for session_json in sessions_dir.glob("*/session.json"):
            try:
                data = json.loads(session_json.read_text(encoding="utf-8", errors="replace"))
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict):
                continue

            ts = data.get("timestamp") or data.get("created_at") or data.get("started_at")
            if not _is_within_days(ts, days):
                continue

            total += 1
            if ts:
                timestamps.append(str(ts))

            c = data.get("complexity_score") or data.get("combined_complexity_score")
            if isinstance(c, (int, float)):
                complexities.append(float(c))

            tt = data.get("task_type") or data.get("type")
            if isinstance(tt, str) and tt:
                task_types[tt] = task_types.get(tt, 0) + 1

            skill = data.get("skill") or data.get("skill_name")
            if isinstance(skill, str) and skill:
                skills[skill] = skills.get(skill, 0) + 1

            agent = data.get("agent") or data.get("agent_name")
            if isinstance(agent, str) and agent:
                agents[agent] = agents.get(agent, 0) + 1

        if total == 0:
            return empty

        timestamps_sorted = sorted(timestamps)
        avg_c = round(sum(complexities) / len(complexities), 2) if complexities else 0.0

        return {
            "total_sessions": total,
            "date_range": {
                "from": timestamps_sorted[0] if timestamps_sorted else None,
                "to": timestamps_sorted[-1] if timestamps_sorted else None,
            },
            "avg_complexity": avg_c,
            "task_types": dict(sorted(task_types.items(), key=lambda x: x[1], reverse=True)),
            "skills_used": dict(sorted(skills.items(), key=lambda x: x[1], reverse=True)),
            "agents_used": dict(sorted(agents.items(), key=lambda x: x[1], reverse=True)),
        }

    except Exception as exc:
        logger.warning("aggregate_sessions failed: %s", exc)
        return empty


def aggregate_step_performance(days: int = 7) -> Dict[str, Any]:
    """Aggregate per-step timing and success statistics from level log files.

    Reads all JSON files from:
        {logs_dir}/level/*.json

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            total_pipeline_avg_ms (float)
            slowest_step (str or None)
            fastest_step (str or None)
            steps (dict): {step_name: {avg_duration_ms, success_rate, call_count}}
    """
    empty: Dict[str, Any] = {
        "total_pipeline_avg_ms": 0.0,
        "slowest_step": None,
        "fastest_step": None,
        "steps": {},
    }

    try:
        level_dir = _get_logs_base() / "level"
        if not level_dir.is_dir():
            return empty

        # {step_name: {durations: [], successes: int, total: int}}
        step_data: Dict[str, Dict[str, Any]] = {}

        for log_file in level_dir.glob("*.json"):
            try:
                raw = log_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # File may be a JSON array or newline-delimited JSON
            entries: List[Any] = []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    entries = parsed
                elif isinstance(parsed, dict):
                    entries = [parsed]
            except json.JSONDecodeError:
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                ts = entry.get("timestamp") or entry.get("created_at")
                if not _is_within_days(ts, days):
                    continue

                step_name = entry.get("step_name") or entry.get("step") or entry.get("node") or "unknown"
                step_name = str(step_name)

                duration_ms = entry.get("duration_ms") or 0
                if entry.get("duration_s"):
                    duration_ms = float(entry["duration_s"]) * 1000
                elif entry.get("duration_seconds"):
                    duration_ms = float(entry["duration_seconds"]) * 1000

                status = entry.get("status") or entry.get("result") or "UNKNOWN"
                is_success = str(status).upper() in ("SUCCESS", "OK", "DONE", "COMPLETE")

                if step_name not in step_data:
                    step_data[step_name] = {"durations": [], "successes": 0, "total": 0}

                step_data[step_name]["durations"].append(float(duration_ms))
                step_data[step_name]["total"] += 1
                if is_success:
                    step_data[step_name]["successes"] += 1

        if not step_data:
            return empty

        steps_out: Dict[str, Any] = {}
        for name, sd in step_data.items():
            durations = sd["durations"]
            avg_ms = round(sum(durations) / len(durations), 1) if durations else 0.0
            success_rate = round(sd["successes"] / sd["total"], 4) if sd["total"] else 0.0
            steps_out[name] = {
                "avg_duration_ms": avg_ms,
                "success_rate": success_rate,
                "call_count": sd["total"],
            }

        all_avgs = {n: d["avg_duration_ms"] for n, d in steps_out.items()}
        slowest = max(all_avgs, key=all_avgs.get) if all_avgs else None  # type: ignore[arg-type]
        fastest = min(all_avgs, key=all_avgs.get) if all_avgs else None  # type: ignore[arg-type]

        all_durations_flat = [d for sd in step_data.values() for d in sd["durations"]]
        total_avg = round(sum(all_durations_flat) / len(all_durations_flat), 1) if all_durations_flat else 0.0

        return {
            "total_pipeline_avg_ms": total_avg,
            "slowest_step": slowest,
            "fastest_step": fastest,
            "steps": steps_out,
        }

    except Exception as exc:
        logger.warning("aggregate_step_performance failed: %s", exc)
        return empty


def aggregate_llm_usage(days: int = 7) -> Dict[str, Any]:
    """Aggregate LLM inference statistics from tool-optimization logs.

    Reads all JSONL entries from:
        {logs_dir}/tool-optimization.jsonl

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            total_llm_calls (int)
            providers (dict): {provider: call_count}
            avg_tokens_per_call (float)
            cache_hit_rate (float)
            total_token_savings (int)
    """
    empty: Dict[str, Any] = {
        "total_llm_calls": 0,
        "providers": {},
        "avg_tokens_per_call": 0.0,
        "cache_hit_rate": 0.0,
        "total_token_savings": 0,
    }

    try:
        log_path = _get_logs_base() / "tool-optimization.jsonl"
        if not log_path.exists():
            return empty

        total_calls = 0
        cache_hits = 0
        total_tokens = 0
        token_savings = 0
        providers: Dict[str, int] = {}

        with open(log_path, encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue

                ts = entry.get("timestamp") or entry.get("created_at")
                if not _is_within_days(ts, days):
                    continue

                entry_type = entry.get("type") or entry.get("event_type") or ""
                is_llm = (
                    "llm" in str(entry_type).lower()
                    or "inference" in str(entry_type).lower()
                    or entry.get("model") is not None
                    or entry.get("provider") is not None
                    or entry.get("tokens") is not None
                    or entry.get("tokens_used") is not None
                )
                if not is_llm:
                    continue

                total_calls += 1

                provider = entry.get("provider") or entry.get("backend") or "unknown"
                if isinstance(provider, str) and provider:
                    providers[provider] = providers.get(provider, 0) + 1

                tokens = entry.get("tokens") or entry.get("tokens_used") or entry.get("total_tokens") or 0
                if isinstance(tokens, (int, float)):
                    total_tokens += int(tokens)

                if entry.get("cache_hit") or entry.get("from_cache"):
                    cache_hits += 1

                saved = entry.get("tokens_saved") or entry.get("savings") or 0
                if isinstance(saved, (int, float)):
                    token_savings += int(saved)

        if total_calls == 0:
            return empty

        avg_tokens = round(total_tokens / total_calls, 1) if total_calls > 0 else 0.0
        cache_hit_rate = round(cache_hits / total_calls, 4) if total_calls > 0 else 0.0

        return {
            "total_llm_calls": total_calls,
            "providers": dict(sorted(providers.items(), key=lambda x: x[1], reverse=True)),
            "avg_tokens_per_call": avg_tokens,
            "cache_hit_rate": cache_hit_rate,
            "total_token_savings": token_savings,
        }

    except Exception as exc:
        logger.warning("aggregate_llm_usage failed: %s", exc)
        return empty


def aggregate_tool_usage(days: int = 7) -> Dict[str, Any]:
    """Aggregate tool call statistics from tool tracking logs.

    Reads all JSONL entries from:
        {logs_dir}/tool-optimization.jsonl

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            total_tool_calls (int)
            tools (dict): {tool_name: call_count}
            optimization_savings_pct (float): Percentage of calls saved via optimization
    """
    empty: Dict[str, Any] = {
        "total_tool_calls": 0,
        "tools": {},
        "optimization_savings_pct": 0.0,
    }

    try:
        log_path = _get_logs_base() / "tool-optimization.jsonl"
        if not log_path.exists():
            return empty

        total_calls = 0
        optimized_calls = 0
        tools: Dict[str, int] = {}

        with open(log_path, encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue

                ts = entry.get("timestamp") or entry.get("created_at")
                if not _is_within_days(ts, days):
                    continue

                tool_name = entry.get("tool") or entry.get("tool_name") or entry.get("tool_type")
                if not tool_name:
                    continue

                total_calls += 1
                if isinstance(tool_name, str) and tool_name:
                    tools[tool_name] = tools.get(tool_name, 0) + 1

                if entry.get("optimized") or entry.get("skipped") or entry.get("deduplicated"):
                    optimized_calls += 1

        if total_calls == 0:
            return empty

        savings_pct = round((optimized_calls / total_calls) * 100, 2) if total_calls > 0 else 0.0

        return {
            "total_tool_calls": total_calls,
            "tools": dict(sorted(tools.items(), key=lambda x: x[1], reverse=True)),
            "optimization_savings_pct": savings_pct,
        }

    except Exception as exc:
        logger.warning("aggregate_tool_usage failed: %s", exc)
        return empty


def get_full_report(days: int = 7) -> Dict[str, Any]:
    """Build a full aggregated metrics report combining all four aggregations.

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            generated_at (str): ISO 8601 timestamp of report generation.
            period_days (int): The requested look-back window.
            sessions (dict): Output of aggregate_sessions().
            step_performance (dict): Output of aggregate_step_performance().
            llm_usage (dict): Output of aggregate_llm_usage().
            tool_usage (dict): Output of aggregate_tool_usage().
    """
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "period_days": days,
        "sessions": aggregate_sessions(days),
        "step_performance": aggregate_step_performance(days),
        "llm_usage": aggregate_llm_usage(days),
        "tool_usage": aggregate_tool_usage(days),
    }


# ---------------------------------------------------------------------------
# Pretty-print helper
# ---------------------------------------------------------------------------


def _fmt_row(label: str, value: Any, width: int = 36) -> str:
    """Format a label/value pair as a fixed-width table row.

    Args:
        label: Row label string.
        value: Value to display (will be str()-converted).
        width: Column width for the label column.

    Returns:
        Formatted string line.
    """
    return "  {:<{w}}  {}".format(label, value, w=width)


def print_report(report: Dict[str, Any]) -> None:
    """Pretty-print the full report to stdout as formatted tables.

    Args:
        report: Dict returned by get_full_report().
    """
    sep = "-" * 60
    print(sep)
    print("  PIPELINE METRICS REPORT")
    print("  Generated : {}".format(report.get("generated_at", "n/a")))
    days = report.get("period_days", 7)
    period_label = "all time" if days <= 0 else "last {} day(s)".format(days)
    print("  Period    : {}".format(period_label))
    print(sep)

    s = report.get("sessions", {})
    print()
    print("  [SESSIONS]")
    print(_fmt_row("Total sessions", s.get("total_sessions", 0)))
    dr = s.get("date_range", {})
    print(_fmt_row("Date from", dr.get("from") or "n/a"))
    print(_fmt_row("Date to", dr.get("to") or "n/a"))
    print(_fmt_row("Avg complexity", s.get("avg_complexity", 0.0)))

    task_types = s.get("task_types", {})
    if task_types:
        top = list(task_types.items())[:5]
        print(_fmt_row("Top task types", ", ".join("{}: {}".format(k, v) for k, v in top)))

    skills = s.get("skills_used", {})
    if skills:
        top = list(skills.items())[:5]
        print(_fmt_row("Top skills", ", ".join("{}: {}".format(k, v) for k, v in top)))

    agents = s.get("agents_used", {})
    if agents:
        top = list(agents.items())[:5]
        print(_fmt_row("Top agents", ", ".join("{}: {}".format(k, v) for k, v in top)))

    sp = report.get("step_performance", {})
    print()
    print("  [STEP PERFORMANCE]")
    print(_fmt_row("Total pipeline avg (ms)", sp.get("total_pipeline_avg_ms", 0.0)))
    print(_fmt_row("Slowest step", sp.get("slowest_step") or "n/a"))
    print(_fmt_row("Fastest step", sp.get("fastest_step") or "n/a"))

    steps = sp.get("steps", {})
    if steps:
        print()
        print("  {:<12}  {:<18}  {:<14}  {}".format("Step", "Avg Duration (ms)", "Success Rate", "Call Count"))
        print("  " + "-" * 56)
        for step_name, sv in sorted(steps.items()):
            print(
                "  {:<12}  {:<18}  {:<14}  {}".format(
                    step_name,
                    sv.get("avg_duration_ms", 0),
                    "{:.1%}".format(sv.get("success_rate", 0)),
                    sv.get("call_count", 0),
                )
            )

    lu = report.get("llm_usage", {})
    print()
    print("  [LLM USAGE]")
    print(_fmt_row("Total LLM calls", lu.get("total_llm_calls", 0)))
    print(_fmt_row("Avg tokens/call", lu.get("avg_tokens_per_call", 0.0)))
    print(_fmt_row("Cache hit rate", "{:.1%}".format(lu.get("cache_hit_rate", 0.0))))
    print(_fmt_row("Total token savings", lu.get("total_token_savings", 0)))

    providers = lu.get("providers", {})
    if providers:
        top = list(providers.items())[:5]
        print(_fmt_row("Providers", ", ".join("{}: {}".format(k, v) for k, v in top)))

    tu = report.get("tool_usage", {})
    print()
    print("  [TOOL USAGE]")
    print(_fmt_row("Total tool calls", tu.get("total_tool_calls", 0)))
    print(_fmt_row("Optimization savings", "{:.1f}%".format(tu.get("optimization_savings_pct", 0.0))))

    tool_counts = tu.get("tools", {})
    if tool_counts:
        top = list(tool_counts.items())[:10]
        print()
        print("  {:<20}  {}".format("Tool", "Calls"))
        print("  " + "-" * 30)
        for tool_name, count in top:
            print("  {:<20}  {}".format(tool_name, count))

    print()
    print(sep)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def parse_days(value: str) -> int:
    """Parse a time range string into an integer number of days.

    Supported formats:
        "7d"  -> 7
        "30d" -> 30
        "1d"  -> 1
        "7"   -> 7  (bare integer treated as days)
        "all" -> 0  (signals all-time query)

    Args:
        value: Time range string.

    Returns:
        int: Number of days (0 means all time).

    Raises:
        ValueError: When the format cannot be parsed.
    """
    if not isinstance(value, str):
        return int(value)
    stripped = value.strip().lower()
    if stripped in ("all", "0", ""):
        return 0
    if stripped.endswith("d"):
        return int(stripped[:-1])
    return int(stripped)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Pipeline metrics aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python metrics_aggregator.py --last 7d\n"
            "  python metrics_aggregator.py --last 30d --json\n"
            "  python metrics_aggregator.py --all\n"
            "  python metrics_aggregator.py --session SESSION_ID\n"
        ),
    )
    parser.add_argument(
        "--last",
        default="7d",
        metavar="RANGE",
        help="Time range, e.g. 7d, 30d, 1d (default: 7d)",
    )
    parser.add_argument(
        "--session",
        metavar="SESSION_ID",
        help="Restrict report to a specific session ID (aggregates that session only)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_time",
        help="Include all available data regardless of age",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output the report as JSON instead of the formatted table",
    )
    args = parser.parse_args()

    if args.all_time:
        days_window = 0
    elif args.session:
        days_window = 0
    else:
        try:
            days_window = parse_days(args.last)
        except ValueError:
            print("ERROR: Invalid --last value: {}".format(args.last), file=sys.stderr)
            sys.exit(1)

    report = get_full_report(days_window)

    if args.output_json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
