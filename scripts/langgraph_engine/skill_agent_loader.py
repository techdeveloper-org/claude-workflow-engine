"""
Skill and Agent Loader Utility

Loads full SKILL.md and agent.md definitions from filesystem for use in skill/agent selection
and final prompt generation. This enables LLM to understand complete capabilities instead of
just skill/agent names.

Key Methods:
- load_skill(skill_name) -> str: Load full SKILL.md content for a skill
- load_agent(agent_name) -> str: Load full agent.md content for an agent
- list_all_skills() -> Dict[str, str]: Load all 23 available skills with full definitions
- list_all_agents() -> Dict[str, str]: Load all 12 available agents with full definitions
"""

from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Optional performance modules (gracefully degraded if unavailable)
try:
    from .parallel_executor import parallel_load_all_skills, parallel_load_all_agents
    from .cache_system import get_pipeline_cache, cached_skill_load
    _PERF_AVAILABLE = True
except ImportError:
    _PERF_AVAILABLE = False


class SkillAgentLoader:
    """Loads skill and agent definitions from ~/.claude/ filesystem structure.

    This loader is critical for context enrichment:
    1. Step 5 (Skill Selection) calls list_all_skills() to get all skill definitions
    2. LLM sees full skill definitions (capabilities, patterns, tools, constraints)
    3. Step 5 selects best skill WITH understanding of what it can do
    4. Step 7 (Final Prompt) calls load_skill() to get selected skill definition
    5. Final prompt includes skill definition in system prompt

    This solves the problem: "LLM selecting skill without knowing what it can do"

    Performance enhancements (when perf modules available):
    - list_all_skills / list_all_agents use concurrent file loading (4 workers)
    - Individual skill loads are cached with 7-day TTL via cache_system
    """

    def __init__(self, use_cache: bool = True, use_parallel: bool = True):
        """Initialize paths for skills and agents directories.

        Args:
            use_cache: Enable skill definition cache (7-day TTL). Default True.
            use_parallel: Enable concurrent skill/agent loading. Default True.
        """
        self.home = Path.home()
        self.skills_dir = self.home / ".claude" / "skills"
        self.agents_dir = self.home / ".claude" / "agents"
        self._use_cache = use_cache and _PERF_AVAILABLE
        self._use_parallel = use_parallel and _PERF_AVAILABLE

        logger.info(
            "SkillAgentLoader initialized: skills=%s, agents=%s, cache=%s, parallel=%s",
            self.skills_dir, self.agents_dir, self._use_cache, self._use_parallel,
        )

    def load_skill(self, skill_name: str) -> Optional[str]:
        """Load full SKILL.md content for a specific skill.

        Uses skill-definitions cache (7-day TTL) when available.

        Args:
            skill_name: Name of the skill (e.g., "java-spring-boot-microservices")

        Returns:
            Full SKILL.md content as string, or None if not found

        Example:
            loader = SkillAgentLoader()
            content = loader.load_skill("java-spring-boot-microservices")
            # Returns full markdown definition with capabilities, patterns, tools, etc.
        """
        # Try to find skill in any subdirectory (skills are organized by domain)
        # Pattern: ~/.claude/skills/*/skill_name/SKILL.md
        skill_files = list(self.skills_dir.glob("*/{}/SKILL.md".format(skill_name)))

        if not skill_files:
            # Also try direct path
            skill_file = self.skills_dir / skill_name / "SKILL.md"
            if not skill_file.exists():
                skill_file = self.skills_dir / skill_name / "skill.md"
                if not skill_file.exists():
                    logger.warning("Skill not found: %s", skill_name)
                    return None
        else:
            skill_file = skill_files[0]

        try:
            if self._use_cache:
                cache = get_pipeline_cache()
                content = cached_skill_load(
                    skill_name,
                    str(skill_file),
                    lambda p: Path(p).read_text(encoding="utf-8"),
                    cache=cache,
                )
            else:
                content = skill_file.read_text(encoding='utf-8')
            logger.info("Loaded skill: %s (%d bytes)", skill_name, len(content))
            return content
        except Exception as e:
            logger.error("Failed to load skill %s: %s", skill_name, e)
            return None

    def load_agent(self, agent_name: str) -> Optional[str]:
        """Load full agent.md content for a specific agent.

        Uses skill-definitions cache (7-day TTL) when available.

        Args:
            agent_name: Name of the agent (e.g., "orchestrator-agent")

        Returns:
            Full agent.md content as string, or None if not found

        Example:
            loader = SkillAgentLoader()
            content = loader.load_agent("orchestrator-agent")
            # Returns full markdown definition with orchestration model, tools, etc.
        """
        agent_file = self.agents_dir / agent_name / "agent.md"

        if not agent_file.exists():
            logger.warning("Agent not found: %s", agent_name)
            return None

        try:
            if self._use_cache:
                cache = get_pipeline_cache()
                content = cached_skill_load(
                    "agent:{}".format(agent_name),
                    str(agent_file),
                    lambda p: Path(p).read_text(encoding="utf-8"),
                    cache=cache,
                )
            else:
                content = agent_file.read_text(encoding='utf-8')
            logger.info("Loaded agent: %s (%d bytes)", agent_name, len(content))
            return content
        except Exception as e:
            logger.error("Failed to load agent %s: %s", agent_name, e)
            return None

    def list_all_skills(self) -> Dict[str, str]:
        """Load all available skills with their full definitions.

        Uses concurrent file loading (4 workers) when parallel module is available,
        falling back to sequential loading otherwise.

        This is critical for Step 5 (Skill Selection) - LLM needs to see ALL options
        with full definitions before choosing the best match.

        Returns:
            Dictionary mapping skill_name -> full_skill_content
            Example: {"java-spring-boot-microservices": "...", "python-backend-engineer": "..."}

        Notes:
            - Scans all domains: backend/, frontend/, devops/, etc.
            - Handles both "SKILL.md" and "skill.md" naming conventions
            - Returns empty dict if no skills found
            - Logs count of skills loaded
        """
        if not self.skills_dir.exists():
            logger.warning("Skills directory not found: %s", self.skills_dir)
            return {}

        if self._use_parallel:
            skills = parallel_load_all_skills(self.skills_dir)
            # Filter empty results
            skills = {k: v for k, v in skills.items() if v}
            logger.info("Loaded %d total skills (parallel)", len(skills))
            return skills

        # Sequential fallback
        skills: Dict[str, str] = {}
        for domain_dir in self.skills_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            for skill_dir in domain_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    skill_file = skill_dir / "skill.md"
                if skill_file.exists():
                    skill_name = skill_dir.name
                    try:
                        content = skill_file.read_text(encoding='utf-8')
                        skills[skill_name] = content
                        logger.debug("Loaded skill: %s (%d bytes)", skill_name, len(content))
                    except Exception as e:
                        logger.warning("Failed to load skill %s: %s", skill_name, e)

        logger.info("Loaded %d total skills", len(skills))
        return skills

    def list_all_agents(self) -> Dict[str, str]:
        """Load all available agents with their full definitions.

        Uses concurrent file loading (4 workers) when parallel module is available.

        This is critical for Step 5 (Skill Selection) - LLM needs to know what agents
        are available for orchestration and coordination.

        Returns:
            Dictionary mapping agent_name -> full_agent_content
            Example: {"orchestrator-agent": "...", "spring-boot-microservices": "..."}

        Notes:
            - Each agent is in agents/agent_name/agent.md
            - Returns empty dict if no agents found
            - Logs count of agents loaded
        """
        if not self.agents_dir.exists():
            logger.warning("Agents directory not found: %s", self.agents_dir)
            return {}

        if self._use_parallel:
            agents = parallel_load_all_agents(self.agents_dir)
            agents = {k: v for k, v in agents.items() if v}
            logger.info("Loaded %d total agents (parallel)", len(agents))
            return agents

        # Sequential fallback
        agents: Dict[str, str] = {}
        for agent_dir in self.agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_file = agent_dir / "agent.md"
            if agent_file.exists():
                agent_name = agent_dir.name
                try:
                    content = agent_file.read_text(encoding='utf-8')
                    agents[agent_name] = content
                    logger.debug("Loaded agent: %s (%d bytes)", agent_name, len(content))
                except Exception as e:
                    logger.warning("Failed to load agent %s: %s", agent_name, e)

        logger.info("Loaded %d total agents", len(agents))
        return agents

    def get_skill_names(self) -> list:
        """Get list of all available skill names (for quick lookup).

        Returns:
            List of skill names: ["java-spring-boot-microservices", "python-backend-engineer", ...]
        """
        return list(self.list_all_skills().keys())

    def get_agent_names(self) -> list:
        """Get list of all available agent names (for quick lookup).

        Returns:
            List of agent names: ["orchestrator-agent", "spring-boot-microservices", ...]
        """
        return list(self.list_all_agents().keys())


def get_skill_agent_loader() -> SkillAgentLoader:
    """Factory function to get SkillAgentLoader instance (singleton pattern).

    Usage:
        loader = get_skill_agent_loader()
        skill_def = loader.load_skill("python-backend-engineer")
        all_skills = loader.list_all_skills()
    """
    return SkillAgentLoader()
