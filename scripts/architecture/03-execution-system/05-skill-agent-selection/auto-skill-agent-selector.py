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
        # Auto-discover skills from ~/.claude/skills/ (no hardcoding)
        _skills_dir = Path.home() / ".claude" / "skills"
        if _skills_dir.exists():
            self.available_skills = sorted([
                d.name for d in _skills_dir.iterdir()
                if d.is_dir() and (d / "SKILL.md").exists()
            ])
        else:
            self.available_skills = []

        # Auto-discover agents from ~/.claude/agents/ (no hardcoding)
        _agents_dir = Path.home() / ".claude" / "agents"
        if _agents_dir.exists():
            self.available_agents = sorted([
                d.name for d in _agents_dir.iterdir()
                if d.is_dir() and (d / "agent.md").exists()
            ])
        else:
            self.available_agents = []

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
                'skill': 'python-core',
                'agent': 'python-backend-engineer',
                'agent_threshold': 10
            },
            'flask': {
                'skill': 'python-core',
                'agent': 'python-backend-engineer',
                'agent_threshold': 10
            },
            'django': {
                'skill': 'python-core',
                'agent': 'python-backend-engineer',
                'agent_threshold': 10
            },
            'langgraph': {
                'skill': 'langgraph-core',
                'agent': 'python-backend-engineer',
                'agent_threshold': 8
            },
            'langchain': {
                'skill': 'langchain-core',
                'agent': 'python-backend-engineer',
                'agent_threshold': 8
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


def load_skill_definitions() -> dict:
    """Load skill definitions from ~/.claude/skills/"""
    import os
    skills = {}
    skills_dir = Path.home() / ".claude" / "skills"

    if not skills_dir.exists():
        return {}

    # Load each skill's metadata
    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                skill_md = skill_dir / "skill.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding='utf-8', errors='ignore')
                    name = skill_dir.name
                    description = ""

                    # Parse YAML frontmatter (between --- markers)
                    if content.startswith('---'):
                        end = content.find('---', 3)
                        if end > 0:
                            for line in content[3:end].split('\n'):
                                if line.strip().startswith('description:'):
                                    description = line.split(':', 1)[1].strip()[:200]
                                    break

                    skills[name] = {
                        'name': name,
                        'description': description or 'Skill module',
                        'has_definition': True
                    }
                except Exception:
                    pass

    return skills


def load_agent_definitions() -> dict:
    """Load agent definitions from ~/.claude/agents/"""
    import os
    agents = {}
    agents_dir = Path.home() / ".claude" / "agents"

    if not agents_dir.exists():
        return {}

    # Load each agent's metadata
    for agent_dir in agents_dir.iterdir():
        if agent_dir.is_dir():
            agent_md = agent_dir / "agent.md"
            if agent_md.exists():
                try:
                    content = agent_md.read_text(encoding='utf-8', errors='ignore')
                    name = agent_dir.name
                    description = ""

                    # Parse YAML frontmatter (between --- markers)
                    if content.startswith('---'):
                        end = content.find('---', 3)
                        if end > 0:
                            for line in content[3:end].split('\n'):
                                if line.strip().startswith('description:'):
                                    description = line.split(':', 1)[1].strip()[:200]
                                    break

                    agents[name] = {
                        'name': name,
                        'description': description or 'Agent module',
                        'has_definition': True
                    }
                except Exception:
                    pass

    return agents


def main():
    """CLI interface - simplified for LangGraph"""
    import sys

    # Check for --analyze flag (LangGraph mode)
    if "--analyze" in sys.argv:
        import urllib.request
        import urllib.error
        import os

        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
            from langgraph_engine.llm_call import llm_call as _llm_call
        except ImportError:
            _llm_call = None

        # Get Ollama config
        ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

        # Default task type for LangGraph
        task_type = "General"
        complexity = 5
        user_message = ""
        context_skills = []
        project_type = ""

        # Parse arguments
        for i, arg in enumerate(sys.argv[1:], 1):
            if arg == "--analyze":
                continue
            elif arg.startswith("--task-type="):
                task_type = arg.split("=", 1)[1]
            elif arg.startswith("--complexity="):
                try:
                    complexity = int(arg.split("=", 1)[1])
                except ValueError:
                    complexity = 5
            elif arg.startswith("--context="):
                try:
                    ctx = json.loads(arg.split("=", 1)[1])
                    task_type = ctx.get("task_type", task_type)
                    complexity = ctx.get("complexity", complexity)
                    user_message = ctx.get("user_message", "")
                    context_skills = ctx.get("available_skills", [])
                    project_type = ctx.get("project_type", "")
                except (json.JSONDecodeError, TypeError):
                    pass
            elif arg.startswith("--context-file="):
                try:
                    ctx_path = arg.split("=", 1)[1]
                    with open(ctx_path, 'r', encoding='utf-8') as f:
                        ctx = json.load(f)
                    task_type = ctx.get("task_type", task_type)
                    complexity = ctx.get("complexity", complexity)
                    user_message = ctx.get("user_message", "")
                    context_skills = ctx.get("available_skills", [])
                    project_type = ctx.get("project_type", "")
                except Exception:
                    pass
            elif not arg.startswith('--'):
                task_type = arg

        # Load actual skill and agent definitions
        available_skills = load_skill_definitions()
        available_agents = load_agent_definitions()

        # Dynamic skill filtering by project type (no hardcoded lists)
        # Logic: if skill name or description contains project_type keyword = relevant
        # If skill is language-agnostic (no language keyword in name) = universal, always include
        all_skill_names = list(available_skills.keys()) if available_skills else context_skills

        # Known language keywords (extracted dynamically from skill names)
        _LANG_KEYWORDS = {'python', 'java', 'spring', 'kotlin', 'android', 'swift',
                          'swiftui', 'typescript', 'javascript', 'react', 'angular'}

        def _is_language_specific(skill_name):
            """Check if skill name contains any language keyword."""
            name_lower = skill_name.lower().replace('-', ' ')
            return any(kw in name_lower for kw in _LANG_KEYWORDS)

        def _matches_project(skill_name, skill_desc, proj_type):
            """Check if skill is relevant to this project type."""
            searchable = (skill_name + ' ' + skill_desc).lower()
            return proj_type.lower() in searchable

        if project_type and project_type.strip():
            filtered_skills = [
                s for s in all_skill_names
                if not _is_language_specific(s)  # universal = always include
                or _matches_project(
                    s,
                    available_skills.get(s, {}).get('description', '') if isinstance(available_skills.get(s), dict) else '',
                    project_type
                )
            ]
        else:
            filtered_skills = all_skill_names

        # Build skill list with descriptions
        skills_text = ""
        if filtered_skills:
            skills_text = f"Available Skills ({len(filtered_skills)} of {len(all_skill_names)}):\n"
            for name in filtered_skills:
                info = available_skills.get(name, {})
                desc = info.get('description', '')[:80] if isinstance(info, dict) else ""
                skills_text += f"  - {name}: {desc}\n" if desc else f"  - {name}\n"
        else:
            skills_text = "Available Skills: None loaded\n"

        # Dynamic agent filtering by project type (match name or description)
        agents_text = ""
        if available_agents:
            if project_type and project_type.strip():
                relevant_agents = {
                    k: v for k, v in available_agents.items()
                    if not _is_language_specific(k)  # generic agents always
                    or _matches_project(
                        k,
                        v.get('description', '') if isinstance(v, dict) else '',
                        project_type
                    )
                }
            else:
                relevant_agents = available_agents

            agents_text = f"Available Agents ({len(relevant_agents)} of {len(available_agents)}):\n"
            for name, info in list(relevant_agents.items()):
                desc = info.get('description', '')[:80]
                agents_text += f"  - {name}: {desc}\n"
        else:
            agents_text = "Available Agents: None loaded\n"

        # Include user message for context-aware selection
        user_msg_text = ""
        if user_message:
            user_msg_text = f"User Request: {user_message[:500]}\n"

        # Include project type for accurate matching
        project_type_text = f"Project Type: {project_type}\n" if project_type else ""

        # Build prompt - select MULTIPLE skills and agent
        prompt = f"""You are a task-to-skill matcher. Select ALL relevant skills and the best agent for this task.

{user_msg_text}
Task Type: {task_type}
Complexity: {complexity}/10
{project_type_text}

{skills_text}
{agents_text}

RULES:
1. Select 1-4 skills that are RELEVANT to this task (multiple allowed)
2. Select 1 agent that best orchestrates the work
3. CRITICAL: Match skills to PROJECT TYPE - do NOT select Java skills for Python projects or vice versa
4. Match by technology: HTML=html5-core, CSS/SCSS=css-core, JS=javascript-core, React=react-core, Angular=angular-core, Python=python-core, Java=java-spring-boot-microservices
5. Include testing-core if complexity >= 7
6. Include ui-ux-core for any design/UI task
7. Agent must match project language (python-backend-engineer for Python, spring-boot-microservices for Java)

Respond ONLY with JSON (no markdown):
{{
  "selected_skills": ["skill1", "skill2"],
  "selected_agents": ["agent1"],
  "confidence": 0.5 to 1.0,
  "reasoning": "why these were chosen"
}}

JSON only:"""

        try:
            llm_response = ""
            if _llm_call:
                llm_response = _llm_call(prompt, model="balanced") or ""

            if not llm_response:
                num_ctx = 8192 if "14b" in ollama_model else 16384
                payload = {
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,
                    "options": {"num_ctx": num_ctx, "num_predict": 2048}
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

            # Support both old format (selected_skill) and new (selected_skills list)
            skills_list = llm_result.get('selected_skills', [])
            agents_list = llm_result.get('selected_agents', [])

            # Backward compat: also check old single-value keys
            if not skills_list and llm_result.get('selected_skill'):
                skills_list = [llm_result['selected_skill']]
            if not agents_list and llm_result.get('selected_agent'):
                agents_list = [llm_result['selected_agent']]

            # Filter empty strings
            skills_list = [s for s in skills_list if s and s.strip()]
            agents_list = [a for a in agents_list if a and a.strip()]

            output = {
                'selected_skill': skills_list[0] if skills_list else '',
                'selected_agent': agents_list[0] if agents_list else '',
                'selected_skills': skills_list,
                'selected_agents': agents_list,
                'confidence': float(llm_result.get('confidence', 0.7)),
                'reasoning': llm_result.get('reasoning', ''),
                'alternatives': [],
                'llm_needed': True,
                'status': 'OK'
            }

        except Exception as e:
            # Fallback if Ollama not available
            output = {
                'selected_skill': '',
                'selected_agent': '',
                'selected_skills': [],
                'selected_agents': [],
                'confidence': 0.0,
                'reasoning': f'Error: {str(e)}',
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
