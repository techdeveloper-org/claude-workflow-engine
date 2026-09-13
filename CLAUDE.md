# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 2.1.0
**Type:** LangGraph Orchestration Pipeline with Call Graph Intelligence + Template Fast-Path
**Last Updated:** 2026-08-07

---

## Project Overview

Claude Workflow Engine is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It handles session sync, coding standards enforcement, and end-to-end 9-step active execution (Steps 0-8) with GitHub integration and hybrid LLM inference across 2 providers (claude_cli, anthropic).

### Quick Info

| Property | Value |
|----------|-------|
| **Languages** | Python |
| **Frameworks** | LangGraph 0.2.0+, LangChain, FastMCP (mcp package) |
| **Status** | Active Development |
| **Primary Location** | langgraph_engine/ |
| **MCP Servers** | 13 servers -- all in separate repos under [techdeveloper-org](https://github.com/orgs/techdeveloper-org/repositories); 1 also keeps an in-engine copy in `src/mcp/` |
| **Total Python Files** | 248 (langgraph_engine/); 493 repo-wide |
| **Test Files** | 105 (96 unit, 5 integration, 3 e2e, 1 load) |
| **Call Graph** | 578 classes, 3,985 methods, 4 languages (Python/Java/TS/Kotlin) |

---

## Architecture & Structure

### Pipeline Flow

Domain-driven Level/Step naming (renamed from the old `Level -1/1/2/3` + `Pre-0, Step 0, Steps 8-14`
scheme -- numbers are kept as a wire-level ordering convenience, but every level and step also
carries a purpose-revealing name; see "Latest Execution Insight" below for the rename rationale):

```
Level 0: Pre-Flight Sanity Guard (3 checks: Unicode, encoding, paths)
    |     Package: langgraph_engine/preflight_guard/
    |
Level 1: Session & Context Synchronization (session + parallel [complexity, context] -> merge)
    |     Package: langgraph_engine/context_sync/
    |     Outputs: combined_complexity_score [1-25] (simple x 0.3 + graph x 0.7)
    |     NOTE: combined_complexity_score is on a 1-25 scale -- do NOT treat as 1-10
    |
Standards (always-on, loaded from disk -- NOT a numbered level; retired in the rename
    |      because it never had pipeline nodes; policies/ is read directly on disk)
    |
Level 2: SDLC Execution Core (9 active steps: Steps 0-8)
    |     Package: langgraph_engine/sdlc_pipeline/
    |
    |-- Step 0: Pre-Analysis & CallGraph Scan
    |           CallGraph scan -> hot_nodes, danger_zones, complexity_boost -> state
    |           Template fast-path detected? -> skip Step 1, jump to Step 2
    |           Normal path -> continue to Step 1 with call graph data already in state
    |
    |-- Step 1: Task Orchestration & Planning -- PromptGen -> TODO Decomposition -> Execution   [v1.20.0]
    |   |
    |   |  WHAT CHANGED (v1.12 -> v1.13 -> v1.14, using THAT era's step numbers):
    |   |  v1.12: Steps 0-7 = 6 separate LLM calls (~75s planning)
    |   |         Step 0: task analysis
    |   |         Step 1: plan mode decision        [REMOVED in v1.13]
    |   |         Step 3: task/phase breakdown      [REMOVED in v1.13]
    |   |         Step 4: TOON refinement           [REMOVED in v1.13]
    |   |         Step 5: skill & agent selection   [REMOVED in v1.13]
    |   |         Step 6: skill validation          [REMOVED in v1.13]
    |   |         Step 7: final prompt generation   [REMOVED in v1.13]
    |   |  v1.13: Step 0 = 2 subprocess calls (~30s planning)
    |   |  v1.14: Step 0 = 2 subprocess calls (claude CLI, ~15s planning)
    |   |  v1.20: monolithic orchestrator call REPLACED by a TODO-decomposition
    |   |         pipeline: prompt_gen -> todo_decomposer -> todo_executor
    |   |  2026-08-07: TODO decomposition and execution REMOVED. Step 1 assembles
    |   |         the prompt and emits it; it no longer runs anything. The three
    |   |         scripts were deleted.   prompt_gen -> emit  <-- CURRENT
    |   |
    |   |-- Phase 1: prompt_gen_expert_caller  (assembles the prompt; no LLM call)
    |   |     Reads: ORCHESTRATION_TEMPLATE.md from the sibling claude-global-library,
    |   |            resolved through the 3-tier ResourceResolver chain. There is no
    |   |            fallback: a missing library raises, it does not degrade.
    |   |     The master template is a standalone instruction document, not a
    |   |     parameterised prompt -- its braces are path patterns and authoring
    |   |     directives the orchestrator fills itself. Runtime values are therefore
    |   |     PREPENDED as an authoritative grounding header, never substituted in:
    |   |       user requirements    <- state["task_description"]
    |   |       runtime context JSON <- call graph + complexity (from Step 0 + Level 1)
    |   |       complexity score     <- state["combined_complexity_score"] (1-25)
    |   |       codebase risk        <- call_graph_metrics["risk_level"]
    |   |       danger zones         <- call_graph_metrics["danger_zones"]
    |   |       affected methods     <- call_graph_metrics["affected_methods"]
    |   |       hot nodes            <- call_graph_metrics["hot_nodes"]
    |   |       KG routing summary   <- KGRouter pre-injection (FR-3)
    |   |     Stores: state["orchestration_prompt"]
    |   |
    |   |-- Phase 2: emit
    |         The node runs inside a hook subprocess, so it cannot execute in the
    |         session it is serving -- it can only hand that session something to
    |         run. The master template's STEP 13 already produces the MULTI-AGENT
    |         PROMPT BUNDLE, so decomposing the prompt again here was re-deriving
    |         work that belongs in the template.
    |         Stores: state["orchestration_prompt"] and state["orchestrator_result"],
    |                 the latter a record of WHAT WAS EMITTED, not what was executed:
    |                 mode, prompt_chars, template_source, library_version
    |                 (the claude-global-library VERSION, read through the resolver;
    |                  degrades to "unknown" rather than failing the step)
    |
    |-- Step 2: Issue Tracking -- GitHub Issue + Jira Issue creation (ENABLE_JIRA, dual-linked)
    |-- Step 3: Branch & Workspace Setup (Jira key: feature/PROJ-123)
    |-- Step 4: Implementation & Code Generation + Jira "In Progress" + Figma "started" comment
    |-- Step 5: Pull Request & Automated Review + Jira PR link + Figma design review
    |-- Step 6: Issue & Ticket Closure (GitHub + Jira "Done" + Figma "complete" comment)
    |-- Step 7: Documentation & UML Generation
    |-- Step 8: Final Telemetry & Summary Report
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
| **v1.16.0** | **8** | **2 (subprocess)** | **~15s** | Level 2 script purge: all level2_standards/ removed; policies in policies/02-standards-system/; level1_cleanup routes directly to level3_init |
| **v1.16.1** | **8** | **2 (subprocess)** | **~15s** | uml/ + drawio/ moved to project root (out of docs/); UML_OUTPUT_DIR + DRAWIO_OUTPUT_DIR env vars |

### Directory Layout

```
/
+-- hooks/                            # Claude Code hook scripts (PreToolUse, PostToolUse, Stop)
|   +-- pre-tool-enforcer.py          # PreToolUse hook entry point (shim -> pre_tool_enforcer/)
|   +-- post-tool-tracker.py          # PostToolUse hook entry point (shim -> post_tool_tracker/)
|   +-- stop-notifier.py              # Stop hook entry point (shim -> stop_notifier/)
|   +-- pre_tool_enforcer/            # PreToolUse hook package (canonical)
|   +-- post_tool_tracker/            # PostToolUse hook package (canonical)
|   +-- stop_notifier/                # Stop hook package (canonical)
|   +-- ide_paths.py                  # Path constants (imported by hook packages)
|   +-- project_session.py            # Session utilities (imported by hook packages)
|   +-- policy_tracking_helper.py     # Policy tracking (imported by hook packages)
+-- langgraph_engine/                 # Core orchestration engine (REPO ROOT -- sibling of scripts/, NOT nested under it)
|   +-- core/  state/  routing/                         # LazyLoader/ErrorHandler, FlowState, routing
|   +-- diagrams/ (+drawio/)  parsers/  integrations/   # Strategy/Factory: UML gens, 4 lang parsers, GitHub/Jira/Figma/Jenkins
|   +-- analysis/ context/ engine_logging/ github/ metrics/ quality/ security/ skills/ standards/   # domain subpackages (v1.20 migration)
|   +-- build_dependency_resolver/  runtime_verification/   # build-dep parsers; node contracts + verifier
|   +-- preflight_guard/  context_sync/  sdlc_pipeline/  # the 3 pipeline levels (each has architecture/; sdlc_pipeline also nodes/ + subgraph.py + sonarqube/)
|   +-- [shared modules]              # orchestrator.py, llm_call, patterns, caching, git, etc.
+-- scripts/                          # Pipeline entry point + supporting tools (NOT the engine itself)
|   +-- 3-level-flow.py               # Main pipeline entry point (filename predates the rename; still the canonical entry point for the 3-level pipeline)
|   +-- architecture/                 # generate_system_diagram.py (shared utility)
|   +-- setup/  bin/  tools/          # env setup; Windows .bat launchers; dev utilities (release.py, sync-version.py, etc.)
|   +-- github_operations/  github_pr_workflow/  helpers/   # GitHub + PR workflow helpers
+-- policies/03-execution-system/failure-prevention/  # failure-kb.json only (read by hooks/pre_tool_enforcer/policies/failure_kb.py); the historical 00-auto-fix/01-sync/02-standards/testing subtrees do not exist on disk -- standards live only in ~/.claude/rules/ (no repo copy, #320)
+-- src/mcp/                          # In-engine copy of session-mgr + bridge (session_hooks, base/)
+-- k8s/                              # Kubernetes manifests (deployment, service, hpa, configmap, secret)
+-- tests/                            # 45 test files (37 unit, 4 integration, 3 e2e, 1 load)
+-- docs/                             # ALL documentation, segregated by kind -- see docs/README.md for the index
|   +-- policies/ (46)                # pipeline policy documentation. NOT a mirror of ~/.claude/policies/ -- see the note below
|   +-- architecture/ (17)            # ADRs, pipeline/level design, flow diagrams, orchestration prompt
|   +-- guides/ (14)                  # getting started, deployment, testing, troubleshooting, runbooks
|   +-- reports/ (20)                 # point-in-time investigations, audits, migration notes
|   +-- releases/ (6)                 # per-version design briefs and review notes
|   +-- contributing/ (5)             # issue/PR templates, CONTRIBUTING, CODE_OF_CONDUCT (here, not root -- rules/11 caps the root at 5 files)
|   +-- api/ (1)  phase-1-architecture/ (2)   # OpenAPI spec; original phase-1 HLD + feasibility
+-- uml/  drawio/                     # Auto-generated UML + draw.io diagrams (13 types each)
```

#### `docs/policies/` and `~/.claude/policies/` are two different things

This file used to call them mirrors. They are not, and had drifted apart by 25 files
when that was checked on 2026-08-08: 18 names in `docs/policies/` are absent from the
machine, and 7 on the machine are in no repository at all -- several of them for
plan-mode and skill-agent-selection, which v1.15.2 purged.

They are not meant to match. `docs/policies/` is **documentation** of what the pipeline
does at each step (`quality-gate-policy.md`, `pr-code-review-policy.md`), and nothing
loads it. `~/.claude/policies/` is the **runtime corpus** that `get_policies_dir()`
reads, and the standards selector consumes a narrow slice of it -- the
`02-standards-system/` tier plus language-mapped files. Calling them mirrors invited
the assumption that editing one affected the other, which it never did in either
direction.

`CLAUDE_POLICIES_DIR` overrides the runtime location. The 7 machine-only files are
unversioned: if that machine is lost, so are they.

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Orchestrator | langgraph_engine/orchestrator.py | Main StateGraph pipeline |
| Flow State | langgraph_engine/flow_state.py | Backward-compat shim -> re-exports from state/ |
| State Package | langgraph_engine/state/ | FlowState, StepKeys, reducers, WorkflowContextOptimizer |
| Core Package | langgraph_engine/core/ | LazyLoader, get_logger, node_error_handler, NodeResult, create_step_node |
| Routing Package | langgraph_engine/routing/ | All routing functions split by level |
| Graph Factory | langgraph_engine/orchestrator.py | create_flow_graph(hook_mode): single canonical StateGraph factory (verify_node runtime-verification wrapping applied here) |
| Diagrams Package | langgraph_engine/diagrams/ | Strategy Pattern: DiagramFactory + 13 generators |
| Parsers Package | langgraph_engine/parsers/ | Abstract Factory: ParserRegistry + 4 language parsers |
| SonarQube Package | langgraph_engine/sdlc_pipeline/sonarqube/ | Facade: api_client, lightweight, aggregator, auto_fixer |
| Integrations Package | langgraph_engine/integrations/ | Abstract Factory + Lifecycle: GitHub/Jira/Figma/Jenkins |
| Level 0 | langgraph_engine/preflight_guard/ | Pre-Flight Sanity Guard -- auto-fix enforcement (canonical) |
| Level 1 | langgraph_engine/context_sync/ | Session & Context Synchronization (canonical). Outputs: `complexity_score` [1-10] (simple heuristic), `combined_complexity_score` [1-25] (simple x 0.3 + graph x 0.7 after linear scaling). **Note: `combined_complexity_score` is on a 1-25 scale -- do NOT treat it as 1-10.** |
| Standards (non-numbered) | ~/.claude/rules/ (the only copy; no repo docs/standards/) + langgraph_engine/standards/ (selector + library_adapter) | Standards policies (.md files, no pipeline nodes) -- always-on, loaded from disk; retired from the level count since it has never had pipeline nodes |
| Level 2 | langgraph_engine/sdlc_pipeline/subgraph.py | SDLC Execution Core -- 9-step active execution (Steps 0-8) -- ACTIVE (nodes in sdlc_pipeline/nodes/) |
| Pre-Analysis Node | langgraph_engine/sdlc_pipeline/subgraph.py | orchestration_pre_analysis_node: CallGraph scan at Step 0; template fast-path detection |
| Hooks | hooks/pre-tool-enforcer.py, post-tool-tracker.py, stop-notifier.py | Tool enforcement + session maintenance |
| Call Graph Builder | langgraph_engine/call_graph_builder.py | AST-based FQN call stack (compat shim -> parsers/) |
| Call Graph Analyzer | langgraph_engine/call_graph_analyzer.py | Pipeline impact analysis (Steps 0/4/5) |
| UML Generators | langgraph_engine/uml_generators.py | Compat shim -> diagrams/DiagramFactory |
| Doc Manager | langgraph_engine/sdlc_pipeline/documentation_manager.py | Circular SDLC doc cycle (Step 1/7) |
| Session Bridge | src/mcp/session_hooks.py | MCP direct import bridge |
| Metrics Aggregator | langgraph_engine/metrics_aggregator.py | Session/step/LLM/tool stats from logs |
| SonarQube Scanner | langgraph_engine/sonarqube_scanner.py | Legacy entry point -> sonarqube/ package |
| Quality Gate | langgraph_engine/quality_gate.py | 4-gate merge enforcement |
| Test Generator | langgraph_engine/test_generator.py | Template-based unit tests (4 languages) |
| Jira Workflow | langgraph_engine/sdlc_pipeline/jira_lifecycle.py | Dual GitHub+Jira integration (Steps 2/3/5/6) |
| Figma Workflow | langgraph_engine/sdlc_pipeline/figma_workflow.py | Design-to-code (components, tokens, review) |
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
| PromptGen Caller | langgraph_engine/sdlc_pipeline/architecture/prompt_gen_expert_caller.py | Step 1 Phase 1: assembles the orchestration prompt from the master template (no LLM call) |

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
Step 0 (Pre-Analysis): analyze_impact_before_change() -> risk_level, danger_zones, affected_methods
                          Planner knows what could break BEFORE suggesting changes

Step 4 (Implementation & Code Generation):  snapshot_call_graph() + get_implementation_context()
                 Captures pre-change state + injects caller/callee awareness

Step 5 (Pull Request & Automated Review): review_change_impact() -> compare before/after graphs
                 Detects breaking changes, orphaned methods, risk assessment
```

Key module: `langgraph_engine/call_graph_analyzer.py`
Data source: `langgraph_engine/call_graph_builder.py`
State fields: `pre_analysis_result`, `step4_pre_change_graph`, `step5_impact_review`

**Stale Graph Guard (v1.6.1):**
After Step 4 writes files, state flag `call_graph_stale = True` is set.
`refresh_call_graph_if_stale(state, project_root)` (in `call_graph_analyzer.py`) checks
this flag and silently rebuilds the graph when stale rather than returning a pre-implementation
cached snapshot.  This prevents multi-phase implementations from using a Phase-0 graph for
later-phase decisions after an earlier phase has already modified files.  The function falls
back through priority order: fresh scan (if stale) -> step4_pre_change_graph ->
pre_analysis_result -> fresh scan (nothing cached).

UML diagrams (13 types) also consume CallGraph as single data source via adapters
in `uml_generators.py`, replacing duplicate AST analysis.

### Execution Modes

```
Hook Mode (default, CLAUDE_HOOK_MODE=1):
  Steps 0-3 (Pre-Analysis, Task Orchestration, Issue Tracking, Branch Setup) -> Pipeline
  Steps 4-8 (Implementation through Final Summary) -> Skipped (user implements,
                                                        then runs Full Mode for PR/closure)

Full Mode (CLAUDE_HOOK_MODE=0):
  Steps 0-8 -> All active steps execute sequentially
```

### Integration Flags

All integrations are configurable via environment variables (default: disabled):

| Flag | Default | Effect |
|------|---------|--------|
| `ENABLE_JIRA` | `0` | Dual GitHub+Jira issue tracking (Steps 2,3,5,6) |
| `ENABLE_JENKINS` | `0` | Jenkins build validation (Step 5) |
| `ENABLE_SONARQUBE` | `0` | SonarQube scan after implementation (Step 4) |
| `ENABLE_FIGMA` | `0` | Figma design-to-code pipeline (Steps 4,5,6 -- extraction/injection now inside Step 1 template) |
| `ENABLE_CI` | `true` | GitHub Actions CI pipeline. A **repo variable**, not a process env var: `ci.yml` reads `vars.ENABLE_CI` and falls back to `true`, so CI runs unless it is explicitly set to `false` |
| `ENABLE_HEALTH_SERVER` | `0` | Start HTTP /health + /readiness on HEALTH_PORT (8080) |
| `ENABLE_METRICS` | `0` | Start Prometheus /metrics server on METRICS_PORT (9090) |
| `ENABLE_TRACING` | `0` | Enable OpenTelemetry tracing (OTLP to OTEL_EXPORTER_OTLP_ENDPOINT) |
| `ENABLE_RATE_LIMITING` | `0` | Token bucket rate limiting on MCP tool endpoints |
| `LOG_FORMAT` | `""` | Set to `json` for structured JSON logging (container log aggregation) |
| `FORCE_GRAPH_REBUILD` | `0` | Force call graph rebuild even if stale flag is False |
| `ENABLE_RUNTIME_VERIFICATION` | `0` | Enable runtime contract/invariant verification on pipeline nodes |
| `STRICT_RUNTIME_VERIFICATION` | `0` | If 1, pipeline halts on first CRITICAL verification violation |

### Integration Lifecycle (Create -> Update -> Close)

When integrations are enabled, the pipeline manages the full lifecycle:

```
Jira Lifecycle (ENABLE_JIRA=1):
  Step 2: CREATE   -> Jira issue created, cross-linked to GitHub Issue
  Step 3: BRANCH   -> Branch named from Jira key (feature/proj-123)
  Step 4: UPDATE   -> Transition to "In Progress", add start comment
  Step 5: LINK     -> PR remote-linked to Jira, transition to "In Review"
  Step 5: MERGE    -> Post-merge comment with PR number and branch
  Step 6: CLOSE    -> Transition to "Done", add implementation summary

Figma Lifecycle (ENABLE_FIGMA=1):
  Step 1: EXTRACT+INJECT -> Components + design tokens extracted inside orchestration template
  Step 4: COMMENT  -> "Implementation started" with component list
  Step 5: REVIEW   -> Design fidelity checklist in code review
  Step 6: COMMENT  -> "Implementation complete" with PR link
```

---

## Development Guidelines

### Code Style

- **Language:** Python 3.10+
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

### Adding a New Pipeline Level

```python
# 1. Create level package in langgraph_engine/my_level/
# 2. Add routing in routing/my_level_routes.py
# 3. Wire the level's nodes + edges into create_flow_graph() in
#    langgraph_engine/orchestrator.py (the single canonical graph factory):
def create_flow_graph(hook_mode: bool = False):
    ...
    graph.add_node("my_level_node", my_level_node)
    graph.add_edge("level1_cleanup", "my_level_node")
    ...
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

**Last Updated:** 2026-08-07


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: Domain-driven Level/Step rename -- Level -1/1/2/3 + Pre-0/Step 0/Steps 8-14 renumbered to Level 0/1/2 (Pre-Flight Sanity Guard / Session & Context Synchronization / SDLC Execution Core) + Steps 0-8, each carrying a purpose name; dead "Level 2: Standards" (never had pipeline nodes) retired from the level count; `level_minus1/`, `level1_sync/`, `level3_execution/` renamed to `preflight_guard/`, `context_sync/`, `sdlc_pipeline/`; StepKeys/state fields, LangGraph node IDs, flow-trace markers (with a `LEGACY_MARKER_ALIASES` compat map), and node-implementation files all renumbered in lockstep; fixed several latent bugs surfaced along the way (duplicate `_apply_step1_standards` function name collision in standards/integration.py, `SELECTED_MODEL` StepKeys/writer mismatch, `_run_step` dry-run/KB-check/pipeline-timing thresholds)
- **Skill**: python-core
- **Agent**: python-backend-engineer
- **Date**: 2026-07-25

## Dependency Notes

- `TTS>=0.22.0` (Coqui TTS) moved to `requirements-optional.txt` -- conflicts with `networkx>=3.1` via `gruut==2.2.3` transitive dep.
- Install voice notifications separately: `pip install -r requirements-optional.txt`
- CI auto-triggers on push/PR to `main`; Python matrix is `["3.10","3.11"]` (mcp>=1.0.0 requires Python>=3.10).
