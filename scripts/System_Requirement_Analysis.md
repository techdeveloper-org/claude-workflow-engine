# System Requirements Analysis

**Project:** Claude Workflow Engine
**Version:** 1.5.0
**Date:** 2026-03-21
**Author:** Claude Workflow Engine Team

---

## Executive Summary

Claude Workflow Engine is a LangGraph-based 4-level pipeline that automates the full Software Development Life Cycle (SDLC) — from task analysis to merged PR closure — using LLM inference, RAG-powered decision caching, AST-based call graph analysis, and 19 MCP servers (323 tools). It is the only AI tool that automates all 15 SDLC steps including GitHub Issues, branch creation, code review, PR merge, Jira tracking, Figma design-to-code, Jenkins CI/CD, SonarQube scanning, UML generation, and documentation updates.

---

## Project Overview

### 1. Purpose and Objectives

Claude Workflow Engine automates software development lifecycle tasks that normally require human coordination across multiple tools (GitHub, Jira, Figma, Jenkins, SonarQube, Qdrant, LLM APIs). A developer provides a natural language task description; the engine handles everything from analysis to delivery.

The system aims to:
- Automate the full 15-step SDLC pipeline from task intake to issue closure
- Enforce project-specific coding standards at every step via 63 policy files
- Reduce LLM inference costs by 60-85% through RAG caching and token optimization
- Support multi-project, multi-language codebases (20+ languages, 15+ frameworks)
- Provide pluggable, extensible architecture so individual steps/levels can be added or removed

### 2. Scope

#### Included

- Python 3.8+ pipeline execution on Windows/Linux/macOS
- LangGraph StateGraph orchestration (Level -1 through Level 3)
- 19 FastMCP servers (323 tools) for GitHub, Jira, Figma, Jenkins, Qdrant, etc.
- RAG vector DB integration (Qdrant, 4 collections)
- Hybrid LLM inference (Ollama → Claude CLI → Anthropic API → OpenAI API)
- AST-based call graph analysis (Python/Java/TypeScript/Kotlin)
- 13 UML diagram types (Mermaid + PlantUML + Kroki.io rendering)
- Hook system (UserPromptSubmit, PreToolUse, PostToolUse, Stop)
- Session management with TOON compression and cross-session RAG learning

#### Excluded

- Web UI / GUI (CLI-only)
- Direct database writes (all DB access via MCP tools)
- Custom LLM training or fine-tuning
- Real-time collaboration between multiple users simultaneously

### 3. Project Context

- **Domain:** Software Development Automation / DevOps
- **Target Users:** Solo developers, engineering teams using Claude Code CLI
- **Deployment:** Local machine, triggered by Claude Code hooks on every user prompt
- **Integration Points:** GitHub, Jira (Cloud+Server), Figma, Jenkins, SonarQube, Qdrant, Ollama, Anthropic API, OpenAI API

---

## Functional Requirements

### FR-1: 4-Level Pipeline Execution

**Description:** Pipeline must execute 4 levels in order: Level -1 (Auto-Fix), Level 1 (Sync), Level 2 (Standards), Level 3 (15-Step Execution). Each level must be independently removable or bypassable.
**Priority:** Critical
**Status:** Implemented
**Key Module:** `orchestrator.py`, `pipeline_builder.py`

### FR-2: 15-Step SDLC Automation (Level 3)

**Description:** Level 3 must execute all 15 steps (Step 0-14) with optional Hook Mode (Steps 0-9 only) via `CLAUDE_HOOK_MODE` env var.

| Step | Action |
|------|--------|
| Step 0 | Task analysis, complexity scoring (1-10), task type detection |
| Step 1 | Plan mode decision (simple vs complex task) |
| Step 2 | Plan execution with CallGraph impact analysis |
| Step 3 | Task/phase breakdown + Figma component extraction |
| Step 4 | TOON context refinement |
| Step 5 | Skill & agent selection (RAG cross-session boost) |
| Step 6 | Skill validation and download |
| Step 7 | Final prompt generation (3 files) + Figma design tokens |
| Step 8 | GitHub Issue + Jira Issue creation (dual, cross-linked) |
| Step 9 | Branch creation (from Jira key if ENABLE_JIRA) |
| Step 10 | Implementation + Jira "In Progress" + Figma "started" |
| Step 11 | PR creation + code review + Jira "In Review" + Figma fidelity check |
| Step 12 | Issue closure: GitHub + Jira "Done" + Figma "complete" |
| Step 13 | Documentation update + 13 UML diagram types |
| Step 14 | Final execution summary + voice notification |

