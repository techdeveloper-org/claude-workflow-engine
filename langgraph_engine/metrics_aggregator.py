"""
Metrics Aggregator - Collects and summarizes pipeline execution metrics.

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
_project_root = _here.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# path_resolver import with fallback
# ---------------------------------------------------------------------------
try:
    from src.utils.path_resolver import get_logs_dir, get_session_logs_dir

    _HAS_PATH_RESOLVER = True
except ImportError:
    _HAS_PATH_RESOLVER = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auto-start Prometheus metrics server if ENABLE_METRICS=1
# ---------------------------------------------------------------------------
try:
    import os as _os

    from langgraph_engine.metrics_exporter import start_metrics_server as _start_metrics

    if _os.environ.get("ENABLE_METRICS", "0") == "1":
        _start_metrics()
except Exception:
    pass

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_logs_base() -> Path:
    """Return the logs base directory using path_resolver when available.

    Falls back to ~/.claude/logs when path_resolver is not importable.

    Returns:
        Path: Absolute path to the logs directory.
    """
    if _HAS_PATH_RESOLVER:
        return get_logs_dir()
    return Path.home() / ".claude" / "logs"


def _get_sessions_log_dir() -> Path:
    """Return the per-session logs directory.

    Returns:
        Path: Absolute path to {logs_dir}/sessions/.
    """
    if _HAS_PATH_RESOLVER:
        return get_session_logs_dir()
    return _get_logs_base() / "sessions"


def _safe_load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file safely, returning None on any error.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict or None if the file is missing, empty, or malformed.
    """
    try:
        if not path.exists() or path.stat().st_size == 0:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        return json.loads(text)
    except Exception as exc:
        logger.debug("Could not read %s: %s", path, exc)
        return None


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string into a timezone-aware datetime.

    Handles both 'Z' suffix and '+00:00' offset. Returns None on failure.

    Args:
        value: Raw value from a JSON field (expected str).

    Returns:
        datetime (UTC-aware) or None.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        # Normalise trailing Z to +00:00 for fromisoformat (Python 3.10 compat)
        normalised = value.rstrip("Z")
        if "+" not in normalised and normalised.count("-") < 3:
            normalised += "+00:00"
        return datetime.fromisoformat(normalised)
    except Exception:
        try:
            # Fallback: strip timezone entirely and assume UTC
            clean = value[:19]  # "YYYY-MM-DDTHH:MM:SS"
            dt = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _is_within_days(timestamp_str: Any, days: int) -> bool:
    """Return True when the timestamp falls within the last N days.

    A days value <= 0 is treated as "all time" and always returns True.

    Args:
        timestamp_str: Raw ISO 8601 string from a log field.
        days: Number of days to look back. 0 or negative means no filter.

    Returns:
        bool: True if within range or days <= 0.
    """
    if days <= 0:
        return True
    dt = _parse_iso(timestamp_str)
    if dt is None:
        return True  # Cannot determine age; include rather than exclude
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=days)
    # Ensure dt is timezone-aware for comparison
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


# ---------------------------------------------------------------------------
# Public aggregation functions
# ---------------------------------------------------------------------------


