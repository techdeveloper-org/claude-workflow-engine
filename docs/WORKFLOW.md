# Claude Workflow Engine: Complete 3-Level Execution Workflow

**Version:** 7.5.0
**Date:** 2026-03-16
**Status:** ACTIVE IMPLEMENTATION

---

## Overview

The Claude Workflow Engine implements a **3-level enforcement architecture** with automated context optimization, plan mode decision-making, and structured task execution. It supports two execution modes controlled by the `CLAUDE_HOOK_MODE` environment variable.

```
USER PROMPT
    ↓
LEVEL -1: AUTO-FIX ENFORCEMENT (Blocking Checks)
    ↓
LEVEL 1: CONTEXT SYNC (Build TOON Object)
    ↓
LEVEL 2: STANDARDS SYSTEM (Standards Loading)
    ↓
LEVEL 3: 15-STEP EXECUTION PIPELINE (Step 0-14)
    │   ├─ RAG lookup BEFORE each LLM call (skip if cached)
    │   └─ RAG store AFTER each step (cache for future)
    ↓
RESULT
```

**Cross-cutting:** RAG layer runs within each step (not after). State managed via `flow_state.py` (TypedDict). Checkpointed to SQLite via `CheckpointerManager` after each node.

---

## EXECUTION MODES

The pipeline is driven by 4 Claude Code hooks configured in `~/.claude/settings.json`:

| Hook Event | Script | When It Fires | Pipeline Action |
|------------|--------|---------------|-----------------|
| UserPromptSubmit | `3-level-flow.py` | Before first tool call | Runs Level -1 → Level 1 → Level 2 → Level 3 Steps 0-9 |
| PreToolUse | `pre-tool-enforcer.py` | Before each tool use | Validates tool call against policies |
| PostToolUse | `post-tool-tracker.py` | After each tool use | Tracks progress, commit readiness |
| Stop | `stop-notifier.py` | When Claude Code stops | Auto-executes Steps 11-14 (PR, close, docs, summary) |

The pipeline supports two modes via `CLAUDE_HOOK_MODE` environment variable (default: `"1"`).

### Hook Mode (Default, CLAUDE_HOOK_MODE=1)

```
UserPromptSubmit Hook triggers 3-level-flow.py
  ↓
Level -1 → Level 1 → Level 2 → Level 3 Steps 0-9
  ↓
level3_merge → output_node → END
  ↓
Claude Code receives prompt, user works on implementation (Step 10)
  ↓
Stop Hook triggers stop-notifier.py
  ↓
Auto-execute: PR Creation → Step 12 (Issue Close) → Step 13 (Docs) → Step 14 (Summary)
```

- Steps 0-9 run in pipeline (~60s)
- Step 10 = Claude Code itself (user implements with generated prompt)
- Steps 11-14 = auto-executed by stop-notifier.py when Claude stops

### Full Mode (CLAUDE_HOOK_MODE=0)

```
3-level-flow.py runs standalone
  ↓
Level -1 → Level 1 → Level 2 → Level 3 Steps 0-14 (all sequential)
  ↓
Step 11 has conditional retry loop:
  review_passed OR retry >= 3 → Step 12
  review_failed AND retry < 3 → Step 10 (re-implement)
  ↓
level3_merge → output_node → END
```

- All 15 steps run sequentially (~170s)
- Step 11 can loop back to Step 10 (max 3 retries)
- Used for standalone pipeline execution without hooks

### Comparison

| Aspect | Hook Mode (Default) | Full Mode |
|--------|-------------------|-----------|
| `CLAUDE_HOOK_MODE` | `1` | `0` |
| Steps in pipeline | 0-9 | 0-14 |
| Step 10 (Implementation) | Claude Code (user) | Hybrid LLM |
| Steps 11-14 | Stop hook auto-executes | In-pipeline sequential |
| Performance | ~60s | ~170s |
| Use case | Normal workflow | Standalone execution |

### Stop Hook Autonomy (Hook Mode Only)

When Claude Code stops, `stop-notifier.py` detects commits on feature branch and auto-executes:

1. **PR Creation** (`_create_pr_from_pipeline_data()`):
   - Reads Step 7 prompt + Step 0 classification from session folder
   - Builds PR title with prefix: Bug Fix→`fix:`, Feature→`feat:`, Refactor→`refactor:`
   - Creates PR via `github_mcp_server.github_create_pr()`

2. **Step 12** (`_step12_close_issue()`): Reads `step-08.json` for issue ID, closes via GitHub MCP

3. **Step 13** (`_step13_update_docs()`): Runs `sync-version.py` for doc updates

4. **Step 14** (`_step14_generate_summary()`): Writes summary to session directory

**Trigger conditions:** Branch != main/master/HEAD AND commits ahead of main > 0

---

## MCP SERVER ARCHITECTURE

The pipeline is backed by 11 FastMCP servers providing 109 tools, registered in `~/.claude/settings.json`.

