"""Backward-compat shim -- canonical location is langgraph_engine.github.mcp."""

from langgraph_engine.github.mcp import *  # noqa: F401, F403

try:
    from langgraph_engine.github.mcp import PYGITHUB_AVAILABLE, GitHubMCP  # noqa: F401
except ImportError:
    PYGITHUB_AVAILABLE = False  # noqa: F841