def aggregate_sessions(days: int = 7) -> Dict[str, Any]:
    """Aggregate session-level statistics from session.json files.

    Reads all session.json files found under:
        {logs_dir}/sessions/*/session.json

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            total_sessions (int)
            date_range (dict): {from, to} ISO strings or None
            avg_complexity (float)
            complexity_distribution (dict): {1: N, ..., 10: N}
            task_types (dict): {type_name: count}
            skills_used (dict): {skill_name: count}
            agents_used (dict): {agent_name: count}
    """
    empty: Dict[str, Any] = {
        "total_sessions": 0,
        "date_range": {"from": None, "to": None},
        "avg_complexity": 0.0,
        "complexity_distribution": {str(i): 0 for i in range(1, 11)},
        "task_types": {},
        "skills_used": {},
        "agents_used": {},
    }

    try:
        sessions_dir = _get_sessions_log_dir()
        if not sessions_dir.exists():
            return empty

        session_files = list(sessions_dir.glob("*/session.json"))
        if not session_files:
            return empty

        total = 0
        complexities: List[float] = []
        complexity_dist: Dict[str, int] = {str(i): 0 for i in range(1, 11)}
        task_types: Dict[str, int] = {}
        skills_used: Dict[str, int] = {}
        agents_used: Dict[str, int] = {}
        timestamps: List[datetime] = []

        for sf in session_files:
            data = _safe_load_json(sf)
            if not data:
                continue

            # Timestamp filter
            ts = data.get("timestamp") or data.get("created_at") or data.get("start_time")
            if not _is_within_days(ts, days):
                continue

            dt = _parse_iso(ts)
            if dt is not None:
                timestamps.append(dt)

            total += 1

            # Complexity
            complexity = data.get("complexity")
            if isinstance(complexity, (int, float)) and 1 <= complexity <= 10:
                complexities.append(float(complexity))
                key = str(int(complexity))
                complexity_dist[key] = complexity_dist.get(key, 0) + 1

            # Task type
            task_type = data.get("task_type") or data.get("type") or data.get("task_category")
            if isinstance(task_type, str) and task_type:
                task_types[task_type] = task_types.get(task_type, 0) + 1

            # Skills
            skill = data.get("skill") or data.get("skill_name") or data.get("selected_skill")
            if isinstance(skill, str) and skill:
                skills_used[skill] = skills_used.get(skill, 0) + 1
            skills_list = data.get("skills") or []
            if isinstance(skills_list, list):
                for s in skills_list:
                    if isinstance(s, str) and s:
                        skills_used[s] = skills_used.get(s, 0) + 1

            # Agents
            agent = data.get("agent") or data.get("agent_name") or data.get("selected_agent")
            if isinstance(agent, str) and agent:
                agents_used[agent] = agents_used.get(agent, 0) + 1
            agents_list = data.get("agents") or []
            if isinstance(agents_list, list):
                for a in agents_list:
                    if isinstance(a, str) and a:
                        agents_used[a] = agents_used.get(a, 0) + 1

        if total == 0:
            return empty

        date_from = min(timestamps).isoformat() if timestamps else None
        date_to = max(timestamps).isoformat() if timestamps else None
        avg_complexity = round(sum(complexities) / len(complexities), 2) if complexities else 0.0

        return {
            "total_sessions": total,
            "date_range": {"from": date_from, "to": date_to},
            "avg_complexity": avg_complexity,
            "complexity_distribution": complexity_dist,
            "task_types": dict(sorted(task_types.items(), key=lambda x: x[1], reverse=True)),
            "skills_used": dict(sorted(skills_used.items(), key=lambda x: x[1], reverse=True)),
            "agents_used": dict(sorted(agents_used.items(), key=lambda x: x[1], reverse=True)),
        }

    except Exception as exc:
        logger.warning("aggregate_sessions failed: %s", exc)
        return empty