| Server | File | Tools | Purpose |
|--------|------|-------|---------|
| git-ops | git_mcp_server.py | 14 | Git (branch, commit, push, pull, stash, diff, fetch, post-merge cleanup) |
| github-api | github_mcp_server.py | 12 | GitHub (PR, issue, merge, label, build validate, full merge cycle) |
| session-mgr | session_mcp_server.py | 14 | Session (create, chain, tag, accumulate, finalize, work items, search) |
| policy-enforcement | enforcement_mcp_server.py | 11 | Policy compliance, flow-trace, module health, system health |
| llm-provider | llm_mcp_server.py | 8 | LLM (4 providers, hybrid GPU-first, model selection, health check) |
| token-optimizer | token_optimization_mcp_server.py | 10 | Token reduction (AST nav, smart read, dedup, 60-85% savings) |
| pre-tool-gate | pre_tool_gate_mcp_server.py | 8 | Pre-tool validation (8 policy checks, skill hints) |
| post-tool-tracker | post_tool_tracker_mcp_server.py | 6 | Post-tool tracking (progress, commit readiness, stats) |
| standards-loader | standards_loader_mcp_server.py | 7 | Standards (project detect, framework detect, hot-reload) |
| skill-manager | skill_manager_mcp_server.py | 8 | Skill lifecycle (load, search, validate, rank, conflicts) |
| vector-db | vector_db_mcp_server.py | 11 | Vector RAG (Qdrant, 4 collections, semantic search, bulk index) |

**Location:** `src/mcp/` | **Framework:** FastMCP (stdio transport) | **Total:** 109 tools

---

## HYBRID LLM PROVIDER CHAIN

The pipeline uses a 4-provider fallback chain for LLM inference, with GPU-first routing.

### Providers (Fallback Order)

| Priority | Provider | Models (Fast / Deep) | Cost |
|----------|----------|---------------------|------|
| 1 | Ollama (local GPU) | qwen2.5:7b / qwen2.5:14b | Free |
| 2 | Claude CLI (subscription) | haiku / sonnet / opus | Subscription |
| 3 | Anthropic API (cloud) | claude-haiku-4-5 / claude-opus-4-6 | API key |
| 4 | OpenAI (cloud) | gpt-4o-mini / gpt-4o | API key |

### Model Tiers

| Tier | Temperature | Use Case |
|------|-------------|----------|
| fast | 0.1 | Classification, JSON, yes/no decisions |
| balanced | 0.3 | Skill selection, code review, synthesis |
| deep | 0.4 | Planning, complex reasoning, architecture |

### Step-to-Model Routing

| Step | Type | Primary Model | Fallback |
|------|------|---------------|----------|
| Step 0 (Task Analysis) | DEEP_LOCAL | qwen2.5:14b | claude-opus-4-6 |
| Step 1 (Plan Decision) | CLASSIFICATION | qwen2.5:7b | claude-opus-4-6 |
| Step 2 (Plan Execution) | DEEP_LOCAL | qwen2.5:14b | claude-opus-4-6 |
| Step 3 (Task Breakdown) | LIGHTWEIGHT | qwen2.5:7b | claude-opus-4-6 |
| Step 4 (TOON Refinement) | NO_LLM | - | - |
| Step 5 (Skill Selection) | DEEP_LOCAL | qwen2.5:14b | claude-opus-4-6 |
| Step 6 (Skill Validation) | NO_LLM | - | - |
| Step 7 (Prompt Generation) | DEEP_LOCAL | qwen2.5:14b | claude-opus-4-6 |
| Steps 8-9 (GitHub/Git) | NO_LLM | - | - |
| Step 10 (Implementation) | COMPLEX | - | claude-opus-4-6 |
| Steps 11-13 (PR/Docs) | NO_LLM | - | - |
| Step 14 (Summary) | DEEP_LOCAL | qwen2.5:14b | claude-opus-4-6 |

### Retry Mechanism

Exponential backoff: `[1s, 2s, 4s, 8s]`, max 3 retries. Retryable errors: timeout, connection, rate_limit, 503/502/500. Non-retryable errors (auth, invalid input) raise immediately.

**Key files:** `llm_call.py` (provider chain), `hybrid_inference.py` (GPU routing), `level3_llm_retry.py` (retry logic), `llm_mcp_server.py` (8 MCP tools)

---

## LEVEL -1: AUTO-FIX ENFORCEMENT

**Subgraph:** `scripts/langgraph_engine/subgraphs/level_minus1.py` | **MAX_ATTEMPTS:** 3

### Purpose
System setup validation with interactive failure handling.

### Flow

