# LEVEL 3 IMPLEMENTATION GUIDE

**Based on:** Finalized Architecture Decisions + Web Research
**Status:** READY FOR IMPLEMENTATION
**Date:** 2026-03-10

---

## TECHNOLOGY STACK (Research-Backed)

### 1. Schema Validation & Serialization

**Libraries:**
- [Pydantic V2](https://docs.pydantic.dev/latest/) - Schema validation
- [Orjson](https://pypi.org/project/orjson-pydantic/) - Fast JSON serialization

**Why:**
- Pydantic V2: 5-50x faster than V1, 10x faster than Marshmallow
- Orjson: 15.8x faster than standard json (820 MB/s vs 52 MB/s)
- Combined: Validates + serializes TOON objects with production speed

**Installation:**
```bash
pip install pydantic[json] orjson-pydantic
```

**Usage Pattern:**
```python
from pydantic import BaseModel
import orjson

class ToonObject(BaseModel):
    session_id: str
    complexity_score: int
    files_loaded: List[str]

    class Config:
        json_encoder = orjson.dumps  # Use orjson for serialization
```

---

### 2. Local LLM Integration

**Library:** [Ollama Python SDK](https://realpython.com/ollama-python/)

**Configuration:**
```python
import ollama

# Default endpoint
OLLAMA_ENDPOINT = "http://127.0.0.1:11434"

# Model routing
MODELS = {
    "planning": "claude-opus",      # Complex reasoning
    "exploration": "claude-haiku",  # Fast file reading
    "classification": "qwen2.5:7b"  # Local fast classification
}

# Fallback strategy
PRIMARY = ollama
FALLBACK = claude  # Claude API as backup
```

**2026 Features (from research):**
- JSON mode: Ensures valid JSON output for tool calling
- OpenAI-compatible API: Switch from OpenAI to Ollama without code changes
- Sub-agent support: Complex task orchestration

**Usage:**
```python
response = ollama.chat(
    model='qwen2.5:7b',
    messages=[
        {'role': 'system', 'content': 'You are a task analyzer...'},
        {'role': 'user', 'content': 'Analyze this prompt...'}
    ],
    format='json'  # Ensure valid JSON output
)
```

---

### 3. GitHub Automation

**Libraries:**
- [PyGithub](https://pygithub.readthedocs.io/) - GitHub API management
- [GitPython](https://github.com/gitpython-developers/GitPython) - Git operations

**Installation:**
```bash
pip install PyGithub GitPython
```

**Configuration:**
```python
from github import Github
from git import Repo

# Authentication
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
github = Github(GITHUB_TOKEN)

# Repository
repo = github.get_user().get_repo('claude-insight')

# Git operations
local_repo = Repo('.')
```

**Operations:**
```python
# Create issue
issue = repo.create_issue(
    title="Fix authentication bug",
    body="...",
    labels=["bug"]
)

# Create branch
repo.create_git_ref(
    ref=f"refs/heads/issue-{issue.number}-bug",
    sha=repo.get_branch('main').commit.sha
)

# Create PR
pr = repo.create_pull(
    title=f"Fix: {issue.title}",
    body=issue.body,
    head=f"issue-{issue.number}-bug",
    base="main"
)
```

---

### 4. Hook System Pattern

**Design Pattern:** Hooks and Anchors

**Implementation:**
```python
class ToolHookManager:
    """Manages pre-tool and post-tool execution hooks."""

    def __init__(self):
        self.pre_hooks = []
        self.post_hooks = []

    def register_pre_hook(self, func):
        self.pre_hooks.append(func)

    def register_post_hook(self, func):
        self.post_hooks.append(func)

    def execute_with_hooks(self, tool_func, *args, **kwargs):
        # Pre-execution hooks
        for hook in self.pre_hooks:
            hook(*args, **kwargs)

        # Actual tool execution
        result = tool_func(*args, **kwargs)

        # Post-execution hooks
        for hook in self.post_hooks:
            hook(result, *args, **kwargs)

        return result
```

**Hook Types (from research):**
1. **PreToolUse** - Validation, blocking dangerous commands
2. **PostToolUse** - Output validation, progress tracking
3. **ExecutionGuard** - Prevent rm -rf, destructive ops

---

### 5. Logging & User Communication

**Libraries:**
- [Loguru](https://github.com/Delgan/loguru) - Production-grade logging
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal output

**Installation:**
```bash
pip install loguru rich
```

**Loguru Features (2026):**
- Zero configuration required
- Structured JSON logging support
- Thread-safe, production-ready
- Automatic exception handling

**Rich Features:**
- Progress bars with multiple columns
- Syntax highlighting
- Beautiful tables
- Console logging integration

**Setup:**
```python
from loguru import logger
from rich.logging import RichHandler
import logging

# Configure loguru with rich
logging.basicConfig(
    handlers=[RichHandler(markup=True)],
    level="INFO"
)

logger.add(
    "level3_execution.log",
    format="{time} | {level} | {message}",
    serialize=True  # JSON output
)
```

---

### 6. Session Management

**Pattern:** File-based session storage with JSON state

**Structure:**
```
~/.claude/logs/sessions/{session_id}/
├── session.json           # Session metadata
├── toon_v1_analysis.json  # From Level 1
├── toon_v2_plan.json      # After Step 4
├── toon_v3_skills.json    # After Step 5
├── prompt.txt             # Step 7 output
├── logs.json              # Structured execution logs
├── tasks.json             # Step 3 breakdown
└── github.json            # Step 8 issue details
```

**Implementation:**
```python
from pathlib import Path
import json
from datetime import datetime

class SessionManager:
    def __init__(self, session_id: str):
        self.session_dir = Path.home() / ".claude" / "logs" / "sessions" / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def save_toon(self, version: int, toon_data: dict):
        """Save TOON version with timestamp."""
        file_path = self.session_dir / f"toon_v{version}_{datetime.now().isoformat()}.json"
        with open(file_path, 'w') as f:
            json.dump(toon_data, f, indent=2)

    def save_prompt(self, prompt_text: str):
        """Save final execution prompt."""
        prompt_path = self.session_dir / "prompt.txt"
        with open(prompt_path, 'w') as f:
            f.write(prompt_text)

    def load_latest_toon(self) -> dict:
        """Load most recent TOON file."""
        toon_files = list(self.session_dir.glob("toon_*.json"))
        if not toon_files:
            return {}
        latest = sorted(toon_files)[-1]
        with open(latest) as f:
            return json.load(f)
```

---

## LEVEL 3 STEP-BY-STEP IMPLEMENTATION

### Step 1: Plan Mode Decision

```python
def step1_plan_mode_decision(toon: dict, user_requirement: str) -> dict:
    """Determine if plan mode is required using local LLM."""

    prompt = f"""Analyze the TOON object and user requirement.

TOON Analysis:
- Complexity: {toon['complexity_score']}/10
- Files: {toon['files_loaded_count']}
- Project Type: {toon.get('project_type', 'unknown')}

User Requirement:
{user_requirement}

Determine if PLAN MODE is required based on:
1. Complexity score
2. Project architecture
3. Requirement complexity
4. Risk assessment

Return JSON:
{
  "plan_required": true/false,
  "reasoning": "explanation",
  "risk_level": "low/medium/high"
}"""

    response = ollama.chat(
        model='qwen2.5:7b',
        messages=[{'role': 'user', 'content': prompt}],
        format='json'
    )

    return json.loads(response['message']['content'])
```

### Step 2: Plan Mode Execution

```python
def step2_plan_execution(toon: dict, user_requirement: str) -> dict:
    """Execute planning phase if required."""

    # OPUS for deep reasoning
    plan_prompt = f"Create detailed implementation plan for: {user_requirement}"

    plan_response = ollama.chat(
        model='claude-opus',
        messages=[
            {'role': 'system', 'content': 'You are a software architect...'},
            {'role': 'user', 'content': plan_prompt}
        ]
    )

    return {
        "plan": plan_response['message']['content'],
        "files_affected": extract_files(plan_response),
        "phases": extract_phases(plan_response),
        "risks": extract_risks(plan_response)
    }
```

### Step 4: TOON Refinement

```python
def step4_toon_refinement(toon: dict, plan: dict) -> dict:
    """Refine TOON to execution blueprint."""

    refined_toon = {
        "session_id": toon['session_id'],
        "timestamp": datetime.now().isoformat(),
        "complexity_score": toon['complexity_score'],
        "plan": plan['plan'],
        "files_affected": plan['files_affected'],
        "phases": plan['phases'],
        "risks": plan['risks'],
        "execution_strategy": "sequential"
    }

    # Validate with Pydantic
    validated = ExecutionBlueprint(**refined_toon)

    return validated.model_dump()
```

### Step 7: Final Prompt Generation

```python
def step7_final_prompt_generation(toon: dict) -> str:
    """Generate execution prompt from refined TOON."""

    prompt = f"""## CONTEXT
Project: {toon.get('project_name')}
Complexity: {toon['complexity_score']}/10

## PROJECT STATE
Files: {toon['files_affected']}

## TASK BREAKDOWN
{format_phases(toon['phases'])}

## SKILLS REQUIRED
{format_skills(toon.get('selected_skills', []))}

## EXECUTION PLAN
{toon['plan']}

## RISKS & MITIGATION
{format_risks(toon['risks'])}

Execute the above plan step by step."""

    return prompt
```

---

## PRODUCTION READINESS CHECKLIST

### Phase 1: Core Implementation
- [ ] Step 1: Plan mode decision (ollama integration)
- [ ] Step 2: Plan execution (opus + haiku)
- [ ] Step 3: Task breakdown (existing script)
- [ ] Step 4: TOON refinement (pydantic)
- [ ] Step 5: Skill selection (existing script)
- [ ] Step 7: Prompt generation (existing + new)

### Phase 2: GitHub Integration
- [ ] Step 8: Issue creation (PyGithub)
- [ ] Step 9: Branch creation (GitPython)
- [ ] Step 11: PR creation (PyGithub)
- [ ] Step 12: Issue closure (PyGithub)

### Phase 3: Documentation & Logging
- [ ] Step 13: Documentation update (ast module + templates)
- [ ] Loguru integration (structured logs)
- [ ] Rich integration (progress + output)
- [ ] Session persistence (file-based)

### Phase 4: Testing & Safety
- [ ] Hook system implementation
- [ ] Error handling + rollback
- [ ] Security (token management)
- [ ] Integration tests

---

## KEY RESEARCH FINDINGS

### Pydantic V2 Performance
- [Pydantic Serialization Docs](https://docs.pydantic.dev/latest/concepts/serialization/)
- 5-50x faster than V1
- 10x faster than alternatives
- JSON schema generation included

### Ollama 2026 Features
- [Complete Ollama Tutorial 2026](https://dev.to/proflead/complete-ollama-tutorial-2026-llms-via-cli-cloud-python-3m97)
- JSON mode for structured output
- OpenAI API compatibility
- Sub-agent support

### Hook System Pattern
- [Hook Pattern Article](https://jamesg.blog/2024/06/16/software-hooks)
- Pre-execution validation
- Post-execution tracking
- Decoupled extensibility

### Loguru Production Use
- [Loguru Guide](https://betterstack.com/community/guides/logging/loguru/)
- Zero configuration
- Structured JSON output
- Thread-safe for production

### Rich Progress Tracking
- [Rich Progress Docs](https://rich.readthedocs.io/en/latest/progress.html)
- Multiple flicker-free bars
- Console integration
- Custom columns

---

## IMPLEMENTATION PRIORITIES

**Priority 1 (Week 1):**
1. Pydantic + Orjson TOON validation
2. Ollama integration for Steps 1, 5, 7
3. Session folder structure
4. Loguru + Rich logging

**Priority 2 (Week 2):**
1. PyGithub integration (GitHub steps)
2. GitPython branch/PR automation
3. Hook system setup
4. Error handling + rollback

**Priority 3 (Week 3):**
1. Documentation auto-update
2. Integration tests
3. Production hardening
4. Performance optimization

---

## CRITICAL NOTES

✓ Use existing scripts where possible
✓ Wrap with service layers (don't modify)
✓ Pydantic for schema, Orjson for speed
✓ Ollama primary, Claude fallback
✓ Sessions file-based (no database)
✓ Logs structured (JSON) + pretty (rich)
✓ Hooks decoupled (register pattern)
✓ Errors logged + rolled back

---

**Status:** READY FOR IMPLEMENTATION
**Next Step:** Implement Phase 1 (Week 1 priorities)

