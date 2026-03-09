#!/usr/bin/env python3
"""
Core Skills Loader - Step 3.5 Pre-Enforcement

CRITICAL: Load skills BEFORE the LLM tries to use them!

Problem: LLM chooses skill → tries to invoke → FAIL (not loaded)
Solution: Load skill first, THEN make it available

Flow:
1. LLM decides to use skill X
2. THIS SCRIPT loads skill X from GitHub/disk
3. Cache it for immediate use
4. LLM then invokes /skill command
5. Skill already loaded → SUCCESS

Version: 1.0.0
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

MEMORY_BASE = Path.home() / '.claude' / 'memory'
SKILLS_DIR = MEMORY_BASE / 'loaded-skills'
AGENTS_DIR = MEMORY_BASE / 'loaded-agents'
SKILLS_CACHE = MEMORY_BASE / 'skills-cache.json'

# GitHub URLs
GITHUB_BASE = "https://raw.githubusercontent.com/piyushmakhija28"
GLOBAL_LIB_URL = f"{GITHUB_BASE}/claude-global-library/main"


class CoreSkillsLoader:
    """Load core skills BEFORE LLM invokes them."""

    def __init__(self):
        """Initialize loader with cache."""
        self.skills_dir = SKILLS_DIR
        self.agents_dir = AGENTS_DIR
        self.cache_file = SKILLS_CACHE
        self.loaded_skills = self._load_cache()

    def _load_cache(self):
        """Load previously loaded skills from cache."""
        if self.cache_file.exists():
            try:
                return json.loads(self.cache_file.read_text())
            except Exception:
                return {'skills': {}, 'agents': {}}
        return {'skills': {}, 'agents': {}}

    def load_skill(self, skill_name):
        """
        Load a skill from GitHub BEFORE LLM tries to use it.

        Returns:
            dict: {'name', 'status', 'loaded', 'path', 'content'}
        """
        # Check cache first
        if skill_name in self.loaded_skills['skills']:
            return {
                'name': skill_name,
                'status': 'cached',
                'loaded': True,
                'path': self.loaded_skills['skills'][skill_name]['path']
            }

        # Try to load from GitHub
        url = f"{GLOBAL_LIB_URL}/skills/{skill_name}/skill.md"

        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as response:
                content = response.read().decode('utf-8')

                # Save to local cache
                self.skills_dir.mkdir(parents=True, exist_ok=True)
                skill_file = self.skills_dir / f"{skill_name}.md"
                skill_file.write_text(content, encoding='utf-8')

                # Update cache
                self.loaded_skills['skills'][skill_name] = {
                    'path': str(skill_file),
                    'loaded_at': datetime.now().isoformat(),
                    'source': 'github'
                }
                self._save_cache()

                return {
                    'name': skill_name,
                    'status': 'loaded',
                    'loaded': True,
                    'path': str(skill_file),
                    'bytes': len(content)
                }

        except Exception as e:
            return {
                'name': skill_name,
                'status': 'failed',
                'loaded': False,
                'error': str(e)
            }

    def load_agent(self, agent_name):
        """Load an agent from GitHub BEFORE LLM tries to use it."""
        # Check cache first
        if agent_name in self.loaded_skills['agents']:
            return {
                'name': agent_name,
                'status': 'cached',
                'loaded': True,
                'path': self.loaded_skills['agents'][agent_name]['path']
            }

        # Try to load from GitHub
        url = f"{GLOBAL_LIB_URL}/agents/{agent_name}/agent.md"

        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as response:
                content = response.read().decode('utf-8')

                # Save to local cache
                self.agents_dir.mkdir(parents=True, exist_ok=True)
                agent_file = self.agents_dir / f"{agent_name}.md"
                agent_file.write_text(content, encoding='utf-8')

                # Update cache
                self.loaded_skills['agents'][agent_name] = {
                    'path': str(agent_file),
                    'loaded_at': datetime.now().isoformat(),
                    'source': 'github'
                }
                self._save_cache()

                return {
                    'name': agent_name,
                    'status': 'loaded',
                    'loaded': True,
                    'path': str(agent_file),
                    'bytes': len(content)
                }

        except Exception as e:
            return {
                'name': agent_name,
                'status': 'failed',
                'loaded': False,
                'error': str(e)
            }

    def _save_cache(self):
        """Persist loaded skills/agents to cache file."""
        self.cache_file.write_text(json.dumps(self.loaded_skills, indent=2))

    def get_loaded_skills(self):
        """List all loaded skills."""
        return list(self.loaded_skills['skills'].keys())

    def get_loaded_agents(self):
        """List all loaded agents."""
        return list(self.loaded_skills['agents'].keys())


if __name__ == '__main__':
    # Demo usage
    loader = CoreSkillsLoader()

    # Example: LLM decides to use docker skill
    skill_to_load = sys.argv[1] if len(sys.argv) > 1 else 'docker'

    result = loader.load_skill(skill_to_load)

    print(json.dumps({
        'step': 'LEVEL_3_SKILL_LOADER',
        'skill_loaded': result,
        'loaded_skills': loader.get_loaded_skills(),
        'loaded_agents': loader.get_loaded_agents(),
        'status': 'OK' if result['loaded'] else 'FAILED'
    }))
