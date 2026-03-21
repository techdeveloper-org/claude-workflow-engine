# Getting Started with Claude Workflow Engine

**Version:** 1.4.1 | **Status:** Alpha

---

## What Is This?

Claude Workflow Engine automates the **entire Software Development Life Cycle** -
not just code generation, but task analysis, planning, GitHub issues, branching,
PR creation, code review, documentation, and issue closure. All from a single
natural language prompt.

```
You say: "Fix the login timeout bug"

Engine does (15 steps, ~60 seconds):
  Step 0:  Analyzes task -> Bug Fix, complexity 4/10
  Step 1:  Decides plan mode -> Not needed (simple bug)
  Step 3:  Breaks into tasks -> 2 tasks with file targets
  Step 5:  Selects skill -> python-core + testing-core
  Step 7:  Generates prompt -> system_prompt.txt + user_message.txt
  Step 8:  Creates GitHub issue + Jira issue (dual tracking)
  Step 9:  Creates branch -> bugfix/proj-123
  Step 10: Implements fix
  Step 11: Creates PR -> Reviews code, retries if needed
  Step 12: Closes issues (GitHub + Jira)
  Step 13: Updates documentation
  Step 14: Final summary + voice notification
```

---

## 3-Step Quickstart

### 1. Clone and Install

```bash
git clone https://github.com/techdeveloper-org/claude-workflow-engine.git
cd claude-workflow-engine
pip install -r requirements.txt
```

### 2. Run Setup Wizard

```bash
python scripts/setup_wizard.py
```

The wizard walks you through:
- System checks (Python, git, GitHub CLI)
- Dependency installation
- `.env` configuration (API keys, integrations)
- MCP server registration in `~/.claude/settings.json`
- Connectivity verification

### 3. Run the Pipeline

```bash
# Using CLI (after pip install -e .)
cwe run "fix the login timeout bug"

# Or directly
python scripts/3-level-flow.py --message "fix the login timeout bug"
```

---

## CLI Commands

After installing (`pip install -e .`), the `cwe` command is available:

| Command | What It Does |
|---------|-------------|
| `cwe run "task"` | Run pipeline on a task (hook mode, Steps 0-9) |
| `cwe run --mode full "task"` | Full pipeline (all 15 steps) |
| `cwe run --dry-run "task"` | Dry run (Steps 0-7 only, no GitHub) |
| `cwe setup` | Interactive first-time setup wizard |
| `cwe health` | Check all dependencies and services |
| `cwe status` | Show latest pipeline session status |
| `cwe doctor` | Diagnose common issues |
| `cwe version` | Show version info |

---

## Architecture at a Glance

```
Level -1: AUTO-FIX       3 checks: Unicode, encoding, paths (Windows safety)
    |
Level 1:  CONTEXT SYNC   Session + complexity + context + TOON compress
    |
Level 2:  STANDARDS       Auto-detect language + load coding standards
    |
Level 3:  EXECUTION       15 steps: Full SDLC automation
```

### Key Numbers

| Metric | Value |
|--------|-------|
| Pipeline Levels | 4 |
| Execution Steps | 15 (Step 0-14) |
| MCP Servers | 18 (313 tools) |
| Engine Modules | 91 |
| Test Files | 66 |
| Supported Languages | 20+ |
| Standards Files | 10 (8 languages) |

---

## Execution Modes

| Mode | Steps | When To Use |
|------|-------|------------|
| **Hook Mode** (default) | 0-9 | Daily work: generates prompt + creates issue + branch. You implement. |
| **Full Mode** | 0-14 | Full automation: implementation + PR + review + closure |
| **Dry Run** | 0-7 | Testing: analysis + prompt generation only, no GitHub calls |

Set via `CLAUDE_HOOK_MODE=1` (hook) or `CLAUDE_HOOK_MODE=0` (full) in `.env`.

---

## Optional Integrations

All integrations are disabled by default. Enable via `.env`:

| Integration | Flag | What It Does |
|-------------|------|-------------|
| **Jira** | `ENABLE_JIRA=1` | Dual GitHub+Jira issue tracking, PR linking, workflow transitions |
| **Jenkins** | `ENABLE_JENKINS=1` | Build validation before PR merge |
| **SonarQube** | `ENABLE_SONARQUBE=1` | Code quality scan after implementation |
| **GitHub Actions CI** | `ENABLE_CI=false` | Automated tests and linting on push (default: disabled) |

---

## Where to Find Things

```
scripts/
  cli.py                    <- CLI entry point (cwe command)
  setup_wizard.py           <- Interactive setup
  3-level-flow.py           <- Pipeline entry point
  langgraph_engine/         <- Core orchestration (91 modules)
    orchestrator.py         <- Main StateGraph pipeline
    flow_state.py           <- 200+ typed state fields
    call_graph_builder.py   <- Code intelligence (578 classes, 3,985 methods)
    subgraphs/              <- Level -1, 1, 2, 3 implementations

src/mcp/                    <- 18 FastMCP servers (313 tools)
policies/                   <- 63 policy definitions
rules/                      <- 10 coding standard files
tests/                      <- 66 test files
docs/                       <- 46 documentation files
```

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Full project overview, architecture, comparison |
| `CLAUDE.md` | Project context for Claude Code sessions |
| `docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md` | Formal SRS with all requirements |
| `docs/LANGGRAPH-ENGINE.md` | Engine implementation details |
| `docs/ARCHITECTURE_REVIEW.md` | Architecture deep-dive |
| `.env.example` | All configurable environment variables |

---

## Troubleshooting

### Common Issues

**"Module not found" errors:**
```bash
pip install -r requirements.txt
```

**"GITHUB_TOKEN not set":**
```bash
# Option 1: Set in .env
GITHUB_TOKEN=ghp_your_token_here

# Option 2: Use GitHub CLI
gh auth login
```

**MCP servers not registered:**
```bash
python scripts/setup_wizard.py  # Re-run setup, it auto-registers
```

**Pipeline seems stuck:**
```bash
cwe doctor    # Diagnose issues
cwe health    # Check all services
```

**Windows encoding errors:**
Level -1 auto-fix handles this. If persistent, check your Python files
for non-ASCII characters.

---

## Getting Help

- Run `cwe doctor` to diagnose issues
- Check `docs/` for detailed guides
- File issues at: https://github.com/techdeveloper-org/claude-workflow-engine/issues

---

**Ready? Run `cwe setup` and you are good to go.**
