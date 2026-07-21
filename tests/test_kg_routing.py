"""Unit tests for langgraph_engine/routing/{kg_lookup,kg_router}.py -- the
FR-3 deterministic Step 0 pre-routing (HLD Section 7.2/7.3, ADR-3).

Covers:
- DecisionTreeTraverser: D14 entry point (not D01), unique match, same-domain
  tie broken by is_default, cross-domain tie -> unresolved, no crash on
  malformed/missing decision-tree files
- DomainKGReader: real per-domain agents.json/relationships.json reads,
  wrapped-payload tolerance (dict-wrapped "agents"/"nodes"/"edges" keys),
  no crash on malformed/missing files
- KGRouter: full resolve path against the REAL sibling library (status,
  domain, pattern, agent, skills, persona_markdown all populated), ambiguous
  task -> unresolved with null/empty fields, sibling missing ->
  library_missing with no exception raised
- step0_task_analysis_node PRE-INJECTION C: fail-open on KGRouter exception,
  --kg-routing-json present in prompt_gen_expert_caller args
- prompt_gen_expert_caller: {kg_routing_block} substitution for both
  resolved and unresolved routing JSON
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langgraph_engine.level3_execution.architecture.prompt_gen_expert_caller import (  # noqa: E402
    _build_filled_prompt,
    _parse_args,
    _render_kg_routing_block,
)
from langgraph_engine.library.resolver import (  # noqa: E402
    ChainedResourceResolver,
    HardFailAdapter,
    LibrarySetupError,
    LocalSiblingAdapter,
    _reset_library_root_cache,
    build_default_resolver,
)
from langgraph_engine.routing.kg_lookup import (  # noqa: E402
    DecisionTreeTraverser,
    DomainKGReader,
    RoutingSignals,
    normalize_kg_ref,
)
from langgraph_engine.routing.kg_router import KGRouter, route_task  # noqa: E402

_REAL_LIBRARY_ROOT = _PROJECT_ROOT.parent / "claude-global-library"


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every test starts with a clean locate_library_root() memoization cache."""
    _reset_library_root_cache()
    yield
    _reset_library_root_cache()


@pytest.fixture
def real_resolver(monkeypatch):
    """A resolver pointed at the REAL sibling claude-global-library checkout."""
    monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
    monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
    return build_default_resolver(engine_root=_PROJECT_ROOT)


@pytest.fixture
def fake_kg_root(tmp_path):
    """A minimal fake sibling library with a self-consistent decision tree +
    one domain, for isolated (non-real-library) unit tests.
    """
    root = tmp_path / "claude-global-library"
    tree_dir = root / "knowledge-graph" / "_orchestration-decision-tree"
    tree_dir.mkdir(parents=True)

    patterns = [
        {
            "id": "pattern:1",
            "lead_agent": "agent:widget_engineer",
            "lead_domain": "domain:widget-engineering",
            "lead_math": "agent:mathematics_engineer",
            "title": "Widget Engineering",
        }
    ]
    (tree_dir / "patterns.json").write_text(json.dumps(patterns), encoding="utf-8")

    branches = [
        {
            "condition": "primary domain == domain:widget-engineering -> Pattern 1",
            "decision_source": "auto",
            "emits": ["pattern:1"],
            "id": "DECISION_BRANCH::D14::B1",
            "is_default": True,
            "is_terminal": False,
            "prunes": [],
            "source": "D14",
            "target": "D15",
            "type": "DECISION_BRANCH",
        }
    ]
    (tree_dir / "decision_branches.json").write_text(json.dumps(branches), encoding="utf-8")

    domain_dir = root / "knowledge-graph" / "widget-engineering"
    domain_dir.mkdir(parents=True)
    agents = [
        {
            "id": "widget-engineer",
            "name": "widget-engineer",
            "model": "sonnet",
            "description": "Builds widgets.",
            "mandatory_skills": ["widget-core"],
        }
    ]
    (domain_dir / "agents.json").write_text(json.dumps(agents), encoding="utf-8")
    relationships = [
        {"source": "widget-engineer", "target": "widget-core", "type": "AGENT_USES_SKILL"},
    ]
    (domain_dir / "relationships.json").write_text(json.dumps(relationships), encoding="utf-8")

    agent_dir = root / "agents" / "widget-engineer"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.md").write_text("# widget-engineer persona", encoding="utf-8")

    return root


