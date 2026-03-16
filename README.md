# Claude Workflow Engine

**Version:** 7.4.0
**Status:** Active Development
**Last Updated:** 2026-03-16

---

## Overview

Claude Workflow Engine is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It handles session management, coding standards enforcement, and end-to-end task execution with GitHub integration.

### Key Features

- **3-Level Architecture** - Sync, Standards, and Execution pipelines
- **LangGraph Orchestration** - StateGraph-based parallel and conditional execution
- **14-Step Execution Pipeline** - From task analysis to PR creation
- **10 MCP Servers** - 91 tools via FastMCP protocol (76% code reduction from 27,800 LOC)
- **Policy System** - 43 policies for sync, standards, and execution
- **Hybrid Inference** - GPU-first (Ollama) + Claude API fallback routing
- **Token Optimization** - AST navigation, context dedup, smart read (60-85% savings)
- **GitHub Integration** - PyGithub + gh CLI fallback with full merge cycles
- **Hook System** - Pre/post tool enforcement with MCP direct imports

---

## Quick Start

### Prerequisites

- Python 3.8+
- Ollama (optional, for local inference)
- GitHub CLI (`gh`) installed and authenticated

### Installation

```bash
git clone https://github.com/techdeveloper-org/claude-workflow-engine.git
cd claude-workflow-engine
pip install -r requirements.txt
```

### Running the Pipeline

```bash
# Full 3-level flow
python scripts/3-level-flow.py --task "your task description"

# Quick mode (skip Level 2 standards)
python scripts/3-level-flow-quick.py --task "your task description"
```

---

## Architecture

### 3-Level Pipeline

```
Level -1: Auto-Fix (encoding, Unicode fixes)
    |
Level 1: Sync (session, context, TOON compression)
    |
Level 2: Standards (coding standards enforcement)
    |
Level 3: Execution (14-step task pipeline)
    |-- Step 0:  Task Analysis + Prompt Generation
    |-- Step 1:  Plan Mode Decision
    |-- Step 2:  Plan Execution (conditional)
    |-- Step 3:  Task Breakdown
    |-- Step 4:  Model Selection
    |-- Step 5:  Skill/Agent Selection
    |-- Step 6:  Skill Validation
    |-- Step 7:  Context Reading + Prompt Synthesis
    |-- Step 8:  GitHub Issue Creation
    |-- Step 9:  Branch Creation + Git Commit
    |-- Step 10: Implementation
    |-- Step 11: Pull Request (with code review loop)
    |-- Step 12: Issue Closure
    |-- Step 13: Documentation Update
    |-- Step 14: Final Summary
```

### Directory Structure

```
/
+-- scripts/              # Pipeline scripts and hooks
|   +-- langgraph_engine/ # Core LangGraph orchestration (72 modules)
|   +-- architecture/     # Architecture system (83 modules)
+-- policies/             # 43 policy definitions
|   +-- 01-sync-system/   # Level 1 policies
|   +-- 02-standards/     # Level 2 policies
|   +-- 03-execution/     # Level 3 policies
+-- src/mcp/              # 10 FastMCP servers (91 tools, 7,235 LOC)
+-- tests/                # Test suite (476 tests, 30 files)
+-- docs/                 # Documentation (40 files)
```

---

## MCP Servers (10 servers, 91 tools)

All registered in `~/.claude/settings.json` and accessible via Claude Code MCP protocol.

| Server | Tools | Purpose |
|--------|-------|---------|
| git-ops | 14 | Git operations (branch, commit, push, pull, stash, post-merge cleanup) |
| github-api | 12 | GitHub (PR, issue, merge, label, build validate, full merge cycle) |
| session-mgr | 14 | Session lifecycle (create, chain, tag, accumulate, finalize, work items) |
| policy-enforcement | 9 | Policy compliance, flow-trace recording, module health check |
| llm-provider | 8 | LLM access (4 providers, hybrid GPU-first routing, model selection) |
| token-optimizer | 10 | Token reduction (AST navigation, smart read, context dedup) |
| pre-tool-gate | 8 | Pre-tool validation (8 policy checks, flag management, skill hints) |
| post-tool-tracker | 6 | Post-tool tracking (progress, commit readiness, tool stats) |
| standards-loader | 6 | Standards discovery (project/framework detection, conflict resolution) |
| skill-manager | 8 | Skill lifecycle (load, search, validate, rank, conflict detection) |

---

## Development

### Testing

```bash
# Run all tests (476 tests)
pytest tests/

# Run MCP server tests only
pytest tests/test_*mcp*.py tests/test_integration_all_mcp.py

# Version sync (updates README, CLAUDE.md from VERSION file)
python scripts/sync-version.py

# Generate MCP tool documentation
python scripts/generate-mcp-docs.py
```

### Key Documentation

- `CLAUDE.md` - Project context and development guidelines
- `WORKFLOW.md` - 14-step execution pipeline specification
- `ARCHITECTURE_QUICK_SUMMARY.md` - Architecture overview
- `LANGGRAPH-ENGINE.md` - Engine implementation details
- `policies/` - All 43 policy definitions

---

## Configuration

See `CLAUDE.md` for project-specific configuration and development guidelines.

---

## License

MIT License - see LICENSE file for details

---

**Maintainers:** TechDeveloper
**Repository:** https://github.com/techdeveloper-org/claude-workflow-engine
**Last Updated:** 2026-03-16
