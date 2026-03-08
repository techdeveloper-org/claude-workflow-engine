#!/usr/bin/env python3
"""
Intelligent Decision Engine (v1.2.0) - LLM-Powered Level 3 Decisions

Replaces keyword-based guessing with local LLM for ALL Level 3 decisions:
  - Task Type classification
  - Model Selection (HAIKU / SONNET / OPUS)
  - Skill/Agent Selection (from registry)
  - Complexity Adjustment

This is a MANDATORY pipeline step. If LLM fails, the entire pipeline fails.
No fallback to keyword-based system.

Pipeline Position: Step 3.3A (after Context Check, before Model Selection)
Called by: 3-level-flow.py

Input: Master context dict with all collected data
Output: JSON with all decisions

LLM: Local Ollama (IPEX-LLM on Intel Arc GPU + NPU) -> OpenRouter fallback
Endpoint: http://127.0.0.1:11434/v1/chat/completions
Model: qwen2.5:1.5b (no API key needed)
Fallback: OpenRouter API if Ollama is not running
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
from urllib import request as urllib_request
from urllib.error import URLError, HTTPError

# Windows ASCII-safe encoding
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
try:
    from ide_paths import CONFIG_DIR, MEMORY_BASE
    API_KEY_FILE = CONFIG_DIR / 'openrouter-api-key'
except ImportError:
    CONFIG_DIR = Path.home() / '.claude' / 'config'
    MEMORY_BASE = Path.home() / '.claude' / 'memory'
    API_KEY_FILE = CONFIG_DIR / 'openrouter-api-key'

LOG_FILE = MEMORY_BASE / 'logs' / 'llm-decision-engine.log'

# Primary: Local Ollama (IPEX-LLM on Intel Arc GPU + NPU)
OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
OLLAMA_TIMEOUT = 120  # seconds - 0 means no timeout (not recommended)
# Preferred models in order - first available model is used
OLLAMA_MODELS = [
    "qwen3:4b",        # Best for structured JSON (if installed)
    "qwen2.5:7b",      # Great JSON support (if installed)
    "qwen2.5:3b",      # Smaller but good JSON (if installed)
    "deepseek-r1:7b",  # Good reasoning but weak JSON (if installed)
    "granite4:3b",      # Fallback - currently installed
]
OLLAMA_MODEL = "granite4:3b"  # Will be auto-detected below

# Fallback: OpenRouter (if Ollama is not running)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [
    "arcee-ai/trinity-large-preview:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
]

# =============================================================================
# AVAILABLE SKILLS & AGENTS REGISTRY
# v1.2.0: Dynamically loaded from actual agent.md / skill.md files
# Extracts description + responsibilities + boundaries for informed LLM selection
# =============================================================================

# Fallback static registry (used if file reading fails)
_FALLBACK_AGENTS = {
    "spring-boot-microservices": "Java/Spring Boot backend, REST APIs, microservices, JPA, security",
    "ui-ux-designer": "UI/UX design, HTML/CSS, layouts, dashboards, admin panels, responsive design",
    "angular-engineer": "Angular/TypeScript frontend, components, routing, RxJS",
    "devops-engineer": "Docker, Kubernetes, Jenkins, CI/CD pipelines, infrastructure",
    "qa-testing-agent": "Unit tests, integration tests, test suites, QA, coverage",
    "android-backend-engineer": "Android/Kotlin, Retrofit, Room, ViewModels, Jetpack",
    "swiftui-designer": "iOS/SwiftUI, iPhone/iPad UI, Xcode",
    "swift-backend-engineer": "Swift server-side, Vapor, Swift REST APIs",
    "orchestrator-agent": "Multi-service coordination, cross-service tasks, full-stack orchestration",
    "dynamic-seo-agent": "SEO for dynamic JS apps (Angular/React), metadata, structured data",
    "static-seo-agent": "SEO for static sites, content optimization, keyword research",
    "python-backend-engineer": "Python backend, Flask, Django, FastAPI, SQLAlchemy",
}

_FALLBACK_SKILLS = {
    "java-spring-boot-microservices": "Spring Boot patterns, configurations, best practices",
    "spring-boot-design-patterns-core": "Java design patterns for Spring Boot applications",
    "java-design-patterns-core": "Core Java design patterns (GoF, SOLID)",
    "docker": "Dockerfile best practices, multi-stage builds, compose",
    "kubernetes": "K8s manifests, deployments, services, ingress, helm",
    "jenkins-pipeline": "Jenkinsfile, pipeline stages, shared libraries",
    "rdbms-core": "SQL, PostgreSQL, MySQL, schema design, migrations",
    "nosql-core": "MongoDB, Elasticsearch, document/key-value stores",
    "css-core": "CSS layouts, flexbox, grid, animations, responsive design",
    "animations-core": "CSS/JS animations, transitions, motion design",
    "seo-keyword-research-core": "SEO keyword research, content optimization",
    "python-system-scripting": "Python scripting, automation, system tools",
    "adaptive-skill-intelligence": "System/meta tasks about Claude memory system itself",
}


def _extract_md_sections(filepath, max_chars=200):
    """Read agent.md or skill.md and extract key sections for LLM context.

    Extracts: description (frontmatter), core responsibilities, boundaries.
    Returns a concise multi-line summary the LLM can use for selection.

    Args:
        filepath: Path to the .md file.
        max_chars: Maximum characters to return (default 200).

    Returns:
        str: Extracted summary, or empty string on failure.
    """
    try:
        content = Path(filepath).read_text(encoding='utf-8')
    except Exception:
        return ''

    lines = content.split('\n')
    desc = ''
    responsibilities = []
    boundaries = []

    # Extract description from frontmatter
    in_frontmatter = False
    for line in lines:
        stripped = line.strip()
        if stripped == '---':
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter and stripped.startswith('description:'):
            desc = stripped.split('description:', 1)[1].strip()

    # Extract core responsibilities and boundaries
    in_resp = False
    in_bound = False
    for line in lines:
        stripped = line.strip()

        if 'Core Responsibilities' in stripped or 'core responsibilities' in stripped:
            in_resp = True
            in_bound = False
            continue
        if 'does not' in stripped.lower() or 'Does NOT' in stripped or 'Boundaries' in stripped:
            in_bound = True
            in_resp = False
            continue
        if stripped.startswith('#'):
            in_resp = False
            in_bound = False

        if in_resp and stripped.startswith('-'):
            responsibilities.append(stripped.lstrip('- '))
        if in_bound and stripped.startswith('-'):
            boundaries.append(stripped.lstrip('- '))

    # Build concise summary
    parts = []
    if desc:
        parts.append(desc)
    if responsibilities:
        parts.append('Does: ' + '; '.join(responsibilities[:6]))
    if boundaries:
        parts.append('NOT: ' + '; '.join(boundaries[:3]))

    result = ' | '.join(parts)
    return result[:max_chars] if result else ''


def _load_agents_from_disk():
    """Load agent descriptions from ~/.claude/agents/*/agent.md files.

    Reads each agent.md, extracts description + responsibilities + boundaries.
    Falls back to static registry if files are missing.

    Returns:
        dict: {agent_name: rich_description_string}
    """
    agents_dir = Path.home() / '.claude' / 'agents'
    if not agents_dir.exists():
        return dict(_FALLBACK_AGENTS)

    result = {}
    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_md = agent_dir / 'agent.md'
        name = agent_dir.name
        if agent_md.exists():
            extracted = _extract_md_sections(agent_md)
            if extracted:
                result[name] = extracted
            elif name in _FALLBACK_AGENTS:
                result[name] = _FALLBACK_AGENTS[name]
        elif name in _FALLBACK_AGENTS:
            result[name] = _FALLBACK_AGENTS[name]

    # Ensure all fallback agents are present
    for name, desc in _FALLBACK_AGENTS.items():
        if name not in result:
            result[name] = desc

    return result


def _load_skills_from_disk():
    """Load skill descriptions from ~/.claude/skills/**/skill.md files.

    Reads each skill.md, extracts description + responsibilities.
    Falls back to static registry if files are missing.

    Returns:
        dict: {skill_name: rich_description_string}
    """
    skills_dir = Path.home() / '.claude' / 'skills'
    if not skills_dir.exists():
        return dict(_FALLBACK_SKILLS)

    result = {}
    for skill_md in skills_dir.glob('**/skill.md'):
        name = skill_md.parent.name
        extracted = _extract_md_sections(skill_md, max_chars=300)
        if extracted:
            result[name] = extracted
        elif name in _FALLBACK_SKILLS:
            result[name] = _FALLBACK_SKILLS[name]

    # Ensure all fallback skills are present
    for name, desc in _FALLBACK_SKILLS.items():
        if name not in result:
            result[name] = desc

    return result


# Load registries at module import (cached for session lifetime)
AVAILABLE_AGENTS = _load_agents_from_disk()
AVAILABLE_SKILLS = _load_skills_from_disk()

MODELS_INFO = {
    "HAIKU": "Fastest, cheapest ($1/$5 MTok). Best for: simple tasks, file reading, status checks, documentation, small bug fixes",
    "SONNET": "Balanced ($3/$15 MTok). Best for: API creation, implementation, frontend, moderate complexity, most coding tasks",
    "OPUS": "Most capable ($5/$25 MTok). Best for: architecture design, complex refactoring, plan mode, security-critical, multi-service coordination",
}


def _detect_best_ollama_model():
    """Auto-detect the best available Ollama model from OLLAMA_MODELS list.

    Queries Ollama /api/tags to get installed models, then picks the first
    match from OLLAMA_MODELS preference order.

    Returns:
        str: Best available model name, or 'granite4:3b' as fallback.
    """
    try:
        req = urllib_request.Request('http://127.0.0.1:11434/api/tags')
        with urllib_request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            installed = {m['name'] for m in data.get('models', [])}
            for preferred in OLLAMA_MODELS:
                if preferred in installed:
                    return preferred
            # None of the preferred models found, use first installed
            if installed:
                return next(iter(installed))
    except Exception:
        pass
    return 'granite4:3b'


# Auto-detect best model at module load
OLLAMA_MODEL = _detect_best_ollama_model()


# =============================================================================
# LOGGING
# =============================================================================

def log(msg):
    """Append timestamped message to decision engine log."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {msg}\n")
    except Exception:
        pass