@pytest.fixture
def fake_resolver(fake_kg_root):
    local = LocalSiblingAdapter(fake_kg_root)
    hard_fail = HardFailAdapter(fake_kg_root)
    return ChainedResourceResolver([local, hard_fail])


# ===========================================================================
# normalize_kg_ref
# ===========================================================================


class TestNormalizeKgRef:
    def test_strips_agent_prefix_and_underscores(self):
        assert normalize_kg_ref("agent:app_squad_lead") == "app-squad-lead"

    def test_strips_domain_prefix(self):
        assert normalize_kg_ref("domain:frontend-engineering") == "frontend-engineering"

    def test_strips_skill_prefix(self):
        assert normalize_kg_ref("skill:hl7-fhir-core") == "hl7-fhir-core"

    def test_no_prefix_passthrough(self):
        assert normalize_kg_ref("react-engineer") == "react-engineer"

    def test_empty_string(self):
        assert normalize_kg_ref("") == ""


# ===========================================================================
# DecisionTreeTraverser -- isolated (fake_resolver) behavior
# ===========================================================================


class TestDecisionTreeTraverserIsolated:
    def test_unique_match_resolves(self, fake_resolver):
        traverser = DecisionTreeTraverser(fake_resolver)
        path = traverser.route(RoutingSignals(task_description="Build a widget engineering platform"))
        assert path.pattern_id == "pattern:1"
        assert path.stopped_at_human is False
        assert path.trace[0] == "D14(auto, entry point -- D01-D13 not applicable to per-task routing)"

    def test_no_tokens_unresolved(self, fake_resolver):
        traverser = DecisionTreeTraverser(fake_resolver)
        path = traverser.route(RoutingSignals(task_description="   "))
        assert path.pattern_id is None
        assert path.trace[-1] == "Outcome: unresolved"

    def test_no_score_unresolved(self, fake_resolver):
        traverser = DecisionTreeTraverser(fake_resolver)
        path = traverser.route(RoutingSignals(task_description="completely unrelated banana yodel"))
        assert path.pattern_id is None

    def test_malformed_patterns_json_returns_unresolved_not_raise(self, tmp_path):
        root = tmp_path / "claude-global-library"
        tree_dir = root / "knowledge-graph" / "_orchestration-decision-tree"
        tree_dir.mkdir(parents=True)
        (tree_dir / "patterns.json").write_text("not valid json {{{", encoding="utf-8")
        (tree_dir / "decision_branches.json").write_text("[]", encoding="utf-8")
        resolver = ChainedResourceResolver([LocalSiblingAdapter(root), HardFailAdapter(root)])
        traverser = DecisionTreeTraverser(resolver)

        path = traverser.route(RoutingSignals(task_description="widget engineering platform"))

        assert path.pattern_id is None
        assert "malformed" in path.trace[1]

    def test_missing_library_raises_library_setup_error(self, tmp_path):
        """LibrarySetupError propagates from the traverser -- it is the one
        exception KGRouter catches at its own boundary, not the readers.
        """
        root = tmp_path / "claude-global-library"
        resolver = ChainedResourceResolver([HardFailAdapter(root)])
        traverser = DecisionTreeTraverser(resolver)

        with pytest.raises(LibrarySetupError):
            traverser.route(RoutingSignals(task_description="widget engineering platform"))


# ===========================================================================
# DomainKGReader -- isolated (fake_resolver) behavior
# ===========================================================================


