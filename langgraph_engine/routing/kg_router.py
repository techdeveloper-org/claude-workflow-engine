"""KGRouter facade (FR-3, C7) -- the sole entry point Step 0's pre-injection
block calls. Composes DecisionTreeTraverser + DomainKGReader + a
ResourceResolver into the single ``FlowState["routing"]`` grounding object
documented in HLD Section 7.3 / ADR-3.

Fail-safe by construction: any ``LibrarySetupError`` raised anywhere in the
routing sequence (missing sibling, or a resource that should exist under a
present sibling but does not) is caught here and converted to
``status="library_missing"`` -- it never propagates into the pipeline (HLD
Section 9.1 escalation boundary). A resolvable library with no confident
domain match yields ``status="unresolved"``. Both cases return the same
schema shape with ``lead_agent``/``skills``/``persona_markdown`` empty, so
downstream consumers (prompt_gen_expert_caller) can gate on ``status`` alone
without a third branch.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

from ..library.resolver import LibrarySetupError, ResourceResolver, build_default_resolver
from .kg_lookup import DecisionTreeTraverser, DomainKGReader, RoutingSignals, normalize_kg_ref

_PATTERNS_RELPATH = "knowledge-graph/_orchestration-decision-tree/patterns.json"


def _empty_routing(status: str, notes: str) -> Dict[str, Any]:
    """Build the ``unresolved``/``library_missing`` shape of the
    ``FlowState["routing"]`` schema (HLD Section 7.3) -- every optional field
    null/empty so consumers cannot mistake it for a resolved route.
    """
    return {
        "status": status,
        "domain": None,
        "pattern_id": None,
        "lead_agent": None,
        "lead_math_agent": None,
        "skills": [],
        "persona_markdown": None,
        "trace": notes,
        "resolver_source": None,
        "notes": notes,
    }


class KGRouter:
    """Facade over ``DecisionTreeTraverser`` + ``DomainKGReader`` +
    ``ResourceResolver`` (HLD Section 6.2 Facade pattern).
    """

    def __init__(self, resolver: Optional[ResourceResolver] = None):
        self._resolver = resolver or build_default_resolver()
        self._traverser = DecisionTreeTraverser(self._resolver)
        self._reader = DomainKGReader(self._resolver)

    def route_task(self, task_description: str) -> Dict[str, Any]:
        """Resolve ``task_description`` to the ``FlowState["routing"]``
        grounding object. Never raises.
        """
        try:
            return self._route(task_description)
        except LibrarySetupError as exc:
            logger.warning(f"[KGRouter] library_missing: {exc}")
            return _empty_routing("library_missing", str(exc))

    def _route(self, task_description: str) -> Dict[str, Any]:
        signals = RoutingSignals(task_description=task_description or "")
        decision_path = self._traverser.route(signals)
        trace_str = "Path: " + " -> ".join(decision_path.trace) if decision_path.trace else ""

        if not decision_path.pattern_id:
            return _empty_routing("unresolved", trace_str or "no confident domain match")

        patterns_resource = self._resolver.fetch_kg_file(_PATTERNS_RELPATH)
        patterns = json.loads(patterns_resource.content)
        pattern = next((p for p in patterns if p.get("id") == decision_path.pattern_id), None)
        if pattern is None:
            return _empty_routing("unresolved", f"pattern {decision_path.pattern_id} not found in patterns.json")

        raw_lead_agent = pattern.get("lead_agent", "")
        raw_lead_domain = pattern.get("lead_domain", "")
        raw_lead_math = pattern.get("lead_math", "")

        domain_slug = normalize_kg_ref(raw_lead_domain)
        lead_agent_slug = normalize_kg_ref(raw_lead_agent)
        if not domain_slug or not lead_agent_slug:
            return _empty_routing("unresolved", f"pattern {decision_path.pattern_id} missing lead_domain/lead_agent")

        agents = self._reader.agents_for_domain(domain_slug)
        agent_ref = next((a for a in agents if a.name == lead_agent_slug), None)
        if agent_ref is None:
            return _empty_routing(
                "unresolved",
                f"lead_agent {lead_agent_slug} not found in knowledge-graph/{domain_slug}/agents.json",
            )

        skills = self._reader.skills_for_agent(domain_slug, agent_ref.id) or agent_ref.mandatory_skills
        agent_resource = self._resolver.fetch_agent(agent_ref.name)

        return {
            "status": "resolved",
            "domain": domain_slug,
            "pattern_id": decision_path.pattern_id,
            "lead_agent": {
                "id": raw_lead_agent,
                "name": agent_ref.name,
                "agent_md_relpath": agent_ref.agent_md_relpath,
                "model": agent_ref.model,
                "role": agent_ref.role,
            },
            "lead_math_agent": raw_lead_math or None,
            "skills": skills,
            "persona_markdown": agent_resource.content,
            "trace": trace_str,
            "resolver_source": agent_resource.source,
            "notes": "",
        }


def route_task(task_description: str, resolver: Optional[ResourceResolver] = None) -> Dict[str, Any]:
    """Module-level convenience wrapper -- builds a ``KGRouter`` and routes
    once. Step 0's pre-injection block calls this directly, mirroring the
    existing CallGraph pre-injection's function-call style rather than
    requiring callers to manage a ``KGRouter`` instance.
    """
    return KGRouter(resolver=resolver).route_task(task_description)
