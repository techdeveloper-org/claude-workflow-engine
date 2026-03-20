# Claude Workflow Engine v1.4.1 - System Requirements Specification

**Document Version:** 3.0
**Release Date:** 2026-03-16
**Last Updated:** 2026-03-16
**Classification:** Enterprise-Grade System Documentation
**Status:** Active

---

## 1. Executive Summary

Claude Workflow Engine v1.4.1 is a 3-level LangGraph-based orchestration pipeline for automating Claude Code development workflows. It provides 16 FastMCP servers (293 tools), 90 LangGraph engine modules, 63 policy definitions, a RAG integration layer with 4 Vector DB collections, and a comprehensive hook system for pre/post tool enforcement.

### Key Statistics

| Metric | Value |
|--------|-------|
| **Version** | 1.4.1 |
| **Pipeline Levels** | 4 (Level -1, Level 1, Level 2, Level 3) |
| **Execution Steps** | 15 (Step 0 through Step 14) |
| **MCP Servers** | 16 |
| **MCP Tools** | 293 |
| **LangGraph Engine Modules** | 90 (84 root + 6 subgraphs) |
| **Policy Files** | 63 (62 .md + 1 .json) |
| **Test Files** | 64 (61 root + 3 integration) |
| **Total Python Files** | 226 |
| **RAG Collections** | 4 |
| **LLM Providers** | 4 (Ollama, Claude CLI, Anthropic API, OpenAI) |
| **Coding Standards** | 10 rule files |
| **Documentation Files** | 46 |

---

## 2. Introduction

### 2.1 Purpose

Claude Workflow Engine orchestrates the complete lifecycle of Claude Code task execution - from prompt analysis to PR creation. It enforces coding standards, manages sessions across multiple windows, provides intelligent model routing, optimizes token usage by 60-85%, and uses RAG-powered decision caching to skip redundant LLM calls.

### 2.2 Scope

The system covers:
- Session management and multi-window isolation
- Coding standards detection and enforcement
- 15-step task execution pipeline (Step 0 through Step 14)
- Pre/post tool enforcement hooks
- Git and GitHub automation (branch, commit, PR, merge, issue lifecycle)
- LLM provider routing (Ollama, Claude CLI, Anthropic API, OpenAI)
- Token optimization (AST navigation, context deduplication, smart reads)
- Skill/agent lifecycle management
- RAG integration with Vector DB for decision caching
- Cross-session learning and pattern detection

### 2.3 Definitions

| Term | Definition |
|------|-----------|
| **MCP Server** | FastMCP-based tool server communicating via JSON-RPC over stdio |
| **Level -1** | Auto-fix layer (encoding, Unicode, Windows path checks) |
| **Level 1** | Sync system (session, context, complexity, TOON compression) |
| **Level 2** | Standards system (project detection, framework standards, tool optimization, MCP discovery) |
| **Level 3** | Execution system (15-step pipeline from task analysis to PR creation) |
| **Hook Mode** | Steps 0-7 in PreToolUse hook, Steps 8-14 deferred to Stop hook |
| **Full Mode** | Steps 0-14 run sequentially without user interaction |
| **TOON** | Compressed context object (10x token reduction) |
| **RAG** | Retrieval-Augmented Generation - vector similarity lookup before LLM calls |
| **FlowState** | TypedDict state definition flowing through the LangGraph StateGraph |

---

## 3. System Architecture

### 3.1 Pipeline Architecture

