"""Routing module - All conditional routing functions for the pipeline graph,
plus the deterministic KG-based Step 0 pre-routing facade (FR-3, ADR-3).

Extracted from orchestrator.py to separate routing decisions from graph construction.
Each level has its own routing submodule.

CHANGE LOG (v1.15.0):
  Removed route_after_step1_decision export -- Step 1 no longer exists in the
  active pipeline graph (removed in v1.13.0). Kept stub in level3_routes.py
  for backward-compat test imports only.

CHANGE LOG (FR-3):
  Added kg_lookup.py (DecisionTreeTraverser, DomainKGReader -- HLD Section 7.2
  ports) and kg_router.py (KGRouter facade -- HLD Section 7.3) alongside the
  existing pipeline-graph routing submodules. Both concerns share this
  package's name ("routing") but are otherwise independent: the graph-routing
  functions decide which pipeline node runs next; KGRouter decides which
  domain/agent/skills a task description resolves to before Step 0's LLM call.
"""

from .kg_lookup import (  # noqa: F401
    AgentRef,
    DecisionPath,
    DecisionTreeTraverser,
    DomainKGReader,
    RoutingSignals,
    normalize_kg_ref,
)
from .kg_router import KGRouter, route_task  # noqa: F401
from .level3_routes import route_after_step11_review
from .level_minus1_routes import route_after_level_minus1, route_after_level_minus1_user_choice

__all__ = [
    "route_after_level_minus1",
    "route_after_level_minus1_user_choice",
    "route_after_step11_review",
    "AgentRef",
    "DecisionPath",
    "DecisionTreeTraverser",
    "DomainKGReader",
    "RoutingSignals",
    "normalize_kg_ref",
    "KGRouter",
    "route_task",
]
