# Claude Workflow Engine

**Version:** 7.5.0 | **Status:** Active Development | **Last Updated:** 2026-03-16

---

## Overview

Claude Workflow Engine is a **3-level LangGraph-based orchestration pipeline** for automating Claude Code development workflows. It handles session management, coding standards enforcement, and end-to-end 15-step task execution (Step 0-14) with full GitHub integration, RAG-powered decision caching, and hybrid LLM inference.

### Key Statistics

| Metric | Value |
|--------|-------|
| **Pipeline Levels** | 4 (Level -1, 1, 2, 3) |
| **Execution Steps** | 15 (Step 0 - Step 14) |
| **MCP Servers** | 11 |
| **MCP Tools** | 109 |
| **LangGraph Engine Modules** | 75 (70 root + 5 subgraphs) |
| **Architecture Modules** | 83 |
| **Policy Files** | 44 (43 .md + 1 .json) |
| **Test Files** | 45 (38 test_*.py + 2 integration) |
| **Total Python Files** | 258 |
| **MCP Server LOC** | 8,400+ |
| **Documentation Files** | 40 |
| **RAG Collections** | 4 (node_decisions, sessions, flow_traces, tool_calls) |

### Key Features

- **3-Level Architecture** - Auto-fix, Sync, Standards, and 15-step Execution (Step 0-14)
- **LangGraph Orchestration** - StateGraph with parallel execution via `Send()` API
- **15-Step Execution Pipeline (Step 0-14)** - From task analysis to PR creation and documentation
- **11 MCP Servers** - 109 tools via FastMCP protocol (stdio JSON-RPC)
- **RAG Integration** - Vector DB decision caching, skip LLM calls when confidence > threshold
- **Policy System** - 44 policies across 3 enforcement levels
- **Hybrid Inference** - GPU-first (Ollama) + Claude API + Anthropic + OpenAI fallback
- **Token Optimization** - AST navigation, context dedup, smart read (60-85% savings)
- **GitHub Integration** - PyGithub + gh CLI fallback with full merge cycles
- **Hook System** - Pre/post tool enforcement with MCP direct imports
- **Session Management** - Cross-window isolation, chaining, TOON compression
- **Cross-Session Learning** - Pattern detection + RAG boost in skill selection

---

## Quick Start

### Prerequisites

- Python 3.8+
- Ollama (optional, for local GPU inference)
- GitHub CLI (`gh`) installed and authenticated
- Qdrant (optional, for RAG vector storage)

### Installation

```bash
git clone https://github.com/techdeveloper-org/claude-insight.git
cd claude-insight
pip install -r requirements.txt
```

### Running the Pipeline

```bash
# Full 3-level flow
python scripts/3-level-flow.py --task "your task description"

# Quick mode (skip Level 2 standards)
python scripts/3-level-flow-quick.py --task "your task description"

# Debug mode
CLAUDE_DEBUG=1 python scripts/3-level-flow.py --task "your task" --summary
```

---

## Architecture

### High-Level Pipeline Flow

```
                    +------------------+
                    |   USER PROMPT    |
                    +--------+---------+
                             |
                    +--------v---------+
                    | LEVEL -1:        |
                    | AUTO-FIX         |
                    | (3 Sequential    |
                    |  Checks)         |
                    +--------+---------+
                             |
                    +--------v---------+
                    | LEVEL 1:         |
                    | CONTEXT SYNC     |
                    | (Session +       |
                    |  Parallel Tasks  |
                    |  + TOON Compress) |
                    +--------+---------+
                             |
                    +--------v---------+
                    | LEVEL 2:         |
                    | STANDARDS        |
                    | (Common + Java   |
                    |  + Tool Opt +    |
                    |  MCP Discovery)  |
                    +--------+---------+
                             |
                    +--------v---------+
                    | LEVEL 3:         |
                    | 15-STEP          |
                    | EXECUTION        |
                    | (Steps 0-14)     |
                    +--------+---------+
                             |
                    +--------v---------+
                    |     RESULT       |
                    +------------------+
```

### Execution Modes