```
USER PROMPT
    |
    v
Level -1: Auto-Fix Enforcement
    |-- Check 1: node_unicode_fix (UTF-8 encoding on Windows)
    |-- Check 2: node_encoding_validation (ASCII-only .py files)
    |-- Check 3: node_windows_path_check (forward slashes)
    |-- Merge: level_minus1_merge_node
    |-- On failure: Interactive auto-fix or skip (max 3 retries)
    |
    v
Level 1: Context Sync (5-step with parallel execution)
    |-- Step 1: node_session_loader (MUST BE FIRST)
    |-- Step 2: PARALLEL [node_complexity_calculation + node_context_loader]
    |-- Step 3: node_toon_compression (compress + clear memory)
    |-- Step 4: level1_merge_node (output TOON only)
    |-- Step 5: cleanup_level1_memory (free RAM)
    |
    v
Level 2: Standards System (5 nodes)
    |-- Node 1: detect_project_type (Python/Java/JS/TS/Go/Rust...)
    |-- Node 2: node_common_standards (shared coding conventions)
    |-- Node 3: node_java_standards (conditional - Java/Spring only)
    |-- Node 4: node_tool_optimization_standards (tool usage policies)
    |-- Node 5: node_mcp_plugin_discovery (register MCP plugins)
    |
    v
Level 3: 15-Step Execution Pipeline (Step 0-14)
    |-- Step 0:  Task Analysis + Prompt Generation
    |-- Step 1:  Plan Mode Decision
    |-- Step 2:  Plan Execution (conditional - complexity-based model)
    |-- Step 3:  Task/Phase Breakdown
    |-- Step 4:  TOON Refinement
    |-- Step 5:  Skill & Agent Selection (RAG cross-session boost)
    |-- Step 6:  Skill Validation & Download
    |-- Step 7:  Final Prompt Generation (3 files)
    |   [Hook Mode: output to Claude here]
    |-- Step 8:  GitHub Issue Creation
    |-- Step 9:  Branch Creation + Git Setup
    |-- Step 10: Implementation Execution
    |-- Step 11: Pull Request & Code Review (review loop)
    |-- Step 12: Issue Closure (detailed comment)
    |-- Step 13: Documentation Update (SRS, README, CLAUDE.md)
    |-- Step 14: Final Summary (narrative + voice)
    |
    v
RESULT (flow-trace.json + session finalized)
```

### 3.2 MCP Server Architecture (16 Servers, 293 Tools)

All servers use FastMCP framework, communicate via stdio, and are registered in `~/.claude/settings.json`.

| # | Server | File | Tools | Purpose |
|---|--------|------|-------|---------|
| 1 | **git-ops** | git_mcp_server.py | 14 | Git operations (branch, commit, push, pull, stash, log, diff, fetch, post-merge cleanup, origin URL) |
| 2 | **github-api** | github_mcp_server.py | 12 | GitHub (create/close issue, PR, merge with gh CLI fallback, label, build validate, full merge cycle, issue branch) |
| 3 | **session-mgr** | session_mcp_server.py | 14 | Session lifecycle (create with ID gen, chain parent/child, tag with auto-extract, accumulate, finalize, work items, search, archive) |
| 4 | **policy-enforcement** | enforcement_mcp_server.py | 11 | Policy compliance (enforce steps 0-13, flow-trace recording, compliance verify, module health, all-server health check) |
| 5 | **llm-provider** | llm_mcp_server.py | 8 | LLM access (4 providers: Ollama/Claude CLI/Anthropic/OpenAI, hybrid GPU-first routing, model selection, discover models, commit title gen) |
| 6 | **token-optimizer** | token_optimization_mcp_server.py | 10 | Token reduction (optimize any tool call, AST code navigation for Java/Python/TS/JS, smart read, context dedup, budget monitor) |
| 7 | **pre-tool-gate** | pre_tool_gate_mcp_server.py | 8 | Pre-tool validation (8 policy checks, task breakdown flag, skill flag, level completion, failure patterns, skill hints) |
| 8 | **post-tool-tracker** | post_tool_tracker_mcp_server.py | 6 | Post-tool tracking (usage logging, progress increment, flag clearing, commit readiness, tool stats) |
| 9 | **standards-loader** | standards_loader_mcp_server.py | 7 | Standards discovery (project type detect, framework detect, load from 4 sources with priority, conflict resolve, hot-reload, list available) |
| 10 | **skill-manager** | skill_manager_mcp_server.py | 8 | Skill lifecycle (load all/single, search by keyword/tag, validate capabilities, rank by relevance, conflict detect, agent load) |
| 11 | **vector-db** | vector_db_mcp_server.py | 11 | Vector RAG (Qdrant backend, 4 collections, semantic search, bulk index, node decision storage, similar lookup, collection stats) |
| 12 | **uml-diagram** | uml_diagram_mcp_server.py | 30 | UML generation (13 diagram types: class, package, component, sequence, activity, state, ER, deployment, use-case, CallGraph, timeline, mind-map, data-flow; AST + LLM + Mermaid/PlantUML, Kroki.io render) |
| 13 | **llm-router** | llm_router_mcp_server.py | 8 | Intelligent LLM routing (selects best provider based on task type, complexity, and availability; no direct LLM calls) |
| 14 | **ollama-provider** | ollama_mcp_server.py | 10 | Local Ollama GPU inference (model management, generation, health check; stdlib-only, no SDK) |
| 15 | **anthropic-provider** | anthropic_mcp_server.py | 8 | Anthropic Claude API direct access (Claude model generation, health, cost estimation) |
| 16 | **openai-provider** | openai_mcp_server.py | 8 | OpenAI GPT direct access (text generation, health, model list, cost estimation; stdlib-only) |

