"""
MCPResponse - Builder Pattern for structured MCP tool responses.

Replaces 11 identical copies of `_json()` and 109 manual dict constructions
across all MCP servers with a fluent, type-safe builder.

Design Pattern: Builder
  - Fluent interface for chaining: MCPResponse.ok().data("key", val).build()
  - Immutable output (returns JSON string, not mutable dict)
  - Consistent timestamp injection
  - Backward compatible with existing _json() callers

Usage:
    # Simple success
    return success(branch="main", commits=5)

    # Simple error
    return error("NOT_FOUND", "File not found", suggestion="Check path")

    # Builder for complex responses
    return (MCPResponse.ok()
        .message("PR created")
        .data("pr_number", 42)
        .data("url", "https://...")
        .build())

Windows-Safe: ASCII only (cp1252 compatible)
"""

import json
from datetime import datetime
from typing import Any, Optional


class MCPResponse:
    """Fluent builder for MCP tool JSON responses.

    Implements the Builder pattern - construct responses step by step,
    then call .build() to produce the final JSON string.
    """

    __slots__ = ("_payload",)

    def __init__(self, is_success: bool = True):
        self._payload = {"success": is_success}

    # -- Factory Methods (static constructors) --

    @classmethod
    def ok(cls) -> "MCPResponse":
        """Create a success response builder."""
        return cls(is_success=True)

    @classmethod
    def fail(cls) -> "MCPResponse":
        """Create a failure response builder."""
        return cls(is_success=False)

    # -- Builder Methods (fluent chaining) --

    def message(self, msg: str) -> "MCPResponse":
        """Set human-readable message."""
        self._payload["message"] = msg
        return self

    def error_detail(self, error_type: str, msg: str,
                     suggestion: Optional[str] = None) -> "MCPResponse":
        """Set structured error details."""
        self._payload["error_type"] = error_type
        self._payload["error"] = msg
        if suggestion:
            self._payload["suggestion"] = suggestion
        return self

    def data(self, key: str, value: Any) -> "MCPResponse":
        """Add a single key-value pair to the response."""
        self._payload[key] = value
        return self

    def merge(self, mapping: dict) -> "MCPResponse":
        """Merge a dictionary into the response payload."""
        self._payload.update(mapping)
        return self

    def timestamp(self) -> "MCPResponse":
        """Add current timestamp to response."""
        self._payload["timestamp"] = datetime.now().isoformat()
        return self

    # -- Terminal Operations --

    def build(self) -> str:
        """Build the final JSON string. Terminal operation."""
        return json.dumps(self._payload, indent=2, default=str)

    def to_dict(self) -> dict:
        """Return payload as dict (for internal composition)."""
        return dict(self._payload)


# ---------------------------------------------------------------------------
# Module-level convenience functions (direct replacements for _json())
# ---------------------------------------------------------------------------

def to_json(data: dict) -> str:
    """Drop-in replacement for the duplicated _json() across all servers.

    This is the simplest migration path - rename `_json` to `to_json`
    and import from base.response.
    """
    return json.dumps(data, indent=2, default=str)


def success(**kwargs) -> str:
    """Build a success JSON response in one call.

    Usage:
        return success(branch="main", commits=5)
        # -> {"success": true, "branch": "main", "commits": 5}
    """
    payload = {"success": True}
    payload.update(kwargs)
    return json.dumps(payload, indent=2, default=str)


def error(msg: str, error_type: str = "ERROR", **kwargs) -> str:
    """Build an error JSON response in one call.

    Usage:
        return error("File not found", error_type="NOT_FOUND")
        # -> {"success": false, "error": "File not found", "error_type": "NOT_FOUND"}
    """
    payload = {"success": False, "error": msg}
    if error_type != "ERROR":
        payload["error_type"] = error_type
    payload.update(kwargs)
    return json.dumps(payload, indent=2, default=str)
