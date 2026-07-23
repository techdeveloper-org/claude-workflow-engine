"""Integration tests against the REAL claude-global-library sibling checkout.

Moved out of the main unit-test files (test_library_resolver.py,
test_import_manager.py, test_kg_routing.py, test_faithfulness_gate.py) because
they require the real `claude-global-library` repo checked out as a sibling
directory next to this repo. That layout exists on developer machines but not
on the GitHub Actions runner (which only checks out this single repo), so this
whole module is skipped there rather than hard-failing CI.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import utils.import_manager as import_manager_module  # noqa: E402
from langgraph_engine.library.resolver import (  # noqa: E402
    _reset_library_root_cache,
    build_default_resolver,
    locate_library_root,
)
from langgraph_engine.routing.kg_router import KGRouter  # noqa: E402
from utils.import_manager import ImportManager  # noqa: E402

_REAL_LIBRARY_ROOT = _PROJECT_ROOT.parent / "claude-global-library"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _REAL_LIBRARY_ROOT.is_dir(),
        reason="requires the claude-global-library sibling checkout (not present in CI)",
    ),
]


@pytest.fixture(autouse=True)
def _reset_resolver_state():
    """Each test gets a fresh resolver singleton and a clean locate_library_root() cache."""
    import_manager_module._resolver = None
    _reset_library_root_cache()
    yield
    import_manager_module._resolver = None
    _reset_library_root_cache()


@pytest.fixture
def real_resolver(monkeypatch):
    """A resolver pointed at the REAL sibling claude-global-library checkout."""
    monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
    monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
    return build_default_resolver(engine_root=_PROJECT_ROOT)


# ---------------------------------------------------------------------------
# From test_library_resolver.py
# ---------------------------------------------------------------------------


class TestLocateLibraryRootRealSibling:
    def test_real_sibling_repo_resolves(self, monkeypatch):
        """Integration check against the REAL sibling checkout on this machine."""
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        result = locate_library_root(_PROJECT_ROOT)
        assert result == _REAL_LIBRARY_ROOT
        assert (result / "skills" / "docker" / "SKILL.md").is_file()
        assert (result / "agents" / "python-backend-engineer" / "agent.md").is_file()


class TestBuildDefaultResolverRealSibling:
    def test_real_sibling_resolves_locally_with_zero_network(self, monkeypatch):
        """End-to-end against the REAL sibling repo: docker skill resolves locally."""
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
        resolver = build_default_resolver(engine_root=_PROJECT_ROOT)

        with patch("urllib.request.urlopen") as mock_urlopen:
            resource = resolver.fetch_skill("docker")

        mock_urlopen.assert_not_called()
        assert resource.source == "local"
        assert "docker" in resource.content.lower()


# ---------------------------------------------------------------------------
# From test_import_manager.py
# ---------------------------------------------------------------------------


class TestGetSkillLocalHit:
    def test_docker_skill_resolves_locally_zero_network(self, monkeypatch):
        """Real integration: skills/docker/SKILL.md exists in the sibling checkout."""
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = ImportManager.get_skill("docker")

        mock_urlopen.assert_not_called()
        assert result is not None
        assert result["name"] == "docker"
        assert result["source"] == "local"
        assert "content" in result and len(result["content"]) > 0
        assert "url" in result

    def test_agent_resolves_locally(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = ImportManager.get_agent("python-backend-engineer")

        mock_urlopen.assert_not_called()
        assert result is not None
        assert result["source"] == "local"
        assert result["name"] == "python-backend-engineer"


# ---------------------------------------------------------------------------
# From test_kg_routing.py
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# From test_faithfulness_gate.py
# ---------------------------------------------------------------------------


def test_prompt_contains_real_skill_content():
    """build_faithfulness_prompt() must embed genuine hallucination-detection-core
    content, not an invented rubric. This reads the real SKILL.md from the
    sibling claude-global-library and asserts a specific, real phrase from it
    appears verbatim in the generated prompt."""
    from langgraph_engine.level3_execution import faithfulness_gate
    from langgraph_engine.level3_execution.faithfulness_gate import build_faithfulness_prompt

    resolver = build_default_resolver()
    resource = resolver.fetch_skill("hallucination-detection-core")

    # Real, specific phrases lifted directly from SKILL.md section 1 and 2
    # (not paraphrased): the extrinsic hallucination definition and the
    # source-level faithfulness aggregation formula.
    assert "The source neither entails nor contradicts c" in resource.content
    assert "faithfulness(g, S) = (1/|C(g)|)" in resource.content

    rubric_content = faithfulness_gate._extract_rubric_sections(resource.content)
    prompt = build_faithfulness_prompt(
        task_description="Add a function that returns 1",
        diff_summary="--- mod.py ---\ndef f():\n    return 1",
        rubric_content=rubric_content,
    )

    assert "faithfulness(g, S) = (1/|C(g)|)" in prompt, "Real NLI faithfulness formula must appear in the prompt"
    assert "Extrinsic Hallucination" in prompt, "Real taxonomy heading must appear in the prompt"