def aggregate_step_performance(days: int = 7) -> Dict[str, Any]:
    """Aggregate per-step performance from level log files.

    Reads all JSON files found under:
        {logs_dir}/level/*.json

    Each file is expected to contain a dict with step-level metrics
    keyed by step name (e.g., "step0", "step1", ...) or as a list
    of step records.

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            steps (dict): {stepN: {avg_duration_ms, success_rate, call_count}}
            slowest_step (str or None)
            fastest_step (str or None)
            total_pipeline_avg_ms (float)
    """
    empty: Dict[str, Any] = {
        "steps": {},
        "slowest_step": None,
        "fastest_step": None,
        "total_pipeline_avg_ms": 0.0,
    }

    try:
        level_dir = _get_logs_base() / "level"
        if not level_dir.exists():
            return empty

        log_files = list(level_dir.glob("*.json"))
        if not log_files:
            return empty

        # step_key -> {durations_ms: [], successes: int, total: int}
        step_accum: Dict[str, Dict[str, Any]] = {}

        def _record_step(step_key: str, duration_ms: float, status: str) -> None:
            if step_key not in step_accum:
                step_accum[step_key] = {"durations_ms": [], "successes": 0, "total": 0}
            step_accum[step_key]["durations_ms"].append(duration_ms)
            step_accum[step_key]["total"] += 1
            if isinstance(status, str) and status.upper() in ("SUCCESS", "OK", "DONE", "COMPLETED"):
                step_accum[step_key]["successes"] += 1

        for lf in log_files:
            data = _safe_load_json(lf)
            if not data:
                continue

            # Timestamp filter on file-level timestamp if present
            ts = data.get("timestamp") or data.get("created_at")
            if not _is_within_days(ts, days):
                continue

            # Support two formats:
            # Format A: {"step0": {...}, "step1": {...}}
            # Format B: {"steps": {"step0": {...}, ...}}
            # Format C: {"steps": [{...}, {...}]} list of step records
            steps_data = data.get("steps", data)

            if isinstance(steps_data, dict):
                for key, val in steps_data.items():
                    if not isinstance(val, dict):
                        continue
                    step_name = val.get("step_name") or val.get("step") or key
                    step_key = str(step_name).lower().replace(" ", "_")
                    if not step_key.startswith("step"):
                        step_key = "step_" + step_key
                    dur = val.get("duration_ms") or val.get("duration_seconds", 0) * 1000
                    status = val.get("status", "")
                    _record_step(step_key, float(dur), status)

            elif isinstance(steps_data, list):
                for val in steps_data:
                    if not isinstance(val, dict):
                        continue
                    step_name = val.get("step_name") or val.get("step") or val.get("name", "unknown")
                    step_key = str(step_name).lower().replace(" ", "_")
                    if not step_key.startswith("step"):
                        step_key = "step_" + step_key
                    dur = val.get("duration_ms") or val.get("duration_seconds", 0) * 1000
                    status = val.get("status", "")
                    _record_step(step_key, float(dur), status)

        if not step_accum:
            return empty

        steps_result: Dict[str, Any] = {}
        for step_key, acc in sorted(step_accum.items()):
            durs = acc["durations_ms"]
            total = acc["total"]
            avg_dur = round(sum(durs) / len(durs), 1) if durs else 0.0
            success_rate = round(acc["successes"] / total, 4) if total > 0 else 0.0
            steps_result[step_key] = {
                "avg_duration_ms": avg_dur,
                "success_rate": success_rate,
                "call_count": total,
            }

        # Identify slowest and fastest
        if steps_result:
            sorted_by_dur = sorted(steps_result.items(), key=lambda x: x[1]["avg_duration_ms"])
            fastest_step = sorted_by_dur[0][0]
            slowest_step = sorted_by_dur[-1][0]
        else:
            fastest_step = None
            slowest_step = None

        # Total pipeline average: sum of per-step averages
        total_avg = round(sum(v["avg_duration_ms"] for v in steps_result.values()), 1)

        return {
            "steps": steps_result,
            "slowest_step": slowest_step,
            "fastest_step": fastest_step,
            "total_pipeline_avg_ms": total_avg,
        }

    except Exception as exc:
        logger.warning("aggregate_step_performance failed: %s", exc)
        return empty


def aggregate_llm_usage(days: int = 7) -> Dict[str, Any]:
    """Aggregate LLM call statistics from tool optimization logs.

    Reads:
        {logs_dir}/tool-optimization.jsonl  (newline-delimited JSON)

    Args:
        days: Look back window in days. 0 or negative means all time.

    Returns:
        dict with keys:
            total_llm_calls (int)
            providers (dict): {provider_name: call_count}
            avg_tokens_per_call (float)
            cache_hit_rate (float): 0.0 - 1.0
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
        providers: Dict[str, int] = {}
        total_tokens = 0
        cache_hits = 0
        token_savings = 0

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

                # Timestamp filter
                ts = entry.get("timestamp") or entry.get("created_at")
                if not _is_within_days(ts, days):
                    continue

                # Count only LLM-related entries
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

                # Provider tracking
                provider = entry.get("provider") or entry.get("backend") or "unknown"
                if isinstance(provider, str) and provider:
                    providers[provider] = providers.get(provider, 0) + 1

                # Token tracking
                tokens = entry.get("tokens") or entry.get("tokens_used") or entry.get("total_tokens") or 0
                if isinstance(tokens, (int, float)):
                    total_tokens += int(tokens)

                # Cache hit tracking
                if entry.get("cache_hit") or entry.get("from_cache"):
                    cache_hits += 1

                # Token savings from optimization
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

                # Timestamp filter
                ts = entry.get("timestamp") or entry.get("created_at")
                if not _is_within_days(ts, days):
                    continue

                # Count tool-related entries
                tool_name = entry.get("tool") or entry.get("tool_name") or entry.get("tool_type")
                if not tool_name:
                    continue

                total_calls += 1
                if isinstance(tool_name, str) and tool_name:
                    tools[tool_name] = tools.get(tool_name, 0) + 1

                # Optimization tracking
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

    # ---- Sessions ----
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

    # ---- Step Performance ----
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

    # ---- LLM Usage ----
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

    # ---- Tool Usage ----
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

    # Determine day window
    if args.all_time:
        days_window = 0
    elif args.session:
        # Session-specific: we still gather all data but filter would be
        # applied by the aggregators on their timestamp fields.
        # For now treat it as all-time within a named session.
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
