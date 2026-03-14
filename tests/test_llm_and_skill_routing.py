"""
Tests for LLM routing and skill/agent loader.

Covers:
- LLM routing: step classification to correct backend (GPU/Claude/skip)
- Skill loader: flat structure, legacy domain structure, missing skills
- Agent loader: load from agents/{name}/agent.md
- YAML frontmatter parsing from skill/agent content
"""

import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from langgraph_engine.hybrid_inference import HybridInferenceManager, StepType
from langgraph_engine.skill_agent_loader import SkillAgentLoader


# ===========================================================================
# Shared fixtures
# ===========================================================================

@pytest.fixture
def tmp_skills_dir(tmp_path):
    """Return a temporary ~/.claude/skills directory."""
    d = tmp_path / ".claude" / "skills"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def tmp_agents_dir(tmp_path):
    """Return a temporary ~/.claude/agents directory."""
    d = tmp_path / ".claude" / "agents"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader_with_dirs(tmp_skills_dir, tmp_agents_dir):
    """SkillAgentLoader pointed at isolated tmp directories, no parallel/cache."""
    loader = SkillAgentLoader(use_cache=False, use_parallel=False)
    loader.skills_dir = tmp_skills_dir
    loader.agents_dir = tmp_agents_dir
    return loader


@pytest.fixture
def manager_no_backends():
    """HybridInferenceManager with router mocked to have no backends."""
    with patch(
        "langgraph_engine.hybrid_inference.InferenceRouter",
        side_effect=RuntimeError("no backends"),
    ):
        m = HybridInferenceManager()
    m.router = None
    return m


# ===========================================================================
# LLM Routing Tests
# ===========================================================================

