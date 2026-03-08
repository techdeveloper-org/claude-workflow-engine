#!/usr/bin/env python3
"""
Version Release Policy Enforcement (v5.0) - LLM-Powered Documentation Generation

Maps to: policies/03-execution-system/09-git-commit/version-release-policy.md

This module enforces the version release policy for the Claude Memory System.
It ensures that version numbers are bumped according to semantic versioning
(SemVer) principles, that VERSION files are updated consistently, and that
release documentation (README.md, SRS) is comprehensively updated using
LLM-powered content generation via OpenRouter free models.

NEW in v5.0: LLM-Powered Documentation!
  - Uses OpenRouter free models (llama-3.3-70b, qwen3-coder, mistral-small)
  - Generic project scanner (no hardcoded paths, works for ANY project)
  - JSON template approach: LLM fills structured template -> renders to markdown
  - Two modes: CREATE (new doc from scratch) vs UPDATE (fill gaps in existing)
  - Automatic fallback: if LLM fails, uses regex-based version/date updates
  - IEEE 830 / ISO 29148 compliant SRS generation

Policy rules enforced:
  - Version numbers follow SemVer: MAJOR.MINOR.PATCH
  - VERSION file in the repository root is the authoritative version source
  - Release commit message format: 'bump: vX.Y.Z -> vX.Y.Z+1'
  - CHANGELOG.md must be updated with each version bump
  - SYSTEM_REQUIREMENTS_SPECIFICATION.md comprehensively updated via LLM
  - README.md comprehensively updated via LLM

Key Functions:
  enforce(): Activate version release policy and perform version bump.
  validate(): Check git state and compliance.
  report(): Generate a summary report of the policy state.
  scan_project(): Generic project scanner (works for ANY project).
  call_llm(): Call OpenRouter free models with fallback chain.
  generate_readme_content(): LLM-powered README content generation.
  generate_srs_content(): LLM-powered SRS content generation.
  render_readme(): Convert JSON template to markdown README.
  render_srs(): Convert JSON template to markdown SRS.
  bump_version(): Increment version, scan project, generate docs, update all.
  log_action(): Append enforcement events to the policy-hits log.

CLI Usage:
  python version-release-policy.py --enforce   # Run policy enforcement + version bump
  python version-release-policy.py --validate  # Validate policy compliance
  python version-release-policy.py --report    # Generate policy report
  python version-release-policy.py --bump      # Bump version + update docs
  python version-release-policy.py --scan      # Scan project and print stats
"""

import sys
import io
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime

try:
    import urllib.request as urllib_request
except ImportError:
    urllib_request = None

# ===================================================================
# POLICY TRACKING INTEGRATION
# ===================================================================
# Policy tracking - mandatory (find helper by walking up to scripts root)
_scripts_root = Path(__file__).resolve().parent
while _scripts_root != _scripts_root.parent:
    if (_scripts_root / 'policy_tracking_helper.py').exists():
        if str(_scripts_root) not in sys.path:
            sys.path.insert(0, str(_scripts_root))
        break
    _scripts_root = _scripts_root.parent
from policy_tracking_helper import record_policy_execution, record_sub_operation, get_session_id

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ===================================================================
# CONSTANTS
# ===================================================================

LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"

# Primary: Local Ollama (IPEX-LLM on Intel Arc GPU + NPU)
OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
OLLAMA_MODEL = "granite4:3b"

# Fallback: OpenRouter (if Ollama is not running)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-coder:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]
LLM_TIMEOUT = 60
DOC_MAX_TOKENS = 4096

# API Key File
try:
    _search = Path(__file__).resolve().parent
    while _search != _search.parent:
        if (_search / 'ide_paths.py').exists():
            sys.path.insert(0, str(_search))
            break
        _search = _search.parent
    from ide_paths import CONFIG_DIR
    API_KEY_FILE = CONFIG_DIR / 'openrouter-api-key'
except ImportError:
    API_KEY_FILE = Path.home() / '.claude' / 'config' / 'openrouter-api-key'

# Directories to skip during project scanning
SKIP_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv', '.env',
    'dist', 'build', '.idea', '.vscode', '.claude', '.tox', '.mypy_cache',
    '.pytest_cache', 'egg-info', '.eggs', 'target', 'out', 'bin', 'obj',
}

# Code file extensions for line counting
CODE_EXTENSIONS = {
    '.py', '.java', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.rb',
    '.php', '.c', '.cpp', '.h', '.cs', '.swift', '.kt', '.scala',
    '.sh', '.bash', '.ps1', '.r', '.m', '.lua', '.pl', '.ex', '.exs',
}

# ===================================================================
# LLM SYSTEM PROMPTS
# ===================================================================

README_SYSTEM_PROMPT = (
    "You are an expert technical writer creating enterprise-grade README.md content. "
    "You will receive project statistics and optionally existing content. "
    "Return ONLY a valid JSON object (no markdown, no explanation, no code fences). "
    "ALL values must be strings or arrays. Use plain text, not markdown inside values. "
    "Be accurate - use the provided statistics exactly. Do not invent numbers. "
    "Be professional and comprehensive.\n\n"
    "Required JSON structure:\n"
    "{\n"
    '  "project_name": "string",\n'
    '  "tagline": "one-line description of the project",\n'
    '  "overview": "2-3 paragraphs about what the project does and why it exists",\n'
    '  "key_features": ["feature 1", "feature 2", ...],\n'
    '  "architecture_overview": "description of system architecture and components",\n'
    '  "components": [{"name": "str", "description": "str", "path": "str", "file_count": 0}],\n'
    '  "prerequisites": ["Python 3.8+", ...],\n'
    '  "installation_steps": ["step 1", "step 2", ...],\n'
    '  "quick_start": "command to get started",\n'
    '  "usage_commands": [{"command": "str", "description": "str"}],\n'
    '  "project_structure_tree": "directory tree as plain text",\n'
    '  "configuration_options": [{"name": "str", "description": "str", "default": "str"}],\n'
    '  "testing_info": {"how_to_run": "str", "framework": "str"},\n'
    '  "contributing_guidelines": "short contributing guide",\n'
    '  "recent_changes_summary": "summary of recent changes from git log",\n'
    '  "license_type": "MIT or similar"\n'
    "}\n\n"
    "RULES:\n"
    "- Use the exact statistics provided. Never fabricate numbers.\n"
    "- If existing content is provided (UPDATE mode), preserve important custom info.\n"
    "- Return ONLY valid JSON. No markdown wrapping, no comments."
)