# =============================================================================
# API KEY
# =============================================================================

def load_api_key():
    """Load OpenRouter API key. Returns key string or None."""
    if not API_KEY_FILE.exists():
        return None
    try:
        key = API_KEY_FILE.read_text(encoding='utf-8').strip()
        if not key or len(key) < 10:
            return None
        return key
    except Exception:
        return None


# =============================================================================
# SYSTEM PROMPT - The brain of the decision engine
# =============================================================================

SYSTEM_PROMPT = """You are a JSON classifier. You classify coding requests.

RESPOND WITH ONLY THIS EXACT JSON FORMAT - NO OTHER TEXT:
{"task_type":"string","complexity":number,"model":"HAIKU|SONNET|OPUS","model_reasoning":"string","agent_name":"string","agent_type":"agent|skill","agent_reasoning":"string","supplementary_skills":[],"confidence":number}

RULES:
- task_type: one of API Creation, Authentication, Security, Database, Dashboard, Frontend, UI/UX, Configuration, Bug Fix, Refactoring, Testing, Documentation, DevOps, Deployment, System/Script, Architecture Design, General Task
- model: HAIKU (simple, complexity<5), SONNET (moderate, 5-19), OPUS (complex, >=20)
- agent_name: MUST be from the AVAILABLE AGENTS list below. Match by what the user WANTS TO DO:
  * Visual/design work (theme, colors, layout, shadows) -> pick the designer agent
  * Building/coding features (routes, APIs, logic, forms) -> pick the engineer agent
  * The tech stack (Angular/React/etc) does NOT decide the agent
- supplementary_skills: from AVAILABLE SKILLS list or empty []
- confidence: 0.0 to 1.0
- complexity: 1 to 25"""


