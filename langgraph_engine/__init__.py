"""
LangGraph 3-Level Flow Engine

This package provides a StateGraph-based orchestration engine that replaces
the sequential 3-level-flow.py with parallel + conditional execution.

Key features:
- Parallel execution for Level 1 (4 independent context tasks)
- Conditional routing for Level 2 (Java-only standards loading)
- 12-step Level 3 execution with proper state transitions
- Session checkpointing with MemorySaver
- Backward-compatible flow-trace.json output

All existing policy scripts continue to work unchanged via PolicyNodeAdapter.
"""

__version__ = "1.19.1"

# Eager submodule imports to bind attributes on the `langgraph_engine` package.
# Required for unittest.mock.patch("langgraph_engine.<submodule>...") target
# resolution on Python 3.10, which does not always auto-import intermediate
# packages during attribute walks. Do NOT convert to `from ... import ...` -- tests
# patch attributes OF these submodules, not names re-exported from them.
from . import github_mcp  # noqa: F401  - required for mock.patch target binding
from . import github_operation_router  # noqa: F401  - required for mock.patch target binding
from . import level3_execution  # noqa: F401  - required for mock.patch target binding
from . import runtime_verification  # noqa: F401  - required for mock.patch target binding
from .backup_manager import BackupManager, create_backup_manager
from .checkpoint_manager import CheckpointManager, create_checkpoint_manager
from .error_logger import ErrorLogger, create_logger
from .flow_state import FlowState
from .hooks_decorator import with_hooks
from .metrics_collector import MetricsCollector, create_metrics_collector
from .orchestrator import create_flow_graph
from .policy_node_adapter import PolicyNodeAdapter
from .recovery_handler import RecoveryHandler, resume_from_checkpoint

__all__ = [
    "FlowState",
    "create_flow_graph",
    "PolicyNodeAdapter",
    "with_hooks",
    "CheckpointManager",
    "create_checkpoint_manager",
    "MetricsCollector",
    "create_metrics_collector",
    "RecoveryHandler",
    "resume_from_checkpoint",
    "ErrorLogger",
    "create_logger",
    "BackupManager",
    "create_backup_manager",
]
