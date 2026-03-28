# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 1.8.0
**Type:** LangGraph Orchestration Pipeline with RAG + Call Graph Intelligence + Template Fast-Path
**Last Updated:** 2026-03-28

---

## Project Overview

Claude Workflow Engine is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It handles session sync, coding standards enforcement, and end-to-end 15-step task execution (Step 0-14) with GitHub integration, RAG-powered decision caching, and hybrid LLM inference across 4 providers.

### Quick Info

| Property | Value |
|----------|-------|
| **Languages** | Python |
| **Frameworks** | LangGraph 0.2.0+, LangChain, FastMCP (mcp package), Qdrant |
| **Status** | Active Development |
| **Primary Location** | scripts/langgraph_engine/ |
| **MCP Servers** | 19 (323 tools) |
| **Total Python Files** | 375+ |
| **Test Files** | 74 |
| **Call Graph** | 578 classes, 3,985 methods, 4 languages (Python/Java/TS/Kotlin) |

---

## Architecture & Structure

### Pipeline Flow

```
Level -1: Auto-Fix (3 checks: Unicode, encoding, paths)
    |
Level 1: Sync (session + parallel [complexity, context] + TOON compress)
    |
Level 2: Standards (common + conditional Java + tool opt + MCP discovery)
    |
Level 3: Execution (15 steps: Step 0 through Step 14)
    |-- Pre-0: Orchestration Pre-Analysis (Template check + CallGraph scan + RAG lookup)
    |           Template provided -> skip Steps 0-5, jump to Step 6 (~6 LLM calls saved, ~15s)
    |           RAG hit (>=0.85) -> skip Steps 0-4, jump to Step 5 (~5 LLM calls saved)
    |           RAG miss -> normal flow; call graph complexity boost injected into Step 0
    |-- Step 0:  Task Analysis + Prompt Generation (complexity boosted by call graph)
    |-- Step 1:  Plan Mode Decision
    |-- Step 2:  Plan Execution (CallGraph impact analysis + complexity-based model)
    |-- Step 3:  Task/Phase Breakdown + Figma component extraction (ENABLE_FIGMA)
    |-- Step 4:  TOON Refinement
    |-- Step 5:  Skill & Agent Selection (RAG cross-session boost + call graph hot-node bonus)
    |-- Step 6:  Skill Validation & Download
    |-- Step 7:  Final Prompt Generation (3 files) + Figma design tokens injection
    |-- Step 8:  GitHub Issue + Jira Issue creation (ENABLE_JIRA, dual-linked)
    |-- Step 9:  Branch Creation (Jira key: feature/PROJ-123)
    |-- Step 10: Implementation + Jira "In Progress" + Figma "started" comment
    |-- Step 11: PR + Code Review + Jira PR link + Figma design review
    |-- Step 12: Issue Closure (GitHub + Jira "Done" + Figma "complete" comment)
    |-- Step 13: Documentation Update + UML Diagram Generation
    |-- Step 14: Final Summary
```

### Directory Layout