```
Hook Mode (default, CLAUDE_HOOK_MODE=1):
  Steps 0-7  --> PreToolUse hook --> output prompt to Claude
  Steps 8-14 --> Stop hook auto-executes (PR, issue close, docs, summary)

Full Mode (CLAUDE_HOOK_MODE=0):
  Steps 0-14 --> sequential (no user interaction mid-pipeline)
```

---

## Level -1: Auto-Fix Enforcement

**Purpose:** System setup validation with interactive failure handling.

### Architecture Diagram

```
START
  |
  v
+-------------------------+
| node_unicode_fix        |  Check 1: Windows UTF-8 encoding
| - sys.stdout.reconfigure|
| - sys.stderr.reconfigure|
+------------+------------+
             |
             v
+-------------------------+
| node_encoding_validation|  Check 2: ASCII-only Python files
| - Scan all .py files    |
| - Flag non-ASCII chars  |
| - cp1252 compatibility  |
+------------+------------+
             |
             v
+-------------------------+
| node_windows_path_check |  Check 3: Forward slashes in paths
| - No backslash paths    |
| - No drive letter refs  |
| - Cross-platform safe   |
+------------+------------+
             |
             v
+-------------------------+
| level_minus1_merge_node |
+-----+-------------+-----+
      |             |
  ALL PASS      ANY FAIL
      |             |
      v             v
  GO TO       +---------------------+
  LEVEL 1     | ask_level_minus1_fix|
              | - Show failures     |
              | - Ask: Auto-fix or  |
              |   Skip?             |
              +---+------------+----+
                  |            |
              Auto-fix       Skip
                  |            |
                  v            v
              +----------+  GO TO
              | fix &    |  LEVEL 1
              | retry    |  (risky)
              | (max 3)  |
              +----------+

Output:
  level_minus1_status: OK | BLOCKED
  auto_fix_applied: [list of fixes]
  retry_count: 0-3
```

---

## Level 1: Context Sync System

**Purpose:** Collect project context, analyze complexity, compress to TOON object.

### Architecture Diagram

```
FROM LEVEL -1 (status: OK)
  |
  v
+-------------------------------+
| Step 1: node_session_loader   |  MUST BE FIRST
| - Create ~/.claude/logs/      |
|   sessions/{session_id}/      |
| - Save session.json           |
| - Generate unique session ID  |
+---------------+---------------+
                |
                v
    +-----------+-----------+
    |     PARALLEL EXECUTION     |
    |     (LangGraph Send() API) |
    +---------------------------+
    |                           |
    v                           v
+-------------------+  +-------------------+
| node_complexity   |  | node_context      |
| _calculation      |  | _loader           |
|                   |  |                   |
| - Analyze project |  | - Read from       |
|   structure       |  |   PROJECT folder  |
| - Build call      |  | - SRS, README.md, |
|   graph (NetworkX)|  |   CLAUDE.md       |
| - Cyclomatic      |  | - Cache check     |
|   complexity      |  |   (hit/miss)      |
| - Score: 1-10     |  | - Streaming for   |
|   (simple) or     |  |   files >1MB      |
|   1-25 (graph)    |  | - Per-file timeout |
+--------+----------+  +--------+----------+
         |                       |
         +-----------+-----------+
                     |
                     v
+-------------------------------+
| Step 3: node_toon_compression |  NEW!
| - Combine all Level 1 data   |
| - Build TOON object:         |
|   {session_id, complexity,    |
|    files_loaded, context}     |
| - Compress via toons library  |
| - Save: context.toon.json    |
| - Clear raw data from memory  |
| - 10x token reduction        |
+---------------+---------------+
                |
                v
+-------------------------------+
| Step 4: level1_merge_node     |
| - Output: level1_context_toon |
| - TOON schema validation      |
+---------------+---------------+
                |
                v
+-------------------------------+
| Step 5: cleanup_level1_memory |
| - Free remaining RAM vars     |
| - Only TOON object survives   |
+---------------+---------------+
                |
                v
            GO TO LEVEL 2

Output (TOON Object):
  {
    "session_id": "SESSION-YYYYMMDD-HHMMSS-XXXX",
    "complexity_score": 7,
    "files_loaded_count": 3,
    "context": { "srs": true, "readme": true, "claude_md": true }
  }
```

