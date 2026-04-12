# pre_tool_enforcer package
# Pre-tool enforcement logic split from pre-tool-enforcer.py
# Re-exports the main entry point for external callers.
from .core import main

__all__ = ["main"]
