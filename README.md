# Claude Workflow Engine

**The first AI tool that follows full SDLC** - from task analysis to merged PR, automatically.

**Version:** 7.5.0 | **Status:** Alpha | **Last Updated:** 2026-03-17

---

## The Problem

Every AI coding tool today does ONE thing: generate code. None of them follow Software Development Life Cycle (SDLC):

| Tool | Code Gen | Task Analysis | Planning | Standards | GitHub Issue | Branch | PR | Code Review | Docs | Summary |
|------|----------|--------------|----------|-----------|-------------|--------|-----|-------------|------|---------|
| GitHub Copilot | Yes | - | - | - | - | - | - | - | - | - |
| Cursor | Yes | - | - | - | - | - | - | - | - | - |
| Devin | Yes | Partial | Partial | - | - | - | - | - | - | - |
| Claude Code | Yes | - | - | - | - | - | - | - | - | - |
| **This Engine** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

**Claude Workflow Engine automates the ENTIRE development lifecycle** - not just code generation, but everything a professional developer does from receiving a task to closing the issue.

---

## What It Does

Give it a task in natural language. It handles everything:

```
You say: "Fix the login timeout bug"

Engine does:
  Step 0:  Analyzes task -> Bug Fix, complexity 4/10
  Step 1:  Decides plan mode -> Not needed (simple bug)
  Step 2:  Skipped (no plan needed)
  Step 3:  Breaks into tasks -> 2 tasks with file targets
  Step 4:  Refines context -> TOON with full project state
  Step 5:  Selects skill -> python-core + testing-core
  Step 6:  Validates skills -> Downloaded and ready
  Step 7:  Generates prompt -> system_prompt.txt + user_message.txt
  Step 8:  Creates GitHub issue -> #42 "bugfix: login timeout"
  Step 9:  Creates branch -> bugfix/issue-42
  Step 10: Implements fix -> With full context from Steps 0-7
  Step 11: Creates PR -> Reviews code, retries if needed (max 3x)
  Step 12: Closes issue -> With implementation summary
  Step 13: Updates docs -> CLAUDE.md + execution-docs.md
  Step 14: Final summary -> execution-summary.txt + voice notification
```

**Total time: ~60 seconds for Steps 0-9 (hook mode), ~170 seconds full pipeline.**

---

## Architecture

### 4-Level Pipeline

```
Level -1: AUTO-FIX         3 checks: Unicode, encoding, paths
    |
Level 1:  CONTEXT SYNC     Session + parallel [complexity, context] + TOON compress
    |
Level 2:  STANDARDS         Common + conditional Java + tool optimization + MCP discovery
    |
Level 3:  EXECUTION         15 steps (Step 0-14): Full SDLC automation
```

### 15-Step SDLC Pipeline (Level 3)

| Phase | Steps | What Happens |
|-------|-------|-------------|
| **Analysis & Planning** | 0-2 | Task analysis, complexity scoring, plan mode decision, plan execution |
| **Preparation** | 3-7 | Task breakdown, TOON refinement, skill/agent selection, prompt generation |
| **GitHub Automation** | 8-9 | Issue creation with semantic labels, branch creation with stash safety |
| **Implementation** | 10 | Code execution with system prompt context (95%+ quality with full context) |
| **Review & Closure** | 11-12 | PR creation with code review loop (max 3 retries), issue closure with summary |
| **Finalization** | 13-14 | Documentation update, execution summary + voice notification |

### Execution Modes

```
Hook Mode (default, CLAUDE_HOOK_MODE=1):
  Steps 0-9   -> Pipeline (analysis + prompt + GitHub issue + branch)
  Steps 10-14 -> Skipped (user implements, then runs Full Mode for PR/closure)

Full Mode (CLAUDE_HOOK_MODE=0):
  Steps 0-14  -> All steps execute sequentially
```

---

## Key Technologies

### LangGraph Orchestration (76 modules)

- StateGraph with 200+ typed state fields
- Parallel execution via `Send()` API (Level 1: 4 concurrent tasks)
- Conditional routing (plan mode, Java detection, PR retry loop)
- Checkpoint recovery (resume from any step after crash)
- Signal handling (Ctrl+C graceful recovery)