### 3.3 RAG Integration Architecture

```
Every LangGraph Node:
  1. BEFORE LLM call: RAG lookup in node_decisions collection
     - If confidence >= step threshold: return cached decision (skip LLM)
     - If confidence < threshold: proceed with LLM call
  2. AFTER node completes: Store decision in Vector DB

Step-Specific Confidence Thresholds:
  Step 0  (Task Analysis):     0.85
  Step 1  (Plan Decision):     0.80
  Step 2  (Plan Execution):    0.88
  Step 5  (Skill Selection):   0.82
  Step 7  (Final Prompt):      0.90
  Step 8  (Issue Label):       0.78
  Step 11 (PR Review):         0.85
  Step 13 (Docs Update):       0.80
  Step 14 (Summary):           0.75

Vector DB Collections (Qdrant):
  1. node_decisions  - Per-node decision history with full context
  2. sessions        - Session-level summaries
  3. flow_traces     - Step-level execution data
  4. tool_calls      - Tool usage patterns
```

### 3.4 Hook System Architecture

| Hook | Script | MCP Integration | Trigger |
|------|--------|-----------------|---------|
| **UserPromptSubmit** | script-chain-executor.py -> 3-level-flow.py | session_hooks.accumulate_request() | Every user message |
| **PreToolUse** | pre-tool-enforcer.py | token-optimizer, skill-manager MCP imports | Before every tool call |
| **PostToolUse** | post-tool-tracker.py | post-tool-tracker MCP imports | After every tool call |
| **Stop** | stop-notifier.py | session_hooks.finalize_session() | Session end (auto PR + Steps 12-14) |

### 3.5 Directory Structure