**Priority:** Critical
**Status:** Implemented
**Key Module:** `subgraphs/level3_execution_v2.py`

### FR-3: RAG Decision Caching

**Description:** Every pipeline node must store its decision in Qdrant. Before LLM calls, the pipeline checks RAG for similar past decisions. If confidence >= step-specific threshold (0.75-0.90), RAG result replaces LLM call.
**Priority:** High
**Status:** Implemented
**Key Module:** `rag_integration.py`
**Collections:** `node_decisions`, `sessions`, `flow_traces`, `tool_calls`

### FR-4: AST-Based Call Graph Analysis

**Description:** Full class-level call graph supporting Python (AST), Java, TypeScript, Kotlin (regex). Used at Steps 2, 10, 11 for impact analysis, implementation context, and PR review.
**Priority:** High
**Status:** Implemented
**Key Modules:** `parsers/` (Abstract Factory), `call_graph_builder.py`, `call_graph_analyzer.py`

### FR-5: Integration Lifecycle Management

**Description:** All integrations follow Create → Update → Close lifecycle. Jira and Figma are toggled via env flags. Operations are non-blocking (failure of one integration does not stop others).

| Integration | Flag | Lifecycle Steps |
|-------------|------|----------------|
| Jira | `ENABLE_JIRA=1` | Create (8), Branch (9), In Progress (10), In Review (11), Done (12) |
| Figma | `ENABLE_FIGMA=1` | Extract (3), Inject tokens (7), Comment started (10), Review (11), Comment done (12) |
| Jenkins | `ENABLE_JENKINS=1` | Trigger (10), Validate (11) |
| SonarQube | `ENABLE_SONARQUBE=1` | Scan (10), Auto-fix loop |

**Priority:** Medium
**Status:** Implemented
**Key Module:** `integrations/` (Abstract Factory + Template Method)

### FR-6: Modular Pipeline Construction

**Description:** Pipeline must be constructable via `PipelineBuilder` chainable API. Individual levels must be addable/removable without modifying orchestrator.
**Priority:** High
**Status:** Implemented
**Key Module:** `pipeline_builder.py`

```python
# Add/remove any level:
create_flow_graph(hook_mode=True)  # default: all 4 levels

# Custom build:
PipelineBuilder().add_level_minus1().add_level1().add_level3().build()
```

### FR-7: 19 MCP Servers (323 Tools)

**Description:** All external service operations (GitHub, Jira, Figma, Jenkins, Qdrant, Git, LLM, etc.) must be accessible as MCP tools registered in `~/.claude/settings.json`.
**Priority:** High
**Status:** Implemented
**Key Location:** `src/mcp/`

### FR-8: Multi-Project Standards Enforcement

**Description:** Level 2 must auto-detect project type (language, framework) and load appropriate coding standards from 63 policy files.
**Priority:** High
**Status:** Implemented
**Key Module:** `subgraphs/level2_standards.py`

### FR-9: Hybrid LLM Inference

**Description:** LLM calls must follow fallback chain: Ollama (local GPU) → Claude CLI → Anthropic API → OpenAI API. Model selection must be complexity-based.
**Priority:** High
**Status:** Implemented
**Key Module:** `src/mcp/llm_mcp_server.py`

### FR-10: Hook System

**Description:** Pipeline must integrate with Claude Code's 4 hook types (UserPromptSubmit, PreToolUse, PostToolUse, Stop) for automated trigger and enforcement.
**Priority:** High
**Status:** Implemented
**Key Scripts:** `scripts/pre-tool-enforcer.py`, `scripts/post-tool-tracker.py`, `scripts/stop-notifier.py`