---

## Level 2: Standards System

**Purpose:** Detect project type and load applicable coding standards before execution.

### Architecture Diagram

```
FROM LEVEL 1 (TOON object ready)
  |
  v
+-------------------------------+
| detect_project_type           |
| - Scan project files          |
| - Detect: Python, Java, JS,  |
|   TypeScript, Go, Rust, etc.  |
| - Detect framework: Spring,   |
|   React, Angular, Flask, etc. |
+---------------+---------------+
                |
                v
+-------------------------------+
| node_common_standards         |
| - Load shared standards       |
| - Coding conventions          |
| - Naming rules, formatting    |
| - From policies/02-standards/ |
+---------------+---------------+
                |
                v
         +------+------+
         | is_java?    |
         +------+------+
         |             |
        YES            NO
         |             |
         v             |
+------------------+   |
| node_java_       |   |
| standards        |   |
| - Spring Boot    |   |
| - JPA patterns   |   |
| - REST API rules |   |
+--------+---------+   |
         |             |
         +------+------+
                |
                v
+-------------------------------+
| node_tool_optimization_       |
| standards                     |
| - Read offset/limit rules    |
| - Grep head_limit policies   |
| - Tool call optimization      |
+---------------+---------------+
                |
                v
+-------------------------------+
| node_mcp_plugin_discovery     |
| - Discover available MCP      |
|   plugins for session         |
| - Register for Level 3 use   |
+---------------+---------------+
                |
                v
+-------------------------------+
| level2_merge_node             |
| - Consolidate all standards   |
| - Resolve conflicts (priority:|
|   custom > team > framework   |
|   > language)                 |
+---------------+---------------+
                |
                v
            GO TO LEVEL 3

Output:
  standards_loaded: true
  standards_count: N
  java_standards_loaded: true|false
  mcp_plugins_discovered: [list]
```

---

## Level 3: 15-Step Execution Pipeline (Step 0-14)

**Purpose:** Execute the actual development task using intelligent planning, skills, agents, and full GitHub automation.

### Complete Architecture Diagram