### 11 MCP Servers (109 tools)

All servers use FastMCP protocol (stdio JSON-RPC), registered in `~/.claude/settings.json`:

| Server | Tools | Purpose |
|--------|-------|---------|
| git-ops | 14 | Git operations (branch, commit, push, pull, stash, diff, fetch, cleanup) |
| github-api | 12 | GitHub (issue, PR, merge, label, build validate, full merge cycle) |
| session-mgr | 14 | Session lifecycle (create, chain, tag, accumulate, finalize, work items) |
| policy-enforcement | 11 | Policy compliance, flow-trace, module health, system health |
| llm-provider | 8 | LLM access (4 providers, hybrid GPU-first, model selection) |
| token-optimizer | 10 | Token reduction (AST navigation, smart read, dedup, 60-85% savings) |
| pre-tool-gate | 8 | Pre-tool validation (8 policy checks, skill hints) |
| post-tool-tracker | 6 | Post-tool tracking (progress, commit readiness, stats) |
| standards-loader | 7 | Standards (project detect, framework detect, hot-reload) |
| skill-manager | 8 | Skill lifecycle (load, search, validate, rank, conflicts) |
| vector-db | 11 | Vector RAG (Qdrant, 4 collections, semantic search, node decisions) |

### RAG Integration (Vector DB Decision Caching)

Every pipeline node stores its decision in Vector DB. Before LLM calls, the pipeline checks RAG for similar past decisions. If confidence >= step-specific threshold, RAG result replaces LLM call (saving inference time and cost).

| Step | Threshold | Rationale |
|------|-----------|-----------|
| Step 0 (Task Analysis) | 0.85 | Needs high match for accurate classification |
| Step 1 (Plan Decision) | 0.80 | Binary decision, easier to cache |
| Step 5 (Skill Selection) | 0.82 | Moderate - needs context match |
| Step 7 (Final Prompt) | 0.90 | Near-exact match needed |
| Step 14 (Summary) | 0.75 | Low stakes, summary is flexible |

**Collections:** `node_decisions`, `sessions`, `flow_traces`, `tool_calls`

### Hybrid LLM Inference (4 providers)

```
GPU-first: Ollama (local) -> Claude CLI -> Anthropic API -> OpenAI API
```

- Complexity-based model selection (simple=fast model, complex=powerful model)
- Automatic fallback chain when primary provider is unavailable
- Cached health checks (60s TTL) to avoid repeated probe calls

### Hook System (Pre/Post Tool Enforcement)

| Hook | Script | Purpose |
|------|--------|---------|
| UserPromptSubmit | 3-level-flow.py | Runs full pipeline on every user message |
| PreToolUse | pre-tool-enforcer.py | Blocks Write/Edit until Level 1/2 complete, tool optimization hints |
| PostToolUse | post-tool-tracker.py | Progress tracking, flag clearing, GitHub integration |
| Stop | stop-notifier.py | Voice notification on session end |

### Multi-Project Support (20+ languages/frameworks)

Auto-detects project type and loads appropriate standards:

**Languages:** Python, JavaScript, TypeScript, Java, Kotlin, Go, Rust, Ruby, C#, PHP, Swift
**Frameworks:** Flask, Django, FastAPI, Spring Boot, React, Angular, Vue, Next.js, Express
**Tools:** Docker, Kubernetes, GitHub Actions, Jenkins

### Policy System (49 policies)

```
policies/
+-- 01-sync-system/        Level 1: Session, context, preferences, patterns (11 files)
+-- 02-standards-system/   Level 2: Common + conditional standards (3 files)
+-- 03-execution-system/   Level 3: All 15 steps + failure prevention (34 files)
+-- testing/               Test case policies (2 files)
```

---

## Current Status: What's Built vs What's Remaining

### BUILT (v7.5.0 - Alpha)

