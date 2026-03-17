"""
MCP Tool Decorators - Cross-cutting concerns for all 109 MCP tools.

Design Pattern: Decorator (structural)
  - Wraps tool functions with standardized error handling
  - Eliminates 109 identical try/except blocks across 11 servers
  - Adds optional logging, timing, and response normalization
  - Zero overhead when not needed (decorator is opt-in)

Before (repeated 109 times):
    @mcp.tool()
    def my_tool(arg: str) -> str:
        try:
            result = do_work(arg)
            return _json({"success": True, "result": result})
        except SomeError as e:
            return _json({"success": False, "error": str(e)})
        except Exception as e:
            return _json({"success": False, "error": str(e)})

After:
    @mcp.tool()
    @mcp_tool_handler
    def my_tool(arg: str) -> dict:
        result = do_work(arg)
        return {"result": result}  # auto-wrapped with success/error

Windows-Safe: ASCII only (cp1252 compatible)
"""

import functools
import json
import time
import traceback
from typing import Callable, Optional, Tuple, Type, Union


def mcp_tool_handler(
    func: Optional[Callable] = None,
    *,
    error_types: Tuple[Type[Exception], ...] = (Exception,),
    include_traceback: bool = False,
    log_duration: bool = False,
):
    """Decorator that wraps MCP tool functions with standardized error handling.

    The decorated function should return a dict (not JSON string).
    The decorator handles:
      1. Wrapping return dict with {"success": True, ...}
      2. Catching exceptions and returning {"success": False, "error": ...}
      3. JSON serialization of the final response
      4. Optional execution timing

    Args:
        func: The tool function to decorate (auto-detected when used without parens)
        error_types: Tuple of exception types to catch (default: all Exception)
        include_traceback: Include traceback snippet in error response
        log_duration: Add duration_ms to response

    Usage:
        # Simple (no args):
        @mcp.tool()
        @mcp_tool_handler
        def my_tool(x: str) -> dict:
            return {"result": x.upper()}

        # With options:
        @mcp.tool()
        @mcp_tool_handler(include_traceback=True, log_duration=True)
        def my_tool(x: str) -> dict:
            return {"result": x.upper()}
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> str:
            start = time.time() if log_duration else 0

            try:
                result = fn(*args, **kwargs)

                # If function already returns a string, pass through
                # (backward compat for gradual migration)
                if isinstance(result, str):
                    return result

                # If function returns a dict, wrap with success
                if isinstance(result, dict):
                    if "success" not in result:
                        result["success"] = True

                    if log_duration:
                        result["duration_ms"] = round(
                            (time.time() - start) * 1000
                        )

                    return json.dumps(result, indent=2, default=str)

                # If function returns None, treat as success with no data
                if result is None:
                    payload = {"success": True}
                    if log_duration:
                        payload["duration_ms"] = round(
                            (time.time() - start) * 1000
                        )
                    return json.dumps(payload, indent=2, default=str)

                # Anything else, wrap it
                return json.dumps(
                    {"success": True, "data": result},
                    indent=2,
                    default=str,
                )

            except error_types as e:
                err_payload = {
                    "success": False,
                    "error": str(e),
                }
                if include_traceback:
                    err_payload["traceback"] = traceback.format_exc()[-500:]
                if log_duration:
                    err_payload["duration_ms"] = round(
                        (time.time() - start) * 1000
                    )
                return json.dumps(err_payload, indent=2, default=str)

        return wrapper

    # Support both @mcp_tool_handler and @mcp_tool_handler(...)
    if func is not None:
        return decorator(func)
    return decorator


def validate_params(*required_params: str):
    """Decorator that validates required parameters before tool execution.

    Usage:
        @mcp.tool()
        @validate_params("session_id", "branch")
        @mcp_tool_handler
        def my_tool(session_id: str, branch: str) -> dict:
            ...

    Raises ValueError with clear message listing missing params.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Union[str, dict]:
            # Check kwargs for missing required params
            missing = [
                p for p in required_params
                if p not in kwargs or not kwargs[p]
            ]
            if missing:
                raise ValueError(
                    f"Missing required parameters: {', '.join(missing)}"
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator
