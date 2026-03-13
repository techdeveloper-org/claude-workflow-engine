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


class SkillAgentLoader:
    """Loads skill and agent definitions from ~/.claude/ filesystem structure.

    This loader is critical for context enrichment:
    1. Step 5 (Skill Selection) calls list_all_skills() to get all skill definitions
    2. LLM sees full skill definitions (capabilities, patterns, tools, constraints)
    3. Step 5 selects best skill WITH understanding of what it can do
    4. Step 7 (Final Prompt) calls load_skill() to get selected skill definition
    5. Final prompt includes skill definition in system prompt

    This solves the problem: "LLM selecting skill without knowing what it can do"
    """

    def __init__(self):
        """Initialize paths for skills and agents directories."""
        self.home = Path.home()
        self.skills_dir = self.home / ".claude" / "skills"
        self.agents_dir = self.home / ".claude" / "agents"

        logger.info(f"SkillAgentLoader initialized: skills={self.skills_dir}, agents={self.agents_dir}")

    def load_skill(self, skill_name: str) -> Optional[str]:
        """Load full SKILL.md content for a specific skill.

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
        skill_files = list(self.skills_dir.glob(f"*/{skill_name}/SKILL.md"))

        if not skill_files:
            # Also try direct path
            skill_file = self.skills_dir / skill_name / "SKILL.md"
            if not skill_file.exists():
                skill_file = self.skills_dir / skill_name / "skill.md"
                if not skill_file.exists():
                    logger.warning(f"Skill not found: {skill_name}")
                    return None
        else:
            skill_file = skill_files[0]

        try:
            content = skill_file.read_text(encoding='utf-8')
            logger.info(f"Loaded skill: {skill_name} ({len(content)} bytes)")
            return content
        except Exception as e:
            logger.error(f"Failed to load skill {skill_name}: {e}")
            return None

    def load_agent(self, agent_name: str) -> Optional[str]:
        """Load full agent.md content for a specific agent.

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
            logger.warning(f"Agent not found: {agent_name}")
            return None

        try:
            content = agent_file.read_text(encoding='utf-8')
            logger.info(f"Loaded agent: {agent_name} ({len(content)} bytes)")
            return content
        except Exception as e:
            logger.error(f"Failed to load agent {agent_name}: {e}")
            return None

    def list_all_skills(self) -> Dict[str, str]:
        """Load all available skills with their full definitions.

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
        skills = {}

        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return skills

        # Search all subdirectories for skill definitions
        # Pattern: skills/domain/skill_name/SKILL.md
        for domain_dir in self.skills_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            for skill_dir in domain_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                # Try SKILL.md first, then skill.md
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    skill_file = skill_dir / "skill.md"

                if skill_file.exists():
                    skill_name = skill_dir.name
                    try:
                        content = skill_file.read_text(encoding='utf-8')
                        skills[skill_name] = content
                        logger.debug(f"Loaded skill: {skill_name} ({len(content)} bytes)")
                    except Exception as e:
                        logger.warning(f"Failed to load skill {skill_name}: {e}")

        logger.info(f"Loaded {len(skills)} total skills")
        return skills

    def list_all_agents(self) -> Dict[str, str]:
        """Load all available agents with their full definitions.

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
        agents = {}

        if not self.agents_dir.exists():
            logger.warning(f"Agents directory not found: {self.agents_dir}")
            return agents

        # Search agents directory for agent definitions
        # Pattern: agents/agent_name/agent.md
        for agent_dir in self.agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue

            agent_file = agent_dir / "agent.md"
            if agent_file.exists():
                agent_name = agent_dir.name
                try:
                    content = agent_file.read_text(encoding='utf-8')
                    agents[agent_name] = content
                    logger.debug(f"Loaded agent: {agent_name} ({len(content)} bytes)")
                except Exception as e:
                    logger.warning(f"Failed to load agent {agent_name}: {e}")

        logger.info(f"Loaded {len(agents)} total agents")
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