```
claude-insight/
+-- scripts/                          # Pipeline scripts and hooks
|   +-- langgraph_engine/             # Core orchestration (90 modules: 84 root + 6 subgraph files)
|   |   +-- orchestrator.py           # Main StateGraph pipeline
|   |   +-- flow_state.py             # FlowState TypedDict
|   |   +-- rag_integration.py        # RAG layer
|   |   +-- subgraphs/               # 6 subgraph modules
|   +-- architecture/                 # Active pipeline scripts
+-- policies/                         # 63 policy definitions (62 .md + 1 .json)
|   +-- 00-auto-fix-system/           # Level -1 policies
|   +-- 01-sync-system/               # Level 1 policies
|   +-- 02-standards-system/          # Level 2 policies
|   +-- 03-execution-system/          # Level 3 policies (15 steps: 0-14)
+-- src/mcp/                          # 16 FastMCP servers (293 tools)
|   +-- session_hooks.py              # Bridge: direct Python import for MCP tools
+-- tests/                            # 64 test files (61 root + 3 integration)
|   +-- integration/                  # 3 integration test files
+-- docs/                             # 46 documentation files
+-- rules/                            # 10 coding standard definitions
+-- VERSION                           # Single source of truth (1.4.1)
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
| FR-SESSION-09 | Search sessions by tag, date, content | session_search | Done |
| FR-SESSION-10 | List all active sessions with metadata | session_list | Done |
| FR-SESSION-11 | Save session state to disk | session_save | Done |
| FR-SESSION-12 | Load session state from disk | session_load | Done |
| FR-SESSION-13 | Query session data by key path | session_query | Done |
| FR-SESSION-14 | Complete work items with status | session_complete_work_item | Done |

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
| FR-POLICY-09 | Verify compliance across all policy steps | verify_compliance | Done |
| FR-POLICY-10 | Check module health (all MCP servers) | check_all_mcp_servers_health | Done |

### 4.3 LLM Provider Management (FR-LLM)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-LLM-01 | Support 4 providers (Ollama, Claude CLI, Anthropic, OpenAI) | llm_generate | Done |
| FR-LLM-02 | Automatic fallback chain (provider A fails -> try B) | llm_generate | Done |
| FR-LLM-03 | GPU-first routing for fast steps | llm_hybrid_generate | Done |
| FR-LLM-04 | Step-aware model classification (15 steps) | llm_classify_step | Done |
| FR-LLM-05 | Intelligent model selection by complexity | llm_select_model | Done |
| FR-LLM-06 | Auto-discover local Ollama models | llm_discover_models | Done |
| FR-LLM-07 | Generate commit titles from staged diff | llm_git_commit_title | Done |
| FR-LLM-08 | Health check with async inference test | llm_health_check | Done |

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
| FR-STD-01 | Detect project type (10+ languages) | detect_project_type | Done |
| FR-STD-02 | Detect framework within language | detect_framework | Done |
| FR-STD-03 | Load from 4 sources with priority (custom>team>framework>language) | load_standards | Done |
| FR-STD-04 | Priority-based conflict resolution | resolve_standard_conflicts | Done |
| FR-STD-05 | Hot-reload standards on change | hot_reload_standards | Done |
| FR-STD-06 | List all available standards | list_available_standards | Done |
| FR-STD-07 | Tool optimization standards loading | load_tool_optimization | Done |

### 4.7 Skill Management (FR-SKILL)

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-SKILL-01 | Load all skills/agents from ~/.claude/ | skill_load_all, agent_load_all | Done |
| FR-SKILL-02 | Search by keyword, tag, project type | skill_search | Done |
| FR-SKILL-03 | Validate skill against required capabilities | skill_validate | Done |
| FR-SKILL-04 | Rank skills by task relevance | skill_rank | Done |
| FR-SKILL-05 | Detect conflicts (exclusive, domain, explicit) | skill_detect_conflicts | Done |

### 4.8 RAG & Vector DB (FR-RAG) - NEW in v7.5.0

| ID | Requirement | MCP Tool | Status |
|----|-------------|----------|--------|
| FR-RAG-01 | Store node decisions with full context in Vector DB | vector_bulk_index | Done |
| FR-RAG-02 | Semantic similarity search across decisions | vector_search_similar | Done |
| FR-RAG-03 | Per-step confidence thresholds for RAG reuse | rag_integration.py | Done |
| FR-RAG-04 | 4 collections: node_decisions, sessions, flow_traces, tool_calls | vector_db_mcp_server.py | Done |
| FR-RAG-05 | Skip LLM call when RAG confidence >= threshold | rag_integration.py | Done |
| FR-RAG-06 | Cross-session learning for skill selection | rag_integration.py | Done |
| FR-RAG-07 | Bulk indexing for batch operations | vector_bulk_index | Done |
| FR-RAG-08 | Collection statistics and health monitoring | vector_collection_stats | Done |

### 4.9 Level 3 Execution Steps (FR-EXEC)

| ID | Step | Requirement | Status |
|----|------|-------------|--------|
| FR-EXEC-00 | Step 0 | Task analysis: type classification + complexity scoring + initial breakdown | Done |
| FR-EXEC-01 | Step 1 | Plan mode decision based on TOON + complexity | Done |
| FR-EXEC-02 | Step 2 | Plan execution with complexity-based model selection (Haiku/Sonnet/Opus) | Done |
| FR-EXEC-03 | Step 3 | Task/phase breakdown with dependencies and execution order | Done |
| FR-EXEC-04 | Step 4 | TOON refinement: keep essentials, delete intermediates | Done |
| FR-EXEC-05 | Step 5 | Skill & agent selection with RAG cross-session boost | Done |
| FR-EXEC-06 | Step 6 | Skill validation and download of missing skills | Done |
| FR-EXEC-07 | Step 7 | Final prompt generation (3 files: system, user, combined) | Done |
| FR-EXEC-08 | Step 8 | GitHub issue creation with label classification | Done |
| FR-EXEC-09 | Step 9 | Branch creation ({label}/issue-{id}) with stash safety | Done |
| FR-EXEC-10 | Step 10 | Implementation execution with tool optimization | Done |
| FR-EXEC-11 | Step 11 | PR creation + automated code review loop | Done |
| FR-EXEC-12 | Step 12 | Issue closure with detailed implementation comment | Done |
| FR-EXEC-13 | Step 13 | Documentation update (SRS, README, CLAUDE.md) | Done |
| FR-EXEC-14 | Step 14 | Final summary generation (narrative format) | Done |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| ID | Requirement | Target | Status |
|----|-------------|--------|--------|
| NFR-PERF-01 | MCP tool call latency | <50ms per call | Done |
| NFR-PERF-02 | Token reduction on tool calls | 60-85% savings | Done |
| NFR-PERF-03 | AST navigation vs full read savings | 80-95% savings | Done |
| NFR-PERF-04 | Test suite execution time | <20 seconds | Done |
| NFR-PERF-05 | Hook subprocess elimination | MCP direct imports | Done |
| NFR-PERF-06 | Level 1 parallel execution speedup | ~4x (8s -> 2s) | Done |
| NFR-PERF-07 | RAG lookup latency | <100ms per lookup | Done |
| NFR-PERF-08 | TOON compression ratio | 10x token reduction | Done |

### 5.2 Compatibility

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-COMPAT-01 | Windows 11 (cp1252 encoding safe) | Done |
| NFR-COMPAT-02 | Python 3.8+ | Done |
| NFR-COMPAT-03 | ASCII-only in all Python files | Done |
| NFR-COMPAT-04 | Cross-platform paths via path_resolver.py | Done |
| NFR-COMPAT-05 | LangGraph 1.0.10+ | Done |

### 5.3 Reliability

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-REL-01 | All MCP tools return JSON with success field | Done |
| NFR-REL-02 | Non-blocking hooks (never crash pipeline) | Done |
| NFR-REL-03 | Fallback paths (MCP fail -> subprocess) | Done |
| NFR-REL-04 | Auto-expire stale flags (60min/90sec TTL) | Done |
| NFR-REL-05 | Atomic file writes (.tmp -> rename) | Done |
| NFR-REL-06 | MemorySaver checkpointing for recovery | Done |
| NFR-REL-07 | Graceful degradation when Vector DB unavailable | Done |
| NFR-REL-08 | Max 3 retry attempts for Level -1 auto-fix | Done |

### 5.4 Maintainability

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-MAINT-01 | Single VERSION file as source of truth | Done |
| NFR-MAINT-02 | Auto-doc generation from @mcp.tool() decorators | Done |
| NFR-MAINT-03 | Comprehensive test suite (45 files) | Done |
| NFR-MAINT-04 | MCP health check for all 11 servers | Done |
| NFR-MAINT-05 | Structured error hierarchy (WorkflowEngineError) | Done |
| NFR-MAINT-06 | Lazy imports to avoid import-time side effects | Done |

### 5.5 Security

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-SEC-01 | No secrets in committed files | Done |
| NFR-SEC-02 | GitHub token via environment variable only | Done |
| NFR-SEC-03 | Stash safety before branch operations | Done |
| NFR-SEC-04 | Input validation on all MCP tool parameters | Done |

---

## 6. LangGraph Engine Modules (90 total)

### 6.1 Core Modules

| Module | File | Size | Purpose |
|--------|------|------|---------|
| Orchestrator | orchestrator.py | 59K | Main StateGraph with all routing |
| FlowState | flow_state.py | 45K | TypedDict state definition |
| RAG Integration | rag_integration.py | 16K | Vector DB decision caching |
| Hybrid Inference | hybrid_inference.py | 31K | GPU-first LLM routing |
| Skill Manager | skill_manager.py | 30K | Skill lifecycle management |
| Conflict Resolver | conflict_resolver.py | 27K | Skill/standard conflict resolution |
| Documentation Generator | documentation_generator.py | 29K | Auto-documentation |
| Performance Benchmarks | performance_benchmarks.py | 26K | Benchmark collection |
| Review Criteria | review_criteria.py | 27K | Code review rules |

### 6.2 Subgraph Modules

| Module | File | Size | Purpose |
|--------|------|------|---------|
| Level -1 | level_minus1.py | 28K | Auto-fix enforcement (3 checks) |
| Level 1 | level1_sync.py | 37K | Context sync + TOON compression |
| Level 2 | level2_standards.py | 15K | Standards loading with conditionals |
| Level 3 v1 | level3_execution.py | 97K | Original pipeline (DEPRECATED) |
| Level 3 v2 | level3_execution_v2.py | 36K | Refactored v2 with RAG integration |

---

## 7. Architecture Module Breakdown (83 total)

### 7.1 Sync System (01-sync-system)

| Subsystem | Modules | Purpose |
|-----------|---------|---------|
| Context Management | 3 | Context monitor, pruning, management policy |
| Pattern Detection | 3 | Cross-project patterns, detection, application |
| Session Management | 11 | Full session lifecycle (create, chain, search, archive) |
| User Preferences | 5 | Preference detection, tracking, loading |

### 7.2 Standards System (02-standards-system)

| Module | Purpose |
|--------|---------|
| coding-standards-enforcement-policy.py | Main enforcement logic |
| common-standards-policy.py | Shared standards across languages |
| standards-loader.py | Standards file discovery and loading |

### 7.3 Execution System (03-execution-system)

| Subsystem | Modules | Purpose |
|-----------|---------|---------|
| Code Graph Analysis | 1 | NetworkX-based code graph analysis (32K) |
| Context Reading | 1 | Project context reader |
| Prompt Generation | 5 | Prompt gen, AI task detection, anti-hallucination |
| Task Breakdown | 4 | Auto-analysis, tracking, phase enforcement |
| Plan Mode | 4 | Plan suggestion, decision, session archival |
| Model Selection | 6 | Intelligent model selector, decision engine (85K) |
| Skill/Agent Selection | 8 | Adaptive registry, auto-selection (54K) |
| Tool Optimization | 8 | AST navigator, smart read, interceptor (100K) |
| Progress Tracking | 4 | Task phase enforcement, progress tracking |
| Git Commit | 3 | Auto-commit policy, version release (80K) |
| Session Save | 1 | Session step |
| Failure Prevention | 3 | Common failures prevention (84K), failure KB |
| GitHub Integration | 5 | Branch, issue, PR, implementation, close |

---

## 8. Test Coverage

### 8.1 Test Files (64 total)

| Category | Files | Purpose |
|----------|-------|---------|
| MCP Server Tests | 14 | Individual server validation (git, github, session, enforcement, llm, token, pre-tool, post-tool, standards, skill, vector-db, uml, base clients/decorators/persistence) |
| Integration Tests | 3 | End-to-end pipeline and failure scenarios (tests/integration/) |
| LangGraph Engine Tests | 8 | Orchestration, levels -1/1/2/3, v2, documentation manager |
| CallGraph Tests | 2 | Call graph builder and analyzer |
| Feature Tests | 14 | RAG, UML, step11 review, task modules, enhancements, new components, cache, checkpoint |
| Robustness & Hook Tests | 8 | Error infrastructure, recovery, retry, pre/post tool enforcer, stop notifier |
| Utility & Root Tests | 8 | Architecture smoke, root scripts, session, skill management, standards, parallel mode, policies, prompt generator, window isolation |
| Runner / Config | 7 | conftest.py, quick_test.py, run_all_tests.py and legacy test scripts |

### 8.2 Integration Test Suites

| File | Size | Purpose |
|------|------|---------|
| test_all_14_steps.py | 62K | Complete 15-step pipeline validation |
| test_failure_scenarios.py | 57K | Comprehensive failure scenario testing |

---

## 9. Version History

| Version | Date | Changes |
|---------|------|---------|
| **7.5.0** | 2026-03-16 | RAG integration, 11th MCP server (vector-db, 11 tools), cross-session learning, 109 total tools, stop hook autonomy, module refactoring |
| 7.4.0 | 2026-03-16 | Dynamic versioning, SRS rewrite, MCP health checks, auto-doc generator |
| 7.3.0 | 2026-03-16 | 10 MCP servers (91 tools), hook migration to MCP direct imports, 476 tests |
| 7.2.0 | 2026-03-15 | 7 design patterns, Anthropic API as 4th LLM provider, strategy pattern |
| 5.7.0 | 2026-03-14 | Monitoring system removed, workflow-only repo |
| 5.6.0 | 2026-03-14 | LangGraph orchestration pipeline |
| 5.0.0 | 2026-03-10 | Initial unified policy enforcement framework |

---

**Document Version:** 3.0 | **Last Updated:** 2026-03-16

*Version synced from VERSION file via scripts/sync-version.py*