```
FROM LEVEL 2 (standards loaded)
  |
  v
+====================================================+
|              LEVEL 3: 15-STEP PIPELINE              |
+====================================================+

  +---------------------------------------------------+
  | PHASE 1: ANALYSIS & PLANNING (Steps 0-2)          |
  +---------------------------------------------------+
  |                                                     |
  |  Step 0: Task Analysis + Prompt Generation          |
  |  +-----------------------------------------------+  |
  |  | - Analyze user message                        |  |
  |  | - Determine task type (Bug/Feature/Refactor/  |  |
  |  |   Documentation/Test)                         |  |
  |  | - Calculate complexity (1-10)                 |  |
  |  | - Initial task breakdown                      |  |
  |  | - RAG lookup for similar past tasks           |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 1: Plan Mode Decision                         |
  |  +-----------------------------------------------+  |
  |  | - Send TOON + requirement to LOCAL LLM        |  |
  |  | - Evaluate: complexity, architecture, scope   |  |
  |  | - Decision: plan_required = true | false      |  |
  |  | - RAG check (threshold: 0.80)                 |  |
  |  +------------------+------------------+---------+  |
  |                     |                  |            |
  |                plan_required      NOT required      |
  |                     |                  |            |
  |  Step 2: Plan Execution       (skip to Step 3)     |
  |  +---------------------------+                      |
  |  | - Model by complexity:   |                      |
  |  |   1-3: Haiku (fast)      |                      |
  |  |   4-7: Sonnet (balanced) |                      |
  |  |   8-10: Opus (deep)      |                      |
  |  | - Exploration: ALWAYS    |                      |
  |  |   Haiku (cost-effective) |                      |
  |  | - Tool optimization      |                      |
  |  |   enforced (offset/limit)|                      |
  |  +------------+-------------+                      |
  |               |                                     |
  +---------------------------------------------------+
                  |
  +---------------------------------------------------+
  | PHASE 2: PREPARATION (Steps 3-7)                   |
  +---------------------------------------------------+
  |                                                     |
  |  Step 3: Task/Phase Breakdown                       |
  |  +-----------------------------------------------+  |
  |  | - Break plan into structured tasks            |  |
  |  | - target_files, modifications, dependencies   |  |
  |  | - execution_order assignment                  |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 4: TOON Refinement                            |
  |  +-----------------------------------------------+  |
  |  | - Keep: final_plan, task_breakdown,           |  |
  |  |   files_involved, change_descriptions         |  |
  |  | - Delete: exploration data, intermediates     |  |
  |  | - Output: Refined TOON = Execution Blueprint  |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 5: Skill & Agent Selection                    |
  |  +-----------------------------------------------+  |
  |  | - Send refined TOON to LOCAL LLM              |  |
  |  | - Match tasks to skills from ~/.claude/skills/|  |
  |  | - Match tasks to agents from ~/.claude/agents/|  |
  |  | - Pre-filter by project type                  |  |
  |  | - RAG cross-session learning boost            |  |
  |  | - RAG check (threshold: 0.82)                 |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 6: Skill Validation & Download                |
  |  +-----------------------------------------------+  |
  |  | - Validate selected skills exist locally      |  |
  |  | - Download missing from Claude Code GitHub    |  |
  |  | - Prepare skill content for prompt generation |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 7: Final Prompt Generation                    |
  |  +-----------------------------------------------+  |
  |  | - Convert TOON to execution prompt            |  |
  |  | - Generate 3 files:                           |  |
  |  |   system_prompt.txt (full context)            |  |
  |  |   user_message.txt (execution instruction)    |  |
  |  |   prompt.txt (combined, backward compat)      |  |
  |  | - Save to session folder                      |  |
  |  | - Delete TOON from memory                     |  |
  |  | - RAG check (threshold: 0.90)                 |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  +---------------------------------------------------+
                  |
     [Hook Mode: Steps 0-7 complete, output to Claude]
     [Full Mode: Continue to Steps 8-14]
                  |
  +---------------------------------------------------+
  | PHASE 3: GITHUB AUTOMATION (Steps 8-12)            |
  +---------------------------------------------------+
  |                                                     |
  |  Step 8: GitHub Issue Creation                      |
  |  +-----------------------------------------------+  |
  |  | - Analyze prompt.txt content                  |  |
  |  | - Classify label: bug, feature, enhancement,  |  |
  |  |   test, documentation                         |  |
  |  | - Create issue via github-api MCP             |  |
  |  | - RAG check (threshold: 0.78)                 |  |
  |  | - Output: issue_id (e.g., #42)                |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 9: Branch Creation + Git Commit               |
  |  +-----------------------------------------------+  |
  |  | - Switch to main/master                       |  |
  |  | - Create branch: {label}/issue-{id}           |  |
  |  |   e.g., bug/issue-42, feature/issue-170       |  |
  |  | - Stash safety (5-step workflow)              |  |
  |  | - Push branch to remote                       |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 10: Implementation Execution                  |
  |  +-----------------------------------------------+  |
  |  | - Execute tasks from prompt.txt               |  |
  |  | - Tool optimization enforced                  |  |
  |  | - Read with offset/limit, Grep with head_limit|  |
  |  | - Follow task dependencies                    |  |
  |  | - Commit after significant changes            |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 11: Pull Request & Code Review                |
  |  +-----------------------------------------------+  |
  |  | - Create PR: branch --> main/master           |  |
  |  | - Automated code review (skills/agents)       |  |
  |  | - RAG check (threshold: 0.85)                 |  |
  |  +-------+-------------------+-------------------+  |
  |          |                   |                      |
  |      REVIEW PASS        REVIEW FAIL                 |
  |          |                   |                      |
  |      Merge PR         Request changes               |
  |      Close PR         Update implementation         |
  |          |            Re-review (loop)              |
  |          +-------+-------+                          |
  |                  |                                  |
  |  Step 12: Issue Closure                             |
  |  +-----------------------------------------------+  |
  |  | - Close GitHub issue with detailed comment    |  |
  |  | - what_implemented, files_modified,           |  |
  |  |   approach_taken, verification_steps          |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  +---------------------------------------------------+
                  |
  +---------------------------------------------------+
  | PHASE 4: FINALIZATION (Steps 13-14)                |
  +---------------------------------------------------+
  |                                                     |
  |  Step 13: Documentation Update                      |
  |  +-----------------------------------------------+  |
  |  | - Check: SRS.md, README.md, CLAUDE.md         |  |
  |  | - Create if missing, update if exists         |  |
  |  | - Reflect latest changes and architecture     |  |
  |  | - RAG check (threshold: 0.80)                 |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  |  Step 14: Final Summary                             |
  |  +-----------------------------------------------+  |
  |  | - Generate execution summary                  |  |
  |  | - Story-style narrative                       |  |
  |  | - What implemented, changed, evolved          |  |
  |  | - RAG check (threshold: 0.75)                 |  |
  |  | - Store decision in Vector DB                 |  |
  |  +----------------------+------------------------+  |
  |                         |                           |
  +---------------------------------------------------+
                  |
                  v
          +-------+-------+
          | level3_merge  |
          | - Final status|
          |   OK/PARTIAL/ |
          |   FAILED      |
          | - Write flow- |
          |   trace.json  |
          +-------+-------+
                  |
                  v
              END
```

