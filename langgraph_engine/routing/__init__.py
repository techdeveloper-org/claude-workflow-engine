"""Routing module - All conditional routing functions for the pipeline graph.

Extracted from orchestrator.py to separate routing decisions from graph construction.
Each level has its own routing submodule.

CHANGE LOG (v1.15.0):
  Removed route_after_step1_decision export -- Step 1 no longer exists in the
  active pipeline graph (removed in v1.13.0). Kept stub in level3_routes.py
  for backward-compat test imports only.
"""

from .level3_routes import route_after_step11_review
from .level_minus1_routes import route_after_level_minus1, route_after_level_minus1_user_choice

__all__ = [
    "route_after_level_minus1",
    "route_after_level_minus1_user_choice",
    "route_after_step11_review",
]
