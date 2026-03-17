"""
Structured MCP error responses for consistent error handling across all MCP servers.

NOTE: For new code, prefer using base.response (MCPResponse, success, error, to_json)
and base.decorators (mcp_tool_handler). This module is kept for backward compatibility
with existing callers outside the MCP server layer.
"""

import json
import traceback
from datetime import datetime

# Re-export from base for convenience
try:
    from base.response import to_json, success as mcp_success, error as mcp_error
except ImportError:
    pass  # Fallback: functions below still work standalone


def mcp_error_response(error_type, message, details=None, suggestion=None):
    """Build a structured error response dict for MCP tool returns.

    Args:
        error_type: Short error category (e.g. "NOT_FOUND", "VALIDATION_ERROR", "IO_ERROR")
        message: Human-readable error description
        details: Optional dict with extra context
        suggestion: Optional fix suggestion string

    Returns:
        JSON string of the error response
    """
    response = {
        "status": "ERROR",
        "error_type": error_type,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    if details:
        response["details"] = details
    if suggestion:
        response["suggestion"] = suggestion
    return json.dumps(response, indent=2, default=str)


def mcp_success_response(data, message=None):
    """Build a structured success response.

    Args:
        data: The response payload dict
        message: Optional human-readable status message

    Returns:
        JSON string of the success response
    """
    response = {
        "status": "OK",
        "timestamp": datetime.now().isoformat(),
    }
    if message:
        response["message"] = message
    response["data"] = data
    return json.dumps(response, indent=2, default=str)


def mcp_safe_execute(func, error_type="INTERNAL_ERROR", fallback=None):
    """Execute a function with automatic error wrapping.

    Args:
        func: Callable to execute
        error_type: Error type string for failures
        fallback: Optional fallback return value

    Returns:
        Function result on success, or error response string on failure
    """
    try:
        return func()
    except Exception as e:
        return mcp_error_response(
            error_type=error_type,
            message=str(e),
            details={"traceback": traceback.format_exc()[-500:]},
        )