---

## RAG Integration Layer

**Purpose:** Store every node's decision in Vector DB and provide RAG-first lookup before LLM calls to save inference time.

### Architecture Diagram

```
+---------------------------------------------------+
|              RAG DECISION FLOW                     |
+---------------------------------------------------+

  Before LLM Call:
  +------------------+
  | RAG Lookup       |
  | - Query: step +  |
  |   user prompt +  |
  |   context        |
  | - Collection:    |
  |   node_decisions |
  +--------+---------+
           |
     +-----+-----+
     | Confidence |
     | Check      |
     +-----+-----+
     |           |
  >= threshold  < threshold
     |           |
     v           v
  +--------+  +----------+
  | Return |  | Call LLM |
  | cached |  | (normal) |
  | result |  +----+-----+
  +--------+       |
                   v
            +------+------+
            | Store in    |
            | Vector DB   |
            | (for future |
            |  lookups)   |
            +-------------+

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
  1. node_decisions  - Per-node decision history
  2. sessions        - Session-level summaries
  3. flow_traces     - Step-level execution data
  4. tool_calls      - Tool usage patterns
```

---

## MCP Servers (11 Servers, 109 Tools)

All servers use FastMCP framework, communicate via stdio JSON-RPC, and are registered in `~/.claude/settings.json`.

| # | Server | File | Tools | Purpose |
|---|--------|------|-------|---------|
| 1 | **git-ops** | git_mcp_server.py | 14 | Git operations (branch, commit, push, pull, stash, log, diff, fetch, post-merge cleanup, origin URL) |
| 2 | **github-api** | github_mcp_server.py | 12 | GitHub (create/close issue, PR, merge with gh CLI fallback, label, build validate, full merge cycle, issue branch) |
| 3 | **session-mgr** | session_mcp_server.py | 14 | Session lifecycle (create with ID gen, chain parent/child, tag with auto-extract, accumulate, finalize, work items, search, archive) |
| 4 | **policy-enforcement** | enforcement_mcp_server.py | 11 | Policy compliance (enforce steps 0-13, flow-trace recording, compliance verify, module health, MCP system health check) |
| 5 | **llm-provider** | llm_mcp_server.py | 8 | LLM access (4 providers: Ollama/Claude CLI/Anthropic/OpenAI, hybrid GPU-first routing, model selection, discover models, commit title gen) |
| 6 | **token-optimizer** | token_optimization_mcp_server.py | 10 | Token reduction (optimize any tool call, AST code navigation, smart read, context dedup, budget monitor, 60-85% savings) |
| 7 | **pre-tool-gate** | pre_tool_gate_mcp_server.py | 8 | Pre-tool validation (8 policy checks, task breakdown flag, skill flag, level completion, failure patterns, skill hints) |
| 8 | **post-tool-tracker** | post_tool_tracker_mcp_server.py | 6 | Post-tool tracking (usage logging, progress increment, flag clearing, commit readiness, tool stats) |
| 9 | **standards-loader** | standards_loader_mcp_server.py | 7 | Standards discovery (project type detect, framework detect, load from 4 sources, conflict resolve, hot-reload, list available) |
| 10 | **skill-manager** | skill_manager_mcp_server.py | 8 | Skill lifecycle (load all/single, search, validate capabilities, rank by relevance, conflict detect, agent load) |
| 11 | **vector-db** | vector_db_mcp_server.py | 11 | Vector RAG (Qdrant backend, 4 collections, semantic search, bulk index, node decision storage, similar lookup) |