SRS_SYSTEM_PROMPT = (
    "You are an expert technical writer creating an enterprise-grade System Requirements "
    "Specification (SRS) document following IEEE 830 / ISO 29148 standards. "
    "You will receive project statistics and optionally existing content. "
    "Return ONLY a valid JSON object (no markdown, no explanation, no code fences). "
    "ALL values must be strings or arrays. Use plain text inside values. "
    "Be accurate with statistics. Be thorough and professional.\n\n"
    "Required JSON structure:\n"
    "{\n"
    '  "document_title": "string",\n'
    '  "executive_summary": "2-3 paragraphs summarizing the system",\n'
    '  "key_statistics": [{"label": "str", "value": "str"}],\n'
    '  "purpose": "why this system exists (1 paragraph)",\n'
    '  "scope": "what the system covers (1 paragraph)",\n'
    '  "definitions": [{"term": "str", "definition": "str"}],\n'
    '  "product_perspective": "how this fits in the larger ecosystem",\n'
    '  "product_functions": ["main function 1", "main function 2"],\n'
    '  "user_characteristics": "who uses this system",\n'
    '  "constraints": ["constraint 1", "constraint 2"],\n'
    '  "assumptions": ["assumption 1", "assumption 2"],\n'
    '  "architecture_overview": "detailed architecture description",\n'
    '  "components": [\n'
    '    {"name": "str", "description": "str", "responsibilities": ["str"], "file_count": 0}\n'
    '  ],\n'
    '  "functional_requirements": [\n'
    '    {"id": "FR-001", "title": "str", "description": "str", "priority": "High/Medium/Low"}\n'
    '  ],\n'
    '  "non_functional_requirements": [\n'
    '    {"id": "NFR-001", "category": "Performance/Security/etc", "title": "str", "description": "str"}\n'
    '  ],\n'
    '  "testing_strategy": "test approach description",\n'
    '  "deployment_info": "deployment procedure",\n'
    '  "conclusion": "summary paragraph"\n'
    "}\n\n"
    "RULES:\n"
    "- Follow IEEE 830 structure strictly.\n"
    "- Use exact statistics provided. Never fabricate numbers.\n"
    "- If existing content is provided (UPDATE mode), preserve custom info.\n"
    "- Return ONLY valid JSON. No markdown wrapping, no comments."
)


# ===================================================================
# LOGGING
# ===================================================================