```
START
  ↓
Three Sequential Checks:
  1. node_unicode_fix (UTF-8 encoding on Windows)
  2. node_encoding_validation (ASCII-only Python files)
  3. node_windows_path_check (Forward slashes, no backslashes)
  ↓
level_minus1_merge_node
  ├─ If ALL PASS → GO TO LEVEL 1
  └─ If ANY FAIL → ask_level_minus1_fix (INTERACTIVE)
      ├─ Show SPECIFIC failures (✓ PASS / ❌ FAIL for each)
      ├─ Ask user: "Auto-fix or Skip?"
      │
      ├─ Choice: "Auto-fix"
      │  ↓
      │  fix_level_minus1_issues
      │  ├─ Attempt fixes (max 3 retries)
      │  ├─ Reset checks
      │  └─ Retry Level -1
      │     ├─ If pass → GO TO LEVEL 1
      │     └─ If fail → Ask again (Attempt #2, #3...)
      │
      └─ Choice: "Skip"
         └─ GO TO LEVEL 1 (⚠️ NOT RECOMMENDED - will break later)
```

### Key Points

- **3 independent checks** run sequentially
- **Individual failure reporting** - shows exactly which check failed
- **Retry loop with max 3 attempts** - prevents infinite loops
- **Memory cleanup on failure** - no state pollution
- **Original user prompt preserved** throughout

### Output

```json
{
  "level_minus1_status": "OK" | "BLOCKED",
  "failed_nodes": ["encoding_validation", "windows_path_check"],
  "auto_fix_applied": ["Unicode UTF-8 encoding"],
  "retry_count": 1
}
```

---

## LEVEL 1: CONTEXT SYNC

### Purpose
Collect project context, analyze complexity, compress to TOON object.

### Flow

```
START (from Level -1)
  ↓
Node 1: node_session_loader (MUST BE FIRST)
  ├─ Create session folder: ~/.claude/logs/sessions/{session_id}/
  ├─ Save: session.json (metadata)
  └─ Output: session_id, session_path
      ↓
Node 2: PARALLEL (Both run simultaneously)
  ├─ node_complexity_calculation
  │  ├─ Analyze project structure
  │  ├─ Build call stack and graph
  │  └─ Output: complexity_score, project_graph, architecture
  │
  └─ node_context_loader
     ├─ Read from PROJECT folder (not ~/.claude/)
     ├─ Try: SRS, README.md, CLAUDE.md
     ├─ Skip if not found
     └─ Output: context_data (full file contents)
      ↓
Node 3: node_toon_compression
  ├─ Combine all Level 1 data
  ├─ Build TOON object:
  │  ├─ session_id
  │  ├─ complexity_score
  │  ├─ files_loaded_count
  │  └─ context (SRS, README, CLAUDE.md status)
  ├─ Compress using toons library
  ├─ Save: ~/.claude/logs/sessions/{session_id}/context.toon.json
  ├─ Clear from memory:
  │  ├─ full_srs_content
  │  ├─ full_readme_content
  │  ├─ full_claude_md_content
  │  ├─ project_graph
  │  └─ architecture
  └─ Output: TOON object (COMPACT)
      ↓
Node 4: level1_merge_node
  ├─ Output: level1_context_toon (ONLY compact TOON object)
  └─ Signal: Memory cleanup completed
      ↓
Node 5: cleanup_level1_memory
  └─ Free remaining RAM variables
      ↓
GO TO LEVEL 2
```

### Key Points

