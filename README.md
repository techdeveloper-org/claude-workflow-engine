# Claude Workflow Engine

**The first AI tool that follows full SDLC** — from task analysis to merged PR, automatically.

**Version:** 1.16.1 | **Status:** Alpha | **Last Updated:** 2026-04-07

---

## The Problem

Every AI coding tool does ONE thing: generate code. None follow Software Development Life Cycle (SDLC):

| Tool | Code Gen | Task Analysis | Planning | GitHub Issue | Branch | PR | Code Review | Docs |
|------|----------|--------------|----------|-------------|--------|-----|-------------|------|
| GitHub Copilot | Yes | - | - | - | - | - | - | - |
| Cursor | Yes | - | - | - | - | - | - | - |
| Devin | Yes | Partial | Partial | - | - | - | - | - |
| Claude Code | Yes | - | - | - | - | - | - | - |
| **This Engine** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

---

## What It Does

Give it a task. It handles everything:

```
You say: "Fix the login timeout bug"

Engine does:
  Level -1: Auto-fix (Unicode, encoding, paths)
  Level 1:  Session sync + complexity score (combined_complexity_score, 1-25 scale)
  Level 2:  (NO-OP) -- policies/ .md files read directly at runtime; no pipeline nodes
  Level 3:
    Pre-0:  Call graph scan -> hot_nodes, danger_zones, complexity_boost
    Step 0: Task Analysis -- PromptGen + Orchestrator (2 subprocess calls, ~15s total)
              Call 1: prompt-gen-expert-caller fills orchestration_system_prompt.txt
              Call 2: orchestrator-agent-caller executes full plan (streamed live)
    Step 8:  GitHub Issue + Jira Issue (dual-linked)
    Step 9:  Branch creation (feature/PROJ-123 from Jira key)
    Step 10: Implementation + Jira "In Progress" + Figma "started"
    Step 11: PR + Code Review + Jira "In Review" + Figma design fidelity check
    Step 12: Issue closure (GitHub + Jira "Done" + Figma "complete")
    Step 13: Documentation + UML diagrams (13 types)
    Step 14: Final summary + voice notification
```

**Total: ~15s planning, ~120s full pipeline.**

### Template Fast-Path

Pre-fill an orchestration template once, skip Step 0 on every run:

```bash
python scripts/3-level-flow.py \
  --message "add document Q&A feature" \
  --orchestration-template=my_template.json
# Step 0 bypassed -> jumps to Step 8 -> planning time ~0s
```

### Planning Phase Evolution

| Version | Steps | LLM Calls (planning) | Planning Time | Key Change |
|---------|-------|----------------------|---------------|------------|
| v1.12.0 | 15 | ~6 | ~75s | Original: Steps 0-7 each called LLM separately |
| v1.13.0 | 9 | 2 (subprocess) | ~30s | Removed Steps 1,3,4,5,6,7 |
| v1.14.0 | 8 | 2 (subprocess) | ~15s | Step 0 = template fill + orchestrator (claude CLI) |
| v1.15.0 | 8 | 2 (subprocess) | ~15s | TOON compression removed from Level 1 |
| v1.15.2 | 8 | 2 (subprocess) | ~15s | Exhaustive artifact purge: TOON/plan-mode/skill-selection |
| v1.15.3 | 8 | 2 (subprocess) | ~15s | Dead LLM provider purge: Ollama/NPU/GPU/OpenAI/DeepSeek removed |
| v1.16.0 | 8 | 2 (subprocess) | ~15s | Level 2 script purge: level2_standards/ removed; policies in policies/02-standards-system/ |
| **v1.16.1** | **8** | **2 (subprocess)** | **~15s** | **uml/ + drawio/ moved to project root; UML_OUTPUT_DIR + DRAWIO_OUTPUT_DIR env vars added** |

---

## Architecture

### 3-Level Pipeline (v1.16.0)

```
Level -1: AUTO-FIX      3 checks: Unicode, encoding, paths
    |
Level 1:  CONTEXT SYNC  Session + parallel [complexity, context] -> merge
    |                   Output: combined_complexity_score [1-25 scale]
    |
Level 2:  (NO-OP)       Coding standards .md files read directly from policies/ at runtime
    |                   No pipeline nodes. Policies in policies/02-standards-system/.
    |
Level 3:  EXECUTION     8 active steps (Pre-0, Step 0, Steps 8-14)
```

