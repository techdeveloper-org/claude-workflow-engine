# Claude Workflow Engine v7.4.0 - System Requirements Specification

**Document Version:** 2.0
**Release Date:** 2026-03-16
**Last Updated:** 2026-03-16
**Classification:** Enterprise-Grade System Documentation
**Status:** Active

---

## 1. Executive Summary

Claude Workflow Engine v7.3.0 is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It provides 10 FastMCP servers (95 tools), 72 LangGraph engine modules, 43 policy definitions, and a comprehensive hook system for pre/post tool enforcement.

### Key Statistics

| Metric | Value |
|--------|-------|
| **Version** | 7.4.0 |
| **MCP Servers** | 10 |
| **MCP Tools** | 95 |
| **LangGraph Modules** | 72 |
| **Architecture Modules** | 83 |
| **Policy Files** | 43 |
| **Test Files** | 30 |
| **Tests Passing** | 476 |
| **MCP Server LOC** | 7,235 |
| **Total Project LOC** | ~86,000+ |

---

## 2. Introduction

### 2.1 Purpose

Claude Workflow Engine orchestrates the complete lifecycle of Claude Code task execution - from prompt analysis to PR creation. It enforces coding standards, manages sessions across multiple windows, provides intelligent model routing, and optimizes token usage by 60-85%.

### 2.2 Scope

The system covers:
- Session management and multi-window isolation
- Coding standards detection and enforcement
- 14-step task execution pipeline (Step 0 to Step 14)
- Pre/post tool enforcement hooks
- Git and GitHub automation (branch, commit, PR, merge)
- LLM provider routing (Ollama, Claude CLI, Anthropic API, OpenAI)
- Token optimization (AST navigation, context deduplication, smart reads)
- Skill/agent lifecycle management

### 2.3 Definitions

| Term | Definition |
|------|-----------|
| MCP Server | FastMCP-based tool server communicating via JSON-RPC over stdio |
| Level -1 | Auto-fix layer (encoding, Unicode, Windows path checks) |
| Level 1 | Sync system (session, context, TOON compression) |
| Level 2 | Standards system (project detection, framework standards, conflict resolution) |
| Level 3 | Execution system (14-step pipeline from task analysis to PR creation) |
| Hook Mode | Steps 0-7 in PreToolUse hook, Steps 8-14 deferred to Stop hook |
| Full Mode | Steps 0-14 run sequentially without user interaction |

---

## 3. System Architecture

### 3.1 Pipeline Architecture