# =============================================================================
# BUILD USER PROMPT
# =============================================================================

def build_user_prompt(context):
    """Build the user prompt from master context dict."""
    parts = []

    user_msg = context.get('user_message', '')
    parts.append(f"USER MESSAGE: {user_msg}")

    # Detect design vs implementation intent from keywords
    design_words = ['redesign', 'theme', 'color', 'shadow', 'hover', 'gradient',
                    'typography', 'layout', 'visual', 'dark mode', 'light mode',
                    'style', 'css', 'scss', 'look and feel', 'aesthetic']
    msg_lower = user_msg.lower()
    design_count = sum(1 for w in design_words if w in msg_lower)
    if design_count >= 2:
        parts.append(f"\nINTENT: DESIGN/VISUAL task (matched {design_count} design keywords). Pick a DESIGNER agent, not an engineer.")

    # Current detections (from keyword-based system - for reference)
    kw_task = context.get('keyword_task_type', 'unknown')
    kw_complexity = context.get('keyword_complexity', 0)
    parts.append(f"\nCURRENT KEYWORD DETECTIONS (may be inaccurate):")
    parts.append(f"  Task Type: {kw_task}")
    parts.append(f"  Complexity: {kw_complexity}")

    # Tech stack
    tech = context.get('tech_stack', [])
    if tech:
        parts.append(f"\nDETECTED TECH STACK: {', '.join(tech)}")

    # Keywords extracted
    keywords = context.get('keywords', [])
    if keywords:
        parts.append(f"EXTRACTED KEYWORDS: {', '.join(keywords[:15])}")

    # Context usage
    ctx_pct = context.get('context_pct', 0)
    if ctx_pct > 0:
        parts.append(f"CONTEXT USAGE: {ctx_pct}%")

    # Task count
    task_count = context.get('task_count', 0)
    if task_count > 0:
        parts.append(f"TASK COUNT: {task_count}")

    # Plan mode
    if context.get('plan_required', False):
        parts.append("PLAN MODE: Required (forces OPUS)")

    # Project type
    project = context.get('project_name', '')
    if project:
        parts.append(f"PROJECT: {project}")

    # Available registry
    parts.append(f"\nAVAILABLE AGENTS:")
    for name, desc in AVAILABLE_AGENTS.items():
        parts.append(f"  - {name}: {desc}")

    parts.append(f"\nAVAILABLE SKILLS:")
    for name, desc in AVAILABLE_SKILLS.items():
        parts.append(f"  - {name}: {desc}")

    parts.append(f"\nMODEL OPTIONS:")
    for name, desc in MODELS_INFO.items():
        parts.append(f"  - {name}: {desc}")

    parts.append("\nCLASSIFY the user message above. Return ONLY the JSON object.")

    return "\n".join(parts)