### Level 3 — 8-Step Active SDLC

| Phase | Step | What Happens |
|-------|------|-------------|
| Pre-Analysis | Pre-0 | Call graph scan: hot nodes, danger zones, complexity boost into Step 0 context |
| Analysis | Step 0 | PromptGen (template fill) + Orchestrator (full plan) — 2 claude CLI subprocess calls |
| Issue & Branch | Steps 8-9 | GitHub Issue + Jira Issue (dual-linked); branch from Jira key |
| Implementation | Step 10 | Code + CallGraph snapshot; Jira "In Progress"; Figma "started" comment |
| Review & Closure | Steps 11-12 | PR + code review + CallGraph diff; Jira "In Review" → "Done"; Figma fidelity check |
| Finalization | Steps 13-14 | Documentation + 13 UML diagram types; execution summary + voice notification |

### Execution Modes

```
Hook Mode (CLAUDE_HOOK_MODE=1, default):
  Pre-0, Step 0, Steps 8-9 only (analysis + issue + branch)
  Steps 10-14 skipped — user implements, then runs Full Mode

Full Mode (CLAUDE_HOOK_MODE=0):
  All 8 active steps execute sequentially
```

### Integration Flags (all disabled by default)

| Flag | Effect |
|------|--------|
| `ENABLE_JIRA=1` | Dual GitHub + Jira issue lifecycle (Steps 8,9,11,12) |
| `ENABLE_JENKINS=1` | Jenkins build validation (Steps 10,11) |
| `ENABLE_SONARQUBE=1` | SonarQube scan + auto-fix loop (Step 10) |
| `ENABLE_FIGMA=1` | Figma component extraction + design review (Steps 10,11,12) |
| `ENABLE_HEALTH_SERVER=1` | HTTP `/health` + `/readiness` on HEALTH_PORT (8080) |
| `ENABLE_METRICS=1` | Prometheus `/metrics` on METRICS_PORT (9090) |
| `ENABLE_TRACING=1` | OpenTelemetry OTLP tracing |
| `LOG_FORMAT=json` | Structured JSON logging for container log aggregation |

---

## Policy System

All pipeline policies are organized by level in `policies/`:

| Level | Directory | Purpose |
|-------|-----------|---------|
| Level -1 | `00-auto-fix-system/` | Unicode, encoding, Windows path checks (blocking pre-flight, max 3 retries) |
| Level 1 | `01-sync-system/` | Session management, context optimization (70/85/90% thresholds), user preferences, pattern detection |
| Level 2 | `02-standards-system/` | Common coding standards (12 categories, ~65 rules) + Spring Boot microservices standards (15 categories, ~139 rules, conditional) |
| Level 3 | `03-execution-system/` | Step-by-step execution policies (prompt generation, progress tracking, git commit, implementation, PR, issue closure, docs, summary) |
| Testing | `testing/` | Test scripts and testing policies (phase testing, skill testing, infrastructure health) |

---

## CallGraph Intelligence

The call graph is the brain of the engine — a complete AST-based call stack across the entire codebase.

**Stats:** 578 classes, 3,985 methods, 4 languages (Python full AST; Java, TypeScript, Kotlin regex-based)

**Pipeline use:**

| Step | Function | What It Does |
|------|----------|-------------|
| Pre-0 | `analyze_impact_before_change()` | Risk assessment before any code change |
| Step 10 | `snapshot_call_graph()` + `get_implementation_context()` | Pre-change snapshot + caller/callee context |
| Step 11 | `review_change_impact(before, after)` | Diff: detects breaking changes, new/removed edges |
| Step 11+ | `refresh_call_graph_if_stale()` | Rebuilds graph when `call_graph_stale=True` (set after Step 10 writes) |

UML diagrams (13 types) also use the call graph as their single data source.

---

## 13 MCP Servers (295 Tools)

