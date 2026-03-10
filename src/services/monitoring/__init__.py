"""Monitoring Services - Metrics, logs, policy tracking.

Core monitoring layer that reads data produced by the Claude Memory System
hook scripts and exposes structured objects for the dashboard routes.

All services in this sub-package are read-only with respect to the memory
system: they parse log files and JSON state files but never write back to
the Claude memory directories.

Exported classes:
    PerformanceProfiler  -- Parses metrics.jsonl to compute per-hook and
                            per-step timing distributions for the performance
                            analytics view.
    AutomationTracker    -- Tracks how often automated enforcement actions
                            (task breakdowns, skill selections, model choices)
                            fire versus manual overrides.
    SkillAgentTracker    -- Records which skills and agents were selected in
                            each session, enabling usage-frequency dashboards.
    OptimizationTracker  -- Monitors tool-usage optimisation hints emitted by
                            the pre-tool-enforcer and measures their adoption.

Usage::

    from src.services.monitoring import PerformanceProfiler
    profiler = PerformanceProfiler(logs_dir)
    stats = profiler.get_summary()
"""

from .performance_profiler import PerformanceProfiler
from .automation_tracker import AutomationTracker
from .skill_agent_tracker import SkillAgentTracker
from .optimization_tracker import OptimizationTracker

__all__ = [
    'PerformanceProfiler',
    'AutomationTracker',
    'SkillAgentTracker',
    'OptimizationTracker',
]