- **Session isolated in ~/.claude/logs/sessions/**
- **Context from PROJECT folder** (not ~/.claude/memory/)
- **TOON compression 10x token reduction**
- **Memory cleaned after compression** (project files safe)
- **Only TOON object flows to Level 3**

### Output (TOON Object)

```json
{
  "session_id": "session-20260310-120000-abc12345",
  "timestamp": "2026-03-10T12:00:00.123456",
  "complexity_score": 7,
  "files_loaded_count": 3,
  "context": {
    "files": ["SRS", "README", "CLAUDE.md"],
    "srs": true,
    "readme": true,
    "claude_md": true
  }
}
```

---

## LEVEL 2: STANDARDS SYSTEM

**Subgraph:** `scripts/langgraph_engine/subgraphs/level2_standards.py`

### Purpose
Detect project type and load applicable coding standards before execution.

### Implementation

**IS part of the orchestrator graph** - Level 2 runs after Level 1 and before Level 3.

### Flow

```
START (from Level 1)
  |
Node 1: level2_select_standards_node
  |- Detect project type: Python, Java, JavaScript, etc.
  |- Select applicable standard set
  |
Node 2: node_common_standards
  |- Load standards shared across all project types
  |- Coding conventions, formatting, naming rules
  |
Node 3: node_java_standards (conditional)
  |- Runs ONLY if project type is Java/Spring
  |- Load Spring Boot, JPA, REST API standards
  |
Node 4: node_tool_optimization_standards
  |- Load tool usage policies
  |- Read offset/limit rules, grep head_limit, etc.
  |
Node 5: node_mcp_plugin_discovery
  |- Discover available MCP plugins for the session
  |- Register applicable plugins for Level 3 use
  |
Node 6: optimize_context_after_level2
  |- Token optimization pass on loaded standards
  |- Dedup and compress before Level 3
  |
GO TO LEVEL 3
```

### In Workflow

- **6 explicit nodes** in the orchestrator graph
- **Runs after Level 1** (context sync complete)
- **Runs before Level 3** (standards ready for execution)
- **Conditional branching** for language-specific standards

---

## RAG INTEGRATION LAYER

### Purpose
Cache and reuse pipeline decisions across sessions using Vector DB semantic search. Every LangGraph node stores its decision; before LLM calls, RAG checks for similar past decisions to skip inference.

### Architecture

```
Pipeline Step (0-14)
  |
  +---> [BEFORE LLM] rag_lookup_before_llm(step, query, state)
  |     |-- Search node_decisions collection (all-MiniLM-L6-v2, 384-dim)
  |     |-- Filter by step name, min_score = step threshold
  |     |-- IF match (score >= threshold) --> Skip LLM, use cached decision
  |     +-- IF no match --> Proceed to LLM call
  |
  +---> [AFTER STEP] rag_store_after_node(step, decision, state)
  |     |-- Embed decision text (max 2000 chars)
  |     +-- Upsert into node_decisions collection (non-blocking)
  |
  +---> [PIPELINE END] output_node
        |-- store_session_summary() --> sessions collection
        +-- store_flow_trace() x3 --> flow_traces collection
```

### Key Module
- **File:** `scripts/langgraph_engine/rag_integration.py` (469 lines)
- **Class:** `RAGLayer` (singleton per session via `get_rag_layer()`)
- **Backend:** Qdrant local persistent (`~/.claude/memory/vector_db/`)
- **Embedding:** all-MiniLM-L6-v2 (sentence-transformers, 384 dimensions, Cosine distance)

### Vector DB Collections (4)

| Collection | Purpose | Indexed By |
|------------|---------|------------|
| node_decisions | Pipeline step decisions (RAG cache) | rag_store_after_node() |
| sessions | Session summaries for cross-session learning | store_session_summary() |
| flow_traces | Step-level execution traces | store_flow_trace() |
| tool_calls | Tool execution records | vector_index_tool_call() |

### Confidence Thresholds (Step-Specific)

| Step | Threshold | Rationale |
|------|-----------|-----------|
| step0 (Task Analysis) | 0.85 | High confidence needed for classification |
| step1 (Plan Decision) | 0.80 | Binary decision, easier to match |
| step2 (Plan Execution) | 0.88 | Complex planning, needs close match |
| step5 (Skill Selection) | 0.82 | Moderate (default) |
| step7 (Prompt Generation) | 0.90 | Near-exact match required for safe reuse |
| step8 (Issue Labeling) | 0.78 | Simple classification |
| step11 (PR Review) | 0.85 | High confidence for code review |
| step13 (Documentation) | 0.80 | Moderate |
| step14 (Summary) | 0.75 | Lowest stakes, loosest match |
| **Default** | **0.82** | Applied when no step-specific threshold |

### RAG Statistics
Tracked per session: `lookups`, `hits`, `misses`, `stores`, `errors`, `llm_calls_saved`
Hit rate printed at pipeline end: `[RAG] Stats: N stored, N hits, N misses, X% hit rate`

### Error Handling
- All RAG operations are **non-blocking** (wrapped in try-except)
- Lookup failure → return None → proceed with normal LLM call
- Store failure → logged but pipeline continues
- Vector DB unavailable → graceful degradation (all functions return None/False)

---

## LEVEL 3: 15-STEP EXECUTION PIPELINE (Step 0-14)

### Implementation Architecture

- **Active:** `subgraphs/level3_execution_v2.py` (1001 lines) - wrapper/bridge module
- **Deprecated:** `subgraphs/level3_execution.py` (2488 lines) - original, used as backend by v2
- **Orchestrator imports from v2:** `from .subgraphs.level3_execution_v2 import ...`

v2 wraps v1 functions with infrastructure: loguru logging, time tracking, session management, LangGraph routing, error handling, checkpointing (SQLite), and metrics collection. Lazy-loaded per session: CheckpointManager, MetricsCollector, ErrorLogger, BackupManager.

### Module Organization

| Module | Steps | Purpose |
|--------|-------|---------|
| level3_execution_v2.py | All (0-14) | Active wrapper with infrastructure |
| level3_remaining_steps.py | 2-7, 13-14 | Plan, breakdown, TOON, skills, docs, summary |
| level3_steps8to12_github.py | 8-12 | GitHub workflow (issue, branch, PR, closure) |
| level3_code_explorer.py | (utility) | Tool-optimized file read/grep/search |
| github_code_review.py | 11 | Diff analysis, Python/Java/Docker checks, LLM review |
| level3_llm_retry.py | (utility) | Exponential backoff retry logic |
| hybrid_inference.py | 10 | GPU-first inference routing |
| github_merge_validation.py | 11 | PR merge validation |

### Purpose
Execute the actual development task using plan, skills, agents, and automation.

### Input

```json
{
  "user_requirement": "Fix dashboard bug in...",
  "toon_object": { /* from Level 1 */ }
}
```

### Flow

#### STEP 0: TASK ANALYSIS (Pre-Pipeline)

```
Action:
  Analyze user message to determine:
  1. Task type (Bug Fix, Feature, Refactoring, Documentation, etc.)
  2. Complexity score (1-10)
  3. Initial task breakdown