---

## Non-Functional Requirements

### NFR-1: Performance

- **Hook Mode target:** Steps 0-9 complete in < 60 seconds
- **Full Mode target:** Steps 0-14 complete in < 170 seconds
- **RAG cache hit:** Reduces LLM call time by 70-90%
- **Token savings:** 60-85% reduction via AST navigation + dedup
- **Status:** Implemented

### NFR-2: Extensibility

- Adding a new pipeline level: implement subgraph, call `PipelineBuilder().add_my_level()`
- Adding a new routing rule: add function to `routing/` package, register in orchestrator
- Adding a new integration: extend `AbstractIntegration` in `integrations/`
- Adding a new UML diagram: extend `AbstractDiagramGenerator` in `diagrams/`
- Adding a new language parser: extend `AbstractLanguageParser` in `parsers/`
- **Status:** Implemented via 9 modular packages (v1.5.0)

### NFR-3: Reliability

- Checkpoint recovery: pipeline can resume from any step after crash
- Signal handling: Ctrl+C triggers graceful recovery with checkpoint save
- Non-blocking integrations: Jira/Figma/Jenkins failure does not abort pipeline
- Error propagation: `node_error_handler` decorator standardizes all node failures
- **Status:** Implemented

### NFR-4: Backward Compatibility

- All existing imports continue to work unchanged:
  - `from langgraph_engine.flow_state import FlowState` (shim re-exports from `state/`)
  - `from langgraph_engine.uml_generators import generate_all` (shim re-exports from `diagrams/`)
  - `from langgraph_engine.call_graph_builder import CallGraphBuilder` (shim re-exports from `parsers/`)
- **Status:** Implemented

### NFR-5: Platform Compatibility

- Python 3.8+ on Windows (cp1252-safe ASCII-only source files), Linux, macOS
- Cross-platform paths via `path_resolver.py`
- UTF-8 encoding throughout; no non-ASCII characters in `.py` files
- **Status:** Implemented

### NFR-6: Security

- API keys read from `.env` file, never hardcoded
- Input sanitization before LLM calls
- GitHub tokens scoped to minimum required permissions
- **Status:** Implemented (hardening ongoing)

---

## Architecture & Design

### System Architecture

```
User Prompt
    |
    v
[UserPromptSubmit Hook] -> scripts/3-level-flow.py
    |
    v
[LangGraph StateGraph] (orchestrator.py)
    |
    +-- Level -1: Auto-Fix (Unicode, encoding, path checks)
    |
    +-- Level 1:  Context Sync (session, complexity, TOON compression)
    |
    +-- Level 2:  Standards (project detection, policy loading)
    |
    +-- Level 3:  Execution (15-step SDLC pipeline)
            |
            +-- RAG lookup (Qdrant) before each LLM call
            +-- CallGraph analysis at Steps 2, 10, 11
            +-- Integration lifecycle (Jira/Figma/Jenkins/SonarQube)
            +-- MCP tool calls (19 servers, 323 tools)
```

### Technology Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Orchestration | LangGraph | 0.2.0+ | Stateful graph execution with conditional routing |
| LLM Framework | LangChain | 0.1.0+ | LLM abstraction, prompt templates |
| MCP Protocol | FastMCP (mcp) | 1.0+ | Stdio JSON-RPC tool protocol |
| Vector DB | Qdrant | 1.7+ | RAG decision caching, semantic search |
| Language | Python | 3.8+ | Primary implementation language |
| Testing | pytest | 7.0+ | 69 test files, 1,608 passing tests |
| AST Analysis | Python ast | stdlib | Call graph extraction for Python |

### Package Architecture (v1.5.0 Modularization)