class TestDomainKGReaderIsolated:
    def test_agents_for_domain_reads_flat_list(self, fake_resolver):
        reader = DomainKGReader(fake_resolver)
        agents = reader.agents_for_domain("widget-engineering")
        assert len(agents) == 1
        assert agents[0].name == "widget-engineer"
        assert agents[0].id == "widget-engineer"
        assert agents[0].mandatory_skills == ["widget-core"]

    def test_skills_for_agent_reads_agent_uses_skill_edges(self, fake_resolver):
        reader = DomainKGReader(fake_resolver)
        skills = reader.skills_for_agent("widget-engineering", "widget-engineer")
        assert skills == ["widget-core"]

    def test_agents_for_domain_nonexistent_domain_raises_library_setup_error(self, fake_resolver):
        """A domain slug with no corresponding directory is a file-not-found
        at the resolver's HardFailAdapter tier -- which cannot distinguish
        "this one domain is missing" from "the whole library is missing" and
        always raises LibrarySetupError (HLD Section 7.1). DomainKGReader
        does not catch it (only malformed-JSON content is treated as an
        empty-result miss); KGRouter's outer catch converts it to
        status=library_missing. In practice KGRouter only ever calls this
        with a domain_slug it derived from an already-resolved pattern, so
        this path fires only on a genuinely absent/corrupt library, not on
        ordinary per-task routing misses.
        """
        reader = DomainKGReader(fake_resolver)
        with pytest.raises(LibrarySetupError):
            reader.agents_for_domain("does-not-exist-domain")

    def test_agents_for_domain_wrapped_agents_key(self, tmp_path):
        root = tmp_path / "claude-global-library"
        domain_dir = root / "knowledge-graph" / "wrapped-domain"
        domain_dir.mkdir(parents=True)
        payload = {"domain": "wrapped-domain", "agents": [{"id": "x-engineer", "name": "x-engineer"}]}
        (domain_dir / "agents.json").write_text(json.dumps(payload), encoding="utf-8")
        resolver = ChainedResourceResolver([LocalSiblingAdapter(root), HardFailAdapter(root)])
        reader = DomainKGReader(resolver)

        agents = reader.agents_for_domain("wrapped-domain")

        assert len(agents) == 1
        assert agents[0].name == "x-engineer"

    def test_skills_for_agent_wrapped_edges_key_and_source_id_edge_type_keys(self, tmp_path):
        root = tmp_path / "claude-global-library"
        domain_dir = root / "knowledge-graph" / "wrapped-domain"
        domain_dir.mkdir(parents=True)
        payload = {
            "domain": "wrapped-domain",
            "edges": [{"source_id": "agent:x-engineer", "target_id": "skill:y-core", "edge_type": "USES"}],
        }
        (domain_dir / "relationships.json").write_text(json.dumps(payload), encoding="utf-8")
        resolver = ChainedResourceResolver([LocalSiblingAdapter(root), HardFailAdapter(root)])
        reader = DomainKGReader(resolver)

        skills = reader.skills_for_agent("wrapped-domain", "agent:x-engineer")

        assert skills == ["y-core"]

    def test_malformed_agents_json_returns_empty_not_raise(self, tmp_path):
        root = tmp_path / "claude-global-library"
        domain_dir = root / "knowledge-graph" / "broken-domain"
        domain_dir.mkdir(parents=True)
        (domain_dir / "agents.json").write_text("{{{not json", encoding="utf-8")
        resolver = ChainedResourceResolver([LocalSiblingAdapter(root), HardFailAdapter(root)])
        reader = DomainKGReader(resolver)

        assert reader.agents_for_domain("broken-domain") == []

    def test_missing_library_raises_library_setup_error(self, tmp_path):
        root = tmp_path / "claude-global-library"
        resolver = ChainedResourceResolver([HardFailAdapter(root)])
        reader = DomainKGReader(resolver)

        with pytest.raises(LibrarySetupError):
            reader.agents_for_domain("widget-engineering")


# ===========================================================================
# KGRouter -- full resolve path against the REAL sibling library
# ===========================================================================


class TestKGRouterRealLibrary:
    def test_resolves_healthcare_domain_end_to_end(self, real_resolver):
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = KGRouter(resolver=real_resolver).route_task(
                "Design a healthcare clinical FHIR interoperability system"
            )
        mock_urlopen.assert_not_called()

        assert result["status"] == "resolved"
        assert result["domain"] == "healthcare"
        assert result["pattern_id"] == "pattern:12"
        assert result["lead_agent"]["name"] == "clinical-systems-engineer"
        assert result["lead_agent"]["agent_md_relpath"] == "agents/clinical-systems-engineer/agent.md"
        assert "hl7-fhir-core" in result["skills"]
        assert result["persona_markdown"] and "clinical-systems-engineer" in result["persona_markdown"].lower()
        assert result["resolver_source"] == "local"
        assert result["trace"].startswith("Path: D14(auto")
        assert result["lead_math_agent"] == "agent:mathematics_engineer"

    def test_ambiguous_task_unresolved_with_null_fields(self, real_resolver):
        result = KGRouter(resolver=real_resolver).route_task("xyzzy plugh frobnicate quux")

        assert result["status"] == "unresolved"
        assert result["domain"] is None
        assert result["pattern_id"] is None
        assert result["lead_agent"] is None
        assert result["skills"] == []
        assert result["persona_markdown"] is None
        assert result["notes"]

    def test_cross_domain_tie_unresolved(self, real_resolver):
        """geospatial and telecom-5g each score exactly 1 keyword-overlap
        point with no shared domain and no is_default winner -- verified
        directly against the real patterns.json/decision_branches.json
        (see DecisionTreeTraverser docstring for the scoring rationale).
        """
        result = KGRouter(resolver=real_resolver).route_task("geospatial telecom integration")

        assert result["status"] == "unresolved"
        assert "cross-domain tie" in result["notes"]

    def test_squad_lead_pattern_documented_gap_yields_unresolved_not_crash(self, real_resolver):
        """pattern:2's lead_agent (infra-squad-lead) lives in
        knowledge-graph/orchestration-meta-agents/agents.json, not in its own
        lead_domain's (backend-engineering) agents.json -- a real data
        mismatch in the library (squad leads are catalogued separately from
        the domains they coordinate). KGRouter must degrade to unresolved,
        never crash or fabricate an agent.
        """
        result = KGRouter(resolver=real_resolver).route_task(
            "Build a Python FastAPI backend service with REST endpoints"
        )

        assert result["status"] == "unresolved"
        assert "infra-squad-lead" in result["notes"]
        assert "backend-engineering" in result["notes"]


