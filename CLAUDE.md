# Claude Workflow Engine - Project Context

**Project:** Claude Workflow Engine
**Version:** 5.6.0
**Type:** LangGraph Orchestration Pipeline
**Last Updated:** 2026-03-14

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
|   +-- langgraph_engine/ # Core LangGraph orchestration (58 modules)
|   +-- agents/           # Automation agents
|   +-- architecture/     # Architecture documentation
+-- policies/             # 40+ policy definitions
|   +-- 01-sync-system/   # Level 1 policies
|   +-- 02-standards/     # Level 2 policies
|   +-- 03-execution/     # Level 3 policies
+-- src/                  # Shared utilities
|   +-- mcp/              # MCP enforcement server
|   +-- services/         # Claude API integration
|   +-- utils/            # Path resolver, imports
+-- tests/                # Test suite
+-- docs/                 # Documentation
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
| GitHub MCP | scripts/langgraph_engine/github_mcp.py | PyGithub wrapper |
| GitHub Router | scripts/langgraph_engine/github_operation_router.py | MCP + CLI hybrid |
| Hooks | scripts/pre-tool-enforcer.py, post-tool-tracker.py | Tool enforcement |

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

**Last Updated:** 2026-03-14


<!-- execution-insight- -->
## Latest Execution Insight

- **Task**: Bug Fix (complexity 4/10)
- **Skill**: langgraph-core
- **Agent**: spring-boot-microservices
- **Date**: 2026-03-15