| Package | Pattern | Files | Replaces |
|---------|---------|-------|---------|
| `core/` | Decorator + Factory | 7 | 25+ copy-pasted loguru blocks, 9 integration hooks, 15+ step wrappers |
| `state/` | — | 6 | `flow_state.py` (1,131 lines monolith) |
| `routing/` | — | 5 | Routing functions embedded in `orchestrator.py` |
| `helper_nodes/` | — | 6 | Helper node functions embedded in `orchestrator.py` |
| `diagrams/` | Strategy | 15 | `uml_generators.py` (1,556 lines monolith) |
| `parsers/` | Abstract Factory | 8 | `call_graph_builder.py` (1,419 lines monolith) |
| `sonarqube/` | Facade | 6 | `sonarqube_scanner.py` (1,639 lines monolith) |
| `integrations/` | Abstract Factory + Template | 7 | Scattered lifecycle code in 3+ files |
| `pipeline_builder.py` | Builder | 1 | `create_flow_graph()` inline in orchestrator |

---

## Implementation Status

### Completed Features (v1.5.0)

- [x] 4-Level pipeline (Level -1, 1, 2, 3)
- [x] 15-step SDLC automation
- [x] 19 MCP servers (323 tools)
- [x] RAG decision caching (Qdrant, 4 collections)
- [x] Hybrid LLM inference (4 providers, GPU-first)
- [x] AST call graph analysis (4 languages)
- [x] 13 UML diagram types
- [x] Jira full lifecycle integration
- [x] Figma design-to-code integration
- [x] Jenkins CI/CD integration
- [x] SonarQube scan + auto-fix loop
- [x] Hook system (4 hook types)
- [x] Policy system (63 policies)
- [x] Token optimization (60-85% savings)
- [x] Session management + TOON compression
- [x] Checkpoint recovery
- [x] **Modular architecture: 9 packages, design patterns** (v1.5.0)
- [x] Backward-compatible shims for all refactored modules

### In Progress

- [ ] Code coverage measurement (pytest --cov, 70% threshold)
- [ ] GitHub Actions CI pipeline
- [ ] Docker containerization

### Planned

- [ ] PyPI package (`pip install claude-workflow-engine`)
- [ ] CLI interface (`cwe run "fix the bug"`)
- [ ] Configuration wizard for first-time setup
- [ ] Multi-region / team deployment

---

## Testing Strategy

### Unit Testing

- Framework: pytest
- Test files: 69+
- Passing: 1,608 tests
- Coverage target: 70%+

### Integration Testing

- Full pipeline integration tests at `tests/integration/`
- MCP server tests: `pytest tests/test_*mcp*.py`
- CallGraph tests: `pytest tests/test_call_graph_builder.py tests/test_call_graph_analyzer.py`
- RAG tests: `pytest tests/test_rag_integration.py`

### Known Failing Tests (Pre-existing)

- `tests/test_vector_db_mcp_server.py` — requires live Qdrant instance (infra dependency)
- `tests/test_recovery_handler.py::test_save_step_checkpoint_success` — pre-existing fixture issue

---

## Deployment & Operations

### Deployment Process

1. Developer runs `git clone` and `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, fill in API keys
3. Run `python scripts/sync-mcp-servers.py` to register MCP servers in `~/.claude/settings.json`
4. Pipeline triggers automatically via Claude Code hook on every user prompt

### Operational Requirements

- **Monitoring:** Per-step JSONL telemetry, metrics aggregator CLI (`metrics_aggregator.py`)
- **Logging:** Structured loguru / stdlib logging throughout
- **Recovery:** Checkpoint at every step boundary; resume via `--resume` flag
- **Backup:** Session data backed up to `BackupManager` on each checkpoint

---

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| Qdrant unavailable | Medium | Medium | RAG skipped, LLM fallback used directly |
| All LLM providers fail | High | Low | 4-provider fallback chain; pipeline halts gracefully |
| Jira/Figma API unavailable | Low | Medium | Non-blocking; pipeline continues without that integration |
| Large codebase exceeds CallGraph limits | Medium | Low | MAX_FILES=300, MAX_FILE_SIZE_KB=100 in `parsers/config.py` |
| Windows encoding issues | Medium | Low | ASCII-only .py files; path_resolver.py for cross-platform paths |

---

**Last Updated:** 2026-03-21
**Next Review:** 2026-06-21