```
Level -1: Auto-Fix (encoding, Unicode, Windows path)
    |
Level 1: Sync (session load, context, TOON compression)
    |
Level 2: Standards (project detect, framework standards, conflict resolve)
    |
Level 3: Execution (14-step pipeline)
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

### 3.2 MCP Server Architecture (10 Servers, 95 Tools)

All servers use FastMCP framework, communicate via stdio, and are registered in `~/.claude/settings.json`.

| # | Server | File | Tools | Purpose |
|---|--------|------|-------|---------|
| 1 | git-ops | git_mcp_server.py | 14 | Git operations (branch, commit, push, pull, stash, log, post-merge cleanup, origin URL) |
| 2 | github-api | github_mcp_server.py | 12 | GitHub (create/close issue, PR, merge with gh CLI fallback, label, build validate, merge cycle) |
| 3 | session-mgr | session_mcp_server.py | 14 | Session lifecycle (create with ID gen, chain parent/child, tag with auto-extract, accumulate, finalize, work items, search) |
| 4 | policy-enforcement | enforcement_mcp_server.py | 10 | Policy compliance (enforce steps 0-13, flow-trace recording, compliance verify, module health, MCP health check) |
| 5 | llm-provider | llm_mcp_server.py | 8 | LLM access (4 providers, hybrid GPU-first routing, model selection, discover models, commit title gen) |
| 6 | token-optimizer | token_optimization_mcp_server.py | 10 | Token reduction (optimize any tool call, AST code nav, smart read, context dedup, budget monitor) |
| 7 | pre-tool-gate | pre_tool_gate_mcp_server.py | 8 | Pre-tool validation (8 policy checks, task breakdown flag, skill flag, level completion, failure patterns, skill hints) |
| 8 | post-tool-tracker | post_tool_tracker_mcp_server.py | 6 | Post-tool tracking (usage logging, progress increment, flag clearing, commit readiness, tool stats) |
| 9 | standards-loader | standards_loader_mcp_server.py | 6 | Standards (project type detect, framework detect, load from 4 sources, conflict resolve, list available) |
| 10 | skill-manager | skill_manager_mcp_server.py | 8 | Skill lifecycle (load all/single, search, validate caps, rank, conflict detect, agent load) |

### 3.3 Hook System

| Hook | Script | MCP Integration | Trigger |
|------|--------|-----------------|---------|
| UserPromptSubmit | script-chain-executor.py -> 3-level-flow.py | session_hooks.accumulate_request() | Every user message |
| PreToolUse | pre-tool-enforcer.py | token-optimizer, skill-manager MCP imports | Before every tool call |
| PostToolUse | post-tool-tracker.py | post-tool-tracker MCP imports | After every tool call |
| Stop | stop-notifier.py | session_hooks.finalize_session() | Session end |

### 3.4 Directory Structure

```
/
+-- scripts/                  # Pipeline scripts and hooks
|   +-- langgraph_engine/     # Core LangGraph orchestration (72 modules)
|   +-- architecture/         # Architecture system (83 modules)
|   +-- sync-version.py       # VERSION -> docs version sync
|   +-- generate-mcp-docs.py  # Auto-generate MCP tool reference
+-- policies/                 # 43 policy definitions
|   +-- 01-sync-system/       # Level 1 policies
|   +-- 02-standards/         # Level 2 policies
|   +-- 03-execution/         # Level 3 policies (14 steps)
+-- src/mcp/                  # 10 FastMCP servers (95 tools, 7,235 LOC)
|   +-- session_hooks.py      # Bridge: direct Python import for MCP tools
+-- tests/                    # Test suite (476 tests, 30 files)
+-- docs/                     # Documentation (40+ files)
+-- VERSION                   # Single source of truth for version (7.3.0)
```

---

## 4. Functional Requirements

### 4.1 Session Management (FR-SESSION)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-SESSION-01 | Generate unique session IDs (SESSION-YYYYMMDD-HHMMSS-XXXX) | session_create | Done |
| FR-SESSION-02 | Link parent/child sessions on /clear | session_link | Done |
| FR-SESSION-03 | Auto-extract tags from prompt (30+ tech keywords) | session_tag | Done |
| FR-SESSION-04 | Build ancestor chain context (max 5 ancestors) | session_get_context | Done |
| FR-SESSION-05 | Accumulate per-request data (prompt, skill, complexity) | session_accumulate | Done |
| FR-SESSION-06 | Generate comprehensive markdown summary on close | session_finalize | Done |
| FR-SESSION-07 | Track work items within sessions | session_add_work_item | Done |
| FR-SESSION-08 | Archive sessions older than N days | session_archive | Done |

### 4.2 Policy Enforcement (FR-POLICY)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-POLICY-01 | Block Write/Edit if task breakdown pending | validate_tool_call | Done |
| FR-POLICY-02 | Block Write/Edit if skill selection pending | validate_tool_call | Done |
| FR-POLICY-03 | Verify Level 1 sync complete before coding | check_level_completion | Done |
| FR-POLICY-04 | Verify Level 2 standards loaded before coding | check_level_completion | Done |
| FR-POLICY-05 | Block Windows commands in Bash on win32 | validate_tool_call | Done |
| FR-POLICY-06 | Block non-ASCII in .py files on Windows | validate_tool_call | Done |
| FR-POLICY-07 | Auto-expire stale flags after 90 seconds | _check_flag_with_ttl | Done |
| FR-POLICY-08 | Record policy execution to flow-trace.json | record_policy_execution | Done |

### 4.3 LLM Provider Management (FR-LLM)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-LLM-01 | Support 4 providers (Ollama, Claude CLI, Anthropic, OpenAI) | llm_generate | Done |
| FR-LLM-02 | Automatic fallback chain (provider A fails -> try B) | llm_generate | Done |
| FR-LLM-03 | GPU-first routing for fast steps | llm_hybrid_generate | Done |
| FR-LLM-04 | Step-aware model classification (14 steps) | llm_classify_step | Done |
| FR-LLM-05 | Intelligent model selection by complexity | llm_select_model | Done |
| FR-LLM-06 | Auto-discover local Ollama models | llm_discover_models | Done |
| FR-LLM-07 | Generate commit titles from staged diff | llm_git_commit_title | Done |

### 4.4 Token Optimization (FR-TOKEN)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-TOKEN-01 | Auto-add head_limit=100 to Grep calls | optimize_tool_call | Done |
| FR-TOKEN-02 | Auto-add offset/limit for files >500 lines | optimize_tool_call | Done |
| FR-TOKEN-03 | AST code navigation (Java, Python, TS, JS) | ast_navigate_code | Done |
| FR-TOKEN-04 | Context deduplication (>20% savings threshold) | deduplicate_context | Done |
| FR-TOKEN-05 | Smart file reading strategy recommendation | smart_read_analyze | Done |
| FR-TOKEN-06 | Context budget monitoring (200KB, 85% alert) | context_budget_status | Done |

### 4.5 Git & GitHub Operations (FR-GIT)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-GIT-01 | Branch create with stash safety (5-step workflow) | git_branch_create | Done |
| FR-GIT-02 | Post-merge cleanup (checkout, pull, delete, prune) | git_post_merge_cleanup | Done |
| FR-GIT-03 | Force push support | git_push (force=True) | Done |
| FR-GIT-04 | Create PR with gh CLI fallback for merge | github_merge_pr | Done |
| FR-GIT-05 | Auto-commit + PR in one call | github_auto_commit_and_pr | Done |
| FR-GIT-06 | Build validation before merge | github_validate_build | Done |
| FR-GIT-07 | Full merge cycle (build -> merge -> cleanup) | github_full_merge_cycle | Done |
| FR-GIT-08 | Issue branch creation with auto-naming | github_create_issue_branch | Done |

### 4.6 Standards Management (FR-STD)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-STD-01 | Detect project type (10 languages) | detect_project_type | Done |
| FR-STD-02 | Detect framework within language | detect_framework | Done |
| FR-STD-03 | Load from 4 sources with priority (custom>team>framework>language) | load_standards | Done |
| FR-STD-04 | Priority-based conflict resolution | resolve_standard_conflicts | Done |

### 4.7 Skill Management (FR-SKILL)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-SKILL-01 | Load all skills/agents from ~/.claude/ | skill_load_all, agent_load_all | Done |
| FR-SKILL-02 | Search by keyword, tag, project type | skill_search | Done |
| FR-SKILL-03 | Validate skill against required capabilities | skill_validate | Done |
| FR-SKILL-04 | Rank skills by task relevance | skill_rank | Done |
| FR-SKILL-05 | Detect conflicts (exclusive, domain, explicit) | skill_detect_conflicts | Done |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| ID | Requirement | Target | Status |
|----|-------------|--------|--------|
| NFR-PERF-01 | MCP tool call latency | <50ms per call | Done |
| NFR-PERF-02 | Token reduction on tool calls | 60-85% savings | Done |
| NFR-PERF-03 | AST navigation vs full read savings | 80-95% savings | Done |
| NFR-PERF-04 | Test suite execution time | <20 seconds | Done (15.87s) |
| NFR-PERF-05 | Hook subprocess elimination | MCP direct imports | Done |

### 5.2 Compatibility

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-COMPAT-01 | Windows 11 (cp1252 encoding safe) | Done |
| NFR-COMPAT-02 | Python 3.8+ | Done |
| NFR-COMPAT-03 | ASCII-only in all Python files | Done |
| NFR-COMPAT-04 | Cross-platform paths via path_resolver.py | Done |

### 5.3 Reliability

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-REL-01 | All MCP tools return JSON with success field | Done |
| NFR-REL-02 | Non-blocking hooks (never crash pipeline) | Done |
| NFR-REL-03 | Fallback paths (MCP fail -> subprocess) | Done |
| NFR-REL-04 | Auto-expire stale flags (60min/90sec TTL) | Done |
| NFR-REL-05 | Atomic file writes (.tmp -> rename) | Done |

### 5.4 Maintainability

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-MAINT-01 | Single VERSION file as source of truth | Done |
| NFR-MAINT-02 | Auto-doc generation from @mcp.tool() decorators | Done |
| NFR-MAINT-03 | 476 tests with 100% pass rate | Done |
| NFR-MAINT-04 | MCP health check for all 10 servers | Done |

---

## 6. Version History

| Version | Date | Changes |
|---------|------|---------|
| 7.3.0 | 2026-03-16 | 10 MCP servers (95 tools), hook migration, dynamic versioning |
| 5.7.0 | 2026-03-14 | Monitoring system removed, workflow-only repo |
| 5.6.0 | 2026-03-14 | LangGraph orchestration pipeline |
| 5.0.0 | 2026-03-10 | Initial unified policy enforcement framework |

---

**Document Version:** 2.0 | **Last Updated:** 2026-03-16

*Version synced from VERSION file via scripts/sync-version.py*
