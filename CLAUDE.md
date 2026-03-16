# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 7.5.0
**Type:** LangGraph Orchestration Pipeline
**Last Updated:** 2026-03-16

---

## Project Overview

Claude Workflow Engine is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It handles session sync, coding standards enforcement, and end-to-end 14-step task execution with GitHub integration.

### Quick Info

| Property | Value |
|----------|-------|
| **Languages** | Python |
| **Frameworks** | LangGraph, LangChain |
| **Status** | Active Development |
| **Primary Location** | scripts/langgraph_engine/ |

---

## Architecture & Structure

### Directory Layout

```
/
+-- scripts/              # Pipeline scripts and hooks
|   +-- langgraph_engine/ # Core LangGraph orchestration (72 modules)
|   +-- architecture/     # Architecture system (83 modules)
+-- policies/             # 43 policy definitions
|   +-- 01-sync-system/   # Level 1 policies
|   +-- 02-standards/     # Level 2 policies
|   +-- 03-execution/     # Level 3 policies
+-- src/mcp/              # 11 FastMCP servers (102 tools, 8,400+ LOC)
+-- tests/                # Test suite (476 tests, 30 files)
+-- docs/                 # Documentation (40 files)
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Orchestrator | scripts/langgraph_engine/orchestrator.py | Main StateGraph pipeline |
| Flow State | scripts/langgraph_engine/flow_state.py | TypedDict state definition |
| Level -1 | scripts/langgraph_engine/subgraphs/level_minus1.py | Auto-fix (encoding) |
| Level 1 | scripts/langgraph_engine/subgraphs/level1_sync.py | Session/context sync |
| Level 2 | scripts/langgraph_engine/subgraphs/level2_standards.py | Standards enforcement |
| Level 3 | scripts/langgraph_engine/subgraphs/level3_execution_v2.py | 14-step execution |
| Hooks | scripts/pre-tool-enforcer.py, post-tool-tracker.py | Tool enforcement |
| Session Bridge | src/mcp/session_hooks.py | MCP direct import bridge |

### MCP Servers (11 servers, 103 tools)

All registered in `~/.claude/settings.json`. Version synced via `scripts/sync-version.py`.

| Server | File | Tools | Purpose |
|--------|------|-------|---------|
| git-ops | git_mcp_server.py | 14 | Git (branch, commit, push, pull, stash, post-merge cleanup) |
| github-api | github_mcp_server.py | 12 | GitHub (PR, issue, merge, label, build validate, merge cycle) |
| session-mgr | session_mcp_server.py | 14 | Session (create, chain, tag, accumulate, finalize, work items) |
| policy-enforcement | enforcement_mcp_server.py | 10 | Policy compliance, flow-trace, module health, system health |
| llm-provider | llm_mcp_server.py | 8 | LLM (4 providers, hybrid GPU-first, async health, cached) |
| token-optimizer | token_optimization_mcp_server.py | 10 | Token reduction (AST nav, smart read, dedup, 60-85% savings) |
| pre-tool-gate | pre_tool_gate_mcp_server.py | 8 | Pre-tool validation (8 policy checks, skill hints) |
| post-tool-tracker | post_tool_tracker_mcp_server.py | 6 | Post-tool tracking (progress, commit readiness, stats) |
| standards-loader | standards_loader_mcp_server.py | 7 | Standards (project detect, framework detect, hot-reload) |
| skill-manager | skill_manager_mcp_server.py | 8 | Skill lifecycle (load, search, validate, rank, conflicts) |
| vector-db | vector_db_mcp_server.py | 11 | Vector RAG (Qdrant, 4 collections, semantic search, bulk index, node decisions) |

### RAG Integration (NEW)

Every LangGraph node stores its decision in Vector DB (`node_decisions` collection).
Before LLM calls, the pipeline checks RAG for similar past decisions.
If confidence > threshold, RAG result replaces LLM call (saving inference time).

Key module: `scripts/langgraph_engine/rag_integration.py`
Collections: `node_decisions`, `sessions`, `flow_traces`, `tool_calls`

### Execution Modes

```
Hook Mode (default, CLAUDE_HOOK_MODE=1):
  Steps 0-7 -> PreToolUse hook -> output prompt to Claude
  Steps 8-14 -> Stop hook auto-executes (PR, issue close, docs, summary)

Full Mode (CLAUDE_HOOK_MODE=0):
  Steps 0-14 -> sequential (no user interaction mid-pipeline)
```

---

## Development Guidelines

### Code Style

- **Language:** Python 3.8+
- **Encoding:** UTF-8, ASCII-only (cp1252 safe for Windows)
- **Format:** Follow PEP 8 conventions
- **Testing:** All new code requires tests
- **Paths:** Always use path_resolver.py for cross-platform paths

### Running the Pipeline

```bash
python scripts/3-level-flow.py --task "your task"
```

### Testing

```bash
pytest tests/
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
- Ollama endpoint configuration
- Claude API keys
- GitHub token
- Debug modes

---

**Last Updated:** 2026-03-16


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: Bug Fix (complexity 4/10)
- **Skill**: langgraph-core
- **Agent**: spring-boot-microservices
- **Date**: 2026-03-15