| Component | Status | Details |
|-----------|--------|---------|
| **15-Step Pipeline** | COMPLETE | All steps produce real output (not stubs) |
| **4-Level Architecture** | COMPLETE | Level -1 through Level 3 fully operational |
| **11 MCP Servers** | COMPLETE | 109 tools, all tested and registered |
| **RAG Integration** | COMPLETE | 4 Vector DB collections, step-specific thresholds |
| **Hook System** | COMPLETE | Pre/post tool enforcement with blocking |
| **Policy System** | COMPLETE | 49 policies covering all 15 steps |
| **Multi-Project Detection** | COMPLETE | 20+ languages/frameworks auto-detected |
| **Hybrid LLM Inference** | COMPLETE | 4-provider fallback chain |
| **Token Optimization** | COMPLETE | AST navigation, dedup, 60-85% savings |
| **Session Management** | COMPLETE | Chaining, TOON compression, archival |
| **GitHub Integration** | COMPLETE | Issue, branch, PR, merge, review loop |
| **Standards Enforcement** | COMPLETE | Common + framework-specific with 5 hooks |
| **Cross-Session Learning** | COMPLETE | RAG pattern detection + skill selection boost |
| **Test Suite** | COMPLETE | 46 test files, 1366+ tests, integration tests for all 15 steps |
| **Documentation** | COMPLETE | 40 docs, architecture diagrams, guides |
| **Installation** | COMPLETE | setup.py, requirements.txt, .env.example |

### REMAINING (Roadmap to v1.0.0 Production)

#### Phase 1: Hardening (Priority: HIGH)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| Code coverage measurement | Add `pytest --cov`, set 70% threshold | 2 hrs | Know actual test coverage % |
| Input validation layer | Sanitize user prompts, length limits, injection prevention | 3 hrs | Security for production use |
| Checkpoint recovery testing | Test resume-from-crash at every step in staging | 4 hrs | Reliability guarantee |
| Error message standardization | Consistent error codes across all 15 steps | 3 hrs | Better debugging |

#### Phase 2: CI/CD & Automation (Priority: HIGH)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| GitHub Actions pipeline | Run tests on push, coverage reports, security scan | 4 hrs | Automated quality gates |
| Docker containerization | Dockerfile + docker-compose for easy deployment | 3 hrs | One-command setup |
| Version auto-bump | Semantic versioning on merge to main | 2 hrs | Release automation |
| Pre-commit hooks | Lint, format, type-check before commit | 2 hrs | Code quality enforcement |

#### Phase 3: Validation (Priority: MEDIUM)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| Multi-project testing | Test on 10+ real projects (Python, Java, JS, Go, Rust) | 1 week | Prove multi-project readiness |
| Load testing | 100 concurrent pipeline executions | 2 days | Performance baseline |
| Fallback chain testing | Test all 4 LLM providers with intentional failures | 1 day | Reliability proof |
| Checkpoint disaster drill | Kill process at each step, verify resume | 1 day | Recovery confidence |

#### Phase 4: Release (Priority: MEDIUM)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| PyPI package publish | `pip install claude-workflow-engine` | 1 day | Easy distribution |
| CLI interface | `cwe run "fix the bug"` command | 2 days | User-friendly entry point |
| Configuration wizard | Interactive setup for first-time users | 1 day | Onboarding experience |
| Release notes + changelog | v1.0.0 announcement | 1 day | Community awareness |

#### Phase 5: Enterprise Features (Priority: LOW - Future)

| Task | Description | Impact |
|------|-------------|--------|
| Metrics dashboard | Real-time pipeline execution monitoring | Observability |
| Team collaboration | Multi-user sessions with role-based access | Team use |
| Custom policy editor | UI for creating/editing policies | Customization |
| Webhook integrations | Slack, Teams, Discord notifications | Enterprise workflow |
| Audit trail | Complete compliance logging | Enterprise compliance |
| Plugin system | Third-party skill/agent marketplace | Ecosystem growth |

---

## Quick Start

### Prerequisites

- Python 3.8+
- GitHub CLI (`gh`) installed and authenticated
- Ollama (optional, for local GPU inference)
- Qdrant (optional, for RAG vector storage)

### Installation

```bash
git clone https://github.com/techdeveloper-org/claude-insight.git
cd claude-insight
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Running the Pipeline

```bash
# Full 15-step pipeline
python scripts/3-level-flow.py --task "your task description"

