#!/usr/bin/env python3
"""
Automatic Skill & Agent Selector
Context-aware selection based on task type, complexity, and technologies
"""

# Fix encoding for Windows console
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


import json
import yaml
from typing import Dict, List
from pathlib import Path


class AutoSkillAgentSelector:
    """
    Automatically selects skills and agents based on context
    """

    def __init__(self):
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

    def select(
        self,
        task_type: str,
        complexity: Dict,
        structured_prompt: Dict
    ) -> Dict:
        """
        Main selection logic
        """
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
                # Exact match or word boundary match (avoid 'java' matching 'javascript')
                tech_lower = tech.lower().strip()
                if tech_lower == key or f' {key} ' in f' {tech_lower} ' or tech_lower.startswith(key + ' ') or tech_lower.endswith(' ' + key):
                    # v3.9.2: ALWAYS invoke - no complexity threshold
                    # Add both agent AND skill if available (Claude decides by task nature)
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

        # Task type mappings (v3.9.2 - ALWAYS invoke, task nature decides Skill vs Agent)
        if 'api' in task_lower or 'microservice' in task_lower:
            if 'java' in task_lower or 'spring' in task_lower:
                # Both skill and agent available - select by task nature
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
            # Agent-based execution
            if len(selection['agents']) == 1:
                agent = selection['agents'][0]
                plan.append(f"1. Execute: Task(subagent_type='{agent}', prompt='...')")

                if selection['skills']:
                    plan.append(f"2. Skills available to agent: {', '.join(selection['skills'])}")
            else:
                # Multiple agents - need orchestrator
                plan.append(f"1. Orchestrator coordinates {len(selection['agents'])} agents")
                for i, agent in enumerate(selection['agents'], 2):
                    plan.append(f"{i}. Agent: {agent}")

        elif selection['skills']:
            # Skill-based execution (direct)
            plan.append(f"1. Direct execution with skills:")
            for skill in selection['skills']:
                plan.append(f"   - Use {skill} knowledge")

        else:
            # No skills/agents needed
            plan.append("1. Direct execution with base knowledge")

        return plan


def main():
    """CLI interface - simplified for LangGraph"""
    import sys

    # Check for --analyze flag (LangGraph mode)
    if "--analyze" in sys.argv:
        import urllib.request
        import urllib.error
        import os

        # Get Ollama config
        ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")
        ollama_model = os.getenv("OLLAMA_MODEL", "mistral")

        # Default task type for LangGraph
        task_type = "General"

        # Look for task type in arguments
        for i, arg in enumerate(sys.argv[1:], 1):
            if not arg.startswith('--'):
                task_type = arg
                break

        # Use Ollama to suggest skills/agents
        available_skills = "docker, java-spring-boot, python-backend, angular-frontend, kubernetes, jenkins, database, security"
        available_agents = "orchestrator-agent, spring-boot-microservices, python-backend-engineer, angular-engineer"

        prompt = f"""What skill and agent would best help with this task? Respond ONLY with JSON (no markdown):

Task Type: {task_type}
Available Skills: {available_skills}
Available Agents: {available_agents}

JSON format (no markdown):
{{
  "selected_skill": "skill name or empty string",
  "selected_agent": "agent name or empty string",
  "confidence": 0.0 to 1.0,
  "reasoning": "why these choices"
}}

JSON only:"""

        try:
            payload = {
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.3
            }
            req = urllib.request.Request(
                ollama_endpoint,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                llm_response = result.get("response", "")

            # Parse JSON from response
            if "{" in llm_response:
                json_start = llm_response.index("{")
                json_end = llm_response.rindex("}") + 1
                llm_result = json.loads(llm_response[json_start:json_end])
            else:
                llm_result = json.loads(llm_response)

            output = {
                'selected_skill': llm_result.get('selected_skill', ''),
                'selected_agent': llm_result.get('selected_agent', ''),
                'confidence': float(llm_result.get('confidence', 0.7)),
                'alternatives': [],
                'llm_needed': False,
                'status': 'OK'
            }

        except Exception as e:
            # Fallback if Ollama not available
            output = {
                'selected_skill': '',
                'selected_agent': '',
                'confidence': 0.0,
                'alternatives': [],
                'llm_needed': False,
                'status': 'error',
                'error': str(e)
            }

        print(json.dumps(output))
        sys.exit(0)

    # Original file-based mode
    if len(sys.argv) < 4:
        print("Auto Skill & Agent Selector")
        sys.exit(0)

    task_type = sys.argv[1]

    try:
        with open(sys.argv[2], 'r') as f:
            complexity = json.load(f)
    except Exception:
        complexity = {'score': 5, 'level': 'MODERATE'}

    try:
        with open(sys.argv[3], 'r') as f:
            prompt = yaml.safe_load(f)
    except Exception:
        prompt = {'metadata': {'original_request': task_type}}

    selector = AutoSkillAgentSelector()
    selection = selector.select(task_type, complexity, prompt)

    # Save output
    output_file = 'skill_agent_selection.yaml'
    try:
        with open(output_file, 'w') as f:
            yaml.dump(selection, f, default_flow_style=False, sort_keys=False)
        print(f"Selection saved to: {output_file}")
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
