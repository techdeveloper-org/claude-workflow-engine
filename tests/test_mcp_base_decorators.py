"""
Tests for src/mcp/base/decorators.py - mcp_tool_handler and validate_params.

Covers:
- Dict return wrapped with {success: True, ...}
- Exception caught and returned as {success: False, error, error_type}
- String return passes through unchanged (backward compat)
- include_traceback flag adds traceback field on error
- log_duration flag adds duration_ms field
- Both decorator syntaxes: @mcp_tool_handler and @mcp_tool_handler(...)
- validate_params blocks missing/None params (raises ValueError)
- validate_params allows falsy values: 0, False, ""
- validate_params only checks explicitly listed params

ASCII-only: cp1252 safe for Windows.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "mcp"))

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(json_str):
    """Parse JSON string returned by decorated functions."""
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# mcp_tool_handler - Dict return
# ---------------------------------------------------------------------------


class TestMcpToolHandlerDictReturn:

    def test_mcp_tool_handler_wraps_dict_return(self):
        """Dict returned by tool gets {success: True} injected."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            return {"result": "hello"}

        data = _parse(my_tool())
        assert data["success"] is True
        assert data["result"] == "hello"

    def test_mcp_tool_handler_preserves_existing_success_field(self):
        """success field already in dict is not overwritten."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            return {"success": False, "result": "kept"}

        data = _parse(my_tool())
        assert data["success"] is False
        assert data["result"] == "kept"

    def test_mcp_tool_handler_none_return_treated_as_success(self):
        """None return becomes {success: True} with no extra fields."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            return None

        data = _parse(my_tool())
        assert data["success"] is True


# ---------------------------------------------------------------------------
# mcp_tool_handler - Exception handling
# ---------------------------------------------------------------------------


class TestMcpToolHandlerExceptions:

    def test_mcp_tool_handler_catches_exception(self):
        """Exception is caught and returned as {success: False, error, error_type}."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            raise ValueError("something went wrong")

        data = _parse(my_tool())
        assert data["success"] is False
        assert "something went wrong" in data["error"]
        assert data["error_type"] == "ValueError"

    def test_mcp_tool_handler_error_type_matches_exception_class(self):
        """error_type field reflects the exact exception class name."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            raise FileNotFoundError("no file")

        data = _parse(my_tool())
        assert data["error_type"] == "FileNotFoundError"

    def test_mcp_tool_handler_specific_error_types(self):
        """Only listed error_types are caught; others propagate."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler(error_types=(ValueError,))
        def my_tool():
            raise TypeError("not caught")

        with pytest.raises(TypeError, match="not caught"):
            my_tool()

    def test_mcp_tool_handler_specific_error_types_caught(self):
        """Listed error_types are properly caught."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler(error_types=(ValueError, KeyError))
        def my_tool():
            raise KeyError("missing key")

        data = _parse(my_tool())
        assert data["success"] is False
        assert data["error_type"] == "KeyError"


# ---------------------------------------------------------------------------
# mcp_tool_handler - String passthrough
# ---------------------------------------------------------------------------


class TestMcpToolHandlerStringPassthrough:

    def test_mcp_tool_handler_string_passthrough(self):
        """String return value is passed through as-is (backward compat)."""
        from base.decorators import mcp_tool_handler

        raw_json = '{"already": "serialized"}'

        @mcp_tool_handler
        def my_tool():
            return raw_json

        assert my_tool() == raw_json


# ---------------------------------------------------------------------------
# mcp_tool_handler - include_traceback flag
# ---------------------------------------------------------------------------


class TestMcpToolHandlerIncludeTraceback:

    def test_mcp_tool_handler_include_traceback_present_on_error(self):
        """traceback field is included in error response when flag is True."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler(include_traceback=True)
        def my_tool():
            raise RuntimeError("trace me")

        data = _parse(my_tool())
        assert data["success"] is False
        assert "traceback" in data
        assert "RuntimeError" in data["traceback"]

    def test_mcp_tool_handler_no_traceback_by_default(self):
        """traceback field is absent by default."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            raise RuntimeError("no trace")

        data = _parse(my_tool())
        assert "traceback" not in data

    def test_mcp_tool_handler_traceback_limited_to_500_chars(self):
        """traceback is capped at 500 characters."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler(include_traceback=True)
        def my_tool():
            raise RuntimeError("x" * 1000)

        data = _parse(my_tool())
        assert len(data["traceback"]) <= 500


# ---------------------------------------------------------------------------
# mcp_tool_handler - log_duration flag
# ---------------------------------------------------------------------------


class TestMcpToolHandlerLogDuration:

    def test_mcp_tool_handler_log_duration_on_success(self):
        """duration_ms field is present in success response when flag is True."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler(log_duration=True)
        def my_tool():
            return {"value": 1}

        data = _parse(my_tool())
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], int)
        assert data["duration_ms"] >= 0

    def test_mcp_tool_handler_log_duration_on_error(self):
        """duration_ms field is present in error response when flag is True."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler(log_duration=True)
        def my_tool():
            raise ValueError("timed failure")

        data = _parse(my_tool())
        assert data["success"] is False
        assert "duration_ms" in data

    def test_mcp_tool_handler_no_duration_by_default(self):
        """duration_ms is absent when log_duration is not set."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            return {"value": 2}

        data = _parse(my_tool())
        assert "duration_ms" not in data