All servers are in separate repos under [`techdeveloper-org`](https://github.com/orgs/techdeveloper-org/repositories).
`session-mgr` also keeps an in-engine copy (`src/mcp/`) for tight coupling.

| # | Server | Repo | Tools | Purpose |
|---|--------|------|-------|---------|
| 1 | session-mgr | [mcp-session-mgr](https://github.com/techdeveloper-org/mcp-session-mgr) | 14 | Session lifecycle |
| 2 | git-ops | [mcp-git-ops](https://github.com/techdeveloper-org/mcp-git-ops) | 14 | Git operations |
| 3 | github-api | [mcp-github-api](https://github.com/techdeveloper-org/mcp-github-api) | 12 | GitHub PR/issue/merge |
| 4 | policy-enforcement | [mcp-policy-enforcement](https://github.com/techdeveloper-org/mcp-policy-enforcement) | 11 | Policy compliance + health |
| 5 | token-optimizer | [mcp-token-optimizer](https://github.com/techdeveloper-org/mcp-token-optimizer) | 10 | Token reduction (60-85% savings) |
| 6 | pre-tool-gate | [mcp-pre-tool-gate](https://github.com/techdeveloper-org/mcp-pre-tool-gate) | 13 | Pre-tool validation |
| 7 | post-tool-tracker | [mcp-post-tool-tracker](https://github.com/techdeveloper-org/mcp-post-tool-tracker) | 6 | Post-tool progress tracking |
| 8 | standards-loader | [mcp-standards-loader](https://github.com/techdeveloper-org/mcp-standards-loader) | 7 | Standards detection + hot-reload |
| 9 | uml-diagram | [mcp-uml-diagram](https://github.com/techdeveloper-org/mcp-uml-diagram) | 15 | 13 UML diagram types (Mermaid/PlantUML) |
| 10 | drawio-diagram | [mcp-drawio-diagram](https://github.com/techdeveloper-org/mcp-drawio-diagram) | 5 | Draw.io editable diagrams |
| 11 | jira-api | [mcp-jira-api](https://github.com/techdeveloper-org/mcp-jira-api) | 10 | Jira full lifecycle |
| 12 | jenkins-ci | [mcp-jenkins-ci](https://github.com/techdeveloper-org/mcp-jenkins-ci) | 10 | Jenkins build + CI validation |
| 13 | figma-api | [mcp-figma](https://github.com/techdeveloper-org/mcp-figma) | 10 | Figma components + design tokens |

> Shared base: [mcp-base](https://github.com/techdeveloper-org/mcp-base) — MCPResponse, @mcp_tool_handler, AtomicJsonStore, LazyClient

---

## LLM Providers

2 supported providers, auto-fallback chain:

```
claude_cli  -> Claude Code CLI (uses Anthropic subscription)
anthropic   -> Anthropic API (needs ANTHROPIC_API_KEY)

LLM_PROVIDER=auto   -> tries claude_cli -> anthropic in order
LLM_PROVIDER=claude_cli -> Claude CLI first, fallback -> anthropic
```

---

## Hook System

| Hook | Script | Purpose |
|------|--------|---------|
| UserPromptSubmit | 3-level-flow.py | Runs full pipeline on every user message |
| PreToolUse | hooks/pre-tool-enforcer.py | Tool validation + Level 1 checkpoint enforcement |
| PostToolUse | hooks/post-tool-tracker.py | Progress tracking, flag clearing, GitHub integration |
| Stop | hooks/stop-notifier.py | Voice notification + session save on session end |

---

## Quick Start

### Prerequisites

- Python 3.8+
- GitHub CLI (`gh`) installed and authenticated

### Installation

```bash
git clone https://github.com/techdeveloper-org/claude-workflow-engine.git
cd claude-workflow-engine
make install        # installs deps + activates pre-commit hooks
cp .env.example .env
# Edit .env with your API keys
```

### Running the Pipeline

```bash
# Hook mode (default: Pre-0, Step 0, Steps 8-9 only)
python scripts/3-level-flow.py --message "fix login bug"

# Full mode (all 8 active steps)
CLAUDE_HOOK_MODE=0 python scripts/3-level-flow.py --message "add user profile feature"

# Template fast-path (skip Step 0, jump to Step 8)
python scripts/3-level-flow.py \
  --message "add document Q&A" \
  --orchestration-template=my_template.json

# Debug mode
CLAUDE_DEBUG=1 python scripts/3-level-flow.py --message "your task" --summary
```

### Testing

```bash
pytest tests/                          # all tests
pytest tests/test_*mcp*.py            # MCP server tests
pytest tests/integration/             # integration tests
pytest tests/ --cov=langgraph_engine --cov-report=html
```

---

## Directory Structure

```
claude-workflow-engine/
+-- scripts/
|   +-- langgraph_engine/
|   |   +-- core/                     # LazyLoader, ErrorHandler, NodeResult, create_step_node
|   |   +-- state/                    # FlowState, StepKeys, reducers, WorkflowContextOptimizer
|   |   +-- routing/                  # Routing functions split by level
|   |   +-- helper_nodes/             # Helper node functions split by concern
|   |   +-- diagrams/                 # Strategy: DiagramFactory + 13 UML generators
|   |   +-- parsers/                  # Abstract Factory: 4 language parsers (Py/Java/TS/Kotlin)
|   |   +-- integrations/             # Lifecycle: GitHub/Jira/Figma/Jenkins adapters
|   |   +-- pipeline_builder.py       # Builder: PipelineBuilder chainable API
|   |   +-- orchestrator.py           # Main StateGraph pipeline
|   |   +-- level_minus1/             # Level -1: Auto-fix (Unicode, encoding, paths)
|   |   +-- level1_sync/              # Level 1: Session + complexity sync
|   |   +-- level3_execution/         # Level 3: 8-step SDLC (subgraph.py + nodes/ + sonarqube/)
|   |   +-- call_graph_analyzer.py    # Impact analysis, snapshots, diff (Steps Pre-0/10/11)
|   |   +-- [60+ shared modules]      # LLM, caching, metrics, git, standards, etc.
|   +-- setup/                        # One-time setup scripts
|   +-- bin/                          # Windows .bat launchers
|   +-- tools/                        # Developer utilities (release, sync, metrics, voice)
|   +-- 3-level-flow.py               # Pipeline entry point
+-- hooks/                            # Claude Code hook scripts
|   +-- pre-tool-enforcer.py          # PreToolUse hook shim
|   +-- post-tool-tracker.py          # PostToolUse hook shim
|   +-- stop-notifier.py              # Stop hook shim
|   +-- pre_tool_enforcer/            # PreToolUse hook package
|   +-- post_tool_tracker/            # PostToolUse hook package
|   +-- stop_notifier/                # Stop hook package
+-- src/mcp/                          # In-engine session-mgr copy + bridge (session_hooks)
+-- policies/                         # Pipeline policies by level (00-auto-fix, 01-sync, 02-standards, 03-execution)
+-- tests/                            # 74 test files
+-- docs/                             # Documentation files
+-- uml/                              # Auto-generated UML diagrams (13 types)
+-- drawio/                           # Auto-generated draw.io diagrams (13 types)
+-- rules/                            # 34 coding standard definitions
+-- k8s/                              # Kubernetes manifests (Deployment, ConfigMap, HPA)
+-- VERSION                           # Single version source
+-- CLAUDE.md                         # Project context for Claude Code
+-- requirements.txt                  # Python dependencies
+-- requirements-optional.txt         # TTS/voice (separate due to networkx conflict)
+-- .env.example                      # Configuration template
```

---

## Key Statistics

| Metric | Value |
|--------|-------|
| Pipeline Levels | 3 active (Level -1, 1, 3) — Level 2 is NO-OP |
| Execution Steps | 8 (Pre-0, Step 0, Steps 8-14) |
| MCP Servers | 13 (295 tools) in separate repos |
| LangGraph Modules | 60+ shared + 9 canonical packages |
| Policy Files | policies/ directory (4 level subdirs + testing) |
| Standards Files | 34 |
| Test Files | 74 |
| Total Python Files | 304+ |
| Call Graph | 578 classes, 3,985 methods, 4 languages |
| UML Diagram Types | 13 (CallGraph-powered) |
| LLM Providers | 2 (claude_cli, anthropic) |
| Supported Languages | 20+ |
| Quality Gates | 4 (SonarQube, coverage, breaking changes, tests) |

---

## Production Features

| Feature | Module |
|---------|--------|
| Health + Readiness endpoints | `scripts/health_server.py` — `ENABLE_HEALTH_SERVER=1` |
| Prometheus metrics (9 metrics) | `langgraph_engine/metrics_exporter.py` — `ENABLE_METRICS=1` |
| Structured JSON logging | `langgraph_engine/core/structured_logger.py` — `LOG_FORMAT=json` |
| OpenTelemetry tracing | `langgraph_engine/tracing.py` — `ENABLE_TRACING=1` |
| Sentry error tracking | `langgraph_engine/error_tracking.py` — no-op without `SENTRY_DSN` |
| Secrets validation | `langgraph_engine/secrets_manager.py` — startup check + AWS SM |
| Rate limiting | `src/mcp/rate_limiter.py` — TokenBucket, 100/min tools, 10/min LLM |
| Input validation | `src/mcp/input_validator.py` — null-byte strip, prompt injection detection |
| Audit logging | `langgraph_engine/audit_logger.py` — append-only JSON, credential redaction |
| Secrets scanner (CI gate) | `scripts/secrets_check.py` — 6 regex patterns, exit 1 on finding |
| Kubernetes manifests | `k8s/` — Deployment (2 replicas), ConfigMap, Secret, HPA |
| Pre-commit hooks | `.pre-commit-config.yaml` — ruff, black, isort, secrets-check |

```bash
# Production run
ENABLE_HEALTH_SERVER=1 ENABLE_METRICS=1 LOG_FORMAT=json \
  python scripts/3-level-flow.py --message "your task"

# Kubernetes
kubectl apply -f k8s/secret.yaml -f k8s/configmap.yaml \
  -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml
```

---

## Known Issues & Production Readiness

**Current production readiness: ~60%.** Infrastructure is solid (health server, metrics, tracing, audit log, secrets manager all implemented), but the test suite currently reports **701 passed / 113 failed / 38 errors** (80.5% pass rate) — below the 95%+ bar required for production.

**Root cause:** Recent refactor commits (v1.15.0 → v1.16.1) deleted or moved several modules (TOON schema, UML refactor, MCP servers → separate repos, Level 2 purge, timeout wrapper API changes) but the corresponding test files were not updated. Almost all failures are tests referencing deleted code, not production regressions.

### Open Issues (Ship-Blockers)

| # | Issue | Tests Affected | Severity | Category |
|---|-------|---------------:|----------|----------|
| [#200](../../issues/200) | 33 tests reference deleted `langgraph_engine.toon_schema` + `subgraphs` (v1.15.2 purge) | 33 | CRITICAL | test |
| [#201](../../issues/201) | 40 tests reference deleted `UMLAstAnalyzer` class (diagrams/ Strategy refactor) | 40 | CRITICAL | test |
| [#202](../../issues/202) | 37 MCP tests reference deleted `src/mcp/*_mcp_server.py` (servers moved to techdeveloper-org) | 37 | HIGH | test |
| [#203](../../issues/203) | 16 tests reference deleted `scripts/session-id-generator.py` + `metrics-emitter.py` | 16 | HIGH | test |
| [#204](../../issues/204) | 10 `call_graph_analyzer` tests use stale stats key `methods_in_phase` (renamed to `methods_in_scope`) | 10 | MEDIUM | test |
| [#205](../../issues/205) | 7 `level3_robustness` tests import removed `timeout_wrapper.fallback_step2` | 7 | MEDIUM | test |
| [#206](../../issues/206) | 3 `test_new_components` tests reference removed `check_level2_standards_complete` (v1.16.0 Level 2 purge) | 3 | MEDIUM | test |
| [#207](../../issues/207) | `graph_model.compute_call_paths` hard `max_depth=15` cap — truncates call-graph analysis | pipeline | HIGH | backend |
| [#208](../../issues/208) | Python 3.13 `DeprecationWarning: __package__ != __spec__.parent` in `hooks/pre_tool_enforcer/policies/*.py` | pipeline | MEDIUM | scripts |
| [#209](../../issues/209) | Deferred build_dependency_resolver defects D9–D16 (parser edge cases) | — | MEDIUM | enhancement |
| [#210](../../issues/210) | Miscellaneous test failures (e2e stale guard, retry history, BDR self-test, pre_tool_enforcer) | 6 | MEDIUM | test |

**Total:** 11 open issues tracking 152 failing tests + 2 non-test correctness issues.

### Recently Fixed

- **[commit `f27cae0`]** build_dependency_resolver — 11 defects fixed (D1 critical no-op at caller site, D2 wrong edge dedup schema, D3 missing FQN namespacing, D4 unbounded filesystem scan, D5 unbounded rglob, D6 circular import, D7 setattr cache invalidation, D8 discarded delta tracking, D12 O(N²) classification, D14 sys.path-polluting import chain, D15 detect_build_system single-match). New `registries.py` leaf module. 82 new tests, 75.4% coverage on the module. **This was the first half of the original "call graph depth not what I expect" complaint** — see [#207](../../issues/207) for the second half.

### Production Readiness Checklist

| Check | Status | Note |
|-------|--------|------|
| Test suite ≥ 95% pass | 🔴 80.5% | Blocked by issues #200–#206 |
| No test collection errors | 🔴 38 errors | Mostly deleted-module imports |
| Call graph pipeline verified | 🟡 Partial | `build_dependency_resolver` fixed; `call_graph_analyzer` tests blocked on #204 |
| UML pipeline verified | 🔴 Broken | Blocked by #201 |
| MCP integration verified | 🔴 Broken | Blocked by #202 |
| Depth issue fully resolved | 🟡 Half done | First half fixed in `f27cae0`; second half tracked in #207 |
| Python 3.13 compat | 🟡 Warnings | Tracked in #208 |
| Python 3.14 ready | 🔴 Not yet | #208 will become hard ImportError |
| Health + metrics + tracing | 🟢 Implemented | Code exists; runtime verification pending |
| Secrets manager + audit log | 🟢 Implemented | Code exists; runtime verification pending |
| Kubernetes manifests | 🟢 Present | `k8s/` directory with deployment, service, HPA |
| CI pipeline | 🟡 Manual-only | `workflow_dispatch` only per `.github/workflows/` |

**To reach production-ready:** fix the 11 open issues in priority order (CRITICAL → HIGH → MEDIUM), re-run full test suite, target ≥ 95% pass rate.

---

## Comparison: Claude Workflow Engine vs Other AI Tools

| Capability | **This Engine** | Copilot | Cursor | Devin |
|-----------|:---:|:---:|:---:|:---:|
| Code generation | Yes | Yes | Yes | Yes |
| Task analysis + complexity scoring | Yes | - | - | Partial |
| Call graph analysis (impact before change) | Yes | - | - | - |
| Breaking change detection (graph diff) | Yes | - | - | - |
| Auto GitHub issue creation | Yes | - | - | - |
| Dual issue tracking (GitHub + Jira) | Yes | - | - | - |
| Auto branch creation | Yes | - | - | - |
| Auto PR creation + code review | Yes | - | - | - |
| Quality gate enforcement (4 gates) | Yes | - | - | - |
| Auto unit test generation (4 languages) | Yes | - | - | - |
| Auto documentation update | Yes | - | - | - |
| UML diagram generation (13 types) | Yes | - | - | - |
| SonarQube + auto-fix loop | Yes | - | - | - |
| Figma design-to-code extraction | Yes | - | - | - |
| Jenkins CI integration | Yes | - | - | - |
| Full issue lifecycle (create → close) | Yes | - | - | - |

Other tools do one thing well: code generation. This engine does what a full engineering team does — from ticket to merged PR.

---

## Configuration Reference

Key environment variables (see `.env.example` for full list):

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `GITHUB_TOKEN` | GitHub personal access token |
| `CLAUDE_HOOK_MODE` | `1` = Hook mode (default), `0` = Full mode |
| `CLAUDE_DEBUG` | `1` = Debug logging |
| `ENABLE_JIRA` | `1` = Enable Jira integration |
| `ENABLE_SONARQUBE` | `1` = Enable SonarQube scan |
| `ENABLE_JENKINS` | `1` = Enable Jenkins CI |
| `ENABLE_FIGMA` | `1` = Enable Figma design pipeline |
| `LLM_PROVIDER` | `claude_cli` / `anthropic` / `auto` |

---

**Last Updated:** 2026-04-07