```
/
+-- scripts/                          # Pipeline scripts and hooks
|   +-- langgraph_engine/             # Core orchestration (155+ modules)
|   |   +-- core/                     # [NEW v1.5] Cross-cutting abstractions (LazyLoader, ErrorHandler, NodeResult, etc.)
|   |   +-- state/                    # [NEW v1.5] FlowState split into 6 focused modules
|   |   +-- routing/                  # [NEW v1.5] All routing functions split by level
|   |   +-- helper_nodes/             # [NEW v1.5] Helper node functions split by concern
|   |   +-- diagrams/                 # [NEW v1.5] Strategy Pattern: 13 swappable UML generators
|   |   +-- parsers/                  # [NEW v1.5] Abstract Factory: 4 language parsers (Py/Java/TS/Kotlin)
|   |   +-- sonarqube/                # [NEW v1.5] Facade: api_client + lightweight + aggregator + auto_fixer
|   |   +-- integrations/             # [NEW v1.5] Abstract Factory + Lifecycle: GitHub/Jira/Figma/Jenkins
|   |   +-- pipeline_builder.py       # [NEW v1.5] Builder Pattern: PipelineBuilder chainable API
|   |   +-- subgraphs/               # Level -1, 1, 2, 3 implementations
|   +-- architecture/                 # Active pipeline scripts (6 scripts + 1 data file)
+-- policies/                         # 63 policy definitions (62 .md + 1 .json)
|   +-- 00-auto-fix-system/           # Level -1 policies (Unicode, encoding, paths, recovery)
|   +-- 01-sync-system/               # Level 1 policies
|   +-- 02-standards-system/          # Level 2 policies (+ tool optimization, MCP discovery)
|   +-- 03-execution-system/          # Level 3 policies (15 steps + RAG, CallGraph, QualityGate, hooks)
+-- src/mcp/                          # 19 FastMCP servers (323 tools)
+-- tests/                            # 69 test files
+-- docs/                             # 46 documentation files
+-- docs/uml/                         # Auto-generated UML diagrams (13 types)
+-- rules/                            # 12 coding standard definitions (incl. doc governance + docstrings-only)
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Orchestrator | scripts/langgraph_engine/orchestrator.py | Main StateGraph pipeline |
| Flow State | scripts/langgraph_engine/flow_state.py | Backward-compat shim → re-exports from state/ |
| State Package | scripts/langgraph_engine/state/ | FlowState, StepKeys, reducers, ToonObject, optimizer |
| Core Package | scripts/langgraph_engine/core/ | LazyLoader, get_logger, node_error_handler, NodeResult, create_step_node |
| Routing Package | scripts/langgraph_engine/routing/ | All 7 routing functions split by level |
| Helper Nodes | scripts/langgraph_engine/helper_nodes/ | 11 helper node functions split by concern |
| Pipeline Builder | scripts/langgraph_engine/pipeline_builder.py | Builder Pattern: chainable add_level*().build() |
| Diagrams Package | scripts/langgraph_engine/diagrams/ | Strategy Pattern: DiagramFactory + 13 generators |
| Parsers Package | scripts/langgraph_engine/parsers/ | Abstract Factory: ParserRegistry + 4 language parsers |
| SonarQube Package | scripts/langgraph_engine/sonarqube/ | Facade: api_client, lightweight, aggregator, auto_fixer |
| Integrations Package | scripts/langgraph_engine/integrations/ | Abstract Factory + Lifecycle: GitHub/Jira/Figma/Jenkins |
| RAG Integration | scripts/langgraph_engine/rag_integration.py | Vector DB decision caching + orchestration-level plan cache |
| Pre-Analysis Node | scripts/langgraph_engine/subgraphs/level3_execution_v2.py | orchestration_pre_analysis_node: CallGraph scan + RAG lookup before Step 0 |
| Level -1 | scripts/langgraph_engine/subgraphs/level_minus1.py | Auto-fix enforcement |
| Level 1 | scripts/langgraph_engine/subgraphs/level1_sync.py | Session/context sync + TOON |
| Level 2 | scripts/langgraph_engine/subgraphs/level2_standards.py | Standards loading |
| Level 3 v2 | scripts/langgraph_engine/subgraphs/level3_execution_v2.py | 15-step execution with RAG - ACTIVE |
| Level 3 v1 | scripts/langgraph_engine/subgraphs/level3_execution.py | Original pipeline - DEPRECATED |
| Hooks | scripts/pre-tool-enforcer.py, post-tool-tracker.py | Tool enforcement |
| Call Graph Builder | scripts/langgraph_engine/call_graph_builder.py | AST-based FQN call stack (compat shim → parsers/) |
| Call Graph Analyzer | scripts/langgraph_engine/call_graph_analyzer.py | Pipeline impact analysis (Steps 2/10/11) |
| UML Generators | scripts/langgraph_engine/uml_generators.py | Compat shim → diagrams/DiagramFactory |
| Doc Manager | scripts/langgraph_engine/level3_documentation_manager.py | Circular SDLC doc cycle (Step 0/13) |
| Session Bridge | src/mcp/session_hooks.py | MCP direct import bridge |
| Metrics Aggregator | scripts/langgraph_engine/metrics_aggregator.py | Session/step/LLM/tool stats from logs |
| SonarQube Scanner | scripts/langgraph_engine/sonarqube_scanner.py | Legacy entry point → sonarqube/ package |
| Quality Gate | scripts/langgraph_engine/quality_gate.py | 4-gate merge enforcement |
| Test Generator | scripts/langgraph_engine/test_generator.py | Template-based unit tests (4 languages) |
| Jira Workflow | scripts/langgraph_engine/level3_steps8to12_jira.py | Dual GitHub+Jira integration (Steps 8/9/11/12) |
| Figma Workflow | scripts/langgraph_engine/level3_figma_workflow.py | Design-to-code (components, tokens, review) |
| Health Server | scripts/health_server.py | Stdlib HTTP: GET /health + GET /readiness (daemon thread) |
| DB Migrate | scripts/db_migrate.py | Idempotent Qdrant collection bootstrap + index creation |
| Secrets Manager | scripts/langgraph_engine/secrets_manager.py | Startup secrets validation + AWS SM integration + rotation hints |
| Audit Logger | scripts/langgraph_engine/audit_logger.py | Append-only JSON audit log, daily rotation, credential redaction |
| Metrics Exporter | scripts/langgraph_engine/metrics_exporter.py | Prometheus: 9 metrics, start_metrics_server(port) |
| Structured Logger | scripts/langgraph_engine/core/structured_logger.py | JSON log sink (LOG_FORMAT=json), ContextVar session/step injection |
| Tracing | scripts/langgraph_engine/tracing.py | OpenTelemetry OTLP/console, create_span() context manager |
| Error Tracking | scripts/langgraph_engine/error_tracking.py | Sentry capture_exception(), no-op without SENTRY_DSN |
| Cache Invalidation | scripts/langgraph_engine/cache_invalidation.py | Qdrant cache purge by session/project/step/age; CLI |
| Rate Limiter | src/mcp/rate_limiter.py | TokenBucket per client, 100/min tools, 10/min LLM |
| Input Validator | src/mcp/input_validator.py | Null-byte strip, length limit, prompt injection detection |
| Secrets Scanner | scripts/secrets_check.py | CI gate: 6 regex patterns, exit 1 on finding |
| Pin Requirements | scripts/pin_requirements.py | Generates requirements.pinned.txt + requirements.bounds.txt |

### MCP Servers (20 servers, 328 tools)

All registered in `~/.claude/settings.json`. Version synced via `scripts/sync-version.py`.

| Server | File | Tools | Purpose |
|--------|------|-------|---------|
| git-ops | git_mcp_server.py | 14 | Git (branch, commit, push, pull, stash, diff, fetch, post-merge cleanup) |
| github-api | github_mcp_server.py | 12 | GitHub (PR, issue, merge, label, build validate, full merge cycle) |
| session-mgr | session_mcp_server.py | 14 | Session (create, chain, tag, accumulate, finalize, work items, search) |
| policy-enforcement | enforcement_mcp_server.py | 11 | Policy compliance, flow-trace, module health, system health |
| llm-provider | llm_mcp_server.py | 8 | LLM (4 providers, hybrid GPU-first, async health, cached) |
| token-optimizer | token_optimization_mcp_server.py | 10 | Token reduction (AST nav, smart read, dedup, 60-85% savings) |
| pre-tool-gate | pre_tool_gate_mcp_server.py | 8 | Pre-tool validation (8 policy checks, skill hints) |
| post-tool-tracker | post_tool_tracker_mcp_server.py | 6 | Post-tool tracking (progress, commit readiness, stats) |
| standards-loader | standards_loader_mcp_server.py | 7 | Standards (project detect, framework detect, hot-reload) |
| skill-manager | skill_manager_mcp_server.py | 8 | Skill lifecycle (load, search, validate, rank, conflicts) |
| vector-db | vector_db_mcp_server.py | 11 | Vector RAG (Qdrant, 4 collections, semantic search, bulk index, node decisions) |
| uml-diagram | uml_diagram_mcp_server.py | 15 | UML generation (13 diagram types, CallGraph + AST + LLM, Mermaid/PlantUML, Kroki.io) |
| drawio-diagram | drawio_mcp_server.py | 5 | Draw.io editable diagrams (12 types, .drawio files, shareable URLs, no API needed) |
| jira-api | jira_mcp_server.py | 10 | Jira (create/search/transition issues, link PRs, Cloud+Server, ADF+plain text) |
| jenkins-api | jenkins_mcp_server.py | 10 | Jenkins CI/CD (trigger/abort builds, console output, queue, build polling) |
| figma-api | figma_mcp_server.py | 10 | Figma (file info, components, design tokens, styles, design review) |

### RAG Integration

Every LangGraph node stores its decision in Vector DB (`node_decisions` collection).
Before LLM calls, the pipeline checks RAG for similar past decisions.
If confidence >= step-specific threshold, RAG result replaces LLM call (saving inference time).

Key module: `scripts/langgraph_engine/rag_integration.py`
Collections: `node_decisions`, `sessions`, `flow_traces`, `tool_calls`
Default threshold: 0.82 (step-specific: 0.75-0.90)

**Orchestration-level RAG (v1.6.0 NEW):**
`rag_lookup_orchestration()` / `rag_store_orchestration()` operate at the plan level
(step="orchestration_plan", threshold=0.85). On hit, the full orchestration plan
(agent roster, task type, complexity, skill selection) is reused from cache,
bypassing Steps 0-4 entirely and saving ~5 LLM calls per session.

**RAG Cross-Project Guard (v1.6.1 NEW):**
Every payload stored in `node_decisions` includes a `codebase_hash` — a 12-char SHA1
fingerprint of the sorted list of top-level Python module file names.  During lookup,
if the query hash differs from the stored hash, the similarity score is penalised ×0.65,
effectively blocking false positives where two identically-worded tasks from different
projects (e.g. "Add login to dashboard" in Project A vs Project B) would otherwise match
at 0.95+ and inject the wrong blueprint.  Empty hashes (unavailable codebase) are treated
as unknown and incur no penalty.

### CallGraph-Driven Pipeline Intelligence

The pipeline uses a full AST-based call graph (578 classes, 3,985 methods) to make
informed decisions at critical steps instead of blind code generation.
CallGraph now supports 4 languages: Python (full AST), Java, TypeScript, Kotlin (regex-based).

```
Step 2 (Plan):   analyze_impact_before_change() -> risk_level, danger_zones, affected_methods
                 Planner knows what could break BEFORE suggesting changes