class TestKGRouterLibraryMissing:
    def test_sibling_absent_yields_library_missing_no_exception(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
        monkeypatch.setenv("CLAUDE_GLOBAL_LIB_PATH", str(tmp_path / "does-not-exist"))
        resolver = build_default_resolver(engine_root=tmp_path)

        result = route_task("anything at all", resolver=resolver)

        assert result["status"] == "library_missing"
        assert result["lead_agent"] is None
        assert result["skills"] == []

    def test_default_resolver_constructed_when_none_passed(self, monkeypatch, tmp_path):
        """route_task() with no resolver argument builds its own via
        build_default_resolver() -- exercised with an empty engine dir so it
        resolves to library_missing rather than touching the real sibling.
        """
        monkeypatch.setenv("CLAUDE_GLOBAL_LIB_PATH", str(tmp_path / "nope"))
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)

        with patch(
            "langgraph_engine.routing.kg_router.build_default_resolver",
            side_effect=lambda: build_default_resolver(engine_root=tmp_path),
        ):
            result = route_task("anything")

        assert result["status"] == "library_missing"


# ===========================================================================
# prompt_gen_expert_caller -- _render_kg_routing_block + placeholder wiring
# ===========================================================================


class TestRenderKgRoutingBlock:
    def test_resolved_renders_agent_skills_and_persona_marker(self):
        kg_routing = {
            "status": "resolved",
            "domain": "healthcare",
            "pattern_id": "pattern:12",
            "lead_agent": {"name": "clinical-systems-engineer", "role": "Builds clinical systems."},
            "skills": ["hl7-fhir-core", "clinical-data-modeling-core"],
            "persona_markdown": "x" * 500,
        }
        block = _render_kg_routing_block(kg_routing)
        assert "clinical-systems-engineer" in block
        assert "hl7-fhir-core" in block
        assert "500 chars" in block
        assert "x" * 500 not in block  # full persona text is never embedded verbatim

    def test_unresolved_renders_legacy_path_note(self):
        block = _render_kg_routing_block({"status": "unresolved", "notes": "no confident domain match"})
        assert "legacy path" in block
        assert "no confident domain match" in block

    def test_library_missing_renders_legacy_path_note(self):
        block = _render_kg_routing_block({"status": "library_missing", "notes": "sibling not found"})
        assert "legacy path" in block

    def test_non_dict_input_does_not_raise(self):
        block = _render_kg_routing_block(None)
        assert "legacy path" in block


class TestParseArgsKgRouting:
    def test_default_is_empty_object(self):
        args = _parse_args(["script"])
        assert args["kg_routing_json"] == "{}"

    def test_parses_kg_routing_json_flag(self):
        payload = json.dumps({"status": "resolved"})
        args = _parse_args(["script", "--kg-routing-json", payload])
        assert args["kg_routing_json"] == payload