# ---------------------------------------------------------------------------
# mcp_tool_handler - Both syntaxes
# ---------------------------------------------------------------------------


class TestMcpToolHandlerBothSyntaxes:

    def test_mcp_tool_handler_bare_decorator_syntax(self):
        """Works as @mcp_tool_handler without parentheses."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def my_tool():
            return {"ok": True}

        data = _parse(my_tool())
        assert data["success"] is True

    def test_mcp_tool_handler_call_syntax(self):
        """Works as @mcp_tool_handler(...) with parentheses and options."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler(log_duration=True)
        def my_tool():
            return {"ok": True}

        data = _parse(my_tool())
        assert data["success"] is True
        assert "duration_ms" in data

    def test_mcp_tool_handler_preserves_function_name(self):
        """functools.wraps ensures __name__ and __doc__ are preserved."""
        from base.decorators import mcp_tool_handler

        @mcp_tool_handler
        def unique_function_name():
            """My docstring."""
            return {}

        assert unique_function_name.__name__ == "unique_function_name"
        assert "My docstring" in (unique_function_name.__doc__ or "")


# ---------------------------------------------------------------------------
# validate_params
# ---------------------------------------------------------------------------


class TestValidateParams:

    def test_validate_params_blocks_missing_kwarg(self):
        """ValueError is raised when a required kwarg is absent from the call."""
        from base.decorators import validate_params

        @validate_params("session_id", "branch")
        def my_tool(**kwargs):
            return kwargs

        with pytest.raises(ValueError, match="Missing required parameters"):
            my_tool(session_id="abc")  # branch is missing

    def test_validate_params_blocks_none_value(self):
        """ValueError is raised when a required kwarg is explicitly None."""
        from base.decorators import validate_params

        @validate_params("session_id")
        def my_tool(**kwargs):
            return kwargs

        with pytest.raises(ValueError, match="Missing required parameters"):
            my_tool(session_id=None)

    def test_validate_params_allows_falsy_zero(self):
        """0 is a valid value and must not be blocked by validate_params."""
        from base.decorators import validate_params

        @validate_params("count")
        def my_tool(**kwargs):
            return kwargs

        # Should not raise
        result = my_tool(count=0)
        assert result["count"] == 0

    def test_validate_params_allows_falsy_false(self):
        """False is a valid value and must not be blocked by validate_params."""
        from base.decorators import validate_params

        @validate_params("flag")
        def my_tool(**kwargs):
            return kwargs

        result = my_tool(flag=False)
        assert result["flag"] is False

    def test_validate_params_allows_falsy_empty_string(self):
        """Empty string is a valid value and must not be blocked."""
        from base.decorators import validate_params

        @validate_params("label")
        def my_tool(**kwargs):
            return kwargs

        result = my_tool(label="")
        assert result["label"] == ""

    def test_validate_params_allows_none_for_unchecked_param(self):
        """None is fine for params not listed in the decorator."""
        from base.decorators import validate_params

        @validate_params("required_param")
        def my_tool(**kwargs):
            return kwargs

        # optional_param is not checked, so None is fine
        result = my_tool(required_param="value", optional_param=None)
        assert result["required_param"] == "value"

    def test_validate_params_passes_through_on_valid_input(self):
        """Function is called normally when all required params are present."""
        from base.decorators import validate_params

        @validate_params("x", "y")
        def add(**kwargs):
            return kwargs["x"] + kwargs["y"]

        assert add(x=3, y=4) == 7

    def test_validate_params_preserves_function_name(self):
        """functools.wraps ensures __name__ is preserved on the wrapper."""
        from base.decorators import validate_params

        @validate_params("a")
        def my_named_tool(**kwargs):
            return kwargs

        assert my_named_tool.__name__ == "my_named_tool"
