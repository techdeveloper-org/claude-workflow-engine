# pre_tool_enforcer/compat.py
# Backward-compat wrappers that preserve the original function signatures
# from the monolithic pre-tool-enforcer.py.
#
# Original return convention: (hints: list[str], blocks: list[str])
# New policy return convention: (blocked: bool, message: str)
#
# These wrappers bridge between the two conventions so that tests and
# external callers that depend on the old signatures continue to work.
#
# Windows-safe: ASCII only, no Unicode characters.


def _wrap_bool_to_lists(new_fn):
    """Create a wrapper that converts (blocked, msg) -> (hints, blocks)."""

    def wrapper(*args, **kwargs):
        blocked, msg = new_fn(*args, **kwargs)
        if blocked:
            return [], [msg]
        return [], []

    wrapper.__name__ = new_fn.__name__
    wrapper.__doc__ = new_fn.__doc__
    return wrapper