# =============================================================================
# CALL OPENROUTER LLM
# =============================================================================

def _parse_llm_response(content, model_name):
    """Parse and validate LLM JSON response. Returns decision dict or None."""
    if not content:
        log(f"[LLM] {model_name} returned empty content")
        return None

    # Strip markdown code fences if present
    if content.startswith('```'):
        lines = content.split('\n')
        lines = [l for l in lines if not l.strip().startswith('```')]
        content = '\n'.join(lines).strip()

    # Try to extract JSON from mixed output
    try:
        decision = json.loads(content)
    except json.JSONDecodeError:
        # Find JSON object in mixed text
        first_brace = content.find('{')
        if first_brace >= 0:
            # Find matching closing brace
            depth = 0
            end_pos = -1
            for i in range(first_brace, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 1
                        break
            try:
                decision = json.loads(content[first_brace:end_pos] if end_pos > 0 else content[first_brace:])
            except json.JSONDecodeError:
                log(f"[LLM] {model_name} JSON parse error")
                return None
        else:
            log(f"[LLM] {model_name} no JSON found in response")
            return None

    # Normalize keys to lowercase first (small models often use UPPER_CASE)
    decision = {k.lower(): v for k, v in decision.items()}

    # Normalize field aliases (small models use different names)
    _aliases = {
        'agent': 'agent_name',
        'agent_id': 'agent_name',
        'recommended_agent': 'agent_name',
        'task': 'task_type',
        'type': 'task_type',
        'skills': 'supplementary_skills',
        'reasoning': 'agent_reasoning',
    }
    for alias, canonical in _aliases.items():
        if alias in decision and canonical not in decision:
            decision[canonical] = decision.pop(alias)
            # If task_type got a dict, extract description
            if canonical == 'task_type' and isinstance(decision[canonical], dict):
                decision[canonical] = decision[canonical].get('description', 'General Task')

    # Validate required fields
    if not all(k in decision for k in ('task_type', 'model', 'agent_name')):
        log(f"[LLM] {model_name} missing required fields: {list(decision.keys())}")
        return None

    # Validate model value
    if decision['model'] not in ('HAIKU', 'SONNET', 'OPUS'):
        log(f"[LLM] {model_name} invalid model value: {decision['model']}")
        return None

    # Validate agent_name exists in registry (auto-fix if empty/invalid)
    valid_names = set(AVAILABLE_AGENTS.keys()) | set(AVAILABLE_SKILLS.keys())
    if decision['agent_name'] not in valid_names:
        # Auto-map from task_type for small models that sometimes miss agent_name
        task_type_agent_map = {
            'API Creation': 'spring-boot-microservices',
            'Authentication': 'spring-boot-microservices',
            'Authorization': 'spring-boot-microservices',
            'Security': 'spring-boot-microservices',
            'Database': 'spring-boot-microservices',
            'Dashboard': 'ui-ux-designer',
            'Frontend': 'angular-engineer',
            'UI/UX': 'ui-ux-designer',
            'Configuration': 'devops-engineer',
            'Bug Fix': 'spring-boot-microservices',
            'Refactoring': 'spring-boot-microservices',
            'Testing': 'qa-testing-agent',
            'Documentation': 'python-backend-engineer',
            'DevOps': 'devops-engineer',
            'Deployment': 'devops-engineer',
            'System/Script': 'python-backend-engineer',
            'Sync/Update': 'python-backend-engineer',
            'Architecture Design': 'orchestrator-agent',
            'Migration': 'spring-boot-microservices',
            'General Task': 'python-backend-engineer',
        }
        fallback_agent = task_type_agent_map.get(
            decision.get('task_type', ''), 'python-backend-engineer'
        )
        log(f"[LLM] {model_name} invalid agent_name '{decision['agent_name']}' "
            f"-> auto-mapped to '{fallback_agent}' from task_type '{decision.get('task_type')}'")
        decision['agent_name'] = fallback_agent

    # Validate supplementary_skills
    supp = decision.get('supplementary_skills', [])
    decision['supplementary_skills'] = [s for s in supp if s in AVAILABLE_SKILLS]

    # Determine agent_type if not set
    if 'agent_type' not in decision:
        decision['agent_type'] = 'agent' if decision['agent_name'] in AVAILABLE_AGENTS else 'skill'

    # Ensure complexity is int and clamped
    decision['complexity'] = max(1, min(int(decision.get('complexity', 10)), 25))

    # Ensure confidence
    decision['confidence'] = min(1.0, max(0.0, float(decision.get('confidence', 0.8))))

    return decision


def _call_ollama(user_prompt):
    """Try local Ollama first (fastest, no rate limits, GPU-accelerated).

    Returns:
        tuple: (decision_dict or None, model_name_used)
    """
    model = OLLAMA_MODEL
    log(f"[OLLAMA] Trying local Ollama: {model}")

    try:
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }).encode('utf-8')

        req = urllib_request.Request(
            OLLAMA_URL,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib_request.urlopen(req, timeout=OLLAMA_TIMEOUT or None) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            msg = result.get('choices', [{}])[0].get('message', {})
            content = (msg.get('content') or '').strip()

            decision = _parse_llm_response(content, f"ollama/{model}")
            if decision:
                decision['llm_model_used'] = f"ollama/{model}"
                decision['llm_source'] = 'local'
                decision['llm_attempt'] = 1
                decision['engine_version'] = '1.2.0'
                log(f"[OLLAMA] SUCCESS: task={decision['task_type']}, "
                    f"model={decision['model']}, agent={decision['agent_name']}")
                return decision

    except (URLError, HTTPError) as e:
        log(f"[OLLAMA] Not available: {str(e)[:80]}")
    except Exception as e:
        log(f"[OLLAMA] Error ({type(e).__name__}): {str(e)[:80]}")

    return None


def _call_openrouter(user_prompt):
    """Fallback to OpenRouter if Ollama is not running.

    Returns:
        decision_dict or None
    """
    api_key = load_api_key()
    if not api_key:
        log("[OPENROUTER] No API key found - skipping fallback")
        return None

    for attempt, model in enumerate(OPENROUTER_MODELS, 1):
        try:
            log(f"[OPENROUTER] Attempt {attempt}/{len(OPENROUTER_MODELS)}: {model}")

            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            }).encode('utf-8')

            req = urllib_request.Request(
                OPENROUTER_URL,
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}',
                    'HTTP-Referer': 'https://claude-insight.local',
                    'X-Title': 'Claude Insight Decision Engine',
                },
                method='POST'
            )

            with urllib_request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                msg = result.get('choices', [{}])[0].get('message', {})
                content = (msg.get('content') or '').strip()

                # Fallback: some free models return reasoning instead of content
                if not content:
                    reasoning = (msg.get('reasoning') or '').strip()
                    if reasoning:
                        content = reasoning

                decision = _parse_llm_response(content, model)
                if decision:
                    decision['llm_model_used'] = model
                    decision['llm_source'] = 'openrouter'
                    decision['llm_attempt'] = attempt
                    decision['engine_version'] = '1.2.0'
                    log(f"[OPENROUTER] SUCCESS ({model}): task={decision['task_type']}, "
                        f"model={decision['model']}, agent={decision['agent_name']}")
                    return decision

        except json.JSONDecodeError as e:
            log(f"[OPENROUTER] {model} JSON parse error: {str(e)[:80]}")
            continue
        except (URLError, HTTPError) as e:
            log(f"[OPENROUTER] {model} HTTP error: {str(e)[:80]}")
            continue
        except Exception as e:
            log(f"[OPENROUTER] {model} error ({type(e).__name__}): {str(e)[:80]}")
            continue

    return None


