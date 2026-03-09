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

from .flow_state import FlowState
from .orchestrator import create_flow_graph
from .policy_node_adapter import PolicyNodeAdapter
from .hooks_decorator import with_hooks

__all__ = [
    'FlowState',
    'create_flow_graph',
    'PolicyNodeAdapter',
    'with_hooks',
]