Method:
  Send user message to LLM (DEEP_LOCAL: qwen2.5:14b → claude-opus-4-6 fallback)
  RAG lookup first: threshold 0.85 (high confidence for classification)

Output:
  {
    "task_type": "Bug Fix",
    "complexity": 5,
    "tasks": [{"description": "...", "effort": "medium"}],
    "reasoning": "..."
  }
```

#### STEP 1: PLAN MODE DECISION

```
Action:
  Send TOON + user_requirement to LLM (via hybrid provider chain)

System Prompt:
  "Analyze the project TOON and user requirement.
   Determine if PLAN MODE is required based on:
   - complexity_score
   - project architecture
   - requirement complexity

   Return: { plan_required: true/false, reasoning: '...' }"

Output:
  {
    "plan_required": true | false,
    "reasoning": "explanation"
  }
```

#### STEP 2: PLAN MODE EXECUTION (if required)

```
Model Selection (GPU-first via hybrid provider chain):
  - Planning: Complexity-based Ollama model selection
    * Complexity 1-5: qwen2.5:7b (fast classification)
    * Complexity 6-10: granite4:3b (complex reasoning)
    * Fallback: claude-opus-4-6 (if GPU unavailable)
  - RAG lookup first: threshold 0.88 (high bar for plan reuse)

Tool Optimization (MANDATORY):
  - Read: offset/limit (max 500 lines per file)
  - Grep: head_limit (max 50 matches)
  - Search: max_results (max 10 results)

  Policy: policies/03-execution-system/06-tool-optimization/
  Script: scripts/architecture/03-execution-system/06-tool-optimization/tool-usage-optimizer.py

Output:
  - Detailed implementation plan (from planning model)
  - Analysis of affected files (from exploration)
  - Code context from tool-optimized searches
  - Recommended approach
```

#### STEP 3: TASK/PHASE BREAKDOWN

```
Action:
  Break plan into structured tasks

Each Task:
  - target_files: ["src/component.py", "tests/test.py"]
  - modifications: ["Add feature X", "Update test Y"]
  - dependencies: ["Task 1", "Task 2"]
  - execution_order: 1, 2, 3...

Output:
  Structured task list with dependencies
```

#### STEP 4: TOON REFINEMENT

```
Keep:
  - final_plan
  - task_breakdown
  - files_involved
  - change_descriptions

Delete:
  - unnecessary analysis
  - exploration data
  - intermediate findings

Output:
  Refined TOON = Execution Blueprint
```

#### STEP 5: SKILL & AGENT SELECTION (RAG-Enhanced)

```
Action:
  1. RAG Lookup: Check Vector DB for similar past skill selections
  2. If RAG miss: Send refined TOON + skill/agent definitions to LLM (DEEP_LOCAL)
  3. Score skills using weighted formula + RAG boost

Scoring Formula:
  Score = 0.60 * required_caps_ratio
        + 0.20 * preferred_caps_ratio
        + 0.10 * domain_match
        + 0.10 * tag_overlap
        + RAG_BOOST (up to +0.15)

RAG Boost (from skill_selection_criteria.py):
  Source 1 - Vector DB: Past step5 decisions (min_score 0.70, max boost +0.10)
  Source 2 - Cross-project patterns: ~/.claude/memory/cross-project-patterns.json
             Pattern confidence >= 0.6, +0.025 per match (max +0.05)
  Total RAG boost capped at +0.15

Available Skills:
  (Complete definitions from ~/.claude/skills/)
  - java-spring-boot-microservices, docker, kubernetes
  - jenkins-pipeline, react-core, angular-core, python-core, etc.

Available Agents:
  (Complete definitions from ~/.claude/agents/)
  - spring-boot-microservices, orchestrator-agent
  - devops-engineer, react-engineer, python-backend-engineer, etc.

Output:
  {
    "tasks": [
      {
        "id": "Task-1",
        "skills": ["java-spring-boot"],
        "agents": ["spring-boot-microservices"],
        "rag_boost": 0.12
      }
    ]
  }

Post-Processing:
  - Merge previous TOON + skill mapping TOON
  - Delete all old TOON versions
  - Keep ONLY final merged TOON
```

#### STEP 6: SKILL VALIDATION & DOWNLOAD

```
Action:
  1. Get skills selected by Step 5
  2. Validate: Check if they exist on system
  3. Download: Fetch missing skills from Claude Code GitHub
  4. Return: Selected skills with full content ready to use

Process:
  - Scan available skills/agents locally
  - Validate LLM recommendations from Step 5
  - Download any missing skills from internet
  - Prepare skills for Step 7 prompt generation

Output:
  - final_skills: ["docker", "kubernetes", ...]
  - final_agents: ["devops-engineer", ...]
  - downloaded: List of newly downloaded skills