---

## Hook System

| Hook | Script | MCP Integration | Trigger |
|------|--------|-----------------|---------|
| **UserPromptSubmit** | script-chain-executor.py -> 3-level-flow.py | session_hooks.accumulate_request() | Every user message |
| **PreToolUse** | pre-tool-enforcer.py | token-optimizer, skill-manager MCP imports | Before every tool call |
| **PostToolUse** | post-tool-tracker.py | post-tool-tracker MCP imports | After every tool call |
| **Stop** | stop-notifier.py | session_hooks.finalize_session() | Session end (auto PR + Steps 12-14) |

---

## Directory Structure

```
claude-insight/
|
+-- scripts/                          # Pipeline scripts and hooks (31 root .py)
|   +-- langgraph_engine/             # Core LangGraph orchestration
|   |   +-- orchestrator.py           # Main StateGraph pipeline (59K)
|   |   +-- flow_state.py             # FlowState TypedDict (45K)
|   |   +-- rag_integration.py        # RAG layer, node decisions (16K)
|   |   +-- hybrid_inference.py       # GPU-first LLM routing (31K)
|   |   +-- skill_manager.py          # Skill lifecycle (30K)
|   |   +-- ... (65 more modules)     # 70 total root modules
|   |   +-- subgraphs/
|   |       +-- level_minus1.py       # Auto-fix enforcement (28K)
|   |       +-- level1_sync.py        # Context sync + TOON (37K)
|   |       +-- level2_standards.py   # Standards loading (15K)
|   |       +-- level3_execution.py   # 15-step pipeline original (DEPRECATED) (97K)
|   |       +-- level3_execution_v2.py# 15-step v2 with RAG (ACTIVE) (36K)
|   |
|   +-- architecture/                 # Architecture system (83 modules)
|   |   +-- 01-sync-system/           # Session, context, preferences, patterns
|   |   +-- 02-standards-system/      # Coding standards enforcement
|   |   +-- 03-execution-system/      # All 15 steps (Step 0-14) + failure prevention
|   |   +-- testing/                  # Test case policy scripts
|   |
|   +-- agents/                       # Computer-use agent + tools
|   +-- 3-level-flow.py               # Entry point (~100 line wrapper)
|   +-- pre-tool-enforcer.py          # PreToolUse hook
|   +-- post-tool-tracker.py          # PostToolUse hook
|   +-- stop-notifier.py              # Stop hook
|   +-- sync-version.py               # VERSION -> docs version sync
|   +-- generate-mcp-docs.py          # Auto-generate MCP docs
|
+-- policies/                         # 44 policy definitions
|   +-- 01-sync-system/               # Level 1: session, context, preferences, patterns
|   +-- 02-standards-system/          # Level 2: coding standards, common standards
|   +-- 03-execution-system/          # Level 3: all 15 steps (Step 0-14) + failure prevention
|   +-- testing/                      # Test case policies
|
+-- src/
|   +-- mcp/                          # 11 FastMCP servers (109 tools, 8,400+ LOC)
|   |   +-- git_mcp_server.py         # 14 tools
|   |   +-- github_mcp_server.py      # 12 tools
|   |   +-- session_mcp_server.py     # 14 tools
|   |   +-- enforcement_mcp_server.py # 11 tools
|   |   +-- llm_mcp_server.py         # 8 tools
|   |   +-- token_optimization_mcp_server.py  # 10 tools
|   |   +-- pre_tool_gate_mcp_server.py       # 8 tools
|   |   +-- post_tool_tracker_mcp_server.py   # 6 tools
|   |   +-- standards_loader_mcp_server.py    # 7 tools
|   |   +-- skill_manager_mcp_server.py       # 8 tools
|   |   +-- vector_db_mcp_server.py           # 11 tools
|   |   +-- session_hooks.py          # MCP direct import bridge
|   |   +-- mcp_errors.py             # Structured error responses
|   |
|   +-- services/
|   |   +-- claude_integration.py     # Claude service integration
|   +-- utils/
|       +-- path_resolver.py          # Cross-platform path resolution
|       +-- import_manager.py         # Dynamic import management
|
+-- tests/                            # 45 test files
|   +-- test_*.py                     # 38 root test files
|   +-- integration/
|       +-- test_all_14_steps.py      # Full pipeline integration (62K)
|       +-- test_failure_scenarios.py # Failure scenario testing (57K)
|
+-- docs/                             # 40 documentation files
|   +-- WORKFLOW.md                   # Complete 15-step specification
|   +-- LANGGRAPH-ENGINE.md           # Engine implementation details
|   +-- CHANGELOG.md                  # Version history
|   +-- SYSTEM_REQUIREMENTS_SPECIFICATION.md  # Full SRS
|   +-- ... (36 more docs)
|
+-- rules/                            # 5 coding standard definitions
|   +-- 01-common-standards.md
|   +-- 02-backend-standards.md
|   +-- 03-microservices-standards.md
|   +-- 04-frontend-standards.md
|   +-- 05-security-standards.md
|
+-- VERSION                           # Single source of truth (7.5.0)
+-- CLAUDE.md                         # Project context for Claude Code
+-- README.md                         # This file
+-- requirements.txt                  # Python dependencies
+-- setup.py                          # Package setup
+-- LICENSE                           # MIT License
```