# Hook mode (Steps 0-9 only, default)
CLAUDE_HOOK_MODE=1 python scripts/3-level-flow.py --task "fix login bug"

# Full mode (all 15 steps)
CLAUDE_HOOK_MODE=0 python scripts/3-level-flow.py --task "add user profile feature"

# Debug mode
CLAUDE_DEBUG=1 python scripts/3-level-flow.py --task "your task" --summary
```

### Testing

```bash
# Run all tests
pytest tests/

# Run integration tests (full pipeline)
pytest tests/integration/

# Run MCP server tests
pytest tests/test_*mcp*.py

# Run with coverage (when configured)
pytest --cov=scripts --cov-report=html tests/
```

---

## Directory Structure

```
claude-insight/
|
+-- scripts/
|   +-- langgraph_engine/             # Core orchestration (76 modules)
|   |   +-- orchestrator.py           # Main StateGraph pipeline
|   |   +-- flow_state.py             # TypedDict state (200+ fields)
|   |   +-- rag_integration.py        # Vector DB decision caching
|   |   +-- subgraphs/               # Level -1, 1, 2, 3 implementations
|   +-- architecture/                 # Helper scripts (sync, standards, execution)
|   +-- 3-level-flow.py               # Entry point
|   +-- pre-tool-enforcer.py          # PreToolUse hook
|   +-- post-tool-tracker.py          # PostToolUse hook
|   +-- stop-notifier.py              # Stop hook (voice notification)
|
+-- src/mcp/                          # 11 FastMCP servers (109 tools)
+-- policies/                         # 49 policy definitions
+-- tests/                            # 46 test files (1366+ tests)
+-- docs/                             # 40 documentation files
+-- rules/                            # 5 coding standard definitions
|
+-- VERSION                           # Single source of truth (7.5.0)
+-- CLAUDE.md                         # Project context for Claude Code
+-- setup.py                          # Package installation
+-- requirements.txt                  # Python dependencies
+-- .env.example                      # Configuration template
```

---

## Key Statistics

| Metric | Value |
|--------|-------|
| Pipeline Levels | 4 (Level -1, 1, 2, 3) |
| Execution Steps | 15 (Step 0 - Step 14) |
| MCP Servers | 11 |
| MCP Tools | 109 |
| LangGraph Engine Modules | 76 (70 root + 6 subgraphs) |
| Policy Files | 49 (48 .md + 1 .json) |
| Test Files | 46 |
| Test Functions | 1366+ |
| Total Python Files | 258+ |
| Documentation Files | 40 |
| RAG Collections | 4 |
| Supported Languages | 20+ |
| Supported Frameworks | 15+ |

---

## Configuration

See `.env.example` for all options:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_HOOK_MODE` | `1` | Hook mode (1) or Full mode (0) |
| `CLAUDE_DEBUG` | `0` | Enable debug output |
| `OLLAMA_ENDPOINT` | `http://localhost:11434` | Ollama server URL |
| `ANTHROPIC_API_KEY` | - | Claude API key (optional if using Ollama) |
| `GITHUB_TOKEN` | - | GitHub personal access token |
| `LLM_PROVIDER` | `auto` | Force specific provider (ollama/anthropic/openai/auto) |

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **7.5.0** | 2026-03-17 | Gap analysis fixes, all 49 policies complete, code graph analyzer, Level 1 integration |
| 7.5.0 | 2026-03-16 | RAG integration, 11th MCP server (vector-db), cross-session learning, 109 tools |
| 7.4.0 | 2026-03-16 | Dynamic versioning, SRS rewrite, MCP health checks |
| 7.3.0 | 2026-03-16 | 10 MCP servers (91 tools), hook migration to MCP imports |
| 7.2.0 | 2026-03-15 | 7 design patterns, Anthropic API as 4th LLM provider |
| 5.7.0 | 2026-03-14 | Workflow-only repo (monitoring removed) |
| 5.0.0 | 2026-03-10 | Initial unified policy enforcement framework |

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Maintainers:** TechDeveloper
**Repository:** https://github.com/techdeveloper-org/claude-insight