```

**Note:** RAG-enhanced skill selection was added in v7.5.0. Step 5 uses Vector DB
lookup for historical skill success patterns before LLM selection. Step 6 validates
and downloads the selected skills. See RAG Integration Layer section for details.

#### STEP 7: FINAL PROMPT GENERATION

```
Action:
  Send final merged TOON to LLM (via hybrid provider chain)

System Prompt:
  "Analyze the complete TOON object.
   Convert into a single, optimized execution prompt.

   Include:
   - Full context understanding
   - Detailed task breakdown
   - Required skills
   - Required agents
   - Execution strategy
   - File modifications
   - Expected outcomes

   Generate comprehensive execution blueprint with SEPARATE system prompt
   and user message, plus a combined prompt for backward compatibility."

Output (3 files saved to session folder):
  system_prompt.txt  - Full context (task analysis, breakdown, skills, agents)
  user_message.txt   - Execution instruction for Claude
  prompt.txt         - Combined (system + user) for backward compatibility

File Usage by Mode:
  Hook Mode:  Reads system_prompt.txt + user_message.txt separately
              (system prompt sets Claude context, user message triggers work)
  Full Mode:  Reads prompt.txt as single combined prompt
  Stop Hook:  Reads system_prompt.txt + user_message.txt for PR body generation

Save Location:
  ~/.claude/logs/sessions/{session_id}/system_prompt.txt
  ~/.claude/logs/sessions/{session_id}/user_message.txt
  ~/.claude/logs/sessions/{session_id}/prompt.txt

Post-Processing:
  - Delete TOON object from memory
  - Only prompt files remain
```

#### STEP 8: GITHUB ISSUE CREATION

```
Action:
  Analyze prompt.txt

Determine:
  Issue label from prompt content:
  - bug
  - feature
  - enhancement
  - test
  - documentation

Create GitHub Issue:
  {
    "title": "Issue title from prompt",
    "label": "bug" | "feature" | ... ,
    "body": {
      "task_summary": "...",
      "reasoning": "...",
      "implementation_plan": "...",
      "execution_approach": "..."
    }
  }

Output:
  issue_id (e.g., 42)
```

#### STEP 9: BRANCH CREATION

```
Action:
  1. Switch to: main or master branch
  2. Create new branch: label/issue-{id}
     Example: bug/issue-42, feature/issue-170
  3. Push to remote

Output:
  Branch created and pushed
```

#### STEP 10: IMPLEMENTATION

```
Action:
  Execute tasks from prompt.txt sequentially

Guidelines:
  - Use tool optimization rules
  - Read files with offset/limit
  - Grep with head_limit
  - Follow task dependencies
  - Commit after each significant change

Output:
  Code modifications, file updates
```

#### STEP 11: PULL REQUEST & REVIEW

```
Action:
  1. Create PR: current_branch → main/master
  2. Automated code review (using skills/agents)
  3. If review passes:
     - Merge PR
     - Close PR
  4. If review fails:
     - Request changes
     - Update implementation
     - Re-review

Output:
  PR merged and closed (success)
  OR
  Changes requested (iterate)
```

#### STEP 12: ISSUE CLOSURE

```
Action:
  Close GitHub Issue

Add Comment:
  {
    "what_implemented": "Detailed description",
    "files_modified": ["src/file.py", "tests/test.py"],
    "approach_taken": "Explanation of solution",
    "verification_steps": [
      "Step 1",
      "Step 2"
    ]
  }

Output:
  Issue closed with detailed comment
```

#### STEP 13: PROJECT DOCUMENTATION UPDATE

```
Action:
  Check and update project documentation

Required Files:
  - SRS.md (System Requirements Specification)
  - README.md (Project Overview)
  - CLAUDE.md (Claude-specific context)

If not exist:
  Create them with:
  - Project description
  - Architecture overview
  - Setup instructions
  - Usage guide

If exist:
  Update based on:
  - Latest codebase changes
  - New features
  - Modified architecture
  - Updated standards

Output:
  Comprehensive project documentation
```

#### STEP 14: FINAL SUMMARY

```
Action:
  Generate execution summary

Content:
  - What was implemented
  - What changed
  - How system evolved
  - Key achievements

Format:
  Story-style narrative

Delivery:
  Voice notification to user
```

---

## Complete Execution Example (Hook Mode)

```
User Input:
  "Fix the authentication bug in dashboard"

=== PIPELINE PHASE (UserPromptSubmit hook → 3-level-flow.py) ===

Level -1:
  ✓ Unicode check: PASS
  ✓ Encoding check: PASS
  ✓ Path check: PASS
  → GO TO LEVEL 1

Level 1:
  ✓ Session created: session-20260316-120000-abc123
  ✓ Complexity calculated: 6/10 (parallel with context loading)
  ✓ Context loaded: SRS, README, CLAUDE.md
  ✓ TOON compressed: 10x smaller
  → GO TO LEVEL 2