---

## Development

### Testing

```bash
# Run all tests
pytest tests/

# Run MCP server tests only
pytest tests/test_*mcp*.py tests/test_integration_all_mcp.py

# Run integration tests
pytest tests/integration/

# Run RAG integration tests
pytest tests/test_rag_integration.py

# Version sync (updates README, CLAUDE.md, SRS from VERSION file)
python scripts/sync-version.py

# Generate MCP tool documentation
python scripts/generate-mcp-docs.py
```

### Key Documentation

| Document | Location | Purpose |
|----------|----------|---------|
| CLAUDE.md | Root | Project context for Claude Code |
| WORKFLOW.md | docs/ | Complete 15-step pipeline specification |
| SRS | docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md | Full system requirements |
| CHANGELOG.md | docs/ | Version history and changes |
| LANGGRAPH-ENGINE.md | docs/ | Engine implementation details |
| MCP-TOOLS.md | docs/ | MCP server tool reference |
| TESTING_GUIDE.md | docs/ | Testing strategy and guide |

### Configuration

See `.env.example` for environment variables:
- `OLLAMA_ENDPOINT` - Ollama server URL (default: http://localhost:11434)
- `ANTHROPIC_API_KEY` - Claude API key
- `GITHUB_TOKEN` - GitHub personal access token
- `CLAUDE_DEBUG` - Enable debug output (0/1)
- `CLAUDE_HOOK_MODE` - Hook mode (1) or Full mode (0)

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **7.5.0** | 2026-03-16 | RAG integration, 11th MCP server (vector-db), cross-session learning, 109 tools |
| 7.4.0 | 2026-03-16 | Dynamic versioning, SRS rewrite, MCP health checks |
| 7.3.0 | 2026-03-16 | 10 MCP servers (91 tools), hook migration to MCP imports |
| 7.2.0 | 2026-03-15 | 7 design patterns, Anthropic API as 4th LLM provider |
| 5.7.0 | 2026-03-14 | Workflow-only repo (monitoring removed) |
| 5.6.0 | 2026-03-14 | LangGraph orchestration pipeline |
| 5.0.0 | 2026-03-10 | Initial unified policy enforcement framework |

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Maintainers:** TechDeveloper
**Repository:** https://github.com/techdeveloper-org/claude-insight
**Last Updated:** 2026-03-16
