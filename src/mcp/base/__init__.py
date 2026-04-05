"""
MCP Base Infrastructure - Reusable OOP foundations for all MCP servers.

Design Patterns Applied:
  - Builder Pattern:    ``MCPResponse`` for structured response construction
  - Decorator Pattern:  ``@mcp_tool_handler`` for cross-cutting error handling
  - Singleton Pattern:  ``LazyClient`` for shared resource initialization
  - Repository Pattern: ``AtomicJsonStore``, ``JsonlAppender`` for data persistence

Public API::

    from base import MCPResponse, mcp_tool_handler, AtomicJsonStore, LazyClient
    from base.response import to_json, success, error
    from base.clients import GitRepoClient, GitHubApiClient

Version: 1.1.0
Windows-Safe: ASCII only (cp1252 compatible)
"""

from .clients import LazyClient
from .decorators import mcp_tool_handler
from .persistence import AtomicJsonStore, JsonlAppender, SessionIdResolver
from .response import MCPResponse, error, success, to_json

__all__ = [
    "MCPResponse",
    "success",
    "error",
    "to_json",
    "mcp_tool_handler",
    "AtomicJsonStore",
    "JsonlAppender",
    "SessionIdResolver",
    "LazyClient",
]
