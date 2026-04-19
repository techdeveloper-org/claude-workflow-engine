# Claude Workflow Engine

> Automate your entire software development lifecycle — from task to merged PR — using Claude AI.

[![Version](https://img.shields.io/badge/Version-1.19.1-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)](https://python.org)
[![PyPI](https://img.shields.io/badge/PyPI-claude--workflow--engine-orange)](https://pypi.org/project/claude-workflow-engine/)
[![CI](https://github.com/techdeveloper-org/claude-workflow-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/techdeveloper-org/claude-workflow-engine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-44%20files%20·%204%20integration-brightgreen)](tests/)
[![Discussions](https://img.shields.io/badge/Discussions-GitHub-blueviolet)](../../discussions)

---

## What Is This?

Claude Workflow Engine is a **LangGraph-based AI orchestration pipeline** that automates the full software development lifecycle. You give it a task description. It handles everything else — from analyzing your codebase, creating a GitHub issue, writing the code, opening a PR, running a code review, and closing the issue.

Most AI coding tools generate code and stop there. This engine does what a full engineering team does.

| Capability | This Engine | Copilot | Cursor | Devin |
|---|:---:|:---:|:---:|:---:|
| **Core Generation** | | | | |
| Code generation | Yes | Yes | Yes | Yes |
| Unit test generation (Python/Java/TS/Kotlin) | Yes | — | Partial | — |
| Documentation update (Step 13) | Yes | — | — | — |
| **Planning & Analysis** | | | | |
| Task analysis + complexity scoring [1-25] | Yes | — | — | Partial |
| Call graph impact analysis (pre-change) | Yes | — | — | — |
| Breaking change detection (graph diff) | Yes | — | — | — |
| Multi-language call graph (Python/Java/TS/Kotlin) | Yes | — | — | — |
| Template fast-path (bypass Step 0, ~0s planning) | Yes | — | — | — |
| **GitHub / Jira SDLC** | | | | |
| GitHub issue creation | Yes | — | — | — |
| Dual issue tracking (GitHub + Jira) | Yes | — | — | — |
| Full issue lifecycle (create → close) | Yes | — | — | — |
| Auto branch creation (from Jira key or issue#) | Yes | — | — | — |
| Auto PR + code review | Yes | — | — | — |
| Quality gate enforcement (4 gates) | Yes | — | — | — |
| **Integrations** | | | | |
| UML diagram generation (13 types) | Yes | — | — | — |
| Draw.io editable diagram export | Yes | — | — | — |
| SonarQube scan + auto-fix loop | Yes | — | — | — |
| Figma design-to-code (tokens + component extraction) | Yes | — | — | — |
| Jenkins CI integration | Yes | — | — | — |
| Voice notification on pipeline stop | Yes | — | — | — |
| **Security & Observability** | | | | |
| Append-only JSON audit log (daily rotation) | Yes | — | — | — |
| Prometheus metrics (9 metrics, /metrics endpoint) | Yes | — | — | — |
| OpenTelemetry tracing (OTLP/console) | Yes | — | — | — |
| Health server (GET /health + /readiness) | Yes | — | — | — |
| Secret scanning CI gate (6 regex patterns) | Yes | — | — | — |
| Token bucket rate limiting per client | Yes | — | — | — |
| Prompt injection detection on inputs | Yes | — | — | — |
| **Infrastructure** | | | | |
| Kubernetes manifests (HPA + configmap) | Yes | — | — | — |
| Docker + docker-compose | Yes | — | — | — |
| 13 independent MCP servers (295 tools) | Yes | — | — | — |
| Token optimizer (60-85% context savings) | Yes | — | — | — |

---

## Quick Start

### Prerequisites

- Python 3.10+
- [Claude Code CLI](https://claude.ai/code) installed and authenticated
- `ANTHROPIC_API_KEY` set in your environment
- `GITHUB_TOKEN` with repo permissions

### Install

```bash
# From PyPI (recommended)
pip install claude-workflow-engine

# From source
git clone https://github.com/techdeveloper-org/claude-workflow-engine
cd claude-workflow-engine
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and GITHUB_TOKEN at minimum
```

### Run

```bash
# Hook Mode (default) — runs analysis + creates GitHub issue + branch
python scripts/3-level-flow.py --message "Fix the login timeout bug"

# Full Mode — runs all 8 active steps end-to-end (implements + PR + closes issue)
CLAUDE_HOOK_MODE=0 python scripts/3-level-flow.py --message "Fix the login timeout bug"

# Template Fast-Path — skip Step 0 planning entirely
python scripts/3-level-flow.py \
  --message "Add document Q&A feature" \
  --orchestration-template=orchestration_template.example.json
```

### What happens when you run it

```
Input:  "Fix the login timeout bug"

Level -1  Auto-Fix        Unicode check, encoding fix, path normalization
Level 1   Context Sync    Session load + parallel [complexity, context] → merge
                          Output: combined_complexity_score [1-25 scale]
Level 2   (NO-OP)         Policies are .md files read directly from policies/ at runtime
Level 3   Execution
  Pre-0   Pre-Analysis    Call graph scan → hot_nodes, danger_zones, complexity_boost
  Step 0  Task Analysis   2 claude CLI subprocess calls (~15s total)
            Call 1          prompt_gen_expert_caller fills orchestration template
            Call 2          orchestrator_agent_caller executes full plan (streamed live)
  Step 8  Issue & Branch  GitHub Issue created; Jira Issue (if ENABLE_JIRA=1)
  Step 9  Branch          Branch from Jira key (feature/PROJ-123) or issue number
  Step 10 Implement       Code written; call graph snapshot; Jira → "In Progress"
  Step 11 PR + Review     PR opened; call graph diff; Jira → "In Review"
  Step 12 Close           GitHub + Jira issue closed; Figma "complete" comment
  Step 13 Docs + UML      Documentation updated; 13 UML diagram types generated
  Step 14 Summary         Final report + optional voice notification

Total: ~15s planning, ~120s full pipeline
```

---

## Architecture

### 3-Level LangGraph Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  Level -1  AUTO-FIX                                         │
│  3 checks: Unicode · encoding · cross-platform paths        │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  Level 1   CONTEXT SYNC                                     │
│  Session load + parallel [complexity calc, context load]    │
│  Output: combined_complexity_score  [1-25 scale]            │
│          = simple_score × 0.3  +  graph_score × 0.7         │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  Level 2   (NO-OP)                                          │
│  Coding standards read directly from policies/ at runtime   │
│  No pipeline nodes — zero overhead                          │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  Level 3   EXECUTION  (8 active steps)                      │
│                                                             │
│  Pre-0 → Step 0 → Step 8 → Step 9 → Step 10                │
│                → Step 11 → Step 12 → Step 13 → Step 14     │
└─────────────────────────────────────────────────────────────┘
```

### Execution Modes

| Mode | Env Var | Steps Active | Use Case |
|---|---|---|---|
| **Hook Mode** | `CLAUDE_HOOK_MODE=1` (default) | Pre-0, Step 0, Steps 8-9 | Daily dev workflow — Claude Code hooks trigger analysis + issue + branch |
| **Full Mode** | `CLAUDE_HOOK_MODE=0` | Pre-0, Step 0, Steps 8-14 | End-to-end automation — all steps run sequentially |

### CallGraph-Driven Intelligence

The pipeline builds a full AST call graph of your project (578 classes, 3,985 methods across Python, Java, TypeScript, Kotlin) and uses it at 3 critical points:

```
Pre-0   analyze_impact_before_change()  → risk_level, danger_zones, affected_methods
Step 10 snapshot_call_graph()           → captures pre-change state for Step 11
Step 11 review_change_impact()          → compares before/after graphs, flags breaking changes
```

This means the planner knows what could break **before** suggesting changes, and the reviewer detects regressions based on actual method-level diffs — not just file diffs.

**Stale Graph Guard:** After Step 10 writes files, `call_graph_stale = True` is set. The analyzer silently rebuilds the graph when stale instead of returning a Phase-0 cached snapshot — preventing multi-phase implementations from making decisions on out-of-date graph data.

**Language support:**

| Language | Parser Type | Scope |
|----------|------------|-------|
| Python | Full AST (`ast` module) | Classes, methods, imports, calls |
| Java | Regex-based | Classes, methods, inheritance |
| TypeScript | Regex-based | Classes, functions, exports |
| Kotlin | Regex-based | Classes, functions, companion objects |

### Planning Phase (Step 0)

Step 0 runs two sequential subprocess calls against the Claude CLI:

```
Call 1  prompt_gen_expert_caller  (~5s)
        Reads:    level3_execution/templates/orchestration_system_prompt.txt
        Injects:  task description + call graph metrics + complexity score
        Outputs:  complete orchestration prompt → state["orchestration_prompt"]

Call 2  orchestrator_agent_caller  (~10s, streamed live to terminal)
        Reads:    state["orchestration_prompt"] via temp file
        Executes: solution-architect → consensus → agents → QA
        Outputs:  implementation plan → state["orchestrator_result"]
```

### Template Fast-Path

Pre-fill a JSON orchestration template once, and every subsequent run skips Step 0 entirely:

```bash
python scripts/3-level-flow.py \
  --message "add document Q&A feature" \
  --orchestration-template=orchestration_template.example.json
# Planning time: ~0s (template loaded, Step 0 bypassed)
```

See `orchestration_template.example.json` for the full field reference.

---

## Directory Structure

```
claude-workflow-engine/           # 369 Python files total
├── langgraph_engine/             # Core engine — 211 Python files
│   ├── orchestrator.py           # Main StateGraph pipeline definition
│   ├── pipeline_builder.py       # Builder Pattern: chainable add_level*().build()
│   ├── flow_state.py             # Backward-compat shim → state/ package
│   ├── core/                     # Cross-cutting: LazyLoader, ErrorHandler, infrastructure, structured_logger
│   ├── state/                    # FlowState, StepKeys, reducers, WorkflowContextOptimizer
│   ├── routing/                  # Routing functions split by level
│   ├── helper_nodes/             # Helper node functions split by concern
│   ├── diagrams/                 # Strategy Pattern: 13 UML generators + draw.io converter
│   │   └── drawio/               # DrawioConverter — .drawio XML for all 13 diagram types
│   ├── parsers/                  # Abstract Factory: Python (AST), Java, TypeScript, Kotlin parsers
│   ├── integrations/             # GitHub, Jira, Figma, Jenkins integrations
│   ├── level_minus1/             # Level -1: Auto-Fix (nodes, merge, recovery)
│   ├── level1_sync/              # Level 1: Session + context sync (10 modules)
│   ├── level3_execution/         # Level 3: 8-step SDLC execution
│   │   ├── subgraph.py           # Level 3 StateGraph + _run_step helper
│   │   ├── nodes/                # Step node wrappers + step implementation facades
│   │   ├── architecture/         # prompt_gen_expert_caller, orchestrator_agent_caller
│   │   ├── templates/            # orchestration_system_prompt.txt
│   │   ├── sonarqube/            # SonarQube Facade: api_client, lightweight, aggregator, auto_fixer
│   │   ├── documentation_manager.py
│   │   ├── figma_workflow.py
│   │   ├── steps8to12_github.py
│   │   └── steps8to12_jira.py
│   ├── build_dependency_resolver/ # Multi-language build dependency parser
│   ├── call_graph_builder.py     # Compat shim → parsers/
│   ├── call_graph_analyzer.py    # Impact analysis: risk_level, danger_zones, affected_methods
│   ├── backup_manager.py         # State snapshot + restore on pipeline failure
│   ├── checkpoint_manager.py     # Step-level checkpoint persistence for resume
│   ├── conflict_resolver.py      # Merge conflict detection and resolution hints
│   ├── decision_explainer.py     # Human-readable explanation of pipeline decisions
│   ├── context_deduplicator.py   # Remove repeated schema/state content from context
│   ├── coverage_analyzer.py      # Test coverage gap detection for generated code
│   ├── secrets_manager.py        # Startup secrets validation + AWS SM + rotation hints
│   ├── audit_logger.py           # Append-only JSON audit log, daily rotation
│   ├── metrics_exporter.py       # Prometheus: 9 metrics, start_metrics_server(port)
│   └── tracing.py                # OpenTelemetry OTLP/console, create_span()
│
├── hooks/                        # Claude Code hook scripts — 41 Python files
│   ├── pre-tool-enforcer.py      # PreToolUse hook entry point
│   ├── post-tool-tracker.py      # PostToolUse hook entry point
│   ├── stop-notifier.py          # Stop hook entry point
│   ├── pre_tool_enforcer/        # PreToolUse package (8 policy checks, skill hints)
│   ├── post_tool_tracker/        # PostToolUse package (progress, commit readiness, stats)
│   └── stop_notifier/            # Stop package (voice TTS, PR workflow, session save)
│
├── scripts/                      # Pipeline entry point + tooling — 44 Python files
│   ├── 3-level-flow.py           # Main entry point: --message, --orchestration-template
│   ├── github_pr_workflow/       # PR workflow package: commit, push, review, versioning
│   ├── github_operations/        # GitHub helper operations
│   ├── tools/                    # Developer utilities: release.py, voice-notifier.py, metrics-emitter.py
│   ├── setup/                    # One-time setup: setup_wizard.py, install hooks scripts
│   ├── health_server.py          # GET /health + GET /readiness (stdlib HTTP, daemon thread)
│   ├── secrets_check.py          # CI gate: 6 regex patterns, exit 1 on finding secrets
│   └── pin_requirements.py       # Generates requirements.pinned.txt + requirements.bounds.txt
│
├── src/mcp/                      # In-engine copy of session-mgr MCP server
│   ├── session_mcp_server.py     # MCP server (separate repo is source of truth)
│   ├── session_hooks.py          # Direct import bridge
│   ├── rate_limiter.py           # TokenBucket per client: 100/min tools, 10/min LLM
│   └── input_validator.py        # Null-byte strip, length limit, prompt injection detection
│
├── policies/                     # 46 policy .md files (read directly at runtime, no nodes)
│   ├── 00-auto-fix/              # Level -1 enforcement rules
│   ├── 01-sync/                  # Level 1 context sync policies
│   ├── 02-standards-system/      # Coding standards (Python, Java, TS, Kotlin, etc.)
│   └── 03-execution/             # Level 3 execution policies
│
├── tests/                        # 44 test_*.py files (56 total Python files)
│   ├── test_*.py                 # 36 unit tests
│   ├── integration/              # 4 integration tests (GitHub, MCP, runtime verification)
│   ├── e2e/                      # 3 end-to-end scenario tests
│   └── load/                     # 1 concurrency / load test
│
├── rules/                        # 43 coding standard definitions
├── docs/                         # 55 architecture + implementation documentation files
├── uml/                          # Auto-generated UML diagrams (13 types, Mermaid/PlantUML)
├── drawio/                       # Auto-generated draw.io diagrams (.drawio files)
├── k8s/                          # Kubernetes manifests: deployment, service, HPA, configmap
├── Makefile                      # Common developer tasks: test, lint, docker, k8s targets
├── Dockerfile
├── docker-compose.yml
├── setup.py
├── pyproject.toml                # Build system config + tool config (ruff, pytest)
├── MANIFEST.in                   # Package manifest for PyPI distribution
├── requirements.txt              # Runtime dependencies
├── requirements-dev.txt          # Development dependencies (pytest, ruff, etc.)
├── requirements-optional.txt     # TTS / voice (conflicts with networkx — install separately)
├── orchestration_template.example.json  # Template fast-path reference file
└── .env.example                  # All environment variables with descriptions
```

---

## MCP Servers

The engine connects to 13 MCP servers, all maintained as independent repositories under [`techdeveloper-org`](https://github.com/orgs/techdeveloper-org/repositories). Each server is registered in `~/.claude/settings.json`.

| # | Server | Tools | Purpose |
|---|--------|:---:|---------|
| 1 | [mcp-session-mgr](https://github.com/techdeveloper-org/mcp-session-mgr) | 14 | Session lifecycle management |
| 2 | [mcp-git-ops](https://github.com/techdeveloper-org/mcp-git-ops) | 14 | Git operations (branch, commit, push, stash, diff) |
| 3 | [mcp-github-api](https://github.com/techdeveloper-org/mcp-github-api) | 12 | GitHub (PR, issue, merge, label, build validate) |
| 4 | [mcp-policy-enforcement](https://github.com/techdeveloper-org/mcp-policy-enforcement) | 11 | Policy compliance, flow-trace, system health |
| 5 | [mcp-token-optimizer](https://github.com/techdeveloper-org/mcp-token-optimizer) | 10 | Token reduction: AST navigation, smart read (60-85% savings) |
| 6 | [mcp-pre-tool-gate](https://github.com/techdeveloper-org/mcp-pre-tool-gate) | 13 | Pre-tool validation (8 policy checks, skill hints) |
| 7 | [mcp-post-tool-tracker](https://github.com/techdeveloper-org/mcp-post-tool-tracker) | 6 | Post-tool tracking (progress, commit readiness, stats) |
| 8 | [mcp-standards-loader](https://github.com/techdeveloper-org/mcp-standards-loader) | 7 | Standards (project detect, framework detect, hot-reload) |
| 9 | [mcp-uml-diagram](https://github.com/techdeveloper-org/mcp-uml-diagram) | 15 | UML (13 types, CallGraph + AST + LLM, Mermaid/PlantUML, Kroki.io) |
| 10 | [mcp-drawio-diagram](https://github.com/techdeveloper-org/mcp-drawio-diagram) | 5 | Draw.io editable diagrams (12 types, .drawio files) |
| 11 | [mcp-jira-api](https://github.com/techdeveloper-org/mcp-jira-api) | 10 | Jira (create/search/transition, link PRs, Cloud+Server) |
| 12 | [mcp-jenkins-ci](https://github.com/techdeveloper-org/mcp-jenkins-ci) | 10 | Jenkins CI/CD (trigger/abort builds, console output, queue) |
| 13 | [mcp-figma](https://github.com/techdeveloper-org/mcp-figma) | 10 | Figma (file info, components, design tokens, styles) |

**Shared base package:** [mcp-base](https://github.com/techdeveloper-org/mcp-base) — MCPResponse builder, `@mcp_tool_handler`, AtomicJsonStore, LazyClient. Each server includes a copy as `base/`.

> `session-mgr` also keeps an in-engine copy in `src/mcp/` because it is imported in-process by `session_hooks.py`. The separate repo is the source of truth.

---

## Configuration

All options are set via environment variables. Copy `.env.example` and fill in:

### Required

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `GITHUB_TOKEN` | GitHub personal access token (repo scope) |

### Pipeline Behavior

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_HOOK_MODE` | `1` | `1` = Hook Mode (Steps Pre-0 to 9), `0` = Full Mode (all 8 steps) |
| `CLAUDE_DEBUG` | `0` | `1` = verbose debug logging |
| `LLM_PROVIDER` | `claude_cli` | `claude_cli` or `anthropic` |

### Integrations (all disabled by default)

| Variable | Default | Description |
|---|---|---|
| `ENABLE_JIRA` | `0` | Dual GitHub+Jira issue tracking |
| `ENABLE_JENKINS` | `0` | Jenkins build validation in Step 11 |
| `ENABLE_SONARQUBE` | `0` | SonarQube scan after implementation |
| `ENABLE_FIGMA` | `0` | Figma design-to-code pipeline |
| `ENABLE_CI` | `false` | GitHub Actions CI pipeline |

### Observability (all disabled by default)

| Variable | Default | Description |
|---|---|---|
| `ENABLE_HEALTH_SERVER` | `0` | HTTP `/health` + `/readiness` on `HEALTH_PORT` (default 8080) |
| `ENABLE_METRICS` | `0` | Prometheus `/metrics` on `METRICS_PORT` (default 9090) |
| `ENABLE_TRACING` | `0` | OpenTelemetry tracing to `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `LOG_FORMAT` | `""` | Set to `json` for structured JSON logging |

### Diagram Output

| Variable | Default | Description |
|---|---|---|
| `UML_OUTPUT_DIR` | `uml/` | Output dir for Mermaid/PlantUML diagrams |
| `DRAWIO_OUTPUT_DIR` | `drawio/` | Output dir for draw.io `.drawio` files |

---

## Integrations

All integrations follow the same create → update → close lifecycle pattern when enabled:

### Jira (`ENABLE_JIRA=1`)

```
Step 8:  CREATE   Jira issue created, cross-linked to GitHub Issue
Step 9:  BRANCH   Branch named from Jira key (feature/proj-123)
Step 10: UPDATE   Transition → "In Progress", add start comment
Step 11: LINK     PR linked in Jira, transition → "In Review"
Step 12: CLOSE    Transition → "Done", add implementation summary
```

### Figma (`ENABLE_FIGMA=1`)

```
Step 0:  EXTRACT  Components + design tokens extracted into orchestration prompt
Step 10: COMMENT  "Implementation started" with component list
Step 11: REVIEW   Design fidelity checklist in code review
Step 12: COMMENT  "Implementation complete" with PR link
```

---

## Production Deployment

### Docker

```bash
docker build -t claude-workflow-engine .
docker run --env-file .env claude-workflow-engine \
  python scripts/3-level-flow.py --message "your task"
```

### Docker Compose

```bash
docker-compose up
```

### Kubernetes

```bash
kubectl apply -f k8s/secret.yaml -f k8s/configmap.yaml \
  -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml
```

### With full observability

```bash
ENABLE_HEALTH_SERVER=1 ENABLE_METRICS=1 LOG_FORMAT=json \
  python scripts/3-level-flow.py --message "your task"
```

---

## Testing

44 test_*.py files (56 total Python files in `tests/` including conftest and `__init__` files):

| Category | Files | Notes |
|---|:---:|---|
| Unit tests | 36 | In `tests/test_*.py` — no external dependencies required |
| Integration tests | 4 | `tests/integration/` — require live GitHub token or MCP servers |
| E2E tests | 3 | `tests/e2e/` — require full pipeline environment |
| Load tests | 1 | `tests/load/` — enabled with `RUN_LOAD_TESTS=1` |

```bash
# Full unit suite
pytest tests/

# Specific areas
pytest tests/test_call_graph_analyzer.py
pytest tests/test_uml_generators.py
pytest tests/test_level1_sync.py
pytest tests/test_secrets_manager.py

# Integration tests (require live providers)
pytest tests/integration/ -m integration

# E2E tests (require full pipeline env)
pytest tests/e2e/

# Load / concurrency tests
RUN_LOAD_TESTS=1 pytest tests/load/

# With coverage
pytest tests/ --cov=langgraph_engine --cov-report=html:docs/coverage

# Secret scanning CI gate
python scripts/secrets_check.py

# Dependency pinning
python scripts/pin_requirements.py
```

> MCP server tests live in their respective separate repos — they are not included here.

---

## Benchmarks & Performance

Numbers from the project's internal version history. All measurements taken on a MacBook Pro M2 / Windows 11 machine using Claude Sonnet 3.5 on a mid-complexity task (combined_complexity_score ~ 10/25).

### Planning Phase Evolution

| Version | Active Steps | Planning LLM Calls | Planning Time | Key Change |
|---------|:-----------:|:-----------------:|:-------------:|------------|
| v1.12.0 | 15 | ~6 | ~75s | Original — Steps 0-7 each called LLM separately |
| v1.13.0 | 9 | ~2 (subprocess) | ~30s | Removed Steps 1, 3, 4, 5, 6, 7 |
| v1.14.0 | 8 | 2 (subprocess) | ~15s | Step 0 = template fill + orchestrator (claude CLI) |
| v1.16.0 | 8 | 2 (subprocess) | ~15s | Level 2 purged — standards read from policies/ directly |
| **current** | **8** | **2** | **~15s** | Template fast-path: **~0s** (Step 0 bypassed entirely) |

**Planning overhead reduced by 80%** (75s → 15s) across 4 versions without any loss of output quality.

### Token Optimizer MCP Server

[mcp-token-optimizer](https://github.com/techdeveloper-org/mcp-token-optimizer) uses AST-based navigation, smart file reading, and context deduplication to reduce tokens consumed per pipeline run.

| Technique | Mechanism | Typical Savings |
|-----------|-----------|:--------------:|
| AST navigation | Skip irrelevant functions/classes in large files | 40-60% |
| Smart read | Read only the slice the agent needs (not whole file) | 20-40% |
| Context dedup | Deduplicate repeated state / schema definitions | 10-20% |
| **Combined** | Applied across all 8 active steps | **60-85%** |

### Call Graph Intelligence

The AST-based call graph (578 classes, 3,985 methods across Python, Java, TypeScript, Kotlin) enables:

| Capability | Without Call Graph | With Call Graph |
|------------|:-----------------:|:---------------:|
| Impact scope before change | Manual review | Automatic: `hot_nodes`, `danger_zones`, `affected_methods` |
| Breaking change detection | File diff only | Method-level graph diff (before/after Step 10) |
| Complexity scoring | Heuristic (1-10) | `combined_complexity_score` [1-25] = heuristic × 0.3 + graph × 0.7 |
| Multi-language support | Python only | Python (AST) + Java, TypeScript, Kotlin (regex) |

### Pipeline Size vs. Capability Ratio

| Metric | v1.12 | Current (v1.19.1) | Delta |
|--------|:-----:|:-----------------:|:-----:|
| Active pipeline steps | 15 | 8 | -47% |
| Planning LLM calls | ~6 | 2 | -67% |
| Planning time | ~75s | ~15s | -80% |
| Token optimizer savings | N/A | 60-85% | — |
| Supported languages (call graph) | 1 | 4 | +300% |
| MCP servers | 0 | 13 (295 tools) | — |
| Total Python files | ~50 | 369 | — |
| Test files (test_*.py) | 0 | 44 | — |
| Integration tests | 0 | 4 | — |
| E2E tests | 0 | 3 | — |

---

## Community & Feedback

### GitHub Discussions

We use [GitHub Discussions](https://github.com/techdeveloper-org/claude-workflow-engine/discussions) for:

- **Feature requests** — new integrations, pipeline steps, MCP server ideas
- **Integration questions** — connecting with Latenode, n8n, custom MCP servers, CI systems
- **Workflow sharing** — share your Hook Mode setup, orchestration templates, use cases
- **Q&A** — setup help, debugging, configuration

### MCP Server Adoption Patterns

Based on community usage patterns, the most-adopted server combinations are:

| Pattern | Servers | Why |
|---------|---------|-----|
| **Minimal** (code only) | git-ops + github-api | Branch + PR automation with zero extra infra |
| **Token-efficient** | token-optimizer + session-mgr | 60-85% context savings; long sessions stay coherent |
| **Full GitHub SDLC** | git-ops + github-api + session-mgr | Issue → branch → code → PR → close lifecycle |
| **With diagrams** | uml-diagram + drawio-diagram | Auto-generated architecture docs on every implementation |
| **Enterprise** | jira-api + jenkins-ci + policy-enforcement | Dual ticketing + build gate + policy compliance |
| **Observability** | All 13 servers + health/metrics/tracing | Production-grade pipeline with full telemetry |

### Platform Integration Interest

The engine is designed as a self-contained pipeline but the following no-code/low-code platforms have been explored as integration targets:

| Platform | Integration Path | Status |
|----------|-----------------|--------|
| **GitHub Actions** | `ENABLE_CI=true` + `workflow_dispatch` trigger | Shipped (v1.19.0) |
| **Latenode** | HTTP webhook → `POST /run` with `{"message": "..."}` | Planned |
| **n8n** | Self-hosted node calling `3-level-flow.py` via subprocess | Community interest |
| **Zapier** | Webhook trigger + GitHub Actions bridge | Not planned (closed platform) |

If you are building an integration or have used the engine with an automation platform, share it in [Discussions](https://github.com/techdeveloper-org/claude-workflow-engine/discussions).

### Give Feedback

| Channel | Purpose |
|---------|---------|
| [GitHub Issues](https://github.com/techdeveloper-org/claude-workflow-engine/issues) | Bug reports, reproducible problems |
| [GitHub Discussions](https://github.com/techdeveloper-org/claude-workflow-engine/discussions) | Feature ideas, questions, workflow sharing |
| Security issues | Open a private GitHub Security Advisory (repo → Security tab) |

---

## Roadmap

See [CHANGELOG.md](CHANGELOG.md) for the complete version history.

### Upcoming

- GitHub App install flow (no manual `GITHUB_TOKEN` setup)
- Web dashboard for pipeline run history
- Additional parser languages: Ruby, Go, C++
- YAML-based pipeline configuration (`config.yaml` replacing env var flags)

---

## Limitations & Trade-offs

### Hard Requirements

| Requirement | Why |
|---|---|
| Claude Code CLI must be installed and authenticated | Step 0 runs two subprocess calls against the `claude` CLI — no fallback path exists |
| Python 3.10+ | `mcp>=1.0.0` requires 3.10+; `match` statements used in routing |
| `ANTHROPIC_API_KEY` is always required | The `anthropic` provider is the fallback when `claude_cli` is unavailable |
| `GITHUB_TOKEN` required for any SDLC step | Steps 8-12 all write to GitHub — no local-only mode |

### Known Limitations

**Call graph (Java / TypeScript / Kotlin):** The Java, TypeScript, and Kotlin parsers are regex-based, not full AST parsers. They handle common patterns well but may miss edge cases: anonymous classes, deeply chained lambdas, decorator-wrapped functions, and dynamic imports. The Python parser is the only full AST-based one.

**Full Mode is sequential:** Steps 10-14 execute one after another in a single process. If a network call (GitHub, Jira, Figma) hangs, the entire pipeline stalls. There is no step-level async execution or per-step timeout by default.

**No persistent pipeline state across crashes:** If the Python process is killed mid-run, LangGraph's in-memory state is lost. The `checkpoint_manager.py` writes step-level checkpoints, but resume logic is partial — not all steps support clean resume from a checkpoint.

**SonarQube auto-fix is limited:** The auto-fixer targets common rule violations (unused imports, simple null-safety issues). Complex code smells that require architectural changes are flagged in the PR but not auto-fixed.

**Voice notifications require optional deps:** The `stop-notifier.py` TTS voice feature requires `requirements-optional.txt` (Coqui TTS). Installing it conflicts with `networkx>=3.1` used by the main pipeline via the `gruut==2.2.3` transitive dependency. You cannot have both in the same virtual environment.

**MCP servers are external processes:** All 13 MCP servers run as separate processes registered in `~/.claude/settings.json`. They are not in-process libraries. If a server is down, the MCP tool calls fail silently unless the server has a health-check tool available.

**Regex-based secret scanning:** `secrets_check.py` uses 6 regex patterns covering common formats (AWS keys, GitHub tokens, Anthropic keys, etc.). It will miss custom secret formats and secrets stored in environment-variable lookups inside code.

**Complexity score is not ground truth:** `combined_complexity_score` is a heuristic: `simple_score × 0.3 + graph_score × 0.7`. It is on a 1-25 scale and correlates with effort, but it does not map to story points and should not be treated as precise.

### Trade-offs by Design

| Decision | What You Gain | What You Give Up |
|---|---|---|
| 2-provider LLM chain (`claude_cli` + `anthropic`) | Simplicity, no inference infra | Cannot use Ollama, OpenAI, or local GPU models — all were removed in v1.15.3 |
| Level 2 is NO-OP (policies as .md files) | Zero pipeline overhead for standards | Cannot run per-file standards checks dynamically inside the pipeline |
| Step 0 uses subprocess (not in-process API) | Leverages full Claude Code context + hooks | Adds ~15s overhead; subprocess exit codes are the only error signal |
| Template fast-path bypasses Step 0 | ~0s planning on repeat tasks | Template must be kept manually in sync with task requirements |
| 13 external MCP servers | Independent versioning, reusability | Each server is a separate process; cold-start latency on first tool call |
| Hooks are synchronous (`async: false`) | Predictable execution, no race conditions | Long hook operations (e.g., vector DB indexing) block the Claude Code terminal |
| ASCII-only Python files | Windows cp1252 safe, no encoding bugs | Cannot use Unicode identifiers, emoji, or non-ASCII comments in source |
| In-process `session-mgr` copy in `src/mcp/` | Zero-latency session access | Two copies of the code must be kept in sync when the upstream repo changes |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding standards, and PR guidelines.

Key rules:
- No `# ruff: noqa: F821` file-level suppressors
- ASCII-only in `.py` files (Windows cp1252 safe)
- All paths via `path_resolver.py` — no hardcoded strings
- `pytest tests/` must stay at 100% pass rate
- `ruff check .` must pass clean

---

## License

[MIT](LICENSE) — Copyright (c) 2026 TechDeveloper

---

**Version:** 1.19.1 | **Last Updated:** 2026-04-15