Step 10 (Impl):  snapshot_call_graph() + get_implementation_context()
                 Captures pre-change state + injects caller/callee awareness

Step 11 (Review): review_change_impact() -> compare before/after graphs
                 Detects breaking changes, orphaned methods, risk assessment
```

Key module: `scripts/langgraph_engine/call_graph_analyzer.py`
Data source: `scripts/langgraph_engine/call_graph_builder.py`
State fields: `step2_impact_analysis`, `step10_pre_change_graph`, `step11_impact_review`

**Stale Graph Guard (v1.6.1 NEW):**
After Step 10 writes files, state flag `call_graph_stale = True` is set.
`refresh_call_graph_if_stale(state, project_root)` (in `call_graph_analyzer.py`) checks
this flag and silently rebuilds the graph when stale rather than returning a pre-implementation
cached snapshot.  This prevents multi-phase implementations from using a Phase-0 graph for
Phase-C decisions after Phase-B has already modified files.  The function falls back through
priority order: fresh scan (if stale) → step10_pre_change_graph → step2_impact_analysis →
pre_analysis_result → fresh scan (nothing cached).

UML diagrams (13 types) also consume CallGraph as single data source via adapters
in `uml_generators.py`, replacing duplicate AST analysis.

### Execution Modes

```
Hook Mode (default, CLAUDE_HOOK_MODE=1):
  Steps 0-9   -> Pipeline (analysis + prompt + GitHub issue + branch)
  Steps 10-14 -> Skipped (user implements, then runs Full Mode for PR/closure)

