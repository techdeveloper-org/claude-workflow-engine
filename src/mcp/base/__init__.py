"""
MCP Base Infrastructure - Reusable OOP foundations for all MCP servers.

Design Patterns Applied:
  - Builder Pattern:    MCPResponse for structured response construction
  - Decorator Pattern:  @mcp_tool_handler for cross-cutting error handling
  - Singleton Pattern:  LazyClient for shared resource initialization
  - Repository Pattern: AtomicJsonStore, JsonlAppender for data persistence
  - Strategy Pattern:   Pluggable serializers via MCPResponse

Usage:
    from base import MCPResponse, mcp_tool_handler, AtomicJsonStore, LazyClient

Version: 1.0.0
Windows-Safe: ASCII only (cp1252 compatible)
"""

from .response import MCPResponse, success, error, to_json
from .decorators import mcp_tool_handler
from .persistence import (
    AtomicJsonStore,
    JsonlAppender,
    SessionIdResolver,
)
from .clients import LazyClient

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
