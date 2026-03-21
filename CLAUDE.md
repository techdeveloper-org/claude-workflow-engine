# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 1.5.0
**Type:** LangGraph Orchestration Pipeline with RAG
**Last Updated:** 2026-03-21

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
| **Total Python Files** | 360+ |
| **Test Files** | 69 |
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
    |-- Step 0:  Task Analysis + Prompt Generation
    |-- Step 1:  Plan Mode Decision
    |-- Step 2:  Plan Execution (CallGraph impact analysis + complexity-based model)
    |-- Step 3:  Task/Phase Breakdown + Figma component extraction (ENABLE_FIGMA)
    |-- Step 4:  TOON Refinement
    |-- Step 5:  Skill & Agent Selection (RAG cross-session boost)
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
+-- rules/                            # 10 coding standard definitions
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
| RAG Integration | scripts/langgraph_engine/rag_integration.py | Vector DB decision caching (16K) |
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

### MCP Servers (19 servers, 323 tools)

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
| `ENABLE_CI` | `true` | GitHub Actions CI pipeline |

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

# Integration tests
pytest tests/integration/

# CallGraph tests (builder + analyzer + UML integration)
pytest tests/test_call_graph_builder.py tests/test_call_graph_analyzer.py

# RAG tests
pytest tests/test_rag_integration.py
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

**Last Updated:** 2026-03-21


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: Modularization Refactor (complexity 8/10)
- **Skill**: langgraph-core
- **Agent**: python-backend-engineer
- **Date**: 2026-03-18
