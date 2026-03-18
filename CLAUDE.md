# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 7.5.0
**Type:** LangGraph Orchestration Pipeline with RAG
**Last Updated:** 2026-03-18

---

## Project Overview

Claude Workflow Engine is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It handles session sync, coding standards enforcement, and end-to-end 15-step task execution (Step 0-14) with GitHub integration, RAG-powered decision caching, and hybrid LLM inference across 4 providers.

### Quick Info

| Property | Value |
|----------|-------|
| **Languages** | Python |
| **Frameworks** | LangGraph 1.0.10+, LangChain, FastMCP, Qdrant |
| **Status** | Active Development |
| **Primary Location** | scripts/langgraph_engine/ |
| **MCP Servers** | 12 (124 tools) |
| **Total Python Files** | 263 |
| **Test Files** | 49 |
| **Call Graph** | 574 classes, 3783 methods, 213 files analyzed |

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
    |-- Step 3:  Task/Phase Breakdown
    |-- Step 4:  TOON Refinement
    |-- Step 5:  Skill & Agent Selection (RAG cross-session boost)
    |-- Step 6:  Skill Validation & Download
    |-- Step 7:  Final Prompt Generation (3 files)
    |-- Step 8:  GitHub Issue Creation
    |-- Step 9:  Branch Creation + Git Setup
    |-- Step 10: Implementation Execution (CallGraph context + pre-change snapshot)
    |-- Step 11: Pull Request & Code Review (CallGraph diff + breaking change detection)
    |-- Step 12: Issue Closure
    |-- Step 13: Documentation Update + UML Diagram Generation
    |-- Step 14: Final Summary
```

### Directory Layout

```
/
+-- scripts/                          # Pipeline scripts and hooks
|   +-- langgraph_engine/             # Core orchestration (80 modules: 74 root + 6 subgraph files)
|   +-- architecture/                 # Active pipeline scripts (6 scripts + 1 data file)
+-- policies/                         # 49 policy definitions (48 .md + 1 .json)
|   +-- 01-sync-system/               # Level 1 policies
|   +-- 02-standards-system/          # Level 2 policies
|   +-- 03-execution-system/          # Level 3 policies (15 steps: 0-14 + failure prevention)
+-- src/mcp/                          # 12 FastMCP servers (124 tools, 9,000+ LOC)
+-- tests/                            # 49 test files (42 root + 2 integration + 5 other)
+-- docs/                             # 40 documentation files
+-- docs/uml/                         # Auto-generated UML diagrams (13 types)
+-- rules/                            # 5 coding standard definitions
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Orchestrator | scripts/langgraph_engine/orchestrator.py | Main StateGraph pipeline (59K) |
| Flow State | scripts/langgraph_engine/flow_state.py | TypedDict state definition (45K) |
| RAG Integration | scripts/langgraph_engine/rag_integration.py | Vector DB decision caching (16K) |
| Level -1 | scripts/langgraph_engine/subgraphs/level_minus1.py | Auto-fix enforcement (28K) |
| Level 1 | scripts/langgraph_engine/subgraphs/level1_sync.py | Session/context sync + TOON (37K) |
| Level 2 | scripts/langgraph_engine/subgraphs/level2_standards.py | Standards loading (15K) |
| Level 3 v2 | scripts/langgraph_engine/subgraphs/level3_execution_v2.py | 15-step execution with RAG (36K) - ACTIVE |
| Level 3 v1 | scripts/langgraph_engine/subgraphs/level3_execution.py | Original pipeline (97K) - DEPRECATED, v2 is used |
| Hooks | scripts/pre-tool-enforcer.py, post-tool-tracker.py | Tool enforcement |
| Call Graph Builder | scripts/langgraph_engine/call_graph_builder.py | AST-based FQN call stack with class context |
| Call Graph Analyzer | scripts/langgraph_engine/call_graph_analyzer.py | Pipeline impact analysis (Steps 2/10/11) |
| UML Generators | scripts/langgraph_engine/uml_generators.py | 13 UML diagram types (CallGraph + AST + LLM) |
| Doc Manager | scripts/langgraph_engine/level3_documentation_manager.py | Circular SDLC doc cycle (Step 0/13) |
| Session Bridge | src/mcp/session_hooks.py | MCP direct import bridge |

### MCP Servers (12 servers, 123 tools)

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

### RAG Integration

Every LangGraph node stores its decision in Vector DB (`node_decisions` collection).
Before LLM calls, the pipeline checks RAG for similar past decisions.
If confidence >= step-specific threshold, RAG result replaces LLM call (saving inference time).

Key module: `scripts/langgraph_engine/rag_integration.py`
Collections: `node_decisions`, `sessions`, `flow_traces`, `tool_calls`
Default threshold: 0.82 (step-specific: 0.75-0.90)

### CallGraph-Driven Pipeline Intelligence

The pipeline uses a full AST-based call graph (574 classes, 3783 methods) to make
informed decisions at critical steps instead of blind code generation:

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

**Last Updated:** 2026-03-18


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: New Feature (complexity 7/10)
- **Skill**: langgraph-core
- **Agent**: python-backend-engineer
- **Date**: 2026-03-18
