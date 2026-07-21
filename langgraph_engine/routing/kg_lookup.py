"""KG lookup ports (FR-3, C8) -- DecisionTreeTraverser and DomainKGReader.

Pure-Python readers behind the KGRouter facade (HLD Section 7.2, ADR-3). Read
sibling-library JSON through the ResourceResolver port (HLD Section 7.1);
never load the Master KG's large ``_all.json`` registries or
``super_graph.json``; never raise on a malformed-JSON parse/lookup miss (they
return an empty result so KGRouter can emit ``status=unresolved``).
``LibrarySetupError`` is the one exception that is allowed to propagate --
per HLD Section 9.1 it is caught at the KGRouter node boundary, not here.

Domain-signal derivation (DecisionTreeTraverser.route): the decision tree's
D01-D12 nodes are ``decision_source: "human"`` PRE-FLIGHT questions for
starting a brand-new orchestration session (greenfield/brownfield, "run
Phase 0?", ...). They do not apply to routing a single already-scoped task
inside an already-running pipeline step, and there is no human available to
answer them here, so traversal enters directly at D14 (``decision_source:
"auto"``), the collaboration-pattern-by-primary-domain node. D14's 36
branches each read "primary domain == domain:X -> Pattern N"; the primary
domain itself is derived by a keyword-overlap scorer (DSA Section 6.1: O(P),
P=36) between the task description's tokens and each pattern's title +
lead_domain tokens, mirroring D14's own keyword-based routing intent. A
small stopword list excludes generic words (article/preposition plus
project-scaffolding filler like "build"/"app"/"system") that would otherwise
score against nearly every pattern and defeat the signal. Ties across
patterns sharing one domain (e.g. Pattern 1 vs Pattern 4, both
domain:frontend-engineering) are broken by the D14 branch's ``is_default``
flag; a tie with no unique default winner is genuinely ambiguous and yields
``status=unresolved`` rather than guessing (HLD ADR-3 risk table).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

from ..library.resolver import LibrarySetupError, ResourceResolver

_PATTERNS_RELPATH = "knowledge-graph/_orchestration-decision-tree/patterns.json"
_BRANCHES_RELPATH = "knowledge-graph/_orchestration-decision-tree/decision_branches.json"

_MIN_SCORE = 1

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "be",
        "this",
        "that",
        "it",
        "as",
        "by",
        "at",
        "from",
        "we",
        "you",
        "need",
        "needs",
        "needed",
        "want",
        "wants",
        "wanted",
        "build",
        "building",
        "create",
        "creating",
        "make",
        "making",
        "add",
        "adding",
        "using",
        "use",
        "new",
        "project",
        "app",
        "apps",
        "application",
        "applications",
        "system",
        "systems",
        "please",
        "task",
        "tasks",
        "work",
        "working",
    }
)


def _tokenize(text: str) -> "set[str]":
    """Lowercase-tokenize ``text`` into alphanumeric words, dropping stopwords
    and words shorter than 3 characters.
    """
    tokens = _TOKEN_RE.findall((text or "").lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def normalize_kg_ref(ref: str) -> str:
    """Convert a Master-KG-style ref (``"agent:app_squad_lead"``,
    ``"domain:frontend-engineering"``) into the library's flat hyphenated
    slug (``"app-squad-lead"``, ``"frontend-engineering"``) used by
    ``agents/{slug}/agent.md`` and per-domain ``agents.json`` ``id`` fields.

    Verified against the real sibling library: ``patterns.json`` entries use
    ``"agent:app_squad_lead"`` / ``"domain:frontend-engineering"``; the
    corresponding directory is ``agents/app-squad-lead/`` and the matching
    ``knowledge-graph/frontend-engineering/agents.json`` entry's ``id`` field
    is the already-hyphenated ``"react-engineer"`` style (no prefix, no
    underscores) -- so the transform is: strip an ``"agent:"``/``"domain:"``
    prefix if present, then replace underscores with hyphens.
    """
    if not ref:
        return ""
    slug = ref.split(":", 1)[-1] if ":" in ref else ref
    return slug.replace("_", "-")


@dataclass(frozen=True)
class RoutingSignals:
    """Input to ``DecisionTreeTraverser.route`` -- the free-text task
    description a single Step 0 pre-routing call is scoped to.
    """

    task_description: str


@dataclass(frozen=True)
class DecisionPath:
    """Result of ``DecisionTreeTraverser.route``.

    ``pattern_id`` is ``None`` when no pattern scored above the minimum
    keyword-overlap threshold, or when a tie could not be broken
    deterministically. ``trace`` is an ordered list of human-readable steps;
    KGRouter joins them into the ``"Path: ... -> Outcome: ..."`` string
    written to ``FlowState["routing"]["trace"]``. ``stopped_at_human`` is
    always ``False`` for per-task routing -- the human D01-D12 PRE-FLIGHT
    nodes are never entered (see module docstring).
    """

    pattern_id: Optional[str]
    trace: List[str]
    stopped_at_human: bool


@dataclass(frozen=True)
class AgentRef:
    """A concrete agent resolved from a domain's ``agents.json``.

    ``mandatory_skills`` is an extension beyond the HLD Section 7.2 port
    contract's 5-field shape: real per-domain ``agents.json`` files often
    embed the agent's mandatory-skill list directly on the entry (verified
    across frontend-engineering, healthcare, mobile-engineering). KGRouter
    uses it as a fallback when ``relationships.json`` yields no edges for
    the agent (see ``DomainKGReader.skills_for_agent`` docstring for why
    that is common), rather than a second, less reliable file read.
    """

    id: str
    name: str
    agent_md_relpath: str
    model: str
    role: str
    mandatory_skills: List[str]


class DecisionTreeTraverser:
    """Reads ``patterns.json`` + the D14 slice of ``decision_branches.json``
    through the ``ResourceResolver`` port and resolves a task description to
    a collaboration pattern.
    """

    def __init__(self, resolver: ResourceResolver):
        self._resolver = resolver

    def route(self, signals: RoutingSignals) -> DecisionPath:
        """Resolve ``signals.task_description`` to a pattern via D14 keyword
        matching. Never raises ``LibrarySetupError`` is the sole exception
        allowed to propagate (caught by KGRouter); malformed JSON content
        yields ``DecisionPath(None, ...)`` instead of raising.
        """
        entry_note = "D14(auto, entry point -- D01-D13 not applicable to per-task routing)"
        task_tokens = _tokenize(signals.task_description)
        if not task_tokens:
            return DecisionPath(
                None, [entry_note, "no usable tokens in task_description", "Outcome: unresolved"], False
            )

        try:
            patterns = self._load_patterns()
            default_by_pattern = self._load_d14_defaults()
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(f"[DecisionTreeTraverser] malformed decision-tree JSON: {exc}")
            return DecisionPath(
                None, [entry_note, f"malformed decision-tree data ({exc})", "Outcome: unresolved"], False
            )

        best_score = 0
        best_patterns: List[dict] = []
        for pattern in patterns:
            title = pattern.get("title", "")
            lead_domain = pattern.get("lead_domain", "")
            domain_slug = normalize_kg_ref(lead_domain)
            pattern_tokens = _tokenize(title) | _tokenize(domain_slug.replace("-", " "))
            score = len(task_tokens & pattern_tokens)
            if score > best_score:
                best_score = score
                best_patterns = [pattern]
            elif score == best_score and score > 0:
                best_patterns.append(pattern)

        if best_score < _MIN_SCORE or not best_patterns:
            return DecisionPath(
                None, [entry_note, f"no pattern scored >= {_MIN_SCORE} keyword overlap", "Outcome: unresolved"], False
            )

        if len(best_patterns) == 1:
            chosen = best_patterns[0]
            detail = f"unique highest keyword-overlap score={best_score}"
        else:
            tied_domains = {normalize_kg_ref(p.get("lead_domain", "")) for p in best_patterns}
            defaults = [p for p in best_patterns if default_by_pattern.get(p.get("id"))]
            if len(tied_domains) == 1 and len(defaults) == 1:
                chosen = defaults[0]
                detail = (
                    f"tie among {len(best_patterns)} patterns for domain={next(iter(tied_domains))} "
                    f"at score={best_score} broken by D14 is_default"
                )
            else:
                pattern_ids = ", ".join(p.get("id", "?") for p in best_patterns)
                reason = "cross-domain tie" if len(tied_domains) > 1 else "no unique is_default winner"
                return DecisionPath(
                    None,
                    [
                        entry_note,
                        f"ambiguous tie among [{pattern_ids}] at score={best_score} ({reason})",
                        "Outcome: unresolved",
                    ],
                    False,
                )

        pattern_id = chosen.get("id")
        return DecisionPath(pattern_id, [entry_note, detail, f"Outcome: {pattern_id}"], False)

    def _load_patterns(self) -> List[dict]:
        resource = self._resolver.fetch_kg_file(_PATTERNS_RELPATH)
        data = json.loads(resource.content)
        if not isinstance(data, list):
            raise ValueError("patterns.json root is not a list")
        return data

    def _load_d14_defaults(self) -> Dict[str, bool]:
        resource = self._resolver.fetch_kg_file(_BRANCHES_RELPATH)
        data = json.loads(resource.content)
        if not isinstance(data, list):
            raise ValueError("decision_branches.json root is not a list")
        result: Dict[str, bool] = {}
        for branch in data:
            if branch.get("source") != "D14":
                continue
            emits = branch.get("emits") or []
            if emits:
                result[emits[0]] = bool(branch.get("is_default"))
        return result


_AGENTS_LIST_KEYS = ("agents", "nodes")
_EDGES_LIST_KEYS = ("edges",)
_SKILL_EDGE_TYPES = frozenset({"AGENT_USES_SKILL", "USES"})


def _coerce_list(data: object, wrapper_keys: "tuple[str, ...]") -> list:
    """Unwrap a per-domain KG JSON payload into a flat list of entry dicts.

    Verified against the real sibling library: roughly a third of the 36
    domain ``agents.json`` files are a bare top-level list (e.g.
    frontend-engineering's ``[{"id": "react-engineer", ...}, ...]``), but
    most are dict-wrapped with metadata alongside the list -- most commonly
    under an ``"agents"`` key (healthcare, finance, mobile-engineering), one
    observed case under ``"nodes"`` (edtech). ``relationships.json`` shows
    the same split, wrapped under ``"edges"`` (orchestration-meta-agents).
    Returns ``[]`` for any shape not recognized rather than raising --
    callers treat that as a normal miss, not a corruption.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in wrapper_keys:
            candidate = data.get(key)
            if isinstance(candidate, list):
                return candidate
    return []


class DomainKGReader:
    """Reads a single domain's ``agents.json`` + ``relationships.json``
    through the ``ResourceResolver`` port. Only ever reads the ONE matched
    domain's per-domain files -- never the Master KG's ``agents_all.json`` /
    ``skills_all.json`` / ``edges_all.json`` / ``super_graph.json``.

    The 36 per-domain KGs were authored across many builds with no enforced
    ``agents.json``/``relationships.json`` schema: the agent entry's ``id``
    field alone has at least five different conventions across domains
    (bare hyphenated ``"react-engineer"``, colon-prefixed
    ``"agent:ai-engineer"``, hyphen-prefixed ``"agent-app-squad-lead"``,
    underscore-prefixed ``"agent_hallucination_detector"``, and opaque codes
    like ``"A001"``). The entry's ``name`` field, by contrast, was verified
    consistently equal to the bare hyphenated slug matching
    ``agents/{slug}/agent.md`` across every sampled domain regardless of its
    ``id`` convention -- so KGRouter matches a pattern's normalized
    ``lead_agent`` against ``AgentRef.name``, never ``AgentRef.id``.
    ``relationships.json`` edge keys drift the same way (``source``/``type``
    vs ``source_id``/``edge_type``) and the skill-edge type value itself is
    ``"AGENT_USES_SKILL"`` in some domains and ``"USES"`` in others --
    ``skills_for_agent`` tolerates both.
    """

    def __init__(self, resolver: ResourceResolver):
        self._resolver = resolver

    def agents_for_domain(self, domain_slug: str) -> List[AgentRef]:
        """Return the agent roster for ``domain_slug``, or ``[]`` on a
        malformed/empty/unrecognized-shape file. ``LibrarySetupError``
        propagates (caught by KGRouter).
        """
        try:
            resource = self._resolver.fetch_kg_file(f"knowledge-graph/{domain_slug}/agents.json")
            data = json.loads(resource.content)
        except LibrarySetupError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(f"[DomainKGReader] malformed agents.json for domain={domain_slug}: {exc}")
            return []

        entries = _coerce_list(data, _AGENTS_LIST_KEYS)

        refs: List[AgentRef] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_id = entry.get("id") or entry.get("name")
            if not raw_id:
                continue
            name = entry.get("name") or normalize_kg_ref(raw_id)
            role = entry.get("description") or entry.get("role_summary") or entry.get("role") or ""
            mandatory_skills = [
                normalize_kg_ref(s) for s in (entry.get("mandatory_skills") or []) if isinstance(s, str)
            ]
            refs.append(
                AgentRef(
                    id=raw_id,
                    name=name,
                    agent_md_relpath=f"agents/{name}/agent.md",
                    model=entry.get("model", "sonnet"),
                    role=role,
                    mandatory_skills=mandatory_skills,
                )
            )
        return refs

    def skills_for_agent(self, domain_slug: str, agent_id: str) -> List[str]:
        """Return the skill-id list for the agent whose raw ``agents.json``
        ``id`` field is ``agent_id`` (not the normalized name -- edges
        reference the domain's native id convention), within
        ``domain_slug``. Returns ``[]`` on a malformed/empty/unrecognized-
        shape file, or when the domain records no skill-usage edges for this
        agent (callers fall back to ``AgentRef.mandatory_skills`` in that
        case). ``LibrarySetupError`` propagates (caught by KGRouter).
        """
        try:
            resource = self._resolver.fetch_kg_file(f"knowledge-graph/{domain_slug}/relationships.json")
            data = json.loads(resource.content)
        except LibrarySetupError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(f"[DomainKGReader] malformed relationships.json for domain={domain_slug}: {exc}")
            return []

        edges = _coerce_list(data, _EDGES_LIST_KEYS)

        skills: List[str] = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            edge_type = edge.get("type") or edge.get("edge_type")
            edge_source = edge.get("source") or edge.get("source_id")
            if edge_type in _SKILL_EDGE_TYPES and edge_source == agent_id:
                target = edge.get("target") or edge.get("target_id")
                if target:
                    skills.append(normalize_kg_ref(target))
        return skills