class TestLLMRoutingStepClassification:
    """Verify each step is classified to the correct StepType."""

    def test_step1_is_classification(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step1_plan_mode_decision"]["type"] == StepType.CLASSIFICATION

    def test_step3_is_lightweight(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step3_task_breakdown_validation"]["type"] == StepType.LIGHTWEIGHT_ANALYSIS

    def test_step5_is_deep_local(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step5_skill_agent_selection"]["type"] == StepType.DEEP_LOCAL

    def test_step0_is_deep_local(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step0_task_analysis"]["type"] == StepType.DEEP_LOCAL

    def test_step2_is_deep_local(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step2_plan_execution"]["type"] == StepType.DEEP_LOCAL

    def test_step4_is_no_llm(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step4_toon_refinement"]["type"] == StepType.NO_LLM

    def test_step7_is_deep_local(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step7_final_prompt_generation"]["type"] == StepType.DEEP_LOCAL

    def test_step14_is_deep_local(self):
        routing = HybridInferenceManager.STEP_ROUTING
        assert routing["step14_final_summary_generation"]["type"] == StepType.DEEP_LOCAL


class TestLLMRoutingNoLLMSteps:
    """Steps 6 and 8-14 must return 'skipped' without any LLM call."""

    NO_LLM_STEPS = [
        "step4_toon_refinement",
        "step6_skill_validation_download",
        "step8_github_issue_creation",
        "step9_branch_creation",
        "step11_pull_request_review",
        "step12_issue_closure",
        "step13_project_documentation_update",
    ]

    @pytest.mark.parametrize("step", NO_LLM_STEPS)
    def test_no_llm_step_returns_skipped(self, step, manager_no_backends):
        result = manager_no_backends.invoke(step=step, prompt="(unused)")
        assert result["status"] == "skipped"

    @pytest.mark.parametrize("step", NO_LLM_STEPS)
    def test_no_llm_step_never_calls_claude(self, step, manager_no_backends):
        with patch.object(manager_no_backends, "_invoke_claude") as mock_claude:
            manager_no_backends.invoke(step=step, prompt="(unused)")
            mock_claude.assert_not_called()


class TestLLMRoutingClassificationToGPU:
    """Step 1 should route to GPU when GPU is available."""

    def test_step1_calls_gpu_when_available(self):
        manager = HybridInferenceManager.__new__(HybridInferenceManager)
        manager.mode = "auto"
        manager.stats = {
            "npu_calls": 0,
            "claude_calls": 0,
            "npu_time_ms": 0,
            "claude_time_ms": 0,
            "total_cost": 0.0,
        }

        # Simulate GPU (Ollama) available
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = {
            "message": {"content": "plan_required: true"}
        }
        mock_router = MagicMock()
        mock_router.ollama = mock_ollama
        manager.router = mock_router

        result = manager.invoke(
            step="step1_plan_mode_decision",
            prompt="Should we plan this?",
        )

        assert result["source"] == "gpu"
        mock_ollama.chat.assert_called_once()

    def test_step1_fallback_to_claude_when_gpu_fails(self):
        manager = HybridInferenceManager.__new__(HybridInferenceManager)
        manager.mode = "auto"
        manager.stats = {
            "npu_calls": 0,
            "claude_calls": 0,
            "npu_time_ms": 0,
            "claude_time_ms": 0,
            "total_cost": 0.0,
        }

        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = RuntimeError("GPU offline")
        mock_router = MagicMock()
        mock_router.ollama = mock_ollama
        manager.router = mock_router

        expected = {"status": "ok", "source": "claude-api", "response": "fallback response"}
        with patch.object(manager, "_invoke_claude", return_value=expected) as mock_claude:
            result = manager.invoke(
                step="step1_plan_mode_decision",
                prompt="Should we plan this?",
            )
            mock_claude.assert_called_once()
        assert result["source"] == "claude-api"


class TestLLMRoutingComplexToClande:
    """Step 10 must reach _invoke_claude (only step that needs Claude tools)."""

    def test_step10_calls_invoke_claude(self, manager_no_backends):
        expected = {"status": "ok", "source": "claude-api", "response": "ok"}
        with patch.object(manager_no_backends, "_invoke_claude", return_value=expected) as mock:
            manager_no_backends.invoke(step="step10_implementation_execution", prompt="implement")
            mock.assert_called_once()


class TestLLMRoutingDeepLocal:
    """Steps 0, 2, 5, 7, 14 use deep local GPU (14B) with Claude fallback."""

    DEEP_LOCAL_STEPS = [
        "step0_task_analysis",
        "step2_plan_execution",
        "step5_skill_agent_selection",
        "step7_final_prompt_generation",
        "step14_final_summary_generation",
    ]

    @pytest.mark.parametrize("step", DEEP_LOCAL_STEPS)
    def test_deep_local_falls_back_to_claude_when_no_gpu(self, step, manager_no_backends):
        """When GPU unavailable, deep local steps fall back to Claude."""
        expected = {"status": "ok", "source": "claude-api", "response": "ok"}
        with patch.object(manager_no_backends, "_invoke_claude", return_value=expected) as mock:
            manager_no_backends.invoke(step=step, prompt="analyze this")
            mock.assert_called_once()


class TestLLMRoutingGPUFallback:
    """When GPU fails, classification step falls back to Claude."""

    def test_gpu_failure_falls_back_to_claude(self):
        manager = HybridInferenceManager.__new__(HybridInferenceManager)
        manager.mode = "auto"
        manager.stats = {
            "npu_calls": 0,
            "claude_calls": 0,
            "npu_time_ms": 0,
            "claude_time_ms": 0,
            "total_cost": 0.0,
        }

        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = ConnectionError("Ollama down")
        mock_router = MagicMock()
        mock_router.ollama = mock_ollama
        manager.router = mock_router

        claude_response = {"status": "ok", "source": "claude-api", "response": "yes"}
        with patch.object(manager, "_invoke_claude", return_value=claude_response) as mock_claude:
            result = manager.invoke(
                step="step1_plan_mode_decision",
                prompt="Do we need a plan?",
            )
            mock_claude.assert_called_once()
        assert result["status"] == "ok"


class TestModelSelectionCorrect:
    """Verify the model names configured for each step type are correct."""

    def test_step1_gpu_model_is_qwen(self):
        info = HybridInferenceManager.STEP_ROUTING["step1_plan_mode_decision"]
        assert "qwen" in info.get("gpu_model", "").lower()

    def test_step3_gpu_model_is_llama(self):
        info = HybridInferenceManager.STEP_ROUTING["step3_task_breakdown_validation"]
        assert "llama" in info.get("gpu_model", "").lower()

    def test_step5_gpu_model_is_14b(self):
        info = HybridInferenceManager.STEP_ROUTING["step5_skill_agent_selection"]
        assert "14b" in info.get("gpu_model", "").lower()

    def test_deep_local_steps_use_claude_fallback(self):
        deep_local_steps = [
            "step0_task_analysis",
            "step2_plan_execution",
            "step5_skill_agent_selection",
            "step7_final_prompt_generation",
            "step14_final_summary_generation",
        ]
        for step in deep_local_steps:
            info = HybridInferenceManager.STEP_ROUTING[step]
            assert "claude" in info.get("fallback_model", "").lower(), (
                "Expected claude fallback for %s" % step
            )


class TestUnknownStepRouting:
    """An unknown step name should still produce a result (Claude fallback)."""

    def test_unknown_step_calls_claude(self, manager_no_backends):
        expected = {"status": "ok", "source": "claude-api", "response": "ok"}
        with patch.object(manager_no_backends, "_invoke_claude", return_value=expected) as mock:
            result = manager_no_backends.invoke(step="step99_unknown", prompt="anything")
            mock.assert_called_once()
        assert result["status"] == "ok"


# ===========================================================================
# Skill Loader Tests
# ===========================================================================

class TestLoadSkillFlatStructure:
    """Skills in ~/.claude/skills/{name}/SKILL.md (flat structure)."""

    def test_loads_skill_from_flat_path(self, loader_with_dirs, tmp_skills_dir):
        skill_dir = tmp_skills_dir / "docker"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Docker Skill\nContent here.", encoding="utf-8")

        content = loader_with_dirs.load_skill("docker")
        assert content is not None
        assert "Docker Skill" in content

    def test_loads_skill_lowercase_filename(self, loader_with_dirs, tmp_skills_dir):
        skill_dir = tmp_skills_dir / "kubernetes"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Kubernetes", encoding="utf-8")

        content = loader_with_dirs.load_skill("kubernetes")
        assert content is not None
        assert "Kubernetes" in content

    def test_returns_none_for_missing_skill(self, loader_with_dirs):
        content = loader_with_dirs.load_skill("nonexistent-skill-xyz")
        assert content is None


class TestLoadSkillDomainStructure:
    """Legacy domain structure: skills/{domain}/{name}/SKILL.md."""

    def test_loads_skill_from_domain_path(self, loader_with_dirs, tmp_skills_dir):
        skill_dir = tmp_skills_dir / "backend" / "python-core"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Python Core", encoding="utf-8")

        content = loader_with_dirs.load_skill("python-core")
        assert content is not None
        assert "Python Core" in content


class TestListAllSkillsFlat:
    """list_all_skills() must discover all flat-structure skills."""

    def test_lists_all_flat_skills(self, loader_with_dirs, tmp_skills_dir):
        for name in ["docker", "kubernetes", "python-core"]:
            d = tmp_skills_dir / name
            d.mkdir()
            (d / "SKILL.md").write_text("# %s" % name, encoding="utf-8")

        skills = loader_with_dirs.list_all_skills()
        assert "docker" in skills
        assert "kubernetes" in skills
        assert "python-core" in skills

    def test_lists_skills_with_lowercase_filename(self, loader_with_dirs, tmp_skills_dir):
        d = tmp_skills_dir / "redis-core"
        d.mkdir()
        (d / "skill.md").write_text("# Redis Core", encoding="utf-8")

        skills = loader_with_dirs.list_all_skills()
        assert "redis-core" in skills

    def test_returns_empty_when_dir_missing(self, tmp_path):
        loader = SkillAgentLoader(use_cache=False, use_parallel=False)
        loader.skills_dir = tmp_path / "nonexistent"
        loader.agents_dir = tmp_path / "nonexistent_agents"
        skills = loader.list_all_skills()
        assert skills == {}

    def test_ignores_non_directory_entries(self, loader_with_dirs, tmp_skills_dir):
        # Place a stray file in the skills directory
        (tmp_skills_dir / "README.txt").write_text("ignored", encoding="utf-8")
        d = tmp_skills_dir / "real-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# Real Skill", encoding="utf-8")

        skills = loader_with_dirs.list_all_skills()
        assert "real-skill" in skills
        # The stray file should not appear as a key
        assert "README.txt" not in skills

    def test_flat_and_legacy_coexist(self, loader_with_dirs, tmp_skills_dir):
        # Flat
        flat_dir = tmp_skills_dir / "flat-skill"
        flat_dir.mkdir()
        (flat_dir / "SKILL.md").write_text("# Flat Skill", encoding="utf-8")

        # Legacy domain-based inside a domain folder that has no SKILL.md itself
        legacy_dir = tmp_skills_dir / "domain" / "legacy-skill"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "SKILL.md").write_text("# Legacy Skill", encoding="utf-8")

        skills = loader_with_dirs.list_all_skills()
        assert "flat-skill" in skills
        assert "legacy-skill" in skills


class TestLoadAgent:
    """Agent loading from agents/{name}/agent.md."""

    def test_loads_agent(self, loader_with_dirs, tmp_agents_dir):
        agent_dir = tmp_agents_dir / "python-backend-engineer"
        agent_dir.mkdir()
        (agent_dir / "agent.md").write_text("# Python Backend Agent", encoding="utf-8")

        content = loader_with_dirs.load_agent("python-backend-engineer")
        assert content is not None
        assert "Python Backend Agent" in content

    def test_returns_none_for_missing_agent(self, loader_with_dirs):
        content = loader_with_dirs.load_agent("no-such-agent-xyz")
        assert content is None

    def test_list_all_agents(self, loader_with_dirs, tmp_agents_dir):
        for name in ["orchestrator-agent", "devops-engineer"]:
            d = tmp_agents_dir / name
            d.mkdir()
            (d / "agent.md").write_text("# %s" % name, encoding="utf-8")

        agents = loader_with_dirs.list_all_agents()
        assert "orchestrator-agent" in agents
        assert "devops-engineer" in agents


# ===========================================================================
# YAML Frontmatter Parsing Tests
# ===========================================================================

class TestParseYAMLFrontmatter:
    """SkillAgentLoader.parse_skill_metadata() parses YAML frontmatter."""

    SKILL_WITH_FRONTMATTER = (
        "---\n"
        "name: docker\n"
        "version: 1.0.0\n"
        "description: Docker expert skill\n"
        "allowed-tools: Read,Glob,Grep,Bash\n"
        "user-invocable: true\n"
        "---\n"
        "# Docker Skill\n"
        "Content follows here.\n"
    )

    def test_parses_name_field(self, loader_with_dirs):
        meta = loader_with_dirs.parse_skill_metadata(self.SKILL_WITH_FRONTMATTER)
        assert meta.get("name") == "docker"

    def test_parses_version_field(self, loader_with_dirs):
        meta = loader_with_dirs.parse_skill_metadata(self.SKILL_WITH_FRONTMATTER)
        assert meta.get("version") == "1.0.0"

    def test_parses_description_field(self, loader_with_dirs):
        meta = loader_with_dirs.parse_skill_metadata(self.SKILL_WITH_FRONTMATTER)
        assert meta.get("description") == "Docker expert skill"

    def test_parses_allowed_tools(self, loader_with_dirs):
        meta = loader_with_dirs.parse_skill_metadata(self.SKILL_WITH_FRONTMATTER)
        assert meta.get("allowed-tools") == "Read,Glob,Grep,Bash"

    def test_parses_boolean_field(self, loader_with_dirs):
        meta = loader_with_dirs.parse_skill_metadata(self.SKILL_WITH_FRONTMATTER)
        assert meta.get("user-invocable") == "true"

    def test_returns_empty_when_no_frontmatter(self, loader_with_dirs):
        content = "# Just a plain skill\nNo frontmatter here."
        meta = loader_with_dirs.parse_skill_metadata(content)
        assert meta == {}

    def test_returns_empty_for_unclosed_frontmatter(self, loader_with_dirs):
        content = "---\nname: incomplete\n"
        meta = loader_with_dirs.parse_skill_metadata(content)
        assert meta == {}

    def test_returns_empty_for_empty_string(self, loader_with_dirs):
        meta = loader_with_dirs.parse_skill_metadata("")
        assert meta == {}

    def test_ignores_lines_without_colon(self, loader_with_dirs):
        content = "---\nname: valid\njust_a_line_no_colon\n---\n# Body\n"
        meta = loader_with_dirs.parse_skill_metadata(content)
        assert meta.get("name") == "valid"
        assert "just_a_line_no_colon" not in meta

    def test_preserves_colon_in_value(self, loader_with_dirs):
        content = "---\ndescription: Has: colon inside\n---\n# Body\n"
        meta = loader_with_dirs.parse_skill_metadata(content)
        # Only the first colon splits key from value
        assert meta.get("description") == "Has: colon inside"


# ===========================================================================
# Skill not found / error handling
# ===========================================================================

class TestSkillNotFound:
    """Verify graceful handling when skills are absent."""

    def test_load_skill_returns_none_when_skills_dir_missing(self, tmp_path):
        loader = SkillAgentLoader(use_cache=False, use_parallel=False)
        loader.skills_dir = tmp_path / "no_such_skills"
        loader.agents_dir = tmp_path / "no_such_agents"
        result = loader.load_skill("python-core")
        assert result is None

    def test_list_all_skills_returns_empty_when_dir_missing(self, tmp_path):
        loader = SkillAgentLoader(use_cache=False, use_parallel=False)
        loader.skills_dir = tmp_path / "no_such_skills"
        loader.agents_dir = tmp_path / "no_such_agents"
        skills = loader.list_all_skills()
        assert skills == {}

    def test_load_agent_returns_none_when_agents_dir_missing(self, tmp_path):
        loader = SkillAgentLoader(use_cache=False, use_parallel=False)
        loader.skills_dir = tmp_path / "no_such_skills"
        loader.agents_dir = tmp_path / "no_such_agents"
        result = loader.load_agent("some-agent")
        assert result is None


# ===========================================================================
# Integration: load skill then parse its metadata
# ===========================================================================

class TestLoadSkillAndParseMetadata:
    """Integration: load a flat-structure skill then parse its frontmatter."""

    def test_flat_skill_with_frontmatter_roundtrip(self, loader_with_dirs, tmp_skills_dir):
        content = (
            "---\n"
            "name: redis-core\n"
            "version: 2.0.0\n"
            "description: Redis skill\n"
            "---\n"
            "# Redis Core\n"
            "Full content.\n"
        )
        d = tmp_skills_dir / "redis-core"
        d.mkdir()
        (d / "SKILL.md").write_text(content, encoding="utf-8")

        loaded = loader_with_dirs.load_skill("redis-core")
        assert loaded is not None

        meta = loader_with_dirs.parse_skill_metadata(loaded)
        assert meta.get("name") == "redis-core"
        assert meta.get("version") == "2.0.0"
        assert meta.get("description") == "Redis skill"
