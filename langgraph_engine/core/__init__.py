"""Core reusable abstractions for the claude-workflow-engine pipeline.

This package consolidates cross-cutting utilities that were previously
duplicated across 20-30 individual pipeline modules.  Importing from
``core`` gives access to all public symbols without needing to know which
sub-module each symbol lives in.

Sub-modules
-----------
lazy_loader
    LazyLoader - cached factory for importing classes/functions at runtime
    without incurring import-time side effects or hard failures.

logger_factory
    get_logger - returns a loguru or stdlib logger with a single call,
    replacing the try/except loguru boilerplate in every module.

error_handler
    node_error_handler - decorator that wraps LangGraph node functions with
    standardised try/except, timing, and fallback result handling.

    safe_execute - decorator for non-critical side-effect operations that
    must never crash the pipeline (telemetry, audit logs, session saves).

    NodeResult - fluent builder for constructing LangGraph node return dicts.

integration_hook
    create_integration_hook - factory method that generates the 9 formerly
    duplicated apply_integration_stepN functions from a single template.

infrastructure
    get_infra - returns (and caches) per-session infrastructure objects
    (CheckpointManager, MetricsCollector, ErrorLogger, BackupManager).

    clear_infra_cache - removes cached infrastructure for a given session
    or clears the entire cache (useful in tests).

    _pipeline_start_times - module-level dict mapping session_id to the
    wall-clock time.time() when Step 0 started for that session.  Used
    to compute the total pipeline duration when Step 14 completes.
"""

from .error_handler import NodeResult, node_error_handler, safe_execute
from .infrastructure import _pipeline_start_times, clear_infra_cache, get_infra
from .integration_hook import create_integration_hook
from .lazy_loader import LazyLoader
from .logger_factory import get_logger
from .step_decorator import StepExecutionContext, create_step_node

__all__ = [
    # lazy_loader
    "LazyLoader",
    # logger_factory
    "get_logger",
    # error_handler
    "node_error_handler",
    "safe_execute",
    "NodeResult",
    # integration_hook
    "create_integration_hook",
    # infrastructure
    "get_infra",
    "clear_infra_cache",
    "_pipeline_start_times",
    # step_decorator
    "create_step_node",
    "StepExecutionContext",
]