Level 2:
  ✓ Project type detected: Python
  ✓ Common standards loaded
  ✓ Tool optimization standards loaded
  ✓ MCP plugins discovered: 11 servers
  → GO TO LEVEL 3

Level 3 - Step 0:
  [RAG lookup: threshold 0.85 → miss]
  Task analysis via qwen2.5:14b: Bug Fix, complexity 6/10
  [RAG store: step0 decision cached]

Level 3 - Step 1:
  [RAG lookup: threshold 0.80 → miss]
  Plan required? YES (complexity 6)
  → GO TO STEP 2

Level 3 - Step 2:
  [RAG lookup: threshold 0.88 → miss]
  granite4:3b analyzes (complexity 6 > 5), identifies:
  - 3 files involved, auth middleware + database schema
  → Plan created
  [RAG store: plan decision cached]

Level 3 - Step 3:
  Tasks: (1) Update auth middleware (2) Modify schema (3) Add tests

Level 3 - Step 4:
  TOON refined to execution blueprint (NO_LLM, rule-based)

Level 3 - Step 5:
  [RAG lookup: threshold 0.82 → HIT! score 0.89 from past session]
  Skills: python-core (RAG boost +0.12)
  Agent: python-backend-engineer
  [LLM call SKIPPED - RAG cache reused]

Level 3 - Step 6:
  Skills validated locally (NO_LLM)

Level 3 - Step 7:
  [RAG lookup: threshold 0.90 → miss]
  Prompt generated via qwen2.5:14b → 3 files saved
  [RAG store: prompt decision cached]

Level 3 - Step 8:
  Issue created: #42 (label: bug) via github-api MCP

Level 3 - Step 9:
  Branch created: bug/issue-42 via git-ops MCP

→ Pipeline END (~60s)
  [RAG] Stats: 7 stored, 1 hit, 6 misses, 14.3% hit rate

=== CLAUDE CODE PHASE (User works with generated prompt) ===

Step 10: Claude Code implements fix using system_prompt.txt + user_message.txt
  - Commits changes to bug/issue-42 branch

=== STOP HOOK PHASE (stop-notifier.py auto-executes) ===

Step 11: PR created: "fix: Fix authentication bug in dashboard"
Step 12: Issue #42 closed with implementation details
Step 13: sync-version.py updates docs
Step 14: Summary saved to session directory

Result:
  ✅ Bug fixed, PR merged
  ✅ Issue #42 closed
  ✅ Documentation updated
  ✅ RAG decisions cached for future sessions
```

---

## Critical Rules

### Execution
- ✓ Every step completes before next starts
- ✓ No hallucinations allowed
- ✓ No assumptions allowed
- ✓ If data missing → ask questions first
- ✓ Deterministic execution only
- ✓ Follow defined workflow strictly

### TOON Object
- ✓ Refined at each step
- ✓ Old versions deleted after merge
- ✓ Only final TOON flows through pipeline
- ✓ Converted to prompt.txt for execution

### Tool Usage
- ✓ Read: Use offset/limit for large files
- ✓ Grep: Use head_limit
- ✓ Search: Optimization rules apply
- ✓ Model selection per step (see Hybrid LLM Provider Chain)

### GitHub Integration
- ✓ Issue label determined from prompt
- ✓ Branch naming: label/issue-{id}
- ✓ Automated review before merge
- ✓ Detailed closure comment

---

## Health Monitoring

The `check_system_health()` tool (policy-enforcement MCP server) performs comprehensive system validation.

| Component | Check | Threshold/Detail |
|-----------|-------|-------------------|
| MCP Servers | Import test all 11 servers | All must import successfully |
| Checkpoint DB | SQLite existence + size | `~/.claude/memory/langgraph-checkpoints.db` |
| Vector DB | Qdrant directory + size | `~/.claude/memory/vector_db/` |
| Ollama | GET `/api/tags` + inference test | qwen2.5:7b generate, 5s timeout |
| Anthropic | API key configured | `ANTHROPIC_API_KEY` env var |
| Claude CLI | `claude --version` | 5s timeout |
| Policy Modules | importlib scan `scripts/architecture/` | verified_ok / total ratio |
| Disk Usage | `~/.claude/memory/` total size | Warning if > **500MB** |

**Overall Status:** `HEALTHY` (all pass) or `DEGRADED` (any component unhealthy)

Additional health tools: `check_all_mcp_servers_health()` (11 server import test), `check_module_health()` (architecture module scan)

---

## Policy System

44 policy files (43 `.md` + 1 `.json`) organized by pipeline level. Enforced via the `policy-enforcement` MCP server (`enforce_policy_step`, `verify_compliance`, `record_policy_execution`).

```
policies/
├─ 01-sync-system/                          (11 files)
│  ├─ context-management/                   context-management-policy.md
│  ├─ pattern-detection/                    cross-project-patterns-policy.md
│  ├─ session-management/                   session-chaining, memory, pruning policies
│  └─ user-preferences/                     user-preferences-policy.md
│
├─ 02-standards-system/                     (3 files)
│  ├─ coding-standards-enforcement-policy.md
│  └─ common-standards-policy.md
│
├─ 03-execution-system/                     (28 files)
│  ├─ 00-code-graph-analysis/               code-graph-analysis-policy.md
│  ├─ 00-context-reading/                   context-reading-policy.md
│  ├─ 00-prompt-generation/                 prompt-generation, anti-hallucination
│  ├─ 01-task-breakdown/                    automatic-task-breakdown-policy.md
│  ├─ 02-plan-mode/                         auto-plan-mode-suggestion-policy.md
│  ├─ 04-model-selection/                   intelligent-model-selection, decision-engine
│  ├─ 05-skill-agent-selection/             auto-skill-agent, adaptive-registry, core-mandate
│  ├─ 06-tool-optimization/                 tool-usage-optimization-policy.md
│  ├─ 08-progress-tracking/                 task-progress, phase-enforcement
│  ├─ 09-git-commit/                        git-auto-commit, version-release
│  ├─ failure-prevention/                   common-failures-prevention.md, failure-kb.json
│  ├─ github-branch-pr-policy.md
│  ├─ github-issues-integration-policy.md
│  └─ parallel-execution-policy.md
│
└─ testing/                                 (2 files)
   └─ test-case-policy.md