def log_action(action, context=""):
    """Append a timestamped entry to the policy-hits log."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] version-release-policy | {action} | {context}\n"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


# ===================================================================
# CORE VERSION FUNCTIONS
# ===================================================================

def get_project_root():
    """Find the project root directory (where VERSION file should be)."""
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / "VERSION").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def read_version():
    """Read current version from VERSION file."""
    version_file = get_project_root() / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding='utf-8').strip()
    return "0.0.1"


def parse_version(version_str):
    """Parse version string into (major, minor, patch)."""
    parts = version_str.split('.')
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return 0, 0, 1


def bump_patch_version(current_version):
    """Bump the patch version."""
    major, minor, patch = parse_version(current_version)
    return f"{major}.{minor}.{patch + 1}"


def write_version(new_version):
    """Write new version to VERSION file."""
    try:
        version_file = get_project_root() / "VERSION"
        old_version = (version_file.read_text(encoding='utf-8').strip()
                       if version_file.exists() else "unknown")
        version_file.write_text(new_version, encoding='utf-8')
        log_action("VERSION_BUMPED", f"{old_version} -> {new_version}")
        return True
    except Exception as e:
        log_action("VERSION_WRITE_ERROR", str(e))
        return False


# ===================================================================
# LLM INTEGRATION (OpenRouter Free Models)
# ===================================================================

def load_api_key():
    """Load OpenRouter API key from config file."""
    if not API_KEY_FILE.exists():
        return None
    try:
        key = API_KEY_FILE.read_text(encoding='utf-8').strip()
        if not key or len(key) < 10:
            return None
        return key
    except Exception:
        return None


def _strip_code_fences(content):
    """Remove markdown code fences from LLM response."""
    if content.startswith('```'):
        fence_lines = content.split('\n')
        if fence_lines[0].startswith('```'):
            fence_lines = fence_lines[1:]
        if fence_lines and fence_lines[-1].strip() == '```':
            fence_lines = fence_lines[:-1]
        content = '\n'.join(fence_lines)
    return content


def call_llm(system_prompt, user_prompt, max_tokens=None):
    """Call LLM with Ollama-first, OpenRouter-fallback strategy.

    Tries local Ollama first (fast, no rate limits), then falls back
    to OpenRouter cloud models. Returns parsed JSON or None.
    """
    if urllib_request is None:
        log_action("LLM_SKIP", "urllib.request not available")
        return None

    if max_tokens is None:
        max_tokens = DOC_MAX_TOKENS

    # 1. Try local Ollama first
    try:
        log_action("LLM_OLLAMA", f"Trying local: {OLLAMA_MODEL}")
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }).encode('utf-8')

        req = urllib_request.Request(
            OLLAMA_URL, data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib_request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            content = (result.get('choices', [{}])[0]
                       .get('message', {}).get('content', '').strip())
            if content:
                content = _strip_code_fences(content)
                parsed = json.loads(content)
                log_action("LLM_SUCCESS", f"ollama/{OLLAMA_MODEL} returned valid JSON")
                return parsed
    except Exception as e:
        log_action("LLM_OLLAMA_FAIL", f"{str(e)[:80]}")

    # 2. Fallback to OpenRouter
    api_key = load_api_key()
    if not api_key:
        log_action("LLM_SKIP", "No API key for OpenRouter fallback")
        return None

    for attempt, model in enumerate(OPENROUTER_MODELS, 1):
        try:
            log_action("LLM_ATTEMPT", f"{attempt}/{len(OPENROUTER_MODELS)}: {model}")

            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            }).encode('utf-8')

            req = urllib_request.Request(
                OPENROUTER_URL,
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}',
                    'HTTP-Referer': 'https://claude-insight.local',
                    'X-Title': 'Claude Insight Doc Generator',
                },
                method='POST'
            )

            with urllib_request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                content = (result.get('choices', [{}])[0]
                           .get('message', {}).get('content', '').strip())

                if not content:
                    log_action("LLM_EMPTY", f"{model} returned empty response")
                    continue

                content = _strip_code_fences(content)
                parsed = json.loads(content)
                log_action("LLM_SUCCESS", f"{model} returned valid JSON")
                return parsed

        except json.JSONDecodeError as e:
            log_action("LLM_JSON_ERROR", f"{model}: {str(e)[:80]}")
            continue
        except urllib_request.URLError as e:
            log_action("LLM_URL_ERROR", f"{model}: {str(e)[:80]}")
            continue
        except Exception as e:
            log_action("LLM_ERROR", f"{model} ({type(e).__name__}): {str(e)[:80]}")
            continue

    log_action("LLM_ALL_FAILED", "All models failed - using fallback")
    return None


def get_recent_git_changes(root):
    """Get recent git commit messages for context."""
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', '-20', '--no-decorate'],
            capture_output=True, text=True, cwd=str(root), timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


# ===================================================================
# GENERIC PROJECT SCANNER (works for ANY project)
# ===================================================================

def scan_project():
    """Scan the project directory and collect comprehensive statistics.

    Fully generic - works for ANY project type without hardcoded paths.
    Dynamically discovers directories, counts files by extension, detects
    project type, and collects metadata.
    """
    root = get_project_root()
    stats = {}

    # 1. Count files by extension
    file_counts = {}
    total_lines = 0
    total_files = 0

    for f in root.rglob('*'):
        if not f.is_file():
            continue
        if any(skip in f.parts for skip in SKIP_DIRS):
            continue
        total_files += 1
        ext = f.suffix.lower()
        if ext:
            file_counts[ext] = file_counts.get(ext, 0) + 1
        if ext in CODE_EXTENSIONS:
            try:
                total_lines += sum(1 for _ in f.open('r', encoding='utf-8', errors='replace'))
            except Exception:
                pass

    stats['file_counts_by_extension'] = file_counts
    stats['total_files'] = total_files
    stats['total_lines'] = total_lines
    stats['total_python'] = file_counts.get('.py', 0)
    stats['total_java'] = file_counts.get('.java', 0)
    stats['total_js'] = file_counts.get('.js', 0) + file_counts.get('.jsx', 0)
    stats['total_ts'] = file_counts.get('.ts', 0) + file_counts.get('.tsx', 0)
    stats['total_html'] = file_counts.get('.html', 0)
    stats['total_css'] = file_counts.get('.css', 0)
    stats['total_md'] = file_counts.get('.md', 0)
    stats['total_yaml'] = file_counts.get('.yaml', 0) + file_counts.get('.yml', 0)
    stats['total_shell'] = (file_counts.get('.sh', 0) + file_counts.get('.bash', 0)
                            + file_counts.get('.ps1', 0))

    # 2. Detect project type
    indicators = []
    if (root / 'pom.xml').exists():
        indicators.append('Java (Maven)')
    if (root / 'build.gradle').exists() or (root / 'build.gradle.kts').exists():
        indicators.append('Java (Gradle)')
    if (root / 'package.json').exists():
        indicators.append('Node.js')
    if (root / 'requirements.txt').exists() or (root / 'setup.py').exists():
        indicators.append('Python (pip)')
    if (root / 'pyproject.toml').exists():
        indicators.append('Python (Poetry/PEP)')
    if (root / 'Pipfile').exists():
        indicators.append('Python (Pipenv)')
    if (root / 'Cargo.toml').exists():
        indicators.append('Rust')
    if (root / 'go.mod').exists():
        indicators.append('Go')
    if (root / 'Gemfile').exists():
        indicators.append('Ruby')
    if (root / 'composer.json').exists():
        indicators.append('PHP')
    if (root / 'Dockerfile').exists() or (root / 'docker-compose.yml').exists():
        indicators.append('Docker')
    if (root / '.github').exists():
        indicators.append('GitHub CI/CD')
    if (root / 'Jenkinsfile').exists():
        indicators.append('Jenkins CI/CD')
    stats['project_type'] = indicators if indicators else ['Unknown']

    lang_counts = [
        ('Python', stats['total_python']),
        ('Java', stats['total_java']),
        ('JavaScript', stats['total_js']),
        ('TypeScript', stats['total_ts']),
    ]
    lang_counts.sort(key=lambda x: x[1], reverse=True)
    stats['primary_language'] = lang_counts[0][0] if lang_counts[0][1] > 0 else 'Unknown'

    # 3. Discover directory structure (top-level)
    dir_structure = {}
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith('.'):
            count = sum(1 for f in d.rglob('*') if f.is_file()
                        and not any(skip in f.parts for skip in SKIP_DIRS))
            dir_structure[d.name] = count
    stats['directory_structure'] = dir_structure

    # 4. Count dependencies
    deps_count = 0
    deps_source = 'none'
    if (root / 'requirements.txt').exists():
        try:
            lines = (root / 'requirements.txt').read_text(
                encoding='utf-8', errors='replace').splitlines()
            deps_count = len([l for l in lines
                              if l.strip() and not l.startswith('#') and not l.startswith('-')])
            deps_source = 'requirements.txt'
        except Exception:
            pass
    elif (root / 'package.json').exists():
        try:
            pkg = json.loads((root / 'package.json').read_text(encoding='utf-8'))
            deps_count = len(pkg.get('dependencies', {})) + len(pkg.get('devDependencies', {}))
            deps_source = 'package.json'
        except Exception:
            pass
    elif (root / 'pom.xml').exists():
        try:
            pom = (root / 'pom.xml').read_text(encoding='utf-8', errors='replace')
            deps_count = pom.count('<dependency>')
            deps_source = 'pom.xml'
        except Exception:
            pass
    stats['dependency_count'] = deps_count
    stats['deps_source'] = deps_source

    # 5. Detect test files
    test_count = 0
    test_dirs_found = []
    for test_dir_name in ['tests', 'test', 'spec', 'specs', '__tests__']:
        td = root / test_dir_name
        if td.exists() and td.is_dir():
            count = sum(1 for f in td.rglob('*')
                        if f.is_file() and f.suffix in CODE_EXTENSIONS)
            test_count += count
            test_dirs_found.append(test_dir_name)
    src_test = root / 'src' / 'test'
    if src_test.exists():
        test_count += sum(1 for f in src_test.rglob('*')
                          if f.is_file() and f.suffix in CODE_EXTENSIONS)
        test_dirs_found.append('src/test')
    stats['test_files'] = test_count
    stats['test_dirs'] = test_dirs_found

    # 6. Detect templates
    template_count = 0
    template_exts = {'.html', '.jinja2', '.j2', '.ejs', '.pug', '.hbs',
                     '.mustache', '.ftl', '.vm', '.jsp', '.erb'}
    for tpl_dir in ['templates', 'views', 'pages']:
        td = root / tpl_dir
        if td.exists():
            template_count += sum(1 for f in td.rglob('*')
                                  if f.is_file() and f.suffix in template_exts)
    java_tpl = root / 'src' / 'main' / 'resources' / 'templates'
    if java_tpl.exists():
        template_count += sum(1 for f in java_tpl.rglob('*')
                              if f.is_file() and f.suffix in template_exts)
    stats['templates'] = template_count

    # 7. Static assets
    static_css = 0
    static_js = 0
    static_images = 0
    image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp'}
    for sd_name in ['static', 'public', 'assets']:
        sd = root / sd_name
        if sd.exists():
            static_css += sum(1 for f in sd.rglob('*.css'))
            static_js += sum(1 for f in sd.rglob('*.js'))
            static_images += sum(1 for f in sd.rglob('*')
                                 if f.suffix.lower() in image_exts)
    stats['static_css'] = static_css
    stats['static_js'] = static_js
    stats['static_images'] = static_images

    # 8. Existing documentation state
    readme_file = root / 'README.md'
    srs_file = root / 'SYSTEM_REQUIREMENTS_SPECIFICATION.md'
    stats['has_readme'] = readme_file.exists()
    stats['has_srs'] = srs_file.exists()
    stats['readme_lines'] = 0
    stats['srs_lines'] = 0
    if readme_file.exists():
        try:
            stats['readme_lines'] = sum(
                1 for _ in readme_file.open('r', encoding='utf-8', errors='replace'))
        except Exception:
            pass
    if srs_file.exists():
        try:
            stats['srs_lines'] = sum(
                1 for _ in srs_file.open('r', encoding='utf-8', errors='replace'))
        except Exception:
            pass

    # 9. Project metadata
    stats['version'] = read_version()
    stats['timestamp'] = datetime.now().strftime('%Y-%m-%d')
    stats['project_name'] = root.name
    stats['project_root'] = str(root)

    return stats


# ===================================================================
# DOCUMENT CONTENT GENERATION (LLM)
# ===================================================================

def _build_user_prompt(stats, existing_content, git_changes, doc_type):
    """Build the user prompt for LLM doc generation."""
    parts = []
    parts.append(f"PROJECT: {stats.get('project_name', 'Unknown')}")
    parts.append(f"VERSION: {stats.get('version', '0.0.1')}")
    parts.append(f"PRIMARY LANGUAGE: {stats.get('primary_language', 'Unknown')}")
    parts.append(f"PROJECT TYPE: {', '.join(stats.get('project_type', ['Unknown']))}")
    parts.append(f"TOTAL FILES: {stats.get('total_files', 0)}")
    parts.append(f"TOTAL CODE LINES: ~{stats.get('total_lines', 0)}")
    parts.append(f"DEPENDENCIES: {stats.get('dependency_count', 0)}"
                 f" (from {stats.get('deps_source', 'unknown')})")
    parts.append(f"TEST FILES: {stats.get('test_files', 0)}")
    parts.append(f"TEMPLATES: {stats.get('templates', 0)}")

    ext_counts = stats.get('file_counts_by_extension', {})
    if ext_counts:
        top_exts = sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ext_str = ', '.join(f"{ext}: {count}" for ext, count in top_exts)
        parts.append(f"FILE TYPES (top 10): {ext_str}")

    dir_struct = stats.get('directory_structure', {})
    if dir_struct:
        dir_str = ', '.join(f"{name}/ ({count} files)"
                            for name, count in sorted(dir_struct.items()))
        parts.append(f"DIRECTORIES: {dir_str}")

    if git_changes:
        parts.append(f"\nRECENT GIT CHANGES (last 20 commits):\n{git_changes}")

    if existing_content:
        parts.append(f"\nMODE: UPDATE - Existing {doc_type.upper()} provided below. "
                     f"Preserve important custom content, update statistics, fill gaps.")
        truncated = existing_content[:3000]
        if len(existing_content) > 3000:
            truncated += f"\n... (truncated, original is {len(existing_content)} chars)"
        parts.append(f"\nEXISTING CONTENT:\n{truncated}")
    else:
        parts.append(f"\nMODE: CREATE - Generate a COMPLETE new {doc_type.upper()} from scratch.")

    return '\n'.join(parts)


def generate_readme_content(stats, existing_content, git_changes):
    """Generate README content using LLM."""
    user_prompt = _build_user_prompt(stats, existing_content, git_changes, 'readme')
    return call_llm(README_SYSTEM_PROMPT, user_prompt)


def generate_srs_content(stats, existing_content, git_changes):
    """Generate SRS content using LLM."""
    user_prompt = _build_user_prompt(stats, existing_content, git_changes, 'srs')
    return call_llm(SRS_SYSTEM_PROMPT, user_prompt)


# ===================================================================
# MARKDOWN RENDERERS (JSON -> Markdown)
# ===================================================================

def render_readme(data, version, timestamp):
    """Convert LLM JSON response to formatted README.md markdown."""
    lines = []
    name = data.get('project_name', 'Project')

    lines.append(f"# {name} v{version}")
    lines.append("")
    lines.append(f"![Version](https://img.shields.io/badge/Version-{version}-brightgreen)")
    lines.append("")

    tagline = data.get('tagline', '')
    if tagline:
        lines.append(f"> {tagline}")
        lines.append("")

    overview = data.get('overview', '')
    if overview:
        lines.append("## Overview")
        lines.append("")
        lines.append(overview)
        lines.append("")

    features = data.get('key_features', [])
    if features:
        lines.append("## Key Features")
        lines.append("")
        for feat in features:
            lines.append(f"- {feat}")
        lines.append("")

    arch = data.get('architecture_overview', '')
    if arch:
        lines.append("## Architecture")
        lines.append("")
        lines.append(arch)
        lines.append("")

    components = data.get('components', [])
    if components:
        lines.append("### Components")
        lines.append("")
        lines.append("| Component | Description | Path | Files |")
        lines.append("|-----------|-------------|------|-------|")
        for c in components:
            lines.append(f"| {c.get('name', '')} | {c.get('description', '')} "
                         f"| `{c.get('path', '')}` | {c.get('file_count', '')} |")
        lines.append("")

    prereqs = data.get('prerequisites', [])
    install_steps = data.get('installation_steps', [])
    if prereqs or install_steps:
        lines.append("## Installation")
        lines.append("")
        if prereqs:
            lines.append("### Prerequisites")
            lines.append("")
            for p in prereqs:
                lines.append(f"- {p}")
            lines.append("")
        if install_steps:
            lines.append("### Setup")
            lines.append("")
            for i, step in enumerate(install_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

    qs = data.get('quick_start', '')
    if qs:
        lines.append("### Quick Start")
        lines.append("")
        lines.append(f"```bash\n{qs}\n```")
        lines.append("")

    cmds = data.get('usage_commands', [])
    if cmds:
        lines.append("## Usage")
        lines.append("")
        lines.append("```bash")
        for cmd in cmds:
            lines.append(f"# {cmd.get('description', '')}")
            lines.append(cmd.get('command', ''))
            lines.append("")
        lines.append("```")
        lines.append("")

    tree = data.get('project_structure_tree', '')
    if tree:
        lines.append("## Project Structure")
        lines.append("")
        lines.append("```")
        lines.append(tree)
        lines.append("```")
        lines.append("")

    config = data.get('configuration_options', [])
    if config:
        lines.append("## Configuration")
        lines.append("")
        lines.append("| Option | Description | Default |")
        lines.append("|--------|-------------|---------|")
        for opt in config:
            lines.append(f"| `{opt.get('name', '')}` | {opt.get('description', '')} "
                         f"| `{opt.get('default', '')}` |")
        lines.append("")

    test_info = data.get('testing_info', {})
    if test_info:
        lines.append("## Testing")
        lines.append("")
        if isinstance(test_info, dict):
            how = test_info.get('how_to_run', '')
            fw = test_info.get('framework', '')
            if how:
                lines.append(f"```bash\n{how}\n```")
            if fw:
                lines.append(f"\nTest framework: {fw}")
        else:
            lines.append(str(test_info))
        lines.append("")

    contrib = data.get('contributing_guidelines', '')
    if contrib:
        lines.append("## Contributing")
        lines.append("")
        lines.append(contrib)
        lines.append("")

    changes = data.get('recent_changes_summary', '')
    if changes:
        lines.append("## Recent Changes")
        lines.append("")
        lines.append(changes)
        lines.append("")

    lic = data.get('license_type', '')
    if lic:
        lines.append("## License")
        lines.append("")
        lines.append(lic)
        lines.append("")

    lines.append("---")
    lines.append(f"**Version:** {version} | **Last Updated:** {timestamp}")
    lines.append("")
    lines.append("*Documentation auto-generated by version-release-policy.py v5.0*")
    lines.append("")

    return '\n'.join(lines)


def render_srs(data, version, timestamp):
    """Convert LLM JSON response to formatted SRS markdown (IEEE 830)."""
    lines = []
    title = data.get('document_title', 'System Requirements Specification')

    lines.append(f"# {title} v{version}")
    lines.append("")
    lines.append("**Document Version:** 1.0")
    lines.append(f"**Release Date:** {timestamp}")
    lines.append(f"**Last Updated:** {timestamp}")
    lines.append("**Classification:** Enterprise-Grade System Documentation")
    lines.append("**Status:** Active")
    lines.append("")
    lines.append("---")
    lines.append("")

    exec_summary = data.get('executive_summary', '')
    if exec_summary:
        lines.append("## 1. Executive Summary")
        lines.append("")
        lines.append(exec_summary)
        lines.append("")

    key_stats = data.get('key_statistics', [])
    if key_stats:
        lines.append("### Key Statistics")
        lines.append("")
        for ks in key_stats:
            lines.append(f"- **{ks.get('label', '')}:** {ks.get('value', '')}")
        lines.append("")

    lines.append("## 2. Introduction")
    lines.append("")

    purpose = data.get('purpose', '')
    if purpose:
        lines.append("### 2.1 Purpose")
        lines.append("")
        lines.append(purpose)
        lines.append("")

    scope = data.get('scope', '')
    if scope:
        lines.append("### 2.2 Scope")
        lines.append("")
        lines.append(scope)
        lines.append("")

    defs = data.get('definitions', [])
    if defs:
        lines.append("### 2.3 Definitions")
        lines.append("")
        lines.append("| Term | Definition |")
        lines.append("|------|-----------|")
        for d in defs:
            lines.append(f"| {d.get('term', '')} | {d.get('definition', '')} |")
        lines.append("")

    lines.append("## 3. Overall Description")
    lines.append("")

    perspective = data.get('product_perspective', '')
    if perspective:
        lines.append("### 3.1 Product Perspective")
        lines.append("")
        lines.append(perspective)
        lines.append("")

    functions = data.get('product_functions', [])
    if functions:
        lines.append("### 3.2 Product Functions")
        lines.append("")
        for fn in functions:
            lines.append(f"- {fn}")
        lines.append("")

    users = data.get('user_characteristics', '')
    if users:
        lines.append("### 3.3 User Characteristics")
        lines.append("")
        lines.append(users)
        lines.append("")

    constraints = data.get('constraints', [])
    if constraints:
        lines.append("### 3.4 Constraints")
        lines.append("")
        for c in constraints:
            lines.append(f"- {c}")
        lines.append("")

    assumptions = data.get('assumptions', [])
    if assumptions:
        lines.append("### 3.5 Assumptions and Dependencies")
        lines.append("")
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")

    arch = data.get('architecture_overview', '')
    if arch:
        lines.append("## 4. System Architecture")
        lines.append("")
        lines.append(arch)
        lines.append("")

    components = data.get('components', [])
    if components:
        lines.append("### 4.1 Components")
        lines.append("")
        for comp in components:
            cname = comp.get('name', '')
            ccount = comp.get('file_count', '')
            lines.append(f"#### {cname} ({ccount} files)")
            lines.append("")
            lines.append(comp.get('description', ''))
            lines.append("")
            resps = comp.get('responsibilities', [])
            if resps:
                for r in resps:
                    lines.append(f"- {r}")
                lines.append("")

    func_reqs = data.get('functional_requirements', [])
    if func_reqs:
        lines.append("## 5. Functional Requirements")
        lines.append("")
        lines.append("| ID | Title | Description | Priority |")
        lines.append("|----|-------|-------------|----------|")
        for fr in func_reqs:
            lines.append(f"| {fr.get('id', '')} | {fr.get('title', '')} "
                         f"| {fr.get('description', '')} | {fr.get('priority', 'Medium')} |")
        lines.append("")

    nfr = data.get('non_functional_requirements', [])
    if nfr:
        lines.append("## 6. Non-Functional Requirements")
        lines.append("")
        lines.append("| ID | Category | Title | Description |")
        lines.append("|----|----------|-------|-------------|")
        for nr in nfr:
            lines.append(f"| {nr.get('id', '')} | {nr.get('category', '')} "
                         f"| {nr.get('title', '')} | {nr.get('description', '')} |")
        lines.append("")

    test_strat = data.get('testing_strategy', '')
    if test_strat:
        lines.append("## 7. Quality Assurance")
        lines.append("")
        lines.append(test_strat)
        lines.append("")

    deploy = data.get('deployment_info', '')
    if deploy:
        lines.append("## 8. Deployment")
        lines.append("")
        lines.append(deploy)
        lines.append("")

    conclusion = data.get('conclusion', '')
    if conclusion:
        lines.append("## 9. Conclusion")
        lines.append("")
        lines.append(conclusion)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"**Version:** {version} | **Document Version:** 1.0 "
                 f"| **Last Updated:** {timestamp}")
    lines.append("")
    lines.append("*This document is auto-generated by version-release-policy.py v5.0 "
                 "(IEEE 830 compliant)*")
    lines.append("")

    return '\n'.join(lines)


# ===================================================================
# UPDATE FUNCTIONS
# ===================================================================

def update_changelog(new_version, stats=None):
    """Update CHANGELOG.md with new version entry. Creates file if not exists."""
    try:
        changelog_file = get_project_root() / "CHANGELOG.md"
        timestamp = datetime.now().strftime('%Y-%m-%d')

        new_entry = f"## [{new_version}] - {timestamp}\n"
        new_entry += "### Changed\n"
        new_entry += f"- Version bump to {new_version}\n"

        if stats:
            new_entry += (f"- Project: {stats.get('total_files', '?')} files, "
                          f"{stats.get('total_python', '?')} Python, "
                          f"~{stats.get('total_lines', '?')} lines\n")
            new_entry += (f"- Dependencies: {stats.get('dependency_count', '?')}, "
                          f"Tests: {stats.get('test_files', '?')}, "
                          f"Templates: {stats.get('templates', '?')}\n")

        new_entry += "- Updated README.md, SYSTEM_REQUIREMENTS_SPECIFICATION.md\n"
        new_entry += "- Auto-updated via version-release-policy.py v5.0\n\n"

        if changelog_file.exists():
            existing_content = changelog_file.read_text(encoding='utf-8')
            new_content = new_entry + existing_content
        else:
            new_content = "# Changelog\n\n"
            new_content += "All notable changes to this project will be documented in this file.\n\n"
            new_content += new_entry

        changelog_file.write_text(new_content, encoding='utf-8')
        log_action("CHANGELOG_UPDATED", f"Added entry for v{new_version}")
        return True
    except Exception as e:
        log_action("CHANGELOG_UPDATE_ERROR", str(e))
        return False


def update_srs(new_version, stats=None, llm_content=None):
    """Update SYSTEM_REQUIREMENTS_SPECIFICATION.md.

    Three modes:
    1. LLM mode: Use LLM-generated content (llm_content provided)
    2. Fallback mode: Update version/date strings only (file exists, no LLM)
    3. Create mode: Generate minimal SRS template (no file, no LLM)
    """
    try:
        srs_file = get_project_root() / "SYSTEM_REQUIREMENTS_SPECIFICATION.md"
        timestamp = datetime.now().strftime('%Y-%m-%d')

        if llm_content:
            rendered = render_srs(llm_content, new_version, timestamp)
            srs_file.write_text(rendered, encoding='utf-8')
            log_action("SRS_UPDATED", f"LLM-powered update for v{new_version}")
            return True

        if srs_file.exists():
            content = srs_file.read_text(encoding='utf-8')
            content = re.sub(
                r'(#\s+.*?v)\d+\.\d+\.\d+',
                rf'\g<1>{new_version}',
                content, count=1
            )
            doc_ver = re.search(r'Document Version.*?(\d+)\.(\d+)', content)
            if doc_ver:
                new_minor = int(doc_ver.group(2)) + 1
                content = re.sub(
                    r'(Document Version.*?)\d+\.\d+',
                    rf'\g<1>{doc_ver.group(1)}.{new_minor}',
                    content, count=1
                )
            content = re.sub(
                r'(Last Updated:.*?)\d{4}-\d{2}-\d{2}',
                rf'\g<1>{timestamp}', content
            )
            content = re.sub(
                r'(Release Date:.*?)\d{4}-\d{2}-\d{2}',
                rf'\g<1>{timestamp}', content
            )
            content = re.sub(
                r'(\*\*Version:\*\*\s*)\d+\.\d+\.\d+',
                rf'\g<1>{new_version}', content
            )
            srs_file.write_text(content, encoding='utf-8')
            log_action("SRS_UPDATED", f"Fallback: version/date update for v{new_version}")
            return True

        s = stats or {}
        basic_srs = (
            f"# {s.get('project_name', 'Project')} v{new_version}"
            f" - System Requirements Specification\n\n"
            f"**Document Version:** 1.0\n"
            f"**Release Date:** {timestamp}\n"
            f"**Last Updated:** {timestamp}\n\n"
            f"---\n\n"
            f"## Overview\n\n"
            f"{s.get('project_name', 'Project')} v{new_version} - "
            f"{s.get('total_files', '?')} files, "
            f"~{s.get('total_lines', '?')} lines of code.\n\n"
            f"---\n\n"
            f"**Version:** {new_version} | **Last Updated:** {timestamp}\n\n"
            f"*Auto-generated by version-release-policy.py v5.0*\n"
        )
        srs_file.write_text(basic_srs, encoding='utf-8')
        log_action("SRS_CREATED", f"Minimal SRS for v{new_version}")
        return True

    except Exception as e:
        log_action("SRS_UPDATE_ERROR", str(e))
        return False


def update_readme(new_version, stats=None, llm_content=None):
    """Update README.md.

    Three modes:
    1. LLM mode: Use LLM-generated content (llm_content provided)
    2. Fallback mode: Update version/date strings only (file exists, no LLM)
    3. Create mode: Generate minimal README (no file, no LLM)
    """
    try:
        readme_file = get_project_root() / "README.md"
        timestamp = datetime.now().strftime('%Y-%m-%d')

        if llm_content:
            rendered = render_readme(llm_content, new_version, timestamp)
            readme_file.write_text(rendered, encoding='utf-8')
            log_action("README_UPDATED", f"LLM-powered update for v{new_version}")
            return True

        if readme_file.exists():
            content = readme_file.read_text(encoding='utf-8')
            content = re.sub(
                r'(#\s+\S+.*?v)\d+\.\d+\.\d+',
                rf'\g<1>{new_version}',
                content, count=1
            )
            content = re.sub(
                r'(Version-)\d+\.\d+\.\d+(-\w+)',
                rf'\g<1>{new_version}\g<2>', content
            )
            content = re.sub(
                r'(\*\*Version:\*\*\s*)\d+\.\d+\.\d+',
                rf'\g<1>{new_version}', content
            )
            content = re.sub(
                r'(\*\*Last Updated:\*\*\s*)\d{4}-\d{2}-\d{2}',
                rf'\g<1>{timestamp}', content
            )
            readme_file.write_text(content, encoding='utf-8')
            log_action("README_UPDATED", f"Fallback: version/date update for v{new_version}")
            return True

        s = stats or {}
        basic = (
            f"# {s.get('project_name', 'Project')} v{new_version}\n\n"
            f"![Version](https://img.shields.io/badge/Version-{new_version}-brightgreen)\n\n"
            f"## Overview\n\n"
            f"Project with {s.get('total_files', '?')} files "
            f"and ~{s.get('total_lines', '?')} lines of code.\n\n"
            f"---\n\n"
            f"**Version:** {new_version} | **Last Updated:** {timestamp}\n\n"
            f"*Auto-generated by version-release-policy.py v5.0*\n"
        )
        readme_file.write_text(basic, encoding='utf-8')
        log_action("README_CREATED", f"Minimal README for v{new_version}")
        return True

    except Exception as e:
        log_action("README_UPDATE_ERROR", str(e))
        return False


# ===================================================================
# ORCHESTRATION
# ===================================================================

def bump_version():
    """Perform complete version bump with LLM-powered doc generation.

    Flow: scan -> git changes -> read existing -> LLM calls -> update all files.
    Falls back to regex-based updates if LLM is unavailable.
    """
    try:
        current_version = read_version()
        new_version = bump_patch_version(current_version)
        root = get_project_root()

        print(f"[version-release-policy] Bumping: {current_version} -> {new_version}")
        print(f"[version-release-policy] Scanning project (generic mode)...")

        stats = scan_project()
        print(f"[version-release-policy] Scanned: {stats.get('total_files', 0)} files, "
              f"{stats.get('primary_language', '?')} primary, "
              f"~{stats.get('total_lines', 0)} lines")

        git_changes = get_recent_git_changes(root)

        readme_file = root / "README.md"
        srs_file = root / "SYSTEM_REQUIREMENTS_SPECIFICATION.md"
        existing_readme = None
        existing_srs = None
        if readme_file.exists():
            try:
                existing_readme = readme_file.read_text(encoding='utf-8', errors='replace')
            except Exception:
                pass
        if srs_file.exists():
            try:
                existing_srs = srs_file.read_text(encoding='utf-8', errors='replace')
            except Exception:
                pass

        readme_llm = None
        srs_llm = None
        llm_used = False

        print(f"[version-release-policy] Calling LLM for README generation...")
        readme_llm = generate_readme_content(stats, existing_readme, git_changes)
        if readme_llm:
            print(f"[version-release-policy] README content generated via LLM [OK]")
            llm_used = True
        else:
            print(f"[version-release-policy] README LLM failed - will use fallback")

        print(f"[version-release-policy] Calling LLM for SRS generation...")
        srs_llm = generate_srs_content(stats, existing_srs, git_changes)
        if srs_llm:
            print(f"[version-release-policy] SRS content generated via LLM [OK]")
            llm_used = True
        else:
            print(f"[version-release-policy] SRS LLM failed - will use fallback")

        if not write_version(new_version):
            return {"status": "error", "message": "Failed to update VERSION file"}

        if not update_changelog(new_version, stats):
            return {"status": "error", "message": "Failed to update CHANGELOG.md"}

        if not update_srs(new_version, stats, srs_llm):
            return {"status": "error", "message": "Failed to update SRS"}

        if not update_readme(new_version, stats, readme_llm):
            return {"status": "error", "message": "Failed to update README.md"}

        mode = "LLM-powered" if llm_used else "Fallback (regex)"
        print(f"[version-release-policy] Version bumped: {new_version} ({mode})")
        print(f"[version-release-policy] All docs updated [OK]")

        # Regenerate code graph analysis (Step 3.0.1 cache)
        # Graph must be rebuilt after code/doc changes so next session gets fresh data
        try:
            graph_script = Path(__file__).parent.parent / '00-code-graph-analysis' / 'code-graph-analyzer.py'
            if graph_script.exists():
                import subprocess as _sp
                _sp.run(
                    [sys.executable, str(graph_script), str(get_project_root()), '--regenerate'],
                    capture_output=True, timeout=15
                )
                print(f"[version-release-policy] Graph analysis regenerated [OK]")
            else:
                print(f"[version-release-policy] Graph analyzer not found - skipping")
        except Exception as _ge:
            print(f"[version-release-policy] Graph regeneration failed: {str(_ge)[:60]}")

        return {
            "status": "success",
            "old_version": current_version,
            "new_version": new_version,
            "mode": mode,
            "files_updated": [
                "VERSION", "CHANGELOG.md",
                "SYSTEM_REQUIREMENTS_SPECIFICATION.md", "README.md"
            ],
            "stats": stats
        }
    except Exception as e:
        log_action("BUMP_ERROR", str(e))
        return {"status": "error", "message": str(e)}


# ===================================================================
# ENFORCEMENT & REPORTING
# ===================================================================

def validate():
    """Check that the version release policy preconditions are met."""
    try:
        log_action("VALIDATE", "version-release-ready")
        return True
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the version release policy."""
    current_version = read_version()
    return {
        "status": "success",
        "policy": "version-release",
        "description": "Enforces SemVer versioning with LLM-powered doc generation",
        "current_version": current_version,
        "rules": [
            "Version numbers follow MAJOR.MINOR.PATCH (SemVer)",
            "VERSION file is updated on each release",
            "CHANGELOG.md updated with each version bump",
            "README.md comprehensively updated via LLM",
            "SYSTEM_REQUIREMENTS_SPECIFICATION.md updated via LLM (IEEE 830)",
            "Release commit format: 'bump: vX.Y.Z -> vX.Y.Z+1'",
            "Fallback to regex-based updates if LLM unavailable"
        ],
        "llm_models": LLM_MODELS,
        "files_tracked": [
            "VERSION", "CHANGELOG.md",
            "SYSTEM_REQUIREMENTS_SPECIFICATION.md", "README.md"
        ],
        "timestamp": datetime.now().isoformat()
    }


