# pre_tool_enforcer/registry.py
# PolicyRegistry: ordered list of policy check callables.
# Each check fn takes (tool_name, tool_input) and returns (blocked: bool, message: str).
# Windows-safe: ASCII only, no Unicode characters.


class PolicyRegistry(object):
    """Ordered list of policy check callables.

    Each registered callable receives (tool_name, tool_input) and must return
    a (blocked, message) 2-tuple.  The registry short-circuits on the first
    blocking result.  Errors inside individual checks are silently caught so
    a broken check never prevents a tool from running (fail-open).
    """

    def __init__(self):
        self._checks = []  # List of (name, callable)

    def register(self, name, fn):
        """Append a named check to the ordered list."""
        self._checks.append((name, fn))

    def run_all(self, tool_name, tool_input, session_id=None):
        """Run all checks in order. Return first block result or (False, '').

        Args:
            tool_name (str): Name of the tool about to be invoked.
            tool_input (dict): Parameters dict for the tool.
            session_id (str): Optional session ID (unused by checks, kept for future use).

        Returns:
            tuple: (blocked: bool, message: str)
        """
        for name, check in self._checks:
            try:
                blocked, msg = check(tool_name, tool_input)
                if blocked:
                    return True, msg
            except Exception:
                pass  # Fail-open: never block on check errors
        return False, ""