```

**Naming:** `{topic}-policy.md` | **Numbered prefixes** (00-09) indicate step-wise organization in execution system.

---

## File Locations

```
~/.claude/logs/sessions/{session_id}/
├─ session.json                    (Session metadata)
├─ context-raw.json               (Raw context from Level 1)
├─ context.toon.json              (Compressed TOON object)
├─ system_prompt.txt              (System context for API-style calls)
├─ user_message.txt               (Execution instruction for Claude)
├─ prompt.txt                     (Combined prompt for backward compatibility)
├─ execution-summary.txt          (Task type, complexity, skill used)
└─ step-logs/step-08.json         (Step 8 issue data for Step 12 closure)

~/.claude/memory/
├─ vector_db/                     (Qdrant persistent storage)
├─ langgraph-checkpoints.db       (LangGraph checkpoint SQLite)
└─ cross-project-patterns.json    (Cross-session learning patterns)

~/.claude/rules/
├─ project-standards.md           (Auto-loaded standards)
└─ [other rule files]

~/.claude/skills/                  (Skill definitions)
└─ [skill folders]

~/.claude/agents/                  (Agent definitions)
└─ [agent folders]

scripts/langgraph_engine/          (Core pipeline)
├─ orchestrator.py                 (Main StateGraph, 59K)
├─ flow_state.py                   (TypedDict state, 45K)
├─ rag_integration.py              (RAG layer, 469 lines)
├─ llm_call.py                     (4-provider chain, 555 lines)
├─ hybrid_inference.py             (GPU-first routing, 773 lines)
└─ subgraphs/                      (Level -1, 1, 2, 3v2 subgraphs)

src/mcp/                           (11 FastMCP servers, 109 tools)

policies/                          (44 policy files)
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-10 | Initial implementation of 3-level workflow |
| 2.0.0 | 2026-03-15 | Added Step 0 task analysis; fixed Level 2 description; fixed Step 9 branch naming; renamed to Claude Workflow Engine |
| 3.0.0 | 2026-03-11 | MCP server migration (11 servers, 109 tools via FastMCP) |
| 4.0.0 | 2026-03-12 | Hybrid LLM provider chain (4 providers: Ollama, Claude CLI, Anthropic, OpenAI) |
| 5.0.0 | 2026-03-13 | Hook mode / Full mode execution split (CLAUDE_HOOK_MODE env var) |
| 6.0.0 | 2026-03-14 | Level 3 v2 wrapper architecture; module extraction; stop-notifier autonomy |
| 7.0.0 | 2026-03-15 | Policy system (44 policies); health monitoring; cross-session learning |
| 7.5.0 | 2026-03-16 | RAG integration layer (rag_integration.py); Vector DB node_decisions collection; confidence thresholds |

---

## References

- **CLAUDE.md** - Project context, architecture, MCP servers, execution modes
- **docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md** - System requirements
- **README.md** - Project overview and setup
- **docs/LANGGRAPH-ENGINE.md** - LangGraph engine internals
- **docs/LEVEL3-DESIGN.md** - Level 3 step design details
- **docs/LEVEL3-IMPLEMENTATION-GUIDE.md** - Level 3 implementation guide
- **docs/HYBRID_INFERENCE_SETUP.md** - GPU/NPU hybrid inference setup
- **docs/PARALLEL_EXECUTION_STRATEGY.md** - Parallel execution patterns
- **docs/VECTOR-DB-RAG-FUTURE-PLAN.md** - Vector DB and RAG roadmap
- **docs/TESTING_GUIDE.md** - Test execution guide
- **docs/MCP-TOOLS.md** - MCP server tool reference

---

**Last Updated:** 2026-03-16
**Status:** ACTIVE
**Maintainers:** Claude Workflow Engine Team
