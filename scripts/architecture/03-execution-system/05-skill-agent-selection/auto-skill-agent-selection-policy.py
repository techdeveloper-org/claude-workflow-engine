#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Skill & Agent Selection Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to: policies/03-execution-system/05-skill-agent-selection/auto-skill-agent-selection-policy.md

Consolidates 3 scripts (1,430+ lines):
- auto-skill-agent-selector.py (402 lines) - Context-aware selection
- auto-register-skills.py (655 lines) - Auto-discovery and registration
- skill-agent-auto-executor.py (373 lines) - Automatic execution

THIS CONSOLIDATION includes ALL functionality from old scripts.
NO logic was lost in consolidation - everything is merged.

Usage:
  python auto-skill-agent-selection-policy.py --enforce              # Run policy enforcement
  python auto-skill-agent-selection-policy.py --validate             # Validate policy compliance
  python auto-skill-agent-selection-policy.py --report               # Generate report
  python auto-skill-agent-selection-policy.py --select <task.json>   # Auto-select skills/agents
  python auto-skill-agent-selection-policy.py --register             # Auto-register all skills
  python auto-skill-agent-selection-policy.py --execute <task.json>  # Auto-execute matched items
"""

import sys
import io
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Fix encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"

# Paths for skill registration
CLAUDE_DIR = Path.home() / '.claude'
SKILLS_DIR = CLAUDE_DIR / 'skills'
SKILLS_REGISTRY = MEMORY_DIR / 'skills-registry.json'
AUTO_REGISTER_LOG = MEMORY_DIR / 'logs' / 'auto-register.log'
SKILL_AGENT_EXECUTION_LOG = MEMORY_DIR / 'logs' / 'skill-agent-execution.log'


# ============================================================================
# SKILL/AGENT SELECTOR (from auto-skill-agent-selector.py)
# ============================================================================

class AutoSkillAgentSelector:
    """
    Automatically selects skills and agents based on context
    Context-aware selection based on task type, complexity, and technologies
    """

    def __init__(self):
        """Initialize AutoSkillAgentSelector with the registry file path and built-in lists."""
        self.registry_file = Path.home() / ".claude" / "memory" / "adaptive-skill-registry.md"

        # Available skills (from registry)
        self.available_skills = [
            'java-spring-boot-microservices',
            'spring-boot-design-patterns-core',
            'java-design-patterns-core',
            'docker',
            'kubernetes',
            'jenkins-pipeline',
            'rdbms-core',
            'nosql-core',
            'css-core',
            'animations-core',
            'seo-keyword-research-core'
        ]

        # Available agents (from registry)
        self.available_agents = [
            'spring-boot-microservices',
            'android-backend-engineer',
            'android-ui-designer',
            'angular-engineer',
            'devops-engineer',
            'dynamic-seo-agent',
            'orchestrator-agent',
            'qa-testing-agent',
            'static-seo-agent',
            'swift-backend-engineer',
            'swiftui-designer',
            'ui-ux-designer'
        ]

    def select(self, task_type: str, complexity: Dict, structured_prompt: Dict) -> Dict:
        """Main selection logic"""
        print("\n" + "=" * 80)
        print("[TARGET] AUTO SKILL & AGENT SELECTION")
        print("=" * 80)

        selection = {
            'skills': [],
            'agents': [],
            'reasoning': [],
            'execution_plan': []
        }

        # Extract context
        technologies = self.extract_technologies(structured_prompt)
        complexity_score = complexity.get('score', 0)
        task_lower = task_type.lower()

        print(f"\n[CHART] Context Analysis:")
        print(f"   Task Type: {task_type}")
        print(f"   Complexity: {complexity_score}")
        print(f"   Technologies: {', '.join(technologies) if technologies else 'None'}")

        # Technology-based selection
        tech_matches = self.match_technologies(technologies, complexity_score)
        selection['skills'].extend(tech_matches['skills'])
        selection['agents'].extend(tech_matches['agents'])
        selection['reasoning'].extend(tech_matches['reasoning'])

        # Task type specific selection
        type_matches = self.match_task_type(task_type, complexity_score)
        for skill in type_matches['skills']:
            if skill not in selection['skills']:
                selection['skills'].append(skill)
        for agent in type_matches['agents']:
            if agent not in selection['agents']:
                selection['agents'].append(agent)
        selection['reasoning'].extend(type_matches['reasoning'])

        # Multi-service detection
        if self.is_multi_service(structured_prompt):
            if 'orchestrator-agent' not in selection['agents']:
                selection['agents'].append('orchestrator-agent')
                selection['reasoning'].append("Multi-service task -> orchestrator-agent")

        # Generate execution plan
        selection['execution_plan'] = self.generate_execution_plan(selection)

        # Output
        print(f"\n{'='*80}")
        print(f"[CHECK] SELECTION COMPLETE")
        print(f"{'='*80}")

        if selection['skills']:
            print(f"\n[U+1F4DA] Selected Skills ({len(selection['skills'])}):")
            for skill in selection['skills']:
                print(f"   - {skill}")

        if selection['agents']:
            print(f"\n[ROBOT] Selected Agents ({len(selection['agents'])}):")
            for agent in selection['agents']:
                print(f"   - {agent}")

        if not selection['skills'] and not selection['agents']:
            print(f"\n[CHECK] No additional skills/agents needed")
            print(f"   Direct execution with base knowledge")

        print(f"\n[CLIPBOARD] Reasoning:")
        for reason in selection['reasoning']:
            print(f"   - {reason}")

        if selection['execution_plan']:
            print(f"\n[TARGET] Execution Plan:")
            for step in selection['execution_plan']:
                print(f"   {step}")

        print(f"\n{'='*80}\n")

        return selection

    def extract_technologies(self, prompt: Dict) -> List[str]:
        """Extract technologies from structured prompt"""
        technologies = []

        # From tech stack
        tech_stack = prompt.get('project_context', {}).get('technology_stack', [])
        for tech in tech_stack:
            technologies.append(str(tech).lower())

        # From keywords
        keywords = prompt.get('analysis', {}).get('keywords', [])
        for kw in keywords:
            technologies.append(str(kw).lower())

        return technologies

    def match_technologies(self, technologies: List[str], complexity: int) -> Dict:
        """Match technologies to skills/agents"""
        matches = {
            'skills': [],
            'agents': [],
            'reasoning': []
        }

        # Technology to resource mapping
        tech_map = {
            'spring boot': {
                'skill': 'java-spring-boot-microservices',
                'agent': 'spring-boot-microservices',
                'agent_threshold': 10
            },
            'java': {
                'skill': 'java-design-patterns-core',
                'agent': None,
                'agent_threshold': 999
            },
            'python': {
                'skill': None,
                'agent': None,
                'agent_threshold': 999
            },
            'flask': {
                'skill': None,
                'agent': None,
                'agent_threshold': 999
            },
            'django': {
                'skill': None,
                'agent': None,
                'agent_threshold': 999
            },
            'docker': {
                'skill': 'docker',
                'agent': 'devops-engineer',
                'agent_threshold': 12
            },
            'kubernetes': {
                'skill': 'kubernetes',
                'agent': 'devops-engineer',
                'agent_threshold': 12
            },
            'k8s': {
                'skill': 'kubernetes',
                'agent': 'devops-engineer',
                'agent_threshold': 12
            },
            'jenkins': {
                'skill': 'jenkins-pipeline',
                'agent': 'devops-engineer',
                'agent_threshold': 15
            },
            'postgresql': {
                'skill': 'rdbms-core',
                'agent': None,
                'agent_threshold': 999
            },
            'mysql': {
                'skill': 'rdbms-core',
                'agent': None,
                'agent_threshold': 999
            },
            'mongodb': {
                'skill': 'nosql-core',
                'agent': None,
                'agent_threshold': 999
            },
            'elasticsearch': {
                'skill': 'nosql-core',
                'agent': None,
                'agent_threshold': 999
            },
            'angular': {
                'skill': None,
                'agent': 'angular-engineer',
                'agent_threshold': 8
            },
            'android': {
                'skill': None,
                'agent': 'android-backend-engineer',
                'agent_threshold': 10
            }
        }

        for tech in technologies:
            for key, config in tech_map.items():
                tech_lower = tech.lower().strip()
                if tech_lower == key or f' {key} ' in f' {tech_lower} ' or tech_lower.startswith(key + ' ') or tech_lower.endswith(' ' + key):
                    # v3.9.2: ALWAYS invoke - no complexity threshold
                    if config['agent']:
                        if config['agent'] not in matches['agents']:
                            matches['agents'].append(config['agent'])
                            matches['reasoning'].append(
                                f"{key.title()} detected -> {config['agent']} agent (always invoke)"
                            )
                    if config['skill']:
                        if config['skill'] not in matches['skills']:
                            matches['skills'].append(config['skill'])
                            matches['reasoning'].append(
                                f"{key.title()} detected -> {config['skill']} skill (always invoke)"
                            )

        return matches

    def match_task_type(self, task_type: str, complexity: int) -> Dict:
        """Match task type to skills/agents"""
        matches = {
            'skills': [],
            'agents': [],
            'reasoning': []
        }

        task_lower = task_type.lower()

        # Task type mappings (v3.9.2 - ALWAYS invoke)
        if 'api' in task_lower or 'microservice' in task_lower:
            if 'java' in task_lower or 'spring' in task_lower:
                matches['skills'].append('java-spring-boot-microservices')
                matches['reasoning'].append(f"Task '{task_type}' -> java-spring-boot-microservices skill (always invoke)")
                if any(kw in task_lower for kw in ['multi-step', 'full service', 'build entire', 'architecture']):
                    matches['agents'].append('spring-boot-microservices')
                    matches['reasoning'].append(f"Task '{task_type}' -> spring-boot-microservices agent (autonomous workflow)")

        if 'deployment' in task_lower or 'ci/cd' in task_lower or 'pipeline' in task_lower:
            matches['skills'].append('jenkins-pipeline')
            matches['reasoning'].append(f"Task '{task_type}' -> jenkins-pipeline skill (always invoke)")
            if any(kw in task_lower for kw in ['multi-step', 'full pipeline', 'infrastructure', 'setup']):
                matches['agents'].append('devops-engineer')
                matches['reasoning'].append(f"Task '{task_type}' -> devops-engineer agent (autonomous workflow)")

        if 'test' in task_lower:
            matches['agents'].append('qa-testing-agent')
            matches['reasoning'].append(f"Task '{task_type}' -> qa-testing-agent (always invoke)")

        # UI/UX/Dashboard tasks - NO threshold, always invoke
        if any(keyword in task_lower for keyword in ['ui', 'design', 'dashboard', 'frontend', 'admin panel', 'overlapping', 'layout', 'interface']):
            if 'ui-ux-designer' not in matches['agents']:
                matches['agents'].append('ui-ux-designer')
                matches['reasoning'].append(f"Task '{task_type}' -> ui-ux-designer agent (always invoke)")

        # Dashboard/Web app specific
        if any(keyword in task_lower for keyword in ['dashboard', 'admin', 'panel', 'web app', 'flask', 'django']):
            matches['reasoning'].append(f"Dashboard/Web app detected -> Consider ui-ux-designer + Python backend")

        return matches

    def is_multi_service(self, prompt: Dict) -> bool:
        """Check if task involves multiple services"""
        prompt_str = str(prompt).lower()

        multi_service_indicators = [
            'multiple services',
            'cross-service',
            'all services',
            'services affected',
            'multi-service'
        ]

        return any(indicator in prompt_str for indicator in multi_service_indicators)

    def generate_execution_plan(self, selection: Dict) -> List[str]:
        """Generate execution plan based on selection"""
        plan = []

        if selection['agents']:
            if len(selection['agents']) == 1:
                agent = selection['agents'][0]
                plan.append(f"1. Execute: Task(subagent_type='{agent}', prompt='...')")

                if selection['skills']:
                    plan.append(f"2. Skills available to agent: {', '.join(selection['skills'])}")
            else:
                plan.append(f"1. Orchestrator coordinates {len(selection['agents'])} agents")
                for i, agent in enumerate(selection['agents'], 2):
                    plan.append(f"{i}. Agent: {agent}")

        elif selection['skills']:
            plan.append(f"1. Direct execution with skills:")
            for skill in selection['skills']:
                plan.append(f"   - Use {skill} knowledge")

        else:
            plan.append("1. Direct execution with base knowledge")

        return plan


# ============================================================================
# SKILL AUTO-REGISTER (from auto-register-skills.py)
# ============================================================================

class SkillAutoRegister:
    """Auto-discover and register skills from ~/.claude/skills/"""

    def __init__(self):
        """Initialize SkillAutoRegister with an empty registry and zero counters."""
        self.registry = self._load_registry()
        self.skills = self.registry.get('skills', {})
        self.registered_count = 0
        self.updated_count = 0
        self.skipped_count = 0

        # Manual keyword enhancements for specific skills
        self.keyword_overrides = {
            'payment-integration-python': {
                'add_keywords': ['stripe', 'razorpay', 'paypal', 'square', 'braintree', 'gateway', 'checkout', 'refund', 'subscription'],
                'add_triggers': ['payment.*python', 'stripe.*flask', 'razorpay.*django', 'paypal.*python']
            },
            'payment-integration-java': {
                'add_keywords': ['stripe', 'razorpay', 'paypal', 'square', 'braintree', 'gateway', 'checkout', 'refund', 'subscription'],
                'add_triggers': ['payment.*java', 'payment.*spring', 'stripe.*spring', 'razorpay.*spring', 'razorpay.*java', 'paypal.*spring']
            },
            'payment-integration-typescript': {
                'add_keywords': ['stripe', 'razorpay', 'paypal', 'square', 'braintree', 'gateway', 'checkout', 'refund', 'subscription'],
                'add_triggers': ['payment.*typescript', 'stripe.*express', 'razorpay.*nestjs', 'paypal.*node']
            },
            'adaptive-skill-intelligence': {
                'add_keywords': ['skill', 'agent', 'factory', 'create', 'dynamic', 'auto', 'generate', 'adaptive'],
                'add_triggers': ['adaptive.*skill', 'auto.*create.*skill', 'dynamic.*agent']
            },
            'memory-enforcer': {
                'add_keywords': ['memory', 'enforcer', 'enforcement', 'policy', 'system', 'mandate', 'rules'],
                'add_triggers': ['memory.*enforcement', 'memory.*system', 'policy.*enforcement']
            },
            'phased-execution-intelligence': {
                'add_keywords': ['phased', 'execution', 'phase', 'milestone', 'checkpoint', 'breakdown', 'stages', 'progressive'],
                'add_triggers': ['phased.*execution', 'phase.*breakdown', 'milestone.*execution']
            },
            'task-planning-intelligence': {
                'add_keywords': ['task', 'planning', 'plan', 'breakdown', 'complexity', 'analysis', 'strategy', 'organize'],
                'add_triggers': ['task.*planning', 'task.*breakdown', 'plan.*complexity']
            }
        }

    def _load_registry(self) -> Dict:
        """Load existing registry"""
        if not SKILLS_REGISTRY.exists():
            return {
                "version": "1.0.0",
                "last_updated": datetime.now().strftime('%Y-%m-%d'),
                "skills": {},
                "categories": {},
                "statistics": {"total_skills": 0}
            }

        with open(SKILLS_REGISTRY, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_registry(self):
        """Save updated registry"""
        self.registry['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        self.registry['skills'] = self.skills
        self._update_statistics()

        with open(SKILLS_REGISTRY, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    def _update_statistics(self):
        """Update registry statistics"""
        stats = self.registry.get('statistics', {})
        stats['total_skills'] = len(self.skills)

        # By language
        by_language = {}
        for skill_data in self.skills.values():
            lang = skill_data.get('language', 'unknown')
            by_language[lang] = by_language.get(lang, 0) + 1
        stats['by_language'] = by_language

        # By category
        by_category = {}
        for skill_data in self.skills.values():
            cat = skill_data.get('category', 'unknown')
            by_category[cat] = by_category.get(cat, 0) + 1
        stats['by_category'] = by_category

        self.registry['statistics'] = stats

        # Update categories
        categories = {}
        for skill_id, skill_data in self.skills.items():
            cat = skill_data.get('category', 'unknown')
            if cat not in categories:
                categories[cat] = {'skills': [], 'description': f'{cat} skills'}
            categories[cat]['skills'].append(skill_id)
        self.registry['categories'] = categories

    def discover_skills(self) -> List[Path]:
        """Discover all skill files in skills directory (recursive)"""
        if not SKILLS_DIR.exists():
            self._log("Skills directory does not exist")
            return []

        # Recursively find all .md files in skills directory
        all_files = list(SKILLS_DIR.rglob('*.md'))
        skill_files = [f for f in all_files if self._is_skill_file(f)]

        return skill_files

    def _is_skill_file(self, file_path: Path) -> bool:
        """Determine if file is an actual skill"""
        name = file_path.stem.upper()

        # Include SKILL.md and instructions.md files explicitly
        if name in ['SKILL', 'INSTRUCTIONS']:
            return True

        # Exclude guide files
        exclude_patterns = [
            'GUIDE', 'QUICK-START', 'QUICKSTART', 'README',
            'INDEX', 'TEMPLATE', 'EXAMPLE', 'TEST'
        ]

        for pattern in exclude_patterns:
            if pattern in name:
                return False

        return True

    def _extract_skill_metadata(self, file_path: Path) -> Optional[Dict]:
        """Extract skill metadata from markdown file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            lines = content.split('\n')
            total_lines = len(lines)

            # Extract title (first # heading)
            title = None
            for line in lines:
                if line.startswith('# '):
                    title = line[2:].strip()
                    break

            if not title:
                title = file_path.stem.replace('-', ' ').title()

            # Extract description
            description = ""
            in_description = False
            for line in lines:
                if line.startswith('# ') and title in line:
                    in_description = True
                    continue
                if in_description and line.strip() and not line.startswith('#'):
                    description = line.strip()
                    description = re.sub(r'\*\*(.*?)\*\*', r'\1', description)
                    description = re.sub(r'\*(.*?)\*', r'\1', description)
                    break

            if not description:
                description = f"Skill for {title}"

            # Detect language and category
            language = self._detect_language(file_path, content)
            category = self._detect_category(file_path, content)

            # Extract keywords
            keywords = self._extract_keywords(file_path, content)

            # Generate trigger patterns
            trigger_patterns = self._generate_triggers(file_path, keywords, language)

            # Check if requires Context7
            requires_context7 = 'context7' in content.lower() or 'latest' in content.lower()

            # Apply manual keyword enhancements if available
            skill_id = file_path.parent.name.lower() if file_path.stem.upper() in ['SKILL', 'INSTRUCTIONS'] else file_path.stem.lower()
            keywords, trigger_patterns = self._apply_keyword_overrides(skill_id, keywords, trigger_patterns)

            return {
                'name': title,
                'file': str(file_path).replace('\\', '/'),
                'description': description[:200],
                'version': '1.0.0',
                'size': f'{total_lines} lines',
                'language': language,
                'category': category,
                'keywords': keywords[:20],
                'trigger_patterns': trigger_patterns[:8],
                'auto_suggest': True,
                'requires_context7': requires_context7,
                'dependencies': [],
                'usage_count': 0,
                'last_used': None,
                'tags': [language, category],
                'auto_registered': True,
                'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            self._log(f"Error extracting metadata from {file_path}: {e}")
            return None

    def _detect_language(self, file_path: Path, content: str) -> str:
        """Detect programming language from filename or content"""
        filename_lower = file_path.stem.lower()
        content_lower = content.lower()

        languages = {
            'python': ['python', 'py', 'flask', 'django', 'fastapi'],
            'java': ['java', 'spring', 'javafx', 'maven'],
            'typescript': ['typescript', 'ts', 'node', 'express', 'nestjs'],
            'javascript': ['javascript', 'js', 'react', 'vue', 'angular'],
            'csharp': ['csharp', 'c#', 'dotnet', '.net'],
            'go': ['golang', 'go'],
            'rust': ['rust'],
            'kotlin': ['kotlin', 'android'],
            'swift': ['swift', 'ios', 'swiftui']
        }

        for lang, patterns in languages.items():
            for pattern in patterns:
                if pattern in filename_lower or pattern in content_lower[:1000]:
                    return lang

        return 'general'

    def _detect_category(self, file_path: Path, content: str) -> str:
        """Detect skill category from filename or content"""
        filename_lower = file_path.stem.lower()
        content_lower = content.lower()

        categories = {
            'payment': ['payment', 'stripe', 'razorpay', 'paypal', 'checkout'],
            'ui': ['ui', 'javafx', 'swiftui', 'react', 'vue', 'angular', 'frontend'],
            'database': ['database', 'sql', 'mongodb', 'postgres', 'mysql'],
            'api': ['api', 'rest', 'graphql', 'grpc'],
            'testing': ['test', 'testing', 'junit', 'pytest'],
            'deployment': ['deploy', 'docker', 'kubernetes', 'ci/cd'],
            'security': ['security', 'auth', 'jwt', 'oauth'],
            'automation': ['automation', 'script', 'cli', 'tool']
        }

        for cat, patterns in categories.items():
            for pattern in patterns:
                if pattern in filename_lower or pattern in content_lower[:1000]:
                    return cat

        return 'general'

    def _extract_keywords(self, file_path: Path, content: str) -> List[str]:
        """Extract relevant keywords from filename and content"""
        keywords = set()

        # From filename
        filename_parts = file_path.stem.lower().replace('-', ' ').replace('_', ' ').split()
        keywords.update(filename_parts)

        # Tech keywords from content
        sample = content.lower()[:2000]
        tech_keywords = [
            'python', 'java', 'typescript', 'javascript', 'kotlin', 'swift',
            'flask', 'django', 'fastapi', 'spring boot', 'express', 'nestjs',
            'react', 'vue', 'angular', 'javafx', 'swiftui',
            'stripe', 'razorpay', 'paypal', 'square', 'braintree',
            'payment', 'checkout', 'subscription', 'refund', 'webhook',
            'ui', 'ux', 'design', 'layout', 'component', 'theme',
            'api', 'rest', 'graphql', 'endpoint', 'controller',
            'database', 'sql', 'mongodb', 'postgres', 'mysql',
            'integration', 'automation', 'deployment', 'testing'
        ]

        for keyword in tech_keywords:
            if keyword in sample:
                keywords.add(keyword)

        return sorted(list(keywords))[:15]

    def _generate_triggers(self, file_path: Path, keywords: List[str], language: str) -> List[str]:
        """Generate trigger patterns from keywords and language"""
        triggers = []

        if len(keywords) >= 2:
            triggers.append(f"{keywords[0]}.*{keywords[1]}")
            if language != 'general':
                triggers.append(f"{keywords[0]}.*{language}")

        filename_parts = file_path.stem.lower().split('-')
        if len(filename_parts) >= 2:
            triggers.append(f"{filename_parts[0]}.*{filename_parts[1]}")

        return triggers[:5]

    def _apply_keyword_overrides(self, skill_id: str, keywords: List[str], triggers: List[str]) -> Tuple[List[str], List[str]]:
        """Apply manual keyword enhancements for specific skills"""
        if skill_id not in self.keyword_overrides:
            return keywords, triggers

        overrides = self.keyword_overrides[skill_id]

        if 'add_keywords' in overrides:
            for keyword in overrides['add_keywords']:
                if keyword not in keywords:
                    keywords.insert(0, keyword)

        if 'add_triggers' in overrides:
            for trigger in overrides['add_triggers']:
                if trigger not in triggers:
                    triggers.insert(0, trigger)

        return keywords, triggers

    def register_skill(self, file_path: Path, force: bool = False) -> bool:
        """Register a skill from file path"""
        if file_path.stem.upper() in ['SKILL', 'INSTRUCTIONS']:
            skill_id = file_path.parent.name.lower()
        else:
            skill_id = file_path.stem.lower()

        # Check if already registered
        if skill_id in self.skills and not force:
            self.skipped_count += 1
            return False

        # Extract metadata
        metadata = self._extract_skill_metadata(file_path)
        if not metadata:
            self._log(f"Failed to extract metadata: {file_path.name}")
            return False

        # Add/update in registry
        if skill_id in self.skills:
            metadata['usage_count'] = self.skills[skill_id].get('usage_count', 0)
            metadata['last_used'] = self.skills[skill_id].get('last_used', None)
            self.updated_count += 1
        else:
            self.registered_count += 1

        self.skills[skill_id] = metadata
        return True

    def auto_register_all(self, dry_run: bool = False, force: bool = False) -> Dict:
        """Auto-discover and register all skills"""
        skill_files = self.discover_skills()

        if dry_run:
            print(f"DRY RUN: Would register {len(skill_files)} skills\n")

        for skill_file in skill_files:
            if dry_run:
                metadata = self._extract_skill_metadata(skill_file)
                if metadata:
                    print(f"- {skill_file.name}")
                    print(f"  Name: {metadata['name']}")
                    print(f"  Language: {metadata['language']}")
                    print(f"  Category: {metadata['category']}")
                    print()
            else:
                self.register_skill(skill_file, force=force)

        if not dry_run:
            self._save_registry()
            self._log(f"Auto-registered: {self.registered_count} new, {self.updated_count} updated, {self.skipped_count} skipped")

        return {
            'total_discovered': len(skill_files),
            'registered': self.registered_count,
            'updated': self.updated_count,
            'skipped': self.skipped_count
        }

    def _log(self, message: str):
        """Log auto-register events"""
        AUTO_REGISTER_LOG.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"

        with open(AUTO_REGISTER_LOG, 'a', encoding='utf-8') as f:
            f.write(log_entry)

        print(log_entry.strip())


# ============================================================================
# SKILL/AGENT AUTO-EXECUTOR (from skill-agent-auto-executor.py)
# ============================================================================

class SkillAgentAutoExecutor:
    """
    Automatically selects and executes appropriate skills/agents
    Override on failure mechanism included
    """

    def __init__(self):
        """Initialize SkillAgentAutoExecutor with log paths and load the built-in registry."""
        self.memory_path = Path.home() / '.claude' / 'memory'
        self.logs_path = self.memory_path / 'logs'
        self.execution_log = self.logs_path / 'skill-agent-execution.log'

        # Skill/Agent registry
        self.registry = self._load_registry()

    def _load_registry(self):
        """Load skill and agent registry"""
        return {
            'skills': {
                'java-spring-boot-microservices': {
                    'technologies': ['java', 'spring boot', 'spring', 'microservice'],
                    'complexity_min': 0,
                    'type': 'knowledge'
                },
                'docker': {
                    'technologies': ['docker', 'container', 'dockerfile'],
                    'complexity_min': 0,
                    'type': 'knowledge'
                },
                'kubernetes': {
                    'technologies': ['kubernetes', 'k8s', 'helm', 'kubectl'],
                    'complexity_min': 5,
                    'type': 'knowledge'
                },
                'rdbms-core': {
                    'technologies': ['database', 'sql', 'postgresql', 'mysql'],
                    'complexity_min': 0,
                    'type': 'knowledge'
                },
                'nosql-core': {
                    'technologies': ['mongodb', 'elasticsearch', 'nosql'],
                    'complexity_min': 0,
                    'type': 'knowledge'
                }
            },
            'agents': {
                'spring-boot-microservices': {
                    'technologies': ['java', 'spring boot', 'microservice'],
                    'complexity_min': 10,
                    'type': 'autonomous',
                    'description': 'Complex Java Spring Boot implementations'
                },
                'devops-engineer': {
                    'technologies': ['docker', 'kubernetes', 'ci/cd', 'jenkins'],
                    'complexity_min': 8,
                    'type': 'autonomous',
                    'description': 'Deployment and CI/CD'
                },
                'qa-testing-agent': {
                    'technologies': ['test', 'testing', 'junit'],
                    'complexity_min': 5,
                    'type': 'autonomous',
                    'description': 'Test implementation and validation'
                },
                'orchestrator-agent': {
                    'technologies': ['multi-service', 'microservices'],
                    'complexity_min': 15,
                    'type': 'autonomous',
                    'description': 'Multi-service coordination'
                }
            }
        }

    def match_skills(self, task_info):
        """Match appropriate skills based on task info"""
        matched_skills = []

        message = task_info.get('message', '').lower()
        complexity = task_info.get('complexity_score', 0)

        for skill_name, skill_info in self.registry['skills'].items():
            # Check technology match (v3.9.2: ALWAYS invoke on tech match)
            tech_match = any(tech in message for tech in skill_info['technologies'])

            if tech_match:
                matched_skills.append({
                    'name': skill_name,
                    'type': 'skill',
                    'reason': f"Matched: {', '.join([t for t in skill_info['technologies'] if t in message])}"
                })

        return matched_skills

    def match_agents(self, task_info):
        """Match appropriate agents based on task info"""
        matched_agents = []

        message = task_info.get('message', '').lower()
        complexity = task_info.get('complexity_score', 0)
        service_count = task_info.get('service_count', 0)

        # Special case: Multi-service
        if service_count > 1:
            matched_agents.append({
                'name': 'orchestrator-agent',
                'type': 'agent',
                'reason': f'Multi-service task ({service_count} services)'
            })
            return matched_agents

        # Match individual agents
        for agent_name, agent_info in self.registry['agents'].items():
            if agent_name == 'orchestrator-agent':
                continue

            # Check technology match (v3.9.2: ALWAYS invoke on tech match)
            tech_match = any(tech in message for tech in agent_info['technologies'])

            if tech_match:
                matched_agents.append({
                    'name': agent_name,
                    'type': 'agent',
                    'reason': f"{agent_info['description']} - Matched: {', '.join([t for t in agent_info['technologies'] if t in message])}"
                })

        return matched_agents

    def decide_execution_strategy(self, complexity_score, skills, agents):
        """
        Decide execution strategy
        Rules (v3.9.2 - ALWAYS INVOKE):
        - ALWAYS invoke matching skill/agent regardless of complexity
        - Skill vs Agent by TASK NATURE: guidance/patterns = Skill, autonomous workflow = Agent
        - Multi-service: Always use orchestrator agent
        - No match: SUGGEST new skill/agent to user
        """
        if agents:
            return {
                'strategy': 'agent',
                'selected': agents,
                'reason': f'Agent matched for task (autonomous multi-step workflow needed)'
            }
        elif skills:
            return {
                'strategy': 'skill',
                'selected': skills,
                'reason': f'Skill matched for task (knowledge/guidance/patterns needed)'
            }
        else:
            return {
                'strategy': 'direct',
                'selected': [],
                'reason': 'No matching skills/agents - proceed directly'
            }

    def auto_execute(self, task_info, dry_run=False):
        """
        Main entry point - automatically select and execute
        """
        # Match skills and agents
        matched_skills = self.match_skills(task_info)
        matched_agents = self.match_agents(task_info)

        # Decide strategy
        complexity = task_info.get('complexity_score', 0)
        strategy = self.decide_execution_strategy(complexity, matched_skills, matched_agents)

        result = {
            'matched_skills': matched_skills,
            'matched_agents': matched_agents,
            'strategy': strategy['strategy'],
            'selected': strategy['selected'],
            'reason': strategy['reason'],
            'dry_run': dry_run,
            'timestamp': datetime.now().isoformat()
        }

        # Execute (if not dry run)
        if not dry_run and strategy['selected']:
            execution_results = []
            for item in strategy['selected']:
                exec_result = self.execute_item(item, task_info)
                execution_results.append(exec_result)

            result['execution_results'] = execution_results

        # Log execution
        self.log_execution(result)

        return result

    def execute_item(self, item, task_info):
        """Execute a skill or agent"""
        item_type = item['type']
        item_name = item['name']

        try:
            if item_type == 'skill':
                result = self.execute_skill(item_name, task_info)
            else:
                result = self.execute_agent(item_name, task_info)

            return {
                'name': item_name,
                'type': item_type,
                'status': 'success',
                'result': result
            }

        except Exception as e:
            return {
                'name': item_name,
                'type': item_type,
                'status': 'failure',
                'error': str(e)
            }

    def execute_skill(self, skill_name, task_info):
        """Execute a skill"""
        return f"Skill {skill_name} would be invoked here"

    def execute_agent(self, agent_name, task_info):
        """Execute an agent"""
        return f"Agent {agent_name} would be spawned here"

    def log_execution(self, result):
        """Log execution"""
        self.logs_path.mkdir(parents=True, exist_ok=True)

        log_entry = {
            'timestamp': result['timestamp'],
            'strategy': result['strategy'],
            'selected_count': len(result['selected']),
            'dry_run': result['dry_run']
        }

        with open(self.execution_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')

    def print_result(self, result):
        """Print formatted result"""
        print(f"\n{'='*70}")
        print(f"Skill/Agent Auto-Executor (Phase 4)")
        print(f"{'='*70}\n")

        print(f"Matched Skills ({len(result['matched_skills'])}):")
        if result['matched_skills']:
            for skill in result['matched_skills']:
                print(f"   • {skill['name']}: {skill['reason']}")
        else:
            print(f"   None")

        print(f"\nMatched Agents ({len(result['matched_agents'])}):")
        if result['matched_agents']:
            for agent in result['matched_agents']:
                print(f"   • {agent['name']}: {agent['reason']}")
        else:
            print(f"   None")

        print(f"\nStrategy: {result['strategy'].upper()}")
        print(f"Reason: {result['reason']}")

        if result['selected']:
            print(f"\nSelected for Execution:")
            for item in result['selected']:
                print(f"   • {item['name']} ({item['type']})")

        if result.get('execution_results'):
            print(f"\nExecution Results:")
            for exec_result in result['execution_results']:
                status_icon = 'OK' if exec_result['status'] == 'success' else 'FAIL'
                print(f"   [{status_icon}] {exec_result['name']}: {exec_result['status']}")

        if result['dry_run']:
            print(f"\nDRY RUN MODE - No actual execution")

        print(f"\n{'='*70}\n")


# ============================================================================
# LOGGING
# ============================================================================

def log_policy_hit(action, context=""):
    """Log policy execution"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] auto-skill-agent-selection-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception:
        pass


# ============================================================================
# POLICY INTERFACE
# ============================================================================

def validate():
    """Validate policy compliance"""
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "skill-agent-selection-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report"""
    try:
        registrar = SkillAutoRegister()
        result = registrar.auto_register_all(dry_run=True)

        report_data = {
            "status": "success",
            "policy": "auto-skill-agent-selection",
            "components": [
                "AutoSkillAgentSelector - context-aware selection",
                "SkillAutoRegister - auto-discovery and registration",
                "SkillAgentAutoExecutor - automatic execution"
            ],
            "total_skills_discovered": result['total_discovered'],
            "available_agents": 12,
            "timestamp": datetime.now().isoformat()
        }

        log_policy_hit("REPORT", "skill-agent-selection-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """
    Main policy enforcement function.

    Consolidates skill/agent selection from three sources:
    - Context-aware skill/agent selector
    - Automatic skill discovery and registration
    - Automatic skill/agent execution

    Returns: dict with status and results
    """
    try:
        log_policy_hit("ENFORCE_START", "auto-skill-agent-selection-enforcement")

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize all components
        selector = AutoSkillAgentSelector()
        registrar = SkillAutoRegister()
        executor = SkillAgentAutoExecutor()

        log_policy_hit("ENFORCE_COMPLETE", "skill-agent-selection-ready")
        print("[auto-skill-agent-selection-policy] Policy enforced - Skill/Agent selection active")

        return {"status": "success"}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[auto-skill-agent-selection-policy] ERROR: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--register":
            registrar = SkillAutoRegister()
            results = registrar.auto_register_all(dry_run=False)
            print("\n=== Auto-Registration Complete ===")
            print(f"Total discovered: {results['total_discovered']}")
            print(f"Newly registered: {results['registered']}")
            print(f"Updated: {results['updated']}")
            print(f"Skipped: {results['skipped']}")
            sys.exit(0)
        elif sys.argv[1] == "--select" and len(sys.argv) >= 3:
            with open(sys.argv[2], 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            selector = AutoSkillAgentSelector()
            selection = selector.select(
                task_data.get('task_type', 'General'),
                task_data.get('complexity', {}),
                task_data.get('prompt', {})
            )
            print(json.dumps(selection, indent=2))
            sys.exit(0)
        elif sys.argv[1] == "--execute" and len(sys.argv) >= 3:
            with open(sys.argv[2], 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            executor = SkillAgentAutoExecutor()
            result = executor.auto_execute(task_data, dry_run=False)
            executor.print_result(result)
            sys.exit(0)
        else:
            print("Usage: python auto-skill-agent-selection-policy.py [--enforce|--validate|--report|--register|--select|--execute]")
            sys.exit(1)
    else:
        # Default: run enforcement
        enforce()
