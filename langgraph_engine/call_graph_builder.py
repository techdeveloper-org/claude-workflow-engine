"""Backward-compat shim for call_graph_builder.py.

All call graph logic has been refactored into the parsers/ package.
This file re-exports all public symbols so existing imports keep working.

Windows-safe: ASCII only, no Unicode characters.
"""

from .parsers.call_graph_builder_legacy import (  # noqa: F401
    CallGraphBuilder,
    _safe_avg,
    build_call_graph,
    get_call_graph_metrics,
    get_impact_analysis,
)
from .parsers.graph_model import CallGraph  # noqa: F401
from .parsers.python_parser import _CallGraphVisitor  # noqa: F401
