"""
post_tool_tracker/policies/__init__.py - Policy enforcement sub-package.

Each module implements one policy check function that returns (bool, str):
  (True, message)  -> policy violated, caller must exit(2)
  (False, '')      -> policy satisfied, continue

Non-blocking policies always return (False, '').
"""