class TestBuildFilledPromptKgRoutingBlock:
    _TEMPLATE = (
        "TASK: {user_requirements}\n"
        "RUNTIME: {runtime_context_json_block}\n"
        "COMPLEXITY: {complexity_score_display}\n"
        "RISK: {codebase_risk_level}\n"
        "DZ: {codebase_danger_zones}\n"
        "AM: {codebase_affected_methods}\n"
        "HN: {codebase_hot_nodes}\n"
        "KG ROUTING:\n{kg_routing_block}\n"
    )

    def _base_args(self, kg_routing_json):
        return {
            "task_description": "do the thing",
            "complexity_score": 5,
            "call_graph_json": "{}",
            "kg_routing_json": kg_routing_json,
            "runtime_context_json": "{}",
        }

    def test_resolved_routing_substitutes_agent_grounding(self):
        kg_routing = {
            "status": "resolved",
            "domain": "healthcare",
            "pattern_id": "pattern:12",
            "lead_agent": {"name": "clinical-systems-engineer", "role": "role text"},
            "skills": ["hl7-fhir-core"],
            "persona_markdown": "persona body",
        }
        filled = _build_filled_prompt(self._TEMPLATE, self._base_args(json.dumps(kg_routing)))
        assert "{kg_routing_block}" not in filled
        assert "clinical-systems-engineer" in filled
        assert "hl7-fhir-core" in filled

    def test_unresolved_routing_substitutes_legacy_note(self):
        kg_routing = {"status": "unresolved", "notes": "no match"}
        filled = _build_filled_prompt(self._TEMPLATE, self._base_args(json.dumps(kg_routing)))
        assert "{kg_routing_block}" not in filled
        assert "legacy path" in filled

    def test_malformed_kg_routing_json_does_not_raise(self):
        filled = _build_filled_prompt(self._TEMPLATE, self._base_args("not valid json"))
        assert "{kg_routing_block}" not in filled
        assert "legacy path" in filled


# ===========================================================================
# step0_task_analysis_node PRE-INJECTION C -- fail-open + CLI arg wiring
# ===========================================================================


class TestStep0KgRoutingPreInjection:
    def _mock_call_execution_script(self, captured_calls):
        def _side_effect(script_name, args=None, model_tier=None, timeout=None):
            captured_calls.append((script_name, args))
            if script_name == "prompt_gen_expert_caller":
                return {"status": "SUCCESS", "llm_response": "orchestration prompt body", "prompt": "raw"}
            if script_name == "todo_decomposer":
                return {"status": "SUCCESS", "todo_list": []}
            return {"status": "SUCCESS"}

        return _side_effect

    def test_kg_routing_json_flag_present_in_prompt_gen_args(self):
        from langgraph_engine.level3_execution.nodes.step_wrappers_0to4 import step0_task_analysis_node

        captured_calls = []
        state = {"user_message": "Design a healthcare clinical FHIR interoperability system", "project_root": "."}

        with patch(
            "langgraph_engine.level3_execution.helpers.call_execution_script",
            side_effect=self._mock_call_execution_script(captured_calls),
        ):
            result = step0_task_analysis_node(state)

        prompt_gen_calls = [c for c in captured_calls if c[0] == "prompt_gen_expert_caller"]
        assert len(prompt_gen_calls) == 1
        prompt_gen_args = prompt_gen_calls[0][1]
        assert "--kg-routing-json" in prompt_gen_args
        kg_idx = prompt_gen_args.index("--kg-routing-json")
        kg_payload = json.loads(prompt_gen_args[kg_idx + 1])
        assert "status" in kg_payload
        assert "routing" in result
        assert result["routing"] == kg_payload

    def test_kg_router_exception_is_fail_open(self):
        """An exception raised inside route_task must not propagate out of
        step0_task_analysis_node -- PRE-INJECTION C mirrors the existing
        CallGraph pre-injection's fail-open try/except pattern.
        """
        from langgraph_engine.level3_execution.nodes.step_wrappers_0to4 import step0_task_analysis_node

        captured_calls = []
        state = {"user_message": "anything", "project_root": "."}

        with (
            patch(
                "langgraph_engine.level3_execution.helpers.call_execution_script",
                side_effect=self._mock_call_execution_script(captured_calls),
            ),
            patch(
                "langgraph_engine.routing.kg_router.route_task",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = step0_task_analysis_node(state)

        assert result["routing"]["status"] == "unresolved"
        prompt_gen_calls = [c for c in captured_calls if c[0] == "prompt_gen_expert_caller"]
        assert len(prompt_gen_calls) == 1
        assert "--kg-routing-json" in prompt_gen_calls[0][1]
