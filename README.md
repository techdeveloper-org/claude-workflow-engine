# Claude Workflow Engine

**Version:** 5.6.0
**Status:** Active Development
**Last Updated:** 2026-03-14

---

## Overview

Claude Workflow Engine is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It handles session management, coding standards enforcement, and end-to-end task execution with GitHub integration.

### Key Features

- **3-Level Architecture** - Sync, Standards, and Execution pipelines
- **LangGraph Orchestration** - StateGraph-based parallel and conditional execution
- **14-Step Execution Pipeline** - From task breakdown to PR creation
- **Policy System** - 40+ policies for sync, standards, and execution
- **Hybrid Inference** - Ollama (local) + Claude API (cloud) routing
- **GitHub Integration** - MCP + gh CLI hybrid with automatic fallback
- **Hook System** - Pre/post tool enforcement with auto-fix

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
    |-- Step 1:  Plan Mode Decision
    |-- Step 2:  Plan Execution (conditional)
    |-- Step 3:  Task Breakdown
    |-- Step 4:  TOON Refinement
    |-- Step 5:  Skill Selection
    |-- Step 6:  Skill Validation & Download
    |-- Step 7:  Implementation
    |-- Step 8:  Git Branch Creation
    |-- Step 9:  Git Commit
    |-- Step 10: Implementation Notes
    |-- Step 11: Pull Request (with code review loop)
    |-- Step 12: Closure
    |-- Step 13: Documentation Update
    |-- Step 14: Summary
```

### Directory Structure

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

---

## Development

### Testing

```bash
pytest tests/
```

### Key Documentation

- `WORKFLOW.md` - 14-step execution pipeline specification
- `ARCHITECTURE_QUICK_SUMMARY.md` - Architecture overview
- `LANGGRAPH-ENGINE.md` - Engine implementation details
- `policies/` - All policy definitions

---

## Configuration

See `CLAUDE.md` for project-specific configuration and development guidelines.

---

## License

MIT License - see LICENSE file for details

---

**Maintainers:** TechDeveloper
**Repository:** https://github.com/techdeveloper-org/claude-workflow-engine
**Last Updated:** 2026-03-14
