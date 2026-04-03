# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 1.11.0
**Type:** LangGraph Orchestration Pipeline with RAG + Call Graph Intelligence + Template Fast-Path
**Last Updated:** 2026-04-03

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
| **MCP Servers** | 20 servers (328 tools) -- all in separate repos under [techdeveloper-org](https://github.com/orgs/techdeveloper-org/repositories); 2 also keep in-engine copies in `src/mcp/` |
| **Total Python Files** | 310+ |
| **Test Files** | 75 |
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
|   +-- langgraph_engine/             # Core orchestration engine
|   |   +-- core/                     # Cross-cutting abstractions (LazyLoader, ErrorHandler, NodeResult, etc.)
|   |   +-- state/                    # FlowState split into 6 focused modules
|   |   +-- routing/                  # All routing functions split by level
|   |   +-- helper_nodes/             # Helper node functions split by concern
|   |   +-- diagrams/                 # Strategy Pattern: 13 swappable UML generators
|   |   +-- parsers/                  # Abstract Factory: 4 language parsers (Py/Java/TS/Kotlin)
|   |   +-- integrations/             # Abstract Factory + Lifecycle: GitHub/Jira/Figma/Jenkins
|   |   +-- pipeline_builder.py       # Builder Pattern: PipelineBuilder chainable API
|   |   +-- level_minus1/            # [v1.9] Level -1 Auto-Fix package (nodes, merge, recovery, policies/)
|   |   +-- level1_sync/             # [v1.11] Level 1 Sync package (9 modules + policies/ + architecture/)
|   |   +-- level2_standards/        # [v1.11] Level 2 Standards package (7 modules + policies/ + architecture/)
|   |   +-- level3_execution/        # [v1.11] Level 3 Execution package (20+ modules + nodes/ + subgraph.py + sonarqube/ + policies/ + architecture/)
|   |   +-- [60+ shared modules]     # Cross-level: LLM, caching, metrics, git, state, etc.
|   +-- architecture/                 # generate_system_diagram.py (shared utility)
+-- policies/                         # README pointing to level packages (policies moved into level_*/policies/)
|   +-- testing/                      # Testing policies (unchanged)
+-- src/mcp/                          # In-engine copies of session-mgr + vector-db (repos are source of truth) + bridge (session_hooks, base/)
+-- tests/                            # 75 test files
+-- docs/                             # 47 documentation files
+-- docs/uml/                         # Auto-generated UML diagrams (13 types)
+-- rules/                            # 34 coding standard definitions (incl. doc governance + docstrings-only + microservices patterns)
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Orchestrator | scripts/langgraph_engine/orchestrator.py | Main StateGraph pipeline |
| Flow State | scripts/langgraph_engine/flow_state.py | Backward-compat shim -> re-exports from state/ |
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
| Level -1 | scripts/langgraph_engine/level_minus1/ | Auto-fix enforcement (canonical) |
| Level 1 | scripts/langgraph_engine/level1_sync/ | Session/context sync + TOON (canonical). Outputs: `complexity_score` [1-10] (simple heuristic), `combined_complexity_score` [1-25] (simple x 0.3 + graph x 0.7 after linear scaling). **Note: `combined_complexity_score` is on a 1-25 scale -- do NOT treat it as 1-10.** |
| Level 2 | scripts/langgraph_engine/level2_standards/ | Standards loading (canonical) |
| Level 3 | scripts/langgraph_engine/level3_execution/subgraph.py | 15-step execution with RAG - ACTIVE (nodes in level3_execution/nodes/) |
| Level 3 v1 steps | scripts/langgraph_engine/level3_execution/steps/ | v1 steps (DEPRECATED) |
| Pre-Analysis Node | scripts/langgraph_engine/level3_execution/subgraph.py | orchestration_pre_analysis_node: CallGraph scan + RAG lookup before Step 0 |
| Hooks | scripts/pre-tool-enforcer.py, post-tool-tracker.py | Tool enforcement |
| Call Graph Builder | scripts/langgraph_engine/call_graph_builder.py | AST-based FQN call stack (compat shim -> parsers/) |
| Call Graph Analyzer | scripts/langgraph_engine/call_graph_analyzer.py | Pipeline impact analysis (Steps 2/10/11) |
| UML Generators | scripts/langgraph_engine/uml_generators.py | Compat shim -> diagrams/DiagramFactory |
| Doc Manager | scripts/langgraph_engine/level3_execution/documentation_manager.py | Circular SDLC doc cycle (Step 0/13) |
| Session Bridge | src/mcp/session_hooks.py | MCP direct import bridge |
| Metrics Aggregator | scripts/langgraph_engine/metrics_aggregator.py | Session/step/LLM/tool stats from logs |
| SonarQube Scanner | scripts/langgraph_engine/sonarqube_scanner.py | Legacy entry point -> sonarqube/ package |
| Quality Gate | scripts/langgraph_engine/quality_gate.py | 4-gate merge enforcement |
| Test Generator | scripts/langgraph_engine/test_generator.py | Template-based unit tests (4 languages) |
| Jira Workflow | scripts/langgraph_engine/level3_execution/steps8to12_jira.py | Dual GitHub+Jira integration (Steps 8/9/11/12) |
| Figma Workflow | scripts/langgraph_engine/level3_execution/figma_workflow.py | Design-to-code (components, tokens, review) |
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

### MCP Servers (20 servers, 328 tools) -- All Extracted to Separate Repos

All 20 MCP servers have been extracted to individual private repos under
[`techdeveloper-org`](https://github.com/orgs/techdeveloper-org/repositories)
for independent versioning, testing, and reuse. Each is registered in `~/.claude/settings.json`
and points to `mcp-{name}/server.py` in the local workspace.

> **Note:** `session-mgr` and `vector-db` also keep in-engine copies in `src/mcp/` because
> they are imported in-process by `session_hooks.py` and `rag_integration.py` respectively.
> The separate repos are the source of truth; in-engine copies are kept for tight coupling needs.

#### All 20 MCP Server Repos

| # | Server | Repo | Tools | Purpose |
|---|--------|------|-------|---------|
| 1 | session-mgr | [mcp-session-mgr](https://github.com/techdeveloper-org/mcp-session-mgr) | 14 | Session lifecycle (also in-engine: `src/mcp/session_mcp_server.py`) |
| 2 | vector-db | [mcp-vector-db](https://github.com/techdeveloper-org/mcp-vector-db) | 11 | Qdrant RAG (also in-engine: `src/mcp/vector_db_mcp_server.py`) |
| 3 | git-ops | [mcp-git-ops](https://github.com/techdeveloper-org/mcp-git-ops) | 14 | Git (branch, commit, push, pull, stash, diff, fetch, post-merge cleanup) |
| 4 | github-api | [mcp-github-api](https://github.com/techdeveloper-org/mcp-github-api) | 12 | GitHub (PR, issue, merge, label, build validate, full merge cycle) |
| 5 | policy-enforcement | [mcp-policy-enforcement](https://github.com/techdeveloper-org/mcp-policy-enforcement) | 11 | Policy compliance, flow-trace, module health, system health |
| 6 | llm-provider | [mcp-llm-provider](https://github.com/techdeveloper-org/mcp-llm-provider) | 8 | LLM (4 providers, hybrid GPU-first, async health, cached) |
| 7 | llm-router | [mcp-llm-router](https://github.com/techdeveloper-org/mcp-llm-router) | 4 | Intelligent LLM routing, step classification, model selection |
| 8 | ollama-provider | [mcp-ollama-provider](https://github.com/techdeveloper-org/mcp-ollama-provider) | 5 | Local Ollama GPU inference, model discovery, pull |
| 9 | anthropic-provider | [mcp-anthropic-provider](https://github.com/techdeveloper-org/mcp-anthropic-provider) | 4 | Direct Anthropic Claude API, cost estimation |
| 10 | openai-provider | [mcp-openai-provider](https://github.com/techdeveloper-org/mcp-openai-provider) | 4 | Direct OpenAI GPT API, cost estimation |
| 11 | token-optimizer | [mcp-token-optimizer](https://github.com/techdeveloper-org/mcp-token-optimizer) | 10 | Token reduction (AST navigation, smart read, dedup, 60-85% savings) |
| 12 | pre-tool-gate | [mcp-pre-tool-gate](https://github.com/techdeveloper-org/mcp-pre-tool-gate) | 8 | Pre-tool validation (8 policy checks, skill hints) |
| 13 | post-tool-tracker | [mcp-post-tool-tracker](https://github.com/techdeveloper-org/mcp-post-tool-tracker) | 6 | Post-tool tracking (progress, commit readiness, stats) |
| 14 | standards-loader | [mcp-standards-loader](https://github.com/techdeveloper-org/mcp-standards-loader) | 7 | Standards (project detect, framework detect, hot-reload) |
| 15 | skill-manager | [mcp-skill-manager](https://github.com/techdeveloper-org/mcp-skill-manager) | 8 | Skill lifecycle (load, search, validate, rank, conflicts) |
| 16 | uml-diagram | [mcp-uml-diagram](https://github.com/techdeveloper-org/mcp-uml-diagram) | 15 | UML generation (13 diagram types, CallGraph + AST + LLM, Mermaid/PlantUML, Kroki.io) |
| 17 | drawio-diagram | [mcp-drawio-diagram](https://github.com/techdeveloper-org/mcp-drawio-diagram) | 5 | Draw.io editable diagrams (12 types, .drawio files, shareable URLs, no API needed) |
| 18 | jira-api | [mcp-jira-api](https://github.com/techdeveloper-org/mcp-jira-api) | 10 | Jira (create/search/transition issues, link PRs, Cloud+Server, ADF+plain text) |
| 19 | jenkins-ci | [mcp-jenkins-ci](https://github.com/techdeveloper-org/mcp-jenkins-ci) | 10 | Jenkins CI/CD (trigger/abort builds, console output, queue, build polling) |
| 20 | figma-api | [mcp-figma](https://github.com/techdeveloper-org/mcp-figma) | 10 | Figma (file info, components, design tokens, styles, design review) |

#### Shared Base Package

| Repo | Purpose |
|------|---------|
| [mcp-base](https://github.com/techdeveloper-org/mcp-base) | Shared base package: MCPResponse builder, @mcp_tool_handler decorator, AtomicJsonStore, LazyClient. Each server repo includes a copy as `base/`. |

> **Total:** 20 server repos + 1 shared base = [21 repos](https://github.com/orgs/techdeveloper-org/repositories) under `techdeveloper-org`

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
Every payload stored in `node_decisions` includes a `codebase_hash` -- a 12-char SHA1
fingerprint of the sorted list of top-level Python module file names.  During lookup,
if the query hash differs from the stored hash, the similarity score is penalised x0.65,
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
priority order: fresh scan (if stale) -> step10_pre_change_graph -> step2_impact_analysis ->
pre_analysis_result -> fresh scan (nothing cached).

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

**Last Updated:** 2026-04-03


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: v1.12.0 -- Surgical shim cleanup: delete subgraphs/ shim layer, rename v2_nodes/ -> nodes/ and execution_v2.py -> subgraph.py, delete 8 root-level level3_*.py shims, redirect orchestrator.py + pipeline_builder.py to canonical imports. Zero functional change.
- **Skill**: python-core
- **Agent**: python-backend-engineer
- **Date**: 2026-04-03

## Dependency Notes

- `TTS>=0.22.0` (Coqui TTS) moved to `requirements-optional.txt` -- conflicts with `networkx>=3.1` via `gruut==2.2.3` transitive dep.
- Install voice notifications separately: `pip install -r requirements-optional.txt`
- CI auto-trigger disabled -- workflow runs on `workflow_dispatch` only (manual trigger via GitHub Actions UI).
