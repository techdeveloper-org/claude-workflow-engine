# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 1.16.1
**Type:** LangGraph Orchestration Pipeline with Call Graph Intelligence + Template Fast-Path
**Last Updated:** 2026-04-07

---

## Project Overview

Claude Workflow Engine is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It handles session sync, coding standards enforcement, and end-to-end 8-step active execution (Pre-0, Step 0, Steps 8-14) with GitHub integration and hybrid LLM inference across 2 providers (claude_cli, anthropic).

### Quick Info

| Property | Value |
|----------|-------|
| **Languages** | Python |
| **Frameworks** | LangGraph 0.2.0+, LangChain, FastMCP (mcp package) |
| **Status** | Active Development |
| **Primary Location** | langgraph_engine/ |
| **MCP Servers** | 13 servers -- all in separate repos under [techdeveloper-org](https://github.com/orgs/techdeveloper-org/repositories); 1 also keeps an in-engine copy in `src/mcp/` |
| **Total Python Files** | 304+ |
| **Test Files** | 74 |
| **Call Graph** | 578 classes, 3,985 methods, 4 languages (Python/Java/TS/Kotlin) |

---

## Architecture & Structure

### Pipeline Flow

```
Level -1: Auto-Fix (3 checks: Unicode, encoding, paths)
    |
Level 1: Sync (session + parallel [complexity, context] -> merge)
    |     Outputs: combined_complexity_score [1-25] (simple x 0.3 + graph x 0.7)
    |     NOTE: combined_complexity_score is on a 1-25 scale -- do NOT treat as 1-10
    |
Level 2: (NO-OP -- rules loaded directly from policies/ on disk; no pipeline nodes)
    |
Level 3: Execution (8 active steps: Pre-0, Step 0, Steps 8-14)
    |
    |-- Pre-0: Orchestration Pre-Analysis
    |           CallGraph scan -> hot_nodes, danger_zones, complexity_boost -> state
    |           Template fast-path detected? -> skip Step 0, jump to Step 8
    |           Normal path -> continue to Step 0 with call graph data already in state
    |
    |-- Step 0: Task Analysis v2 -- PromptGen + Orchestrator        [v1.14.0]
    |   |
    |   |  WHAT CHANGED (v1.12 -> v1.13 -> v1.14):
    |   |  v1.12: Steps 0-7 = 6 separate LLM calls (~75s planning)
    |   |         Step 0: task analysis
    |   |         Step 1: plan mode decision        [REMOVED in v1.13]
    |   |         Step 3: task/phase breakdown      [REMOVED in v1.13]
    |   |         Step 4: TOON refinement           [REMOVED in v1.13]
    |   |         Step 5: skill & agent selection   [REMOVED in v1.13]
    |   |         Step 6: skill validation          [REMOVED in v1.13]
    |   |         Step 7: final prompt generation   [REMOVED in v1.13]
    |   |  v1.13: Step 0 = 2 subprocess calls (~30s planning)
    |   |  v1.14: Step 0 = 2 subprocess calls (claude CLI, ~15s planning)  <-- CURRENT
    |   |
    |   |-- Call 1: prompt_gen_expert_caller  (~10s, stdout captured)
    |   |     Reads: level3_execution/templates/orchestration_system_prompt.txt
    |   |     Injects into template:
    |   |       {user_requirements}          <- state["task_description"]
    |   |       {runtime_context_json_block} <- call graph + complexity (from Pre-0 + Level 1)
    |   |       {complexity_score_display}   <- state["combined_complexity_score"] (1-25)
    |   |       {codebase_risk_level}        <- call_graph_metrics["risk_level"]
    |   |       {codebase_danger_zones}      <- call_graph_metrics["danger_zones"][:3]
    |   |       {codebase_affected_methods}  <- call_graph_metrics["affected_methods"]
    |   |       {codebase_hot_nodes}         <- call_graph_metrics["hot_nodes"][:5]
    |   |     claude CLI generates: complete orchestration prompt (agents, phases, contracts)
    |   |     Stores: state["orchestration_prompt"]
    |   |
    |   |-- Call 2: orchestrator_agent_caller  (~30-90s, stderr streamed live)
    |         Reads: state["orchestration_prompt"] via temp file
    |         Executes: full plan (solution-architect -> consensus -> agents -> QA)
    |         User sees in terminal (real-time, flush=True):
    |           [ORCHESTRATOR] Reading orchestration prompt...
    |           [ORCHESTRATOR] Executing plan...
    |           [ORCHESTRATOR] Done.
    |         Stores: state["orchestrator_result"]
    |         Env vars: STEP0_PROMPT_GEN_TIMEOUT (default 60s)
    |                   STEP0_ORCHESTRATOR_TIMEOUT (default 300s)
    |
    |-- Step 8:  GitHub Issue + Jira Issue creation (ENABLE_JIRA, dual-linked)
    |-- Step 9:  Branch Creation (Jira key: feature/PROJ-123)
    |-- Step 10: Implementation + Jira "In Progress" + Figma "started" comment
    |-- Step 11: PR + Code Review + Jira PR link + Figma design review
    |-- Step 12: Issue Closure (GitHub + Jira "Done" + Figma "complete" comment)
    |-- Step 13: Documentation Update + UML Diagram Generation
    |-- Step 14: Final Summary
```

### Planning Phase Evolution

| Version | Active Steps | Planning LLM Calls | Planning Time | Key Change |
|---------|-------------|-------------------|---------------|------------|
| v1.12.0 | 15 | ~6 | ~75s | Original -- Steps 0-7 each called LLM separately |
| v1.13.0 | 9 | ~2 (subprocess) | ~30s | Removed Steps 1,3,4,5,6,7 |
| **v1.14.0** | **8** | **2 (subprocess)** | **~15s** | Step 0 = template fill + orchestrator (claude CLI subprocess) |
| **v1.15.0** | **8** | **2 (subprocess)** | **~15s** | TOON compression removed from Level 1 |
| **v1.15.1** | **8** | **2 (subprocess)** | **~15s** | Source cleanup: deprecated files removed |
| **v1.15.2** | **8** | **2 (subprocess)** | **~15s** | Exhaustive artifact purge: TOON/plan-mode/skill-selection removed; prompt_gen bug fixes |
| **v1.15.3** | **8** | **2 (subprocess)** | **~15s** | Dead LLM provider purge: Ollama, NPU, GPU, OpenAI, DeepSeek, inference_router removed; 2-provider chain only (claude_cli + anthropic) |
| **v1.16.0** | **8** | **2 (subprocess)** | **~15s** | Level 2 script purge: all level2_standards/ Python removed; level1_cleanup routes directly to level3_init; policies/ .md files retained |
| **v1.16.1** | **8** | **2 (subprocess)** | **~15s** | uml/ + drawio/ moved to project root (out of docs/); UML_OUTPUT_DIR + DRAWIO_OUTPUT_DIR env vars |

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
|   |   +-- level1_sync/             # [v1.11] Level 1 Sync package (10 modules + policies/ + architecture/)
|   |   +-- level2_standards/        # Level 2 Standards package -- policies/ only (all Python scripts removed v1.16.0)
|   |   +-- level2_standards/policies/    # Coding standards policy files (.md) -- read directly at runtime
|   |   +-- level3_execution/        # [v1.11] Level 3 Execution package (20+ modules + nodes/ + subgraph.py + sonarqube/ + policies/ + architecture/)
|   |   +-- [60+ shared modules]     # Cross-level: LLM, caching, metrics, git, state, etc.
|   +-- architecture/                 # generate_system_diagram.py (shared utility)
|   +-- setup/                        # One-time environment setup (install-auto-hooks.sh, setup-global-claude.sh/.ps1, setup_wizard.py, etc.)
|   +-- bin/                          # Windows .bat operational launchers (start/stop claude-insight, sync-insight, sync-library)
|   +-- tools/                        # Developer utilities: release.py, sync-version.py, metrics-emitter.py, voice-notifier.py, session-start.sh, etc.
|   +-- pre_tool_enforcer/            # PreToolUse hook package (canonical)
|   +-- post_tool_tracker/            # PostToolUse hook package (canonical)
|   +-- stop_notifier/                # Stop hook package (canonical)
|   +-- github_operations/            # GitHub helper operations
|   +-- github_pr_workflow/           # PR workflow package (canonical)
|   +-- helpers/                      # Shared helper utilities
|   +-- 3-level-flow.py               # Main pipeline entry point
|   +-- pre-tool-enforcer.py          # PreToolUse hook entry point (shim -> pre_tool_enforcer/)
|   +-- post-tool-tracker.py          # PostToolUse hook entry point (shim -> post_tool_tracker/)
|   +-- stop-notifier.py              # Stop hook entry point (shim -> stop_notifier/)
|   +-- ide_paths.py                  # Path constants (imported by hook packages)
|   +-- project_session.py            # Session utilities (imported by hook packages)
|   +-- policy_tracking_helper.py     # Policy tracking (imported by hook packages)
+-- policies/                         # README pointing to level packages (policies moved into level_*/policies/)
|   +-- testing/                      # Testing policies (unchanged)
+-- src/mcp/                          # In-engine copy of session-mgr (repo is source of truth) + bridge (session_hooks, base/)
+-- tests/                            # 75 test files
+-- docs/                             # 69 documentation files
+-- uml/                              # Auto-generated UML diagrams (13 types)
+-- drawio/                           # Auto-generated draw.io diagrams (13 types)
+-- rules/                            # 34 coding standard definitions (incl. doc governance + docstrings-only + microservices patterns)
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Orchestrator | langgraph_engine/orchestrator.py | Main StateGraph pipeline |
| Flow State | langgraph_engine/flow_state.py | Backward-compat shim -> re-exports from state/ |
| State Package | langgraph_engine/state/ | FlowState, StepKeys, reducers, WorkflowContextOptimizer |
| Core Package | langgraph_engine/core/ | LazyLoader, get_logger, node_error_handler, NodeResult, create_step_node |
| Routing Package | langgraph_engine/routing/ | All routing functions split by level |
| Helper Nodes | langgraph_engine/helper_nodes/ | Helper node functions split by concern |
| Pipeline Builder | langgraph_engine/pipeline_builder.py | Builder Pattern: chainable add_level*().build() |
| Diagrams Package | langgraph_engine/diagrams/ | Strategy Pattern: DiagramFactory + 13 generators |
| Parsers Package | langgraph_engine/parsers/ | Abstract Factory: ParserRegistry + 4 language parsers |
| SonarQube Package | langgraph_engine/level3_execution/sonarqube/ | Facade: api_client, lightweight, aggregator, auto_fixer |
| Integrations Package | langgraph_engine/integrations/ | Abstract Factory + Lifecycle: GitHub/Jira/Figma/Jenkins |
| Level -1 | langgraph_engine/level_minus1/ | Auto-fix enforcement (canonical) |
| Level 1 | langgraph_engine/level1_sync/ | Session/context sync (canonical). Outputs: `complexity_score` [1-10] (simple heuristic), `combined_complexity_score` [1-25] (simple x 0.3 + graph x 0.7 after linear scaling). **Note: `combined_complexity_score` is on a 1-25 scale -- do NOT treat it as 1-10.** |
| Level 2 | langgraph_engine/level2_standards/ | Standards loading (canonical) |
| Level 3 | langgraph_engine/level3_execution/subgraph.py | 8-step active execution (Pre-0, Step 0, Steps 8-14) -- ACTIVE (nodes in level3_execution/nodes/) |
| Pre-Analysis Node | langgraph_engine/level3_execution/subgraph.py | orchestration_pre_analysis_node: CallGraph scan before Step 0; template fast-path detection |
| Hooks | scripts/pre-tool-enforcer.py, post-tool-tracker.py | Tool enforcement |
| Call Graph Builder | langgraph_engine/call_graph_builder.py | AST-based FQN call stack (compat shim -> parsers/) |
| Call Graph Analyzer | langgraph_engine/call_graph_analyzer.py | Pipeline impact analysis (Steps 2/10/11) |
| UML Generators | langgraph_engine/uml_generators.py | Compat shim -> diagrams/DiagramFactory |
| Doc Manager | langgraph_engine/level3_execution/documentation_manager.py | Circular SDLC doc cycle (Step 0/13) |
| Session Bridge | src/mcp/session_hooks.py | MCP direct import bridge |
| Metrics Aggregator | langgraph_engine/metrics_aggregator.py | Session/step/LLM/tool stats from logs |
| SonarQube Scanner | langgraph_engine/sonarqube_scanner.py | Legacy entry point -> sonarqube/ package |
| Quality Gate | langgraph_engine/quality_gate.py | 4-gate merge enforcement |
| Test Generator | langgraph_engine/test_generator.py | Template-based unit tests (4 languages) |
| Jira Workflow | langgraph_engine/level3_execution/steps8to12_jira.py | Dual GitHub+Jira integration (Steps 8/9/11/12) |
| Figma Workflow | langgraph_engine/level3_execution/figma_workflow.py | Design-to-code (components, tokens, review) |
| Health Server | scripts/health_server.py | Stdlib HTTP: GET /health + GET /readiness (daemon thread) |
| Secrets Manager | langgraph_engine/secrets_manager.py | Startup secrets validation + AWS SM integration + rotation hints |
| Audit Logger | langgraph_engine/audit_logger.py | Append-only JSON audit log, daily rotation, credential redaction |
| Metrics Exporter | langgraph_engine/metrics_exporter.py | Prometheus: 9 metrics, start_metrics_server(port) |
| Structured Logger | langgraph_engine/core/structured_logger.py | JSON log sink (LOG_FORMAT=json), ContextVar session/step injection |
| Tracing | langgraph_engine/tracing.py | OpenTelemetry OTLP/console, create_span() context manager |
| Error Tracking | langgraph_engine/error_tracking.py | Sentry capture_exception(), no-op without SENTRY_DSN |
| Rate Limiter | src/mcp/rate_limiter.py | TokenBucket per client, 100/min tools, 10/min LLM |
| Input Validator | src/mcp/input_validator.py | Null-byte strip, length limit, prompt injection detection |
| Secrets Scanner | scripts/secrets_check.py | CI gate: 6 regex patterns, exit 1 on finding |
| Pin Requirements | scripts/pin_requirements.py | Generates requirements.pinned.txt + requirements.bounds.txt |
| PromptGen Caller | langgraph_engine/level3_execution/architecture/prompt_gen_expert_caller.py | Step 0 Call 1: fills orchestration template via claude CLI |
| Orchestrator Caller | langgraph_engine/level3_execution/architecture/orchestrator_agent_caller.py | Step 0 Call 2: executes orchestration plan, streams live to terminal |

### MCP Servers (13 servers, 295 tools) -- All Extracted to Separate Repos

All 13 MCP servers have been extracted to individual private repos under
[`techdeveloper-org`](https://github.com/orgs/techdeveloper-org/repositories)
for independent versioning, testing, and reuse. Each is registered in `~/.claude/settings.json`
and points to `mcp-{name}/server.py` in the local workspace.

> **Note:** `session-mgr` also keeps an in-engine copy in `src/mcp/` because
> it is imported in-process by `session_hooks.py`.
> The separate repo is the source of truth; the in-engine copy is kept for tight coupling needs.

#### All 13 MCP Server Repos

| # | Server | Repo | Tools | Purpose |
|---|--------|------|-------|---------|
| 1 | session-mgr | [mcp-session-mgr](https://github.com/techdeveloper-org/mcp-session-mgr) | 14 | Session lifecycle (also in-engine: `src/mcp/session_mcp_server.py`) |
| 2 | git-ops | [mcp-git-ops](https://github.com/techdeveloper-org/mcp-git-ops) | 14 | Git (branch, commit, push, pull, stash, diff, fetch, post-merge cleanup) |
| 3 | github-api | [mcp-github-api](https://github.com/techdeveloper-org/mcp-github-api) | 12 | GitHub (PR, issue, merge, label, build validate, full merge cycle) |
| 4 | policy-enforcement | [mcp-policy-enforcement](https://github.com/techdeveloper-org/mcp-policy-enforcement) | 11 | Policy compliance, flow-trace, module health, system health |
| 5 | token-optimizer | [mcp-token-optimizer](https://github.com/techdeveloper-org/mcp-token-optimizer) | 10 | Token reduction (AST navigation, smart read, dedup, 60-85% savings) |
| 6 | pre-tool-gate | [mcp-pre-tool-gate](https://github.com/techdeveloper-org/mcp-pre-tool-gate) | 13 | Pre-tool validation (8 policy checks, skill hints) |
| 7 | post-tool-tracker | [mcp-post-tool-tracker](https://github.com/techdeveloper-org/mcp-post-tool-tracker) | 6 | Post-tool tracking (progress, commit readiness, stats) |
| 8 | standards-loader | [mcp-standards-loader](https://github.com/techdeveloper-org/mcp-standards-loader) | 7 | Standards (project detect, framework detect, hot-reload) |
| 9 | uml-diagram | [mcp-uml-diagram](https://github.com/techdeveloper-org/mcp-uml-diagram) | 15 | UML generation (13 diagram types, CallGraph + AST + LLM, Mermaid/PlantUML, Kroki.io) |
| 10 | drawio-diagram | [mcp-drawio-diagram](https://github.com/techdeveloper-org/mcp-drawio-diagram) | 5 | Draw.io editable diagrams (12 types, .drawio files, shareable URLs, no API needed) |
| 11 | jira-api | [mcp-jira-api](https://github.com/techdeveloper-org/mcp-jira-api) | 10 | Jira (create/search/transition issues, link PRs, Cloud+Server, ADF+plain text) |
| 12 | jenkins-ci | [mcp-jenkins-ci](https://github.com/techdeveloper-org/mcp-jenkins-ci) | 10 | Jenkins CI/CD (trigger/abort builds, console output, queue, build polling) |
| 13 | figma-api | [mcp-figma](https://github.com/techdeveloper-org/mcp-figma) | 10 | Figma (file info, components, design tokens, styles, design review) |

#### Shared Base Package

| Repo | Purpose |
|------|---------|
| [mcp-base](https://github.com/techdeveloper-org/mcp-base) | Shared base package: MCPResponse builder, @mcp_tool_handler decorator, AtomicJsonStore, LazyClient. Each server repo includes a copy as `base/`. |

> **Total:** 13 server repos + 1 shared base = [14 repos](https://github.com/orgs/techdeveloper-org/repositories) under `techdeveloper-org`

### CallGraph-Driven Pipeline Intelligence

The pipeline uses a full AST-based call graph (578 classes, 3,985 methods) to make
informed decisions at critical steps instead of blind code generation.
CallGraph now supports 4 languages: Python (full AST), Java, TypeScript, Kotlin (regex-based).

```
Pre-0 (Pre-Analysis): analyze_impact_before_change() -> risk_level, danger_zones, affected_methods
                          Planner knows what could break BEFORE suggesting changes

Step 10 (Impl):  snapshot_call_graph() + get_implementation_context()
                 Captures pre-change state + injects caller/callee awareness

Step 11 (Review): review_change_impact() -> compare before/after graphs
                 Detects breaking changes, orphaned methods, risk assessment
```

Key module: `langgraph_engine/call_graph_analyzer.py`
Data source: `langgraph_engine/call_graph_builder.py`
State fields: `pre_analysis_result`, `step10_pre_change_graph`, `step11_impact_review`

**Stale Graph Guard (v1.6.1):**
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
  Pre-0, Step 0, Steps 8-9 -> Pipeline (analysis + prompt + GitHub issue + branch)
  Steps 10-14              -> Skipped (user implements, then runs Full Mode for PR/closure)

Full Mode (CLAUDE_HOOK_MODE=0):
  Pre-0, Step 0, Steps 8-14 -> All active steps execute sequentially
```

### Integration Flags

All integrations are configurable via environment variables (default: disabled):

| Flag | Default | Effect |
|------|---------|--------|
| `ENABLE_JIRA` | `0` | Dual GitHub+Jira issue tracking (Steps 8,9,11,12) |
| `ENABLE_JENKINS` | `0` | Jenkins build validation (Step 11) |
| `ENABLE_SONARQUBE` | `0` | SonarQube scan after implementation (Step 10) |
| `ENABLE_FIGMA` | `0` | Figma design-to-code pipeline (Steps 10,11,12 -- extraction/injection now inside Step 0 template) |
| `ENABLE_CI` | `false` | GitHub Actions CI pipeline |
| `ENABLE_HEALTH_SERVER` | `0` | Start HTTP /health + /readiness on HEALTH_PORT (8080) |
| `ENABLE_METRICS` | `0` | Start Prometheus /metrics server on METRICS_PORT (9090) |
| `ENABLE_TRACING` | `0` | Enable OpenTelemetry tracing (OTLP to OTEL_EXPORTER_OTLP_ENDPOINT) |
| `ENABLE_RATE_LIMITING` | `0` | Token bucket rate limiting on MCP tool endpoints |
| `LOG_FORMAT` | `""` | Set to `json` for structured JSON logging (container log aggregation) |
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
  Step 0:  EXTRACT+INJECT -> Components + design tokens extracted inside orchestration template
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

# Integration tests (require live providers)
pytest tests/integration/ -m integration

# E2E scenario tests
pytest tests/e2e/

# Load / concurrency tests
RUN_LOAD_TESTS=1 pytest tests/load/

# Security unit tests
pytest tests/test_secrets_manager.py tests/test_audit_logger.py

# CallGraph tests
pytest tests/test_call_graph_builder.py tests/test_call_graph_analyzer.py

# With coverage report
pytest tests/ --cov=langgraph_engine --cov-report=html:docs/coverage
```

### First-Time Setup

```bash
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
- `ANTHROPIC_API_KEY` - Claude API key
- `GITHUB_TOKEN` - GitHub personal access token
- `CLAUDE_DEBUG` - Debug mode (0/1)
- `CLAUDE_HOOK_MODE` - Hook mode (1) or Full mode (0)

---

**Last Updated:** 2026-04-06


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: v1.16.1 -- uml/ + drawio/ moved to project root; UML_OUTPUT_DIR + DRAWIO_OUTPUT_DIR env vars added
- **Skill**: python-core
- **Agent**: python-backend-engineer
- **Date**: 2026-04-07

## Dependency Notes

- `TTS>=0.22.0` (Coqui TTS) moved to `requirements-optional.txt` -- conflicts with `networkx>=3.1` via `gruut==2.2.3` transitive dep.
- Install voice notifications separately: `pip install -r requirements-optional.txt`
- CI auto-trigger disabled -- workflow runs on `workflow_dispatch` only (manual trigger via GitHub Actions UI).