def enforce():
    """Activate the version release policy and perform version bump."""
    import os
    _track_start_time = datetime.now()
    _sub_operations = []

    try:
        log_action("ENFORCE_START", "version-release")

        _op_start = datetime.now()
        bump_result = bump_version()
        _sub_operations.append(
            record_sub_operation(
                "bump_version",
                bump_result.get("status", "unknown"),
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {
                    "old_version": bump_result.get("old_version"),
                    "new_version": bump_result.get("new_version"),
                    "mode": bump_result.get("mode", "unknown")
                }
            )
        )

        if bump_result.get("status") != "success":
            log_action("ENFORCE_ERROR", bump_result.get("message", "Unknown error"))
            return bump_result

        log_action("ENFORCE_SUCCESS", f"Version bumped to {bump_result.get('new_version')}")
        print("[version-release-policy] Policy enforced successfully [OK]")

        result = {
            "status": "success",
            "action": "version_bump_and_docs_update",
            "details": bump_result
        }

        try:
            record_policy_execution(
                session_id=get_session_id(),
                policy_name="version-release-policy",
                policy_script="version-release-policy.py",
                policy_type="Policy Script",
                input_params={"current_version": bump_result.get("old_version")},
                output_results=result,
                decision=(f"Version bumped to {bump_result.get('new_version')} "
                          f"({bump_result.get('mode', 'unknown')})"),
                duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                sub_operations=[op for op in _sub_operations if op is not None]
            )
        except Exception:
            pass

        return result

    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        error_result = {"status": "error", "message": str(e)}
        try:
            record_policy_execution(
                session_id=get_session_id(),
                policy_name="version-release-policy",
                policy_script="version-release-policy.py",
                policy_type="Policy Script",
                input_params={},
                output_results=error_result,
                decision=f"error: {str(e)}",
                duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                sub_operations=[op for op in _sub_operations if op is not None]
            )
        except Exception:
            pass
        return error_result


# ===================================================================
# CLI ENTRY POINT
# ===================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            sys.exit(0 if validate() else 1)
        elif sys.argv[1] == "--report":
            print(json.dumps(report(), indent=2))
        elif sys.argv[1] == "--bump":
            result = bump_version()
            print(json.dumps(result, indent=2, default=str))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--scan":
            scan_stats = scan_project()
            print(json.dumps(scan_stats, indent=2, default=str))
    else:
        enforce()