Full Mode (CLAUDE_HOOK_MODE=0):
  Steps 0-14  -> All steps execute sequentially
```

### Integration Flags

All integrations are configurable via environment variables (default: disabled):

| Flag | Default | Effect |
|------|---------|--------|
| `ENABLE_JIRA` | `0` | Dual GitHub+Jira issue tracking (Steps 8,9,11,12) |
| `ENABLE_JENKINS` | `0` | Jenkins build validation (Step 11) |
| `ENABLE_SONARQUBE` | `0` | SonarQube scan after implementation (Step 10) |
| `ENABLE_FIGMA` | `0` | Figma design-to-code extraction (Steps 3,7,11) |
| `ENABLE_CI` | `false` | GitHub Actions CI pipeline |
| `ENABLE_HEALTH_SERVER` | `0` | Start HTTP /health + /readiness on HEALTH_PORT (8080) |
| `ENABLE_METRICS` | `0` | Start Prometheus /metrics server on METRICS_PORT (9090) |
| `ENABLE_TRACING` | `0` | Enable OpenTelemetry tracing (OTLP to OTEL_EXPORTER_OTLP_ENDPOINT) |
| `ENABLE_RATE_LIMITING` | `0` | Token bucket rate limiting on MCP tool endpoints |
| `LOG_FORMAT` | `""` | Set to `json` for structured JSON logging (container log aggregation) |
| `AUTO_CACHE_CLEANUP` | `0` | Auto-invalidate RAG entries older than 30 days at startup |
| `FORCE_GRAPH_REBUILD` | `0` | Force call graph rebuild even if stale flag is False |

### Integration Lifecycle (Create -> Update -> Close)

When integrations are enabled, the pipeline manages the full lifecycle:

```
Jira Lifecycle (ENABLE_JIRA=1):
  Step 8:  CREATE   -> Jira issue created, cross-linked to GitHub Issue
  Step 9:  BRANCH   -> Branch named from Jira key (feature/proj-123)
  Step 10: UPDATE   -> Transition to "In Progress", add start comment
  Step 11: LINK     -> PR remote-linked to Jira, transition to "In Review"
  Step 11: MERGE    -> Post-merge comment with PR number and branch
  Step 12: CLOSE    -> Transition to "Done", add implementation summary