def call_llm(context):
    """Call LLM with master context. Tries local Ollama first, then OpenRouter.

    Returns:
        decision dict or None on failure.
    """
    user_prompt = build_user_prompt(context)
    log(f"[LLM] Calling with message: {context.get('user_message', '')[:100]}")

    # 1. Try local Ollama (fast, free, GPU-accelerated)
    decision = _call_ollama(user_prompt)
    if decision:
        return decision

    # 2. Fallback to OpenRouter (cloud, rate-limited)
    log("[LLM] Ollama unavailable, falling back to OpenRouter")
    decision = _call_openrouter(user_prompt)
    if decision:
        return decision

    log("[FATAL] All LLM sources failed (Ollama + OpenRouter)")
    return None


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def make_decision(context):
    """Main entry point. Takes context dict, returns decision dict.

    Args:
        context: Dict with keys:
            - user_message (str): Raw user prompt
            - keyword_task_type (str): Task type from keyword detection
            - keyword_complexity (int): Complexity from keyword scoring
            - tech_stack (list): Detected technologies
            - keywords (list): Extracted keywords
            - context_pct (int): Context window usage %
            - task_count (int): Number of tasks from breakdown
            - plan_required (bool): Whether plan mode is needed
            - project_name (str): Current project name

    Returns:
        dict with keys: task_type, complexity, model, model_reasoning,
                        agent_name, agent_type, agent_reasoning,
                        supplementary_skills, confidence, engine_version
        OR None if LLM fails (pipeline should fail)
    """
    start = datetime.now()
    log(f"[START] Decision engine called for: {context.get('user_message', '')[:80]}")

    decision = call_llm(context)

    dur_ms = int((datetime.now() - start).total_seconds() * 1000)
    log(f"[DONE] Duration: {dur_ms}ms, Success: {decision is not None}")

    if decision:
        decision['duration_ms'] = dur_ms

        # Override: plan mode ALWAYS forces OPUS (non-negotiable)
        if context.get('plan_required', False):
            decision['model'] = 'OPUS'
            decision['model_reasoning'] = 'Plan mode active - OPUS mandatory'

    return decision


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    """CLI entry point for standalone testing or pipeline integration."""
    if len(sys.argv) < 2:
        print("=" * 70)
        print("Intelligent Decision Engine v1.0.0")
        print("=" * 70)
        print("\nUsage:")
        print("  python intelligent-decision-engine.py <context.json>")
        print("  python intelligent-decision-engine.py --test 'your message here'")
        print("\nContext JSON keys:")
        print("  user_message, keyword_task_type, keyword_complexity,")
        print("  tech_stack, keywords, context_pct, task_count,")
        print("  plan_required, project_name")
        sys.exit(0)

    if sys.argv[1] == '--test':
        # Quick test mode with just a message
        msg = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else 'Create a REST API for user management'
        context = {
            'user_message': msg,
            'keyword_task_type': 'unknown',
            'keyword_complexity': 0,
            'tech_stack': [],
            'keywords': [],
            'context_pct': 0,
            'task_count': 0,
            'plan_required': False,
            'project_name': 'test'
        }
    else:
        # Load context from JSON file
        context_file = Path(sys.argv[1])
        if not context_file.exists():
            print(json.dumps({"error": f"Context file not found: {sys.argv[1]}"}))
            sys.exit(1)
        with open(context_file, 'r', encoding='utf-8') as f:
            context = json.load(f)

    decision = make_decision(context)

    if decision is None:
        print(json.dumps({"error": "LLM decision engine failed - all models unavailable"}))
        sys.exit(1)

    print(json.dumps(decision, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    main()