Figma Lifecycle (ENABLE_FIGMA=1):
  Step 3:  EXTRACT  -> Components extracted for UI task breakdown
  Step 7:  INJECT   -> Design tokens (colors, typography, spacing) into prompt
  Step 10: COMMENT  -> "Implementation started" with component list
  Step 11: REVIEW   -> Design fidelity checklist in code review
  Step 12: COMMENT  -> "Implementation complete" with PR link
```

---

## Development Guidelines

### Code Style

- **Language:** Python 3.8+
- **Encoding:** UTF-8, ASCII-only (cp1252 safe for Windows)
- **Format:** Follow PEP 8 conventions
- **Testing:** All new code requires tests
- **Paths:** Always use path_resolver.py for cross-platform paths
- **Imports:** Lazy imports to avoid import-time side effects

### Running the Pipeline

```bash
python scripts/3-level-flow.py --task "your task"
```

### Testing

```bash
# All tests
pytest tests/

# MCP server tests
pytest tests/test_*mcp*.py

# Integration tests (require live Qdrant + providers)
pytest tests/integration/ -m integration

# E2E scenario tests
pytest tests/e2e/

# Load / concurrency tests
RUN_LOAD_TESTS=1 pytest tests/load/

# Security unit tests
pytest tests/test_secrets_manager.py tests/test_audit_logger.py

# CallGraph tests
pytest tests/test_call_graph_builder.py tests/test_call_graph_analyzer.py

# RAG tests
pytest tests/test_rag_integration.py

# With coverage report
pytest tests/ --cov=scripts/langgraph_engine --cov-report=html:docs/coverage
```

### First-Time Setup

```bash
# Bootstrap Qdrant collections (idempotent)
python scripts/db_migrate.py

# Scan for hardcoded secrets (CI gate)
python scripts/secrets_check.py

# Pin all transitive dependencies
python scripts/pin_requirements.py
```

### Production Run

```bash
# With health server + Prometheus metrics + JSON logs
ENABLE_HEALTH_SERVER=1 ENABLE_METRICS=1 LOG_FORMAT=json \
  python scripts/3-level-flow.py --message "your task"

# Kubernetes
kubectl apply -f k8s/secret.yaml -f k8s/configmap.yaml \
  -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml
```

---

## Naming Conventions

- Files: snake_case.py
- Classes: PascalCase
- Functions/Methods: snake_case
- Constants: UPPER_SNAKE_CASE

---

## Configuration

See environment variables in `.env.example`:
- `OLLAMA_ENDPOINT` - Ollama server URL
- `ANTHROPIC_API_KEY` - Claude API key
- `GITHUB_TOKEN` - GitHub personal access token
- `CLAUDE_DEBUG` - Debug mode (0/1)
- `CLAUDE_HOOK_MODE` - Hook mode (1) or Full mode (0)

---

**Last Updated:** 2026-03-28


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: v1.8.0 — Orchestration Template Fast-Path: `--orchestration-template` flag skips Steps 0-5, routes to Step 6, reduces pipeline from 7-8 LLM calls to 1 call (87% reduction, ~15s hook mode)
- **Skill**: python-core
- **Agent**: python-backend-engineer
- **Date**: 2026-03-28

## Dependency Notes

- `TTS>=0.22.0` (Coqui TTS) moved to `requirements-optional.txt` — conflicts with `networkx>=3.1` via `gruut==2.2.3` transitive dep.
- Install voice notifications separately: `pip install -r requirements-optional.txt`
- CI auto-trigger disabled — workflow runs on `workflow_dispatch` only (manual trigger via GitHub Actions UI).
