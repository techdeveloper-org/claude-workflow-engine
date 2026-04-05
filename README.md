# Claude Workflow Engine

**The first AI tool that follows full SDLC** - from task analysis to merged PR, automatically.

**Version:** 1.15.1 | **Status:** Alpha | **Last Updated:** 2026-04-04

---

## The Problem

Every AI coding tool today does ONE thing: generate code. None of them follow Software Development Life Cycle (SDLC):

| Tool | Code Gen | Task Analysis | Planning | Standards | GitHub Issue | Branch | PR | Code Review | Docs | Summary |
|------|----------|--------------|----------|-----------|-------------|--------|-----|-------------|------|---------|
| GitHub Copilot | Yes | - | - | - | - | - | - | - | - | - |
| Cursor | Yes | - | - | - | - | - | - | - | - | - |
| Devin | Yes | Partial | Partial | - | - | - | - | - | - | - |
| Claude Code | Yes | - | - | - | - | - | - | - | - | - |
| **This Engine** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

**Claude Workflow Engine automates the ENTIRE development lifecycle** - not just code generation, but everything a professional developer does from receiving a task to closing the issue.

---

## What It Does

Give it a task in natural language. It handles everything:

```
You say: "Fix the login timeout bug"

Engine does:
  Level -1: Auto-fix (Unicode, encoding, paths)
  Level 1:  Session sync + complexity score (combined_complexity_score, 1-25 scale)
  Level 2:  Standards loading (Python + framework-specific)

  Pre-0:   Call graph scan (hot nodes, danger zones, complexity boost)

  Step 0:  Task Analysis v2 -- PromptGen + Orchestrator (2 subprocess calls, ~15s total)
  |
  |  [What was before v1.13.0 -- 6 separate subprocess calls:]
  |    Step 0: task analysis, Step 1: plan mode decision,
  |    Step 3: phase breakdown, Step 4: refinement,
  |    Step 5: skill/agent selection, Step 6: validation,
  |    Step 7: final prompt generation
  |
  |  [What happens now -- 2 subprocess calls (claude CLI):]
  |
  |  Call 1 -- prompt-gen-expert-caller (~10s, captured):
  |    Reads orchestration_system_prompt.txt template
  |    Injects: user requirements + combined_complexity_score (from Level 1)
  |             + call graph data (risk_level, danger_zones, hot_nodes from Pre-0)
  |    claude CLI fills: complete orchestration prompt with agents, phases, contracts
  |    Output: fully structured plan stored in state["orchestration_prompt"]
  |
  |  Call 2 -- orchestrator-agent-caller (~30-90s, stderr streamed live):
  |    Receives filled orchestration prompt
  |    Executes full plan: solution-architect -> consensus -> agents -> QA
  |    User sees real-time progress in Claude Code terminal:
  |      [ORCHESTRATOR] Building plan...
  |      [ORCHESTRATOR] Phase A: solution-architect invoked...
  |      [ORCHESTRATOR] Phase B: implementation...
  |      [ORCHESTRATOR] Done.
  |    Output: result stored in state["orchestrator_result"]

  Step 8:  Creates GitHub issue #42 + Jira PROJ-123 (dual-linked)
  Step 9:  Creates branch -> bugfix/proj-123 (from Jira key)
  Step 10: Implements fix + Jira "In Progress" + Figma "started"
  Step 11: Creates PR + Jira "In Review" + Figma design review
  Step 12: Closes issues (GitHub + Jira "Done" + Figma "complete")
  Step 13: Updates docs -> CLAUDE.md + execution-docs.md
  Step 14: Final summary -> execution-summary.txt + voice notification
```

**Total time: ~15s for planning (was ~75s), ~120s full pipeline (was ~170s).**

### Evolution of the Planning Phase

| Version | Steps | LLM Calls (planning) | Time (planning) | What Changed |
|---------|-------|----------------------|-----------------|--------------|
| v1.12.0 | 15 | ~6 | ~75s | Original: Steps 0-7 each made separate LLM calls |
| v1.13.0 | 9 | ~2 (subprocess) | ~30s | Removed Steps 1,3,4,5,6,7. Step 0 used 2 subprocess calls |
| **v1.14.0** | **8** | **2 (subprocess)** | **~15s** | Step 0 redesigned: template fill + orchestrator (claude CLI subprocess with live stderr) |
| **v1.15.0** | **8** | **2 (subprocess)** | **~15s** | TOON compression + orchestration RAG + per-node RAG removed |
| **v1.15.1** | **8** | **2 (subprocess)** | **~15s** | Complete RAG/Qdrant purge -- all dead code, tests, docs, configs removed |

> **Template Fast-Path (unchanged from v1.8.0):** Pre-built orchestration prompt skips Step 0 entirely, jumps to Step 8. Drops planning time to ~0s.

---

## How It Actually Works — Complete Flow Example

### Scenario: User types "Fix the login timeout bug"

Let's trace the complete execution with real data (call graph + LLM decisions):

#### Phase 1: Pre-Analysis Gate (No LLM yet)

```
INPUT: user_message = "Fix the login timeout bug"
       project_root = "/path/to/auth-service"

STEP 1: Call Graph Scan (get_orchestration_context)
  ├─ Scan codebase AST: Find all classes, methods, call edges
  ├─ Identify HOT NODES (5+ callers):
  │  ├─ SessionManager.validate() -> 12 callers (bottleneck!)
  │  ├─ AuthService.check_expiry() -> 8 callers
  │  └─ TokenCache.get() -> 6 callers
  ├─ Identify LEAF NODES (0 callers):
  │  ├─ SessionValidator._is_expired()
  │  ├─ TimeUtils.current_timestamp()
  │  └─ LogUtils.log_timeout()
  ├─ Compute complexity boost:
  │  → Found hot nodes in auth/session modules
  │  → Base complexity = 5, boost = +2
  │  → Final complexity = 7/10 (COMPLEX task)
  └─ Topological sort:
     → SessionManager -> AuthService -> TokenCache (dependency order)

STEP 2: Codebase Fingerprint (for cross-project guard)
  → codebase_hash = SHA1(sorted .py files)[:12]
  → codebase_hash = "a7f3c2b9e1d4"

OUTPUT: {
  "call_graph_metrics": {
    "hot_nodes": [SessionManager.validate, AuthService.check_expiry, TokenCache.get],
    "complexity_boost": 2,
    "affected_modules": ["auth", "session", "cache"]
  },
  "codebase_hash": "a7f3c2b9e1d4"
}
```

#### Phase 2: Analysis (Step 0)

```
Step 0: Task Analysis v2 -- 2 subprocess calls (claude CLI)
  Call 1 -- prompt-gen-expert-caller: fills orchestration_system_prompt.txt template
    INPUT: {
      task: "Fix the login timeout bug",
      hot_nodes: ["SessionManager.validate (12 callers)", ...],
      affected_modules: ["auth", "session"],
      combined_complexity_score: 17  (1-25 scale)
    }
    OUTPUT: complete orchestration prompt (agents, phases, contracts)

  Call 2 -- orchestrator-agent-caller: executes the plan
    → solution-architect -> consensus -> agents -> QA
    OUTPUT: full implementation plan stored in state["orchestrator_result"]
```

#### Phase 3: Implementation & Review (Steps 8-12)

```
Step 8: Create GitHub Issue
  Title: "Fix login timeout bug in SessionManager.validate()"
  Labels: ["bug", "python", "high-priority"]
  Description: "[From Pre-Analysis] Affects 12 dependent methods, risky change"

Step 9: Create Branch
  Name: "bugfix/proj-123" (from Jira key)

Step 10: Implementation
  → AI generates code using system_prompt + user_message
  → Call graph snapshot taken BEFORE changes
  → Jira transitioned: "To Do" → "In Progress"

Step 11: Code Review + PR
  → Snapshots compared: before vs after call graph
  → Detects breaking changes: Did any caller signature break?
  → Risk assessment: "Safe" (all callers updated, tests added)
  → Jira transitioned: "In Progress" → "In Review"
  → PR created with auto-generated review checklist

Step 12: Merge & Close
  → PR merged ✓
  → Jira transitioned: "In Review" → "Done"
  → GitHub issue closed
  → Automated comment: "Fixed in PR #42, merged at commit abc123"
```

#### Summary Statistics

```
EXECUTION SUMMARY:

LLM Calls Used:    4 (out of 12 typical)
  ├─ Pre-0:      0 (call graph scan, no LLM)
  ├─ Step 0:     2 (subprocess: prompt-gen + orchestrator)
  ├─ Step 10:    1 (implementation, structured context)
  └─ Step 11:    1 (review, pre-change snapshot available)

LLM Calls Saved:   via call graph determinism + template fast-path
  ├─ Template Fast-Path:       2 subprocess calls (Step 0 bypassed)
  └─ Call graph complexity:    deterministic (no extra LLM call needed)

Execution Time:    ~45 seconds (Hook Mode: Pre-0, Step 0, Steps 8-9)
  ├─ Pre-0:  1.2s (call graph scan)
  └─ Steps 8-9: 43.8s (GitHub issue + branch creation)

Cost Savings:
  ├─ LLM inference: 67% reduction (4 calls vs 12)
  ├─ Token budget: ~8K tokens saved
  ├─ Total latency: 45s vs typical 70s (35% faster)
  └─ Developer time: Issue → PR in <1 minute
```

This is the **complete end-to-end flow** — from user prompt to merged PR, with every optimization explained.

---

## Architecture

### 4-Level Pipeline

```
Level -1: AUTO-FIX         3 checks: Unicode, encoding, paths
    |
Level 1:  CONTEXT SYNC     Session + parallel [complexity, context]
    |
Level 2:  STANDARDS         Common + conditional Java + tool optimization + MCP discovery
    |
Level 3:  EXECUTION         8 active steps (Pre-0, Step 0, Steps 8-14): Full SDLC automation
```

### 8-Step Active SDLC Pipeline (Level 3)

| Phase | Steps | What Happens |
|-------|-------|-------------|
| **Pre-Analysis Gate** | Pre-0 | Call graph scan: hot nodes, danger zones, complexity boost injected into Step 0 context |
| **Analysis & Planning** | 0 | Task analysis v2: prompt-gen-expert (template fill) + orchestrator-agent (full plan) -- 2 claude CLI subprocess calls. Figma extraction/injection included in template when ENABLE_FIGMA=1 |
| **Issue & Branch** | 8-9 | GitHub Issue + **Jira Issue** (dual, cross-linked); Branch from **Jira key** (`feature/PROJ-123`) |
| **Implementation** | 10 | Implementation + CallGraph snapshot; **Jira -> "In Progress"**; **Figma "started" comment** |
| **Review & Closure** | 11-12 | PR + Code Review + **Jira PR link + "In Review"** + **Figma design fidelity check**; Issue closure (**Jira -> "Done"** + **Figma "complete" comment**) |
| **Finalization** | 13-14 | Documentation + UML diagrams; execution summary + voice notification |

### Execution Modes

```
Hook Mode (default, CLAUDE_HOOK_MODE=1):
  Pre-0, Step 0, Steps 8-9 -> Pipeline (analysis + prompt + GitHub issue + branch)
  Steps 10-14              -> Skipped (user implements, then runs Full Mode for PR/closure)

Full Mode (CLAUDE_HOOK_MODE=0):
  Pre-0, Step 0, Steps 8-14 -> All active steps execute sequentially
```

### Integration Lifecycle

All integrations follow a complete **Create -> Update -> Close** lifecycle across pipeline steps:

#### Jira Lifecycle (ENABLE_JIRA=1)

| Step | Action | What Happens |
|------|--------|-------------|
| Step 8 | **CREATE** | Jira issue created with same title/type as GitHub Issue; cross-link comment added to both |
| Step 9 | **BRANCH** | Branch named from Jira key: `feature/proj-123` (not `feature/issue-42`) |
| Step 10 | **UPDATE** | Jira transitioned to "In Progress"; "Implementation started" comment added |
| Step 11 | **LINK** | PR remote-linked to Jira issue; Jira transitioned to "In Review"; PR comment added |
| Step 11 | **MERGE** | Post-merge comment with PR number, branch name, and URL |
| Step 12 | **CLOSE** | Jira transitioned to "Done"; implementation summary comment with files modified |

#### Figma Lifecycle (ENABLE_FIGMA=1)

| Step | Action | What Happens |
|------|--------|-------------|
| Step 0 | **EXTRACT+INJECT** | Figma components + design tokens (colors, typography, spacing) extracted and injected inside orchestration template |
| Step 10 | **COMMENT** | "Implementation started" comment added to Figma file with component list |
| Step 11 | **REVIEW** | Design fidelity checklist generated (colors match? spacing correct? shadows applied?) |
| Step 12 | **COMMENT** | "Implementation complete" comment added with PR link |

#### Jenkins Lifecycle (ENABLE_JENKINS=1)

| Step | Action | What Happens |
|------|--------|-------------|
| Step 10 | **TRIGGER** | Jenkins build triggered after implementation |
| Step 11 | **VALIDATE** | Build status checked before PR merge; console output on failure |

All integration operations are **non-blocking** - if any service is unavailable, the pipeline continues with remaining integrations.

---

## Key Technologies

### Call Graph Analysis (Class-Level Code Intelligence)

The call graph is the **brain** of the engine. It is NOT a simple JSON dependency list - it is a **complete call stack** that maps every class, every method, every function call, and every relationship in the entire codebase. Think of it as a **live X-ray of your code** - it sees everything.

CallGraph supports 4 languages: Python (full AST analysis), Java, TypeScript/TSX, and Kotlin (regex-based parsing for classes, methods, and call edges).

#### Before vs After

```
OLD (v7.5.0) - File-level flat graph:
  Nodes: 211 files (just filenames, no idea what's inside)
  Edges: 515 imports (only "file A imports file B", nothing deeper)
  Context: ZERO (can't tell Calculator.add from Logger.add - both are just "add")
  Impact: IMPOSSIBLE (can't answer "what breaks if I change this method?")

NEW (v7.6.0) - Class-level call stack:
  Classes: 566 (every class with name, file, line number, parent classes)
  Methods: 3,686 (every method with params, return types, visibility, complexity)
  Functions: 1,061 (standalone functions, separate from methods)
  Call Edges: 25,948 (who calls whom, with exact line numbers)
  Inheritance: 93 edges (Child extends Base, tracked explicitly)
  Resolved: 7,957 edges matched to exact FQN definitions
  Call Paths: Full chains traced from entry points to leaf methods
```

#### Why This Matters - The Real Power

**1. Accurate Complexity Scoring (Step 0)**

The old graph counted files and imports. A project with 100 files all doing simple CRUD got the same score as 100 files with deeply nested recursive algorithms. Now complexity is measured at the **method level** - if `Orchestrator.run()` has cyclomatic complexity 15 and calls 8 other methods across 4 classes, that's a genuinely complex function. The score reflects reality.

**2. Impact Analysis - "What Breaks If I Change This?"**

```
Input:  "I want to change Processor.execute()"
Output: "These 5 methods directly call it:
           - Orchestrator.run() at line 45
           - BatchRunner.process_all() at line 112
           - TestProcessor.test_execute() at line 23
           - CLIHandler.handle_command() at line 89
           - RetryManager.retry_with_backoff() at line 67
         And transitively, 12 more methods are affected through the call chain."
```

This is **impossible** with a file-level graph. You'd only know "engine.py imports processor.py" - useless for understanding the blast radius of a change.

**3. Smarter Task Breakdown (Step 3)**

When the engine breaks a task into subtasks, the call graph tells it:
- Which methods are entry points (never called by others - these are the "doors" into the system)
- Which methods are bottlenecks (called by many others - dangerous to change)
- Which classes are tightly coupled (change one, must change the other)
- What the full call chain looks like from user input to database write

**4. Orchestration Pre-Analysis Gate (Pre-Step 0) — introduced in v1.6.0**

Before any LLM call is made, the engine runs a call graph scan:
1. **Call graph scan** — `get_orchestration_context()` extracts hot nodes (5+ callers), leaf nodes, affected modules, and a topological dependency order
2. **Complexity boost** — computed deterministically without LLM:
   - Hot nodes found → `complexity += 2` (max 10)
   - All-leaf nodes only → `complexity -= 1` (min 1)
3. **Codebase hash** — `SHA1(sorted .py files)[:12]` for cross-project guard

This data is injected into the Step 0 orchestration template so the LLM gets call graph context pre-loaded.

---

### How the Engine Reduces LLM Calls

Every LLM call has latency and cost. The engine uses two mechanisms to avoid unnecessary inference:

| Mechanism | Where | Calls Saved | How |
|-----------|-------|------------|-----|
| **Template Fast-Path** | Pre-Step 0 | 2 subprocess calls | Pre-filled orchestration template skips Step 0 entirely, jumps to Step 8 |
| **Call Graph Complexity Boost** | Pre-0 | deterministic | Complexity score computed without LLM using hot-node count; no extra call needed |

**Total savings on a Template Fast-Path session: Step 0 bypassed (2 subprocess calls avoided), execution starts directly at Step 8.**

#### Pre-Analysis Decision Tree (Priority Order)

```
New task arrives
    |
    v
Pre-Analysis Gate (no LLM)
    |-- Check: --orchestration-template provided?  [HIGHEST PRIORITY]
    |-- Call graph scan: hot nodes, leaf nodes, complexity boost
    |-- Codebase hash: fingerprint current project structure
    |
    v
Priority 1: TEMPLATE FAST-PATH (--orchestration-template=path/to/template.json)
    |
    +-- Template valid? ──────────────────────────────────────────────────────────┐
    |   Step 0 bypassed entirely                                                 |
    |   -> Jump directly to Step 8                                               |
    |   -> 2 subprocess calls saved (planning time ~0s)                          |
    |                                                                             v
    +-- Template not provided -> Full pipeline                             Step 8 onward
    |
    v
Full Pipeline: Step 0 (2 subprocess calls: prompt-gen + orchestrator) -> Steps 8-14
```

#### Cross-Project Guard (v1.6.1) — Preventing False Positives

The codebase hash fingerprints the project so call graph data is never confused across codebases:

```
Project A: "Add login to dashboard"  -> call graph hash "202e89f7b6c8"
Project B: "Add login to dashboard"  -> call graph hash "9a3f12b8c041"

Fix: codebase_hash = SHA1(sorted top-level .py file names)[:12]
     Different hashes → different call graph contexts → separate analysis paths
     Result: Project B always gets fresh call graph analysis, not Project A's
```

#### Stale Graph Guard (v1.6.1) — Preventing Wrong Context After Implementation

```
Timeline of a pipeline run:

Pre-Analysis  ──> builds graph (call_graph_metrics)
Step 0-9      ──> use cached graph (no code changes yet) ✓
Step 10       ──> WRITES FILES (codebase changes!)
                  sets call_graph_stale = True in state
Step 11+      ──> calls refresh_call_graph_if_stale(state, project_root)
                  flag is True → rebuild graph fresh → accurate post-change context ✓

Without fix:  Step 11 would use Step-0's graph (pre-implementation state)
              review_change_impact() would see no changes → miss breaking changes → wrong PR review
```

**4. Precise Code Review (Step 11)**

The PR review loop uses the call graph to check:
- Did the change touch a bottleneck method? Flag for extra review
- Does the new code introduce circular dependencies?
- Is the method complexity within acceptable bounds?
- Are all affected callers still compatible with the change?

**5. Complete UML Diagrams (Step 13)**

Sequence diagrams now show **actual** call flows with class context:
```
Before: add ->> validate: validate()     (which class? unknown)
After:  Calculator.add ->> Calculator._validate: _validate(x)   (exact class + params)
```

#### What the Graph Looks Like

```json
{
  "version": "2.0.0",
  "stats": {
    "total_classes": 566,
    "total_methods": 3686,
    "total_call_edges": 25948,
    "max_call_depth": 7,
    "avg_cyclomatic": 4.01
  },
  "nodes": {
    "classes": [
      {
        "id": "scripts/langgraph_engine/orchestrator.py::Orchestrator",
        "type": "class",
        "name": "Orchestrator",
        "file": "scripts/langgraph_engine/orchestrator.py",
        "line": 45,
        "bases": ["StateGraph"],
        "methods": ["...::Orchestrator.run", "...::Orchestrator._build_graph"]
      }
    ],
    "methods": [
      {
        "id": "scripts/langgraph_engine/orchestrator.py::Orchestrator.run",
        "type": "method",
        "name": "run",
        "parent_class": "...::Orchestrator",
        "params": ["task: str", "session_id: str"],
        "return_type": "dict",
        "visibility": "+",
        "cyclomatic": 12,
        "line": 120
      }
    ]
  },
  "edges": [
    {
      "from": "...::Orchestrator.run",
      "to": "...::HybridInferenceManager.invoke",
      "line": 145,
      "type": "method_call",
      "resolved": true
    }
  ],
  "call_paths": [
    {
      "path": ["main", "run_langgraph_engine", "Orchestrator.run", "HybridInferenceManager.invoke", "LazyClient.get"],
      "depth": 5,
      "total_complexity": 45
    }
  ]
}
```

#### How It Works (Technical)

The key insight: Python's `ast.walk()` **loses class context**. When you walk the AST tree, you see `FunctionDef("add")` but you don't know if it belongs to `Calculator` or `Logger`. Our solution uses `ast.NodeVisitor` which visits nodes in tree order, maintaining a **class stack**:

```
visit_ClassDef("Calculator")     -> push "Calculator" to stack
  visit_FunctionDef("add")       -> FQN = "module.py::Calculator.add" (knows it's inside Calculator)
    found Call("self._validate")  -> resolves to "module.py::Calculator._validate" (same class)
  visit_FunctionDef("_validate") -> FQN = "module.py::Calculator._validate"
pop "Calculator" from stack

visit_FunctionDef("standalone")  -> FQN = "module.py::standalone" (no class, type="function")
```

This simple architectural choice (NodeVisitor vs walk) is what makes the entire system work. Every other feature - impact analysis, call paths, complexity scoring - builds on this foundation of **knowing which class a method belongs to**.

#### Call Graph Analyzer (Pipeline Integration)

`call_graph_analyzer.py` wraps the call graph builder with four pipeline-ready functions that Steps 2, 10, and 11 call directly:

| Function | Used By | What It Does |
|----------|---------|-------------|
| `analyze_impact_before_change(method_fqn)` | Pre-0 | Pre-plan risk assessment - returns all callers, call depth, and blast radius before any code change |
| `get_implementation_context(method_fqn)` | Step 10 | Caller/callee awareness during implementation - gives full context of what calls the target and what it calls |
| `review_change_impact(before_snapshot, after_snapshot)` | Step 11 | Before/after graph comparison for code review - detects new call edges, removed edges, and breaking changes |
| `snapshot_call_graph()` | Step 10 | Captures serializable call graph state for diff comparison in Step 11 |
| `refresh_call_graph_if_stale(state, project_root)` | Step 11+ | **v1.6.1** — Returns fresh graph when `call_graph_stale=True` (set after Step 10 writes files); prevents stale pre-implementation context from being injected into post-implementation steps |

The data flow across steps:
```
Pre-0:   analyze_impact_before_change() -> risk score -> informs plan complexity
Step 10: snapshot_call_graph() -> saved as pre_change_snapshot
         get_implementation_context() -> injected into implementation prompt
Step 11: review_change_impact(pre_change_snapshot, new_snapshot) -> PR review findings
```

The single data source for all 13 UML diagram types is also the call graph - `uml_generators.py` reads the graph once and produces any diagram type from it, ensuring diagrams always reflect the actual code structure.

### Key Modules

| Module | File | Purpose |
|--------|------|---------|
| Orchestrator | orchestrator.py | Main StateGraph pipeline (59K) |
| Flow State | flow_state.py | TypedDict state definition (200+ fields) |
| Call Graph Analyzer | call_graph_analyzer.py | Pipeline impact analysis (6 functions for Steps 2/10/11) |
| Phase-Scoped Context | call_graph_analyzer.py | extract_phase_subgraph + get_phase_scoped_context |
| Dependency Resolver | build_dependency_resolver.py | 5-language build file parsing (Python/Java/Node/Go/Rust) |
| User Interaction | user_interaction.py | InteractionManager + 6 step-specific question generators |
| SonarQube Scanner | sonarqube_scanner.py | API-first SonarQube + lightweight fallback scanner |
| Sonar Auto-Fixer | sonar_auto_fixer.py | Fix-verify loop (template fixes + LLM fixes) |
| Test Generator | test_generator.py | Template-based unit tests (Python/Java/TS/Go) |
| Integration Test Gen | integration_test_generator.py | CallGraph call-path-based integration tests |
| Coverage Analyzer | coverage_analyzer.py | AST-based coverage, risk-prioritized untested methods |
| Quality Gate | quality_gate.py | 4-gate enforcement (SonarQube, coverage, breaking, tests) |
| Metrics Aggregator | metrics_aggregator.py | Session/step/LLM/tool statistics from logs |
| UML Generators | uml_generators.py | 13 UML diagram types (AST + LLM) |
| Doc Manager | level3_documentation_manager.py | Circular SDLC doc cycle (Step 0/13) |

### LangGraph Orchestration (92 modules)

- StateGraph with 200+ typed state fields
- Parallel execution via `Send()` API (Level 1: 4 concurrent tasks)
- Conditional routing (plan mode, Java detection, PR retry loop)
- Checkpoint recovery (resume from any step after crash)
- Signal handling (Ctrl+C graceful recovery)

### 13 MCP Servers — All in Separate Repos

All 13 MCP servers use FastMCP protocol (stdio JSON-RPC) and have been extracted to individual
private repos under [`techdeveloper-org`](https://github.com/orgs/techdeveloper-org/repositories)
for independent versioning, testing, and reuse. Each is registered in `~/.claude/settings.json`
and points to `mcp-{name}/server.py` in the local workspace.

> **Note:** `session-mgr` also keeps an in-engine copy in `src/mcp/` because
> it is imported in-process by `session_hooks.py`. The separate repo is the source of truth.

| # | Server | Repo | Tools | Purpose |
|---|--------|------|-------|---------|
| 1 | session-mgr | [mcp-session-mgr](https://github.com/techdeveloper-org/mcp-session-mgr) | 14 | Session lifecycle (also in-engine: `src/mcp/session_mcp_server.py`) |
| 2 | git-ops | [mcp-git-ops](https://github.com/techdeveloper-org/mcp-git-ops) | 14 | Git (branch, commit, push, pull, stash, diff, fetch, cleanup) |
| 3 | github-api | [mcp-github-api](https://github.com/techdeveloper-org/mcp-github-api) | 12 | GitHub (issue, PR, merge, label, build validate, full merge cycle) |
| 4 | policy-enforcement | [mcp-policy-enforcement](https://github.com/techdeveloper-org/mcp-policy-enforcement) | 11 | Policy compliance, flow-trace, module health, system health |
| 5 | token-optimizer | [mcp-token-optimizer](https://github.com/techdeveloper-org/mcp-token-optimizer) | 10 | Token reduction (AST navigation, smart read, dedup, 60-85% savings) |
| 6 | pre-tool-gate | [mcp-pre-tool-gate](https://github.com/techdeveloper-org/mcp-pre-tool-gate) | 13 | Pre-tool validation (8 policy checks, skill hints) |
| 7 | post-tool-tracker | [mcp-post-tool-tracker](https://github.com/techdeveloper-org/mcp-post-tool-tracker) | 6 | Post-tool tracking (progress, commit readiness, stats) |
| 8 | standards-loader | [mcp-standards-loader](https://github.com/techdeveloper-org/mcp-standards-loader) | 7 | Standards (project detect, framework detect, hot-reload) |
| 9 | uml-diagram | [mcp-uml-diagram](https://github.com/techdeveloper-org/mcp-uml-diagram) | 15 | UML generation (13 diagram types, AST + LLM, Mermaid/PlantUML, Kroki.io) |
| 10 | drawio-diagram | [mcp-drawio-diagram](https://github.com/techdeveloper-org/mcp-drawio-diagram) | 5 | Draw.io editable diagrams (12 types, .drawio files, shareable URLs) |
| 11 | jira-api | [mcp-jira-api](https://github.com/techdeveloper-org/mcp-jira-api) | 10 | Jira (create/search/transition issues, link PRs, Cloud + Server) |
| 12 | jenkins-ci | [mcp-jenkins-ci](https://github.com/techdeveloper-org/mcp-jenkins-ci) | 10 | Jenkins CI/CD (trigger/abort builds, console output, queue, polling) |
| 13 | figma-api | [mcp-figma](https://github.com/techdeveloper-org/mcp-figma) | 10 | Figma (file info, components, design tokens, styles, design review) |

> **Shared base:** [mcp-base](https://github.com/techdeveloper-org/mcp-base) — MCPResponse builder, @mcp_tool_handler, AtomicJsonStore, LazyClient. Each server includes a `base/` copy.
>
> **Total:** 13 server repos + 1 shared base = [14 repos](https://github.com/orgs/techdeveloper-org/repositories) under `techdeveloper-org`

### Hybrid LLM Inference (4 providers)

The engine supports 4 LLM providers. Each provider is **independently selectable** — you choose your primary, and Ollama always serves as the safety net fallback since it runs locally and never goes down.

```
Provider options:
  openai     → OpenAI GPT API   (needs OPENAI_API_KEY)
  anthropic  → Anthropic Claude API  (needs ANTHROPIC_API_KEY)
  claude_cli → Claude Code CLI  (uses your Anthropic subscription)
  ollama     → Local Ollama GPU (free, no API key, always available)
  auto       → tries all in order: Ollama → Claude CLI → Anthropic → OpenAI

Default fallback strategy:
  LLM_PROVIDER=openai     → OpenAI first,     fallback → Ollama
  LLM_PROVIDER=anthropic  → Anthropic first,  fallback → Ollama
  LLM_PROVIDER=claude_cli → Claude CLI first, fallback → Ollama
  LLM_PROVIDER=ollama     → Ollama only       (no fallback needed)
  LLM_PROVIDER=auto       → all 4 in order    (full chain)
```

**Why Ollama as default fallback?** It runs locally — no API key, no rate limits, no network dependency. Even if your cloud API fails (wrong key, rate limit, outage), the pipeline continues uninterrupted.

**Custom fallback** — override via `LLM_FALLBACK`:
```bash
LLM_PROVIDER=openai
LLM_FALLBACK=anthropic,ollama   # OpenAI → Anthropic → Ollama
```

- Complexity-based model selection (simple=fast model, complex=powerful model)
- Anthropic provider uses the official `anthropic` Python SDK (automatic retries, typed errors)
- Cached health checks (60s TTL) to avoid repeated probe calls

### Hook System (Pre/Post Tool Enforcement)

| Hook | Script | Purpose |
|------|--------|---------|
| UserPromptSubmit | 3-level-flow.py | Runs full pipeline on every user message |
| PreToolUse | pre-tool-enforcer.py | Blocks Write/Edit until Level 1/2 complete, tool optimization hints |
| PostToolUse | post-tool-tracker.py | Progress tracking, flag clearing, GitHub integration |
| Stop | stop-notifier.py | Voice notification on session end |

### Multi-Project Support (20+ languages/frameworks)

Auto-detects project type and loads appropriate standards:

**Languages:** Python, JavaScript, TypeScript, Java, Kotlin, Go, Rust, Ruby, C#, PHP, Swift
**Frameworks:** Flask, Django, FastAPI, Spring Boot, React, Angular, Vue, Next.js, Express
**Tools:** Docker, Kubernetes, GitHub Actions, Jenkins

### Policy System (63 policies)

```
policies/
+-- 00-auto-fix-system/    Level -1: Unicode, encoding, paths, recovery
+-- 01-sync-system/        Level 1: Session, context, preferences, patterns
+-- 02-standards-system/   Level 2: Common + conditional standards
+-- 03-execution-system/   Level 3: 8 active steps (Pre-0, Step 0, Steps 8-14) + failure prevention
```

---

## Current Status: What's Built vs What's Remaining

> **Version: 1.7.0** — All core features complete + full production readiness layer added (2026-03-28).

### ✅ COMPLETE (v1.6.0)

| Component | Details |
|-----------|---------|
| **8-Step Active Pipeline** | All active steps produce real output (Pre-0, Step 0, Steps 8-14). Steps 1-7 consolidated into Step 0 (v1.13-v1.14). |
| **4-Level Architecture** | Level -1 → Level 1 → Level 2 → Level 3, fully operational |
| **20 MCP Servers** | 328 tools — all 20 in separate repos under [techdeveloper-org](https://github.com/orgs/techdeveloper-org/repositories); 2 also keep in-engine copies in `src/mcp/` |
| **LLM Provider Routing** | Official Anthropic SDK (auto-retry, typed errors). 4 providers: Ollama · Anthropic · Claude CLI · OpenAI. Specific provider → Ollama fallback by default. |
| **GitHub Integration** | Issue, branch, PR, merge, review loop (Steps 8–12) |
| **Jira Integration** | Dual issue tracking, full lifecycle: Create→InProgress→InReview→Done (Steps 8–12) |
| **Figma Integration** | Component extraction (Step 3), design tokens (Step 7), fidelity review (Step 11) |
| **Jenkins Integration** | Build trigger, CI validation, blocks merge on failure (Step 11) |
| **SonarQube Integration** | API-first scan, lightweight fallback, auto-fixer loop, result aggregator (Step 10) |
| **Quality Gate** | 4-gate PR merge enforcement: coverage · SonarQube · tests · review |
| **Test Generator** | Auto-generates unit tests via CallGraph. Python (pytest), Java (JUnit5), TS (Jest), Go (table-driven) |
| **RAG Integration** | Qdrant, 4 collections, step-specific thresholds (0.75–0.90). Caches LLM decisions. |
| **CallGraph Intelligence** | 578 classes, 3,985 methods. Impact analysis at Steps 2, 10, 11. 4 language parsers. |
| **Hook System** | UserPromptSubmit · PreToolUse · PostToolUse · Stop. Blocks Write/Edit until L1+L2 done. |
| **Policy System** | 63 policies, 9 standards-hook injection points across Level 3 |
| **Multi-Project Detection** | 20+ languages/frameworks auto-detected |
| **Token Optimization** | AST navigation, smart read, dedup — 60–85% savings |
| **Session Management** | Chaining, TOON compression, archival, cross-session memory |
| **Standards Enforcement** | Common + conditional Java + framework-specific |
| **Cross-Session Learning** | RAG pattern detection + skill selection boost (Qdrant semantic search) |
| **Modular Architecture** | 9 packages: core · state · routing · helper_nodes · diagrams · parsers · sonarqube · integrations · pipeline_builder |
| **UML Diagram Generation** | 13 diagram types via Strategy Pattern. CallGraph as single data source. Mermaid/PlantUML/Kroki.io |
| **Draw.io Diagram Support** | 12 diagram types, editable .drawio files, shareable URLs (no API key needed) |
| **Architecture Diagram** | Full 3-level pipeline diagram → `architecture.drawio` in project root |
| **CLI Interface** | `cwe run/setup/status/health/version/doctor` — fully functional |
| **Setup Wizard** | Interactive first-time configuration (`scripts/setup/setup_wizard.py`) |
| **Docker** | `Dockerfile` + `docker-compose.yml` — one-command deployment |
| **GitHub Actions CI** | `.github/workflows/ci.yml` — configurable matrix (Python 3.10/3.12), lint, tests. Auto-trigger disabled; runs on `workflow_dispatch` only. |
| **Version Sync** | `scripts/tools/sync-version.py` — syncs VERSION to in-engine MCP servers (v1.8.1: extracted servers have own versioning in their repos) |
| **Test Suite** | 75 test files covering MCP servers, pipeline steps, integrations, security, e2e, load |
| **Coverage Setup** | `pytest-cov` + `coverage` in requirements.txt |
| **Documentation** | 71 docs, SRS, CHANGELOG, guides, deployment guide, troubleshooting guide, ADRs, runbooks |

---

### ✅ RECENTLY COMPLETED (v1.7.0 — Production Readiness Sprint, 2026-03-28)

| Component | Details |
|-----------|---------|
| **Health & Readiness Endpoints** | `scripts/health_server.py` — stdlib HTTP server, `GET /health` + `GET /readiness` (Qdrant + key checks), daemon thread, zero langgraph_engine imports |
| **Kubernetes Manifests** | `k8s/` — Deployment (2 replicas, liveness/readiness probes), ConfigMap, Secret, ClusterIP Service, HPA (2-6 replicas, 70% CPU) |
| **Qdrant Bootstrap Script** | `scripts/db_migrate.py` — idempotent collection creation + payload indexes, `--recreate` flag |
| **Graceful Shutdown** | `scripts/3-level-flow.py` — SIGTERM/SIGINT handlers; writes interrupted flow-trace.json on shutdown |
| **Prometheus Metrics** | `scripts/langgraph_engine/metrics_exporter.py` — 9 metrics (pipeline/step/RAG/LLM/MCP); `ENABLE_METRICS=1` to activate |
| **Structured JSON Logging** | `scripts/langgraph_engine/core/structured_logger.py` — loguru JSON sink, ContextVar session/step injection, `LOG_FORMAT=json` |
| **OpenTelemetry Tracing** | `scripts/langgraph_engine/tracing.py` — OTLP/console exporter, `create_span()` context manager, `ENABLE_TRACING=1` |
| **Sentry Error Tracking** | `scripts/langgraph_engine/error_tracking.py` — `capture_exception()` with step/session tags, no-op without SENTRY_DSN |
| **RAG Cache Invalidation CLI** | `scripts/langgraph_engine/cache_invalidation.py` — purge by session/project/step/age via Qdrant filters |
| **Secrets Validation** | `scripts/langgraph_engine/secrets_manager.py` — startup validation, rotation hints, optional AWS Secrets Manager |
| **Rate Limiting** | `src/mcp/rate_limiter.py` — TokenBucket per client, 100/min tools, 10/min LLM, `ENABLE_RATE_LIMITING=1` |
| **Input Validation** | `src/mcp/input_validator.py` — null-byte strip, length limits, 6-pattern prompt injection detection |
| **Audit Logging** | `scripts/langgraph_engine/audit_logger.py` — append-only JSON, daily rotation, auto-redacts credentials in metadata |
| **Secrets Scanner (CI Gate)** | `scripts/secrets_check.py` — scans scripts/ + src/, 6 regex patterns, exit 1 on finding; pre-commit hook ready |
| **Requirements Pinning** | `scripts/pin_requirements.py` — generates `requirements.pinned.txt` + `requirements.bounds.txt` via pip show |
| **Runbooks** | `docs/runbooks/` — STALE_GRAPH, RAG_MISS_RATE, LLM_PROVIDER_FAILURE |
| **Architecture Decision Records** | `docs/adr/` — ADR-001 (Qdrant RAG), ADR-002 (Call Graph), ADR-003 (Multi-Provider Routing) |
| **OpenAPI Spec** | `docs/api/OPENAPI_SPEC.yaml` — OpenAPI 3.0.3 for /health, /readiness, /metrics |
| **Deployment Guide** | `docs/DEPLOYMENT_GUIDE.md` — prerequisites, docker-compose, K8s apply order, 20+ env vars reference |
| **Troubleshooting Guide** | `docs/TROUBLESHOOTING_GUIDE.md` — 15 failure modes with exact error messages and fixes |
| **Security Tests** | `tests/test_secrets_manager.py`, `tests/test_audit_logger.py` — 27 tests covering happy path, error, redaction, concurrency |
| **Integration Tests** | `tests/integration/test_mcp_servers_integration.py` — MCP tool schemas, RAG cross-project penalty, rate limiter, input validator |
| **E2E Scenario Tests** | `tests/e2e/test_pipeline_scenarios.py` — RAG hit path, stale graph guard, hook mode routing, secrets validation |
| **Load / Concurrency Tests** | `tests/load/test_concurrent_pipelines.py` — token bucket thread safety, session ID uniqueness (100 concurrent), cross-project RAG penalty math |
| **Coverage Threshold Enforcement** | `.coveragerc` + `pytest.ini` created. CI enforces 50% minimum via `--cov-fail-under=50`. Threshold ratchets up as coverage improves. |
| **Pre-commit Hooks** | `.pre-commit-config.yaml` — file hygiene, ruff, black, isort, secrets-check gate |

**Setup pre-commit locally (one-time):**
```bash
make install                # recommended — installs deps + hooks together
# OR manually:
pip install -r requirements.txt
pre-commit install          # hooks fire on every git commit
pre-commit run --all-files  # run once on existing codebase

# Optional: voice notifications (TTS — installs separately due to networkx conflict)
pip install -r requirements-optional.txt
```

---

### 🔲 REMAINING

#### Priority: MEDIUM

| Task | Why Not Done Yet | Effort |
|------|-----------------|--------|
| **Multi-project real-world testing** | Tested on this repo only — needs 10+ different project types (Python, Java, JS, Go, Rust) | 1 week |
| **Checkpoint disaster drill** | Recovery code exists but never stress-tested (kill at each step, verify resume) | 1 day |
| **Version auto-bump on merge** | `sync-version.py` exists but not wired into CI to auto-bump on merge to main | 2 hrs |
| **Prometheus Grafana dashboard** | `metrics_exporter.py` exports metrics but no pre-built Grafana dashboard JSON yet | 1 day |
| **CORS protection on health/metrics** | Security headers scaffold in place; full CORS configuration pending | 2 hrs |

#### Priority: LOW (Future / Enterprise)

| Task | Description |
|------|-------------|
| **PyPI publish** | `pip install claude-workflow-engine` — package not yet published |
| **Metrics web dashboard** | Prometheus + Grafana dashboard for real-time pipeline visibility |
| **Team collaboration** | Multi-user sessions with role-based access |
| **Custom policy editor** | UI for creating/editing the 63 policies without editing markdown |
| **Webhook notifications** | Slack/Teams/Discord on pipeline complete/fail |
| **Plugin system** | Third-party skill/agent marketplace |

---

---

## Orchestration Template Fast-Path (v1.8.0)

### The Problem It Solves

Every time the pipeline runs, Steps 0-5 spend 6 LLM calls figuring out what you want:

```
Step 0: "What type of task is this?"          → LLM call
Step 1: "Do we need a plan?"                  → LLM call
Step 2: "Generate execution plan"             → LLM call
Step 3: "Break into subtasks"                 → LLM call (via subprocess)
Step 5: "Which skill and agent to use?"       → LLM call (via subprocess)
Step 7: "Build the system prompt"             → LLM call (via subprocess)
```

If you already know the answers — task type, complexity, which agents, what tasks — why make the LLM guess?

### The Solution: Pre-Fill the Template Once, Skip 6 Calls Every Time

```
┌──────────────────────────────────────────────────────────┐
│  Before (no template):                                    │
│  User types task → 7-8 LLM calls → Step 10 implements   │
│  Time: ~60s (hook mode)   Cost: 7 inference calls        │
├──────────────────────────────────────────────────────────┤
│  After (with template):                                   │
│  User fills template → 1 LLM call → Step 10 implements  │
│  Time: ~15s (hook mode)   Cost: 1 inference call         │
└──────────────────────────────────────────────────────────┘
```

**87% reduction in LLM inference cost. 75% reduction in pipeline latency.**

### How It Works

**Step 1 — Generate the template** using `prompt-generation-expert` (one-time per project type):

```
You are prompt-generation-expert. I will describe my project requirements
in plain language. Generate a COMPLETE orchestration template JSON.

MY REQUIREMENTS:
"""
Mujhe ek React + FastAPI app banani hai jisme users apne documents
upload kar sakein aur AI se questions pooch sakein.
PostgreSQL database, AWS deployment, GDPR compliance chahiye.
"""

Generate:
1. task_type, complexity, reasoning
2. tasks array with effort estimates
3. skill and agent selection
4. skills and agents arrays (all needed)
5. execution_pattern (parallel / sequential)
6. domains and constraints
```

**Step 2 — Save as JSON** (`my_project_template.json`):

```json
{
  "version": "1.0",
  "task_type": "Feature",
  "complexity": 8,
  "reasoning": "Multi-service app: React frontend + FastAPI backend + RAG pipeline + AWS infra. High complexity due to cross-service integration and GDPR compliance layer.",
  "plan_required": true,
  "tasks": [
    {"id": "T1", "description": "FastAPI backend with PostgreSQL and JWT auth", "estimated_effort": "high"},
    {"id": "T2", "description": "React frontend with document upload UI and Q&A chat", "estimated_effort": "medium"},
    {"id": "T3", "description": "RAG pipeline using Qdrant for document Q&A", "estimated_effort": "high"},
    {"id": "T4", "description": "AWS deployment with GDPR-compliant data handling", "estimated_effort": "medium"}
  ],
  "skill": "react-core",
  "agent": "react-engineer",
  "skills": ["react-core", "fastapi-core", "rag-core", "cloud-security-core"],
  "agents": ["react-engineer", "python-backend-engineer", "ai-engineer", "cloud-engineer"],
  "execution_pattern": "parallel",
  "domains": ["frontend", "backend", "ai", "cloud", "security"],
  "constraints": ["PostgreSQL", "AWS", "GDPR", "Qdrant", "Docker"]
}
```

**Step 3 — Run pipeline with template**:

```bash
python scripts/3-level-flow.py \
  --message="React + FastAPI document Q&A app with GDPR compliance" \
  --orchestration-template=my_project_template.json
```

**What happens inside:**

```
Pre-Analysis Gate detects template
    ↓
Injects into FlowState:
    step0_task_type    = "Feature"
    step0_complexity   = 8
    step1_plan_required = true
    step3_tasks_validated = [T1, T2, T3, T4]
    step5_skill        = "react-core"
    step5_agent        = "react-engineer"
    step5_skills       = [react-core, fastapi-core, rag-core, cloud-security-core]
    step5_agents       = [react-engineer, python-backend-engineer, ai-engineer, cloud-engineer]
    template_fast_path = True
    ↓
route_pre_analysis → "level3_step6"  (jumps directly)
    ↓
Step 6: Skill validation + download    (no LLM)
Step 7: Prompt assembly from state     (no LLM — template data already there)
Step 8: GitHub Issue creation          (API call)
Step 9: Branch creation                (API call)
Step 10: Implementation                (1 LLM call — the only one)
...
```

### Template vs RAG vs Full Pipeline

| Mode | When | Steps Skipped | LLM Calls | Hook Time |
|------|------|--------------|-----------|-----------|
| **Template Fast-Path** | `--orchestration-template` provided | Step 0 (2 subprocess calls) | **0** | ~2s |
| **RAG Hit** | Similar task run before (>=0.85 match) | Step 0 (2 subprocess calls) | **0** | ~3s |
| **Full Pipeline** | New task, no template | None | **7-8** | ~60s |

### Template Fields Reference

| Field | Required | Type | Maps To |
|-------|----------|------|---------|
| `task_type` | Yes | string | `step0_task_type` ("Feature", "Bug Fix", "Refactor", etc.) |
| `complexity` | Yes | int 1-10 | `step0_complexity` |
| `skill` | Yes | string | `step5_skill` (primary skill name) |
| `agent` | Yes | string | `step5_agent` (primary agent name) |
| `reasoning` | No | string | `step0_reasoning` (shown in prompt) |
| `plan_required` | No | bool | `step1_plan_required` (default: false) |
| `tasks` | No | array | `step3_tasks_validated` (subtask list) |
| `skills` | No | array | `step5_skills` (all skills to load) |
| `agents` | No | array | `step5_agents` (all agents to use) |
| `execution_pattern` | No | string | Informational (parallel/sequential) |
| `domains` | No | array | Informational (shown in prompt context) |
| `constraints` | No | array | Informational (shown in prompt context) |
| `system_prompt` | No | string | Written directly to `session/system_prompt.txt` if provided |

### Fail-Safe Behavior

The template fast-path is **fail-open** — if anything goes wrong, the pipeline falls back to normal flow:

```
Template file not found    → WARNING logged → full pipeline runs normally
Invalid JSON               → WARNING logged → full pipeline runs normally
Missing required fields    → WARNING logged → full pipeline runs normally
Template fast-path error   → WARNING logged → full pipeline runs normally
```

No pipeline interruption. No crash. Just a warning and normal execution.

### When To Use Templates

- **Recurring project types** — same stack every time (React + FastAPI, Spring Boot + Angular, etc.)
- **Team workflows** — standardize which agents and skills the team uses
- **CI/CD integration** — deterministic pipeline behavior without LLM variance
- **Cost optimization** — when running many tasks on the same project type
- **Speed-critical hooks** — when hook mode latency matters (15s vs 60s)

> See `orchestration_template.example.json` in the project root for a fully commented example.

---

## Quick Start

### Prerequisites

- Python 3.8+
- GitHub CLI (`gh`) installed and authenticated
- Ollama (optional, for local GPU inference)
- Qdrant (optional, for RAG vector storage)

### Installation

```bash
git clone https://github.com/techdeveloper-org/claude-workflow-engine.git
cd claude-workflow-engine
make install          # installs deps + activates git hooks in one shot
cp .env.example .env
# Edit .env with your API keys
```

`make install` runs two things automatically:
1. `pip install -r requirements.txt` — all Python dependencies including `pre-commit`
2. `pre-commit install` — activates the git hooks so ruff/black/isort run on every `git commit`

> **No `make`?** Run manually:
> ```bash
> pip install -r requirements.txt
> pre-commit install
> ```

### Running the Pipeline

```bash
# Full pipeline (all active steps)
python scripts/3-level-flow.py --message "your task description"

# Hook mode (Pre-0, Step 0, Steps 8-9 only, default)
CLAUDE_HOOK_MODE=1 python scripts/3-level-flow.py --message "fix login bug"

# Full mode (all 8 active steps including implementation, PR, closure)
CLAUDE_HOOK_MODE=0 python scripts/3-level-flow.py --message "add user profile feature"

# Template fast-path (skips Step 0, jumps to Step 8, ~2s hook time)
python scripts/3-level-flow.py \
  --message "add document Q&A feature" \
  --orchestration-template=my_template.json

# Debug mode
CLAUDE_DEBUG=1 python scripts/3-level-flow.py --message "your task" --summary

# Dry-run (Steps 0-7 only — analysis + prompt, skip GitHub/implementation)
python scripts/3-level-flow.py --message "your task" --dry-run
```

### Testing

```bash
# Run all tests
pytest tests/

# Run integration tests (full pipeline)
pytest tests/integration/

# Run MCP server tests
pytest tests/test_*mcp*.py

# Run with coverage (when configured)
pytest --cov=scripts --cov-report=html tests/
```

---

## Directory Structure

```
claude-workflow-engine/
|
+-- scripts/
|   +-- langgraph_engine/             # Core orchestration (155+ modules)
|   |   +-- core/                     # [v1.5] LazyLoader, ErrorHandler, NodeResult, create_step_node
|   |   +-- state/                    # [v1.5] FlowState, StepKeys, reducers, ToonObject, optimizer
|   |   +-- routing/                  # [v1.5] All routing functions split by level
|   |   +-- helper_nodes/             # [v1.5] Helper node functions split by concern
|   |   +-- diagrams/                 # [v1.5] Strategy: DiagramFactory + 13 UML generators
|   |   +-- parsers/                  # [v1.5] Abstract Factory: 4 language parsers (Py/Java/TS/Kotlin)
|   |   +-- sonarqube/                # Compat shim -> level3_execution/sonarqube/ package
|   |   +-- integrations/             # [v1.5] Lifecycle: GitHub/Jira/Figma/Jenkins adapters
|   |   +-- pipeline_builder.py       # [v1.5] Builder: PipelineBuilder chainable API
|   |   +-- orchestrator.py           # Main StateGraph pipeline
|   |   +-- flow_state.py             # Compat shim -> state/ package
|   |   +-- rag_integration.py        # Vector DB decision caching
|   |   +-- call_graph_builder.py     # Compat shim -> parsers/ package
|   |   +-- call_graph_analyzer.py    # Pipeline-ready analysis (impact, context, review)
|   |   +-- uml_generators.py         # Compat shim -> diagrams/ package
|   +-- architecture/                 # Helper scripts (sync, standards, execution)
|   +-- setup/                        # One-time environment setup scripts
|   +-- bin/                          # Windows .bat operational launchers
|   +-- tools/                        # Developer utilities (release, sync, metrics, voice)
|   +-- 3-level-flow.py               # Entry point
|   +-- pre-tool-enforcer.py          # PreToolUse hook (shim -> pre_tool_enforcer/)
|   +-- post-tool-tracker.py          # PostToolUse hook (shim -> post_tool_tracker/)
|   +-- stop-notifier.py              # Stop hook (shim -> stop_notifier/)
|
+-- src/mcp/                          # In-engine copies of session-mgr + vector-db (repos are source of truth) + bridge (session_hooks)
+-- policies/                         # 63 policy definitions (62 .md + 1 .json)
+-- tests/                            # 75 test files
+-- docs/                             # 71 documentation files
+-- docs/uml/                         # Auto-generated UML diagrams (13 types)
+-- rules/                            # 34 coding standard definitions
|
+-- VERSION                           # Single source of truth (1.8.2)
+-- CLAUDE.md                         # Project context for Claude Code
+-- setup.py                          # Package installation
+-- requirements.txt                  # Python dependencies
+-- .env.example                      # Configuration template
```

---

## Key Statistics

| Metric | Value |
|--------|-------|
| Pipeline Levels | 4 (Level -1, 1, 2, 3) |
| Execution Steps | 15 (Step 0 - Step 14) |
| MCP Servers | 20 (328 tools) — all in separate repos under [techdeveloper-org](https://github.com/orgs/techdeveloper-org/repositories) |
| MCP Tools | 328 |
| LangGraph Engine Modules | 90+ (root modules + 9 canonical packages, no shim layer) |
| Policy Files | 63 (62 .md + 1 .json) |
| Standards Files | 34 |
| Test Files | 75 |
| Total Python Files | 310+ |
| Call Graph | 578 classes, 3,985 methods, 4 languages (Python/Java/TS/Kotlin) |
| UML Diagram Types | 13 (CallGraph-powered) |
| Documentation Files | 71 |
| RAG Collections | 4 (Qdrant vector DB) |
| Supported Languages | 20+ |
| Supported Frameworks | 15+ |
| Quality Gates | 4 (SonarQube, coverage, breaking changes, tests) |

---

## How Our AI Workflow Compares to Others

No other AI coding tool automates the full Software Development Life Cycle. Here is an honest, feature-by-feature comparison:

| Capability | **Claude Workflow Engine** | GitHub Copilot | Cursor | Windsurf | Cline |
|-----------|:---:|:---:|:---:|:---:|:---:|
| **Code generation** | Yes | Yes | Yes | Yes | Yes |
| **Code editing** | Yes | Yes | Yes | Yes | Yes |
| **Multi-file editing** | Yes | Limited | Yes | Yes | Yes |
| **Task analysis + complexity scoring** | Yes (Step 0) | No | No | No | No |
| **Automated planning with phases** | Yes (Step 2) | No | No | No | No |
| **Call graph analysis before changes** | Yes (Steps 2,3,4,10,11) | No | No | No | No |
| **Impact analysis (what could break)** | Yes (danger zones, risk levels) | No | No | No | No |
| **Phase-scoped context (focused, not broad)** | Yes (Step 4) | No | No | No | No |
| **Skill/agent selection (16 skills, 13 agents)** | Yes (Step 5, RAG-powered) | No | No | No | No |
| **Auto GitHub issue creation** | Yes (Step 8) | No | No | No | No |
| **Dual issue tracking (GitHub + Jira)** | Yes (configurable) | No | No | No | No |
| **Figma design-to-code extraction** | Yes (configurable) | No | No | No | No |
| **Full integration lifecycle (create/update/close)** | Yes (Jira+Figma+Jenkins) | No | No | No | No |
| **Auto branch creation** | Yes (Step 9) | No | No | No | No |
| **Auto PR creation** | Yes (Step 11) | No | No | No | No |
| **5-layer code review** | Yes (Step 11) | No | No | No | No |
| **Breaking change detection (graph diff)** | Yes (Step 11) | No | No | No | No |
| **Review retry loop (max 3)** | Yes (Step 11) | No | No | No | No |
| **Auto issue closure** | Yes (Step 12) | No | No | No | No |
| **Auto documentation update** | Yes (Step 13, circular SDLC) | No | No | No | No |
| **UML diagram generation (13 types)** | Yes (Step 13) | No | No | No | No |
| **SonarQube/static analysis** | Yes (scan + auto-fix loop) | No | No | No | No |
| **Auto unit test generation (4 languages)** | Yes (template-based) | No | No | No | No |
| **Auto integration test generation** | Yes (CallGraph call-path based) | No | No | No | No |
| **Coverage analysis (AST-based)** | Yes (risk-prioritized) | No | No | No | No |
| **Quality gate enforcement** | Yes (4 gates, configurable) | No | No | No | No |
| **Tool call optimization (60-85% savings)** | Yes (4-layer system) | No | No | No | No |
| **Cross-session RAG learning** | Yes (Qdrant, 4 collections) | No | No | No | No |
| **Multi-language standards (8 langs)** | Yes (34 rule files, 5,000+ lines) | No | No | No | No |
| **Dependency resolution (5 build systems)** | Yes (Python/Java/Node/Go/Rust) | No | No | No | No |
| **Smart user interaction** | Yes (6 step-specific Q&A) | No | No | No | No |
| **Pipeline telemetry** | Yes (per-step JSONL) | No | No | No | No |
| **Dry-run mode** | Yes (--dry-run, Steps 0-7) | No | No | No | No |
| **Metrics aggregation** | Yes (sessions, steps, LLM, tools) | No | No | No | No |

### Summary

Other AI tools do **one thing well: code generation.** They read your file, suggest changes, and move on.

Claude Workflow Engine does **everything a software engineer does:**
1. Understands the task (complexity, type, risk)
2. Plans before coding (phases, impact analysis, CallGraph)
3. Selects the right tools (skills, agents, models)
4. Creates proper engineering artifacts (issue, branch)
5. Implements with full context (system prompt, graph awareness)
6. Reviews its own work (5-layer review, breaking change detection)
7. Fixes quality issues (SonarQube scan, auto-fix loop)
8. Generates tests (unit + integration, coverage-driven)
9. Enforces quality gates (block merge if gates fail)
10. Updates documentation (SRS, README, CHANGELOG, UML)
11. Closes the loop (issue closure, metrics, summary)

**The result: Not just code, but production-grade software delivered through an automated SDLC.**

---

## Quality Intelligence Pipeline

After implementation (Step 10), the system runs a complete quality pipeline:

```
Step 10: Implementation Complete
    |
    v
SonarQube Scan (API-first, configurable)
    |-- GET /api/issues/search -> bugs, vulnerabilities, code smells
    |-- GET /api/measures/component -> coverage, duplications
    |-- GET /api/qualitygates/project_status -> quality gate
    |-- Fallback: lightweight AST+regex scanner if SonarQube unavailable
    |
    v
Auto-Fix Loop (max 3 iterations)
    |-- Template fixes: bare except, eval, unused imports, hardcoded creds
    |-- Re-scan after fix to verify
    |-- Remaining issues flagged for LLM/human review
    |
    v
Test Generation
    |-- Unit tests: pytest (Python), JUnit5 (Java), Jest (TS), testing (Go)
    |-- Integration tests: CallGraph call-path-based
    |-- Coverage analysis: risk-prioritized untested methods
    |
    v
Quality Gate Enforcement
    |-- Gate 1: SonarQube (no CRITICAL/BLOCKER findings)
    |-- Gate 2: Coverage (>= 70% threshold, configurable)
    |-- Gate 3: Breaking Changes (CallGraph diff, no signature breaks)
    |-- Gate 4: Tests Exist (every modified file has test coverage)
    |-- Result: MERGE / FIX_AND_RETRY / MANUAL_REVIEW
    |
    v
Step 11: PR + Code Review (with quality gate results)
```

### Quality Gate Configuration

Quality gates are configurable via `.quality-gate.json` in your project root:

```json
{
    "sonar_block_on_critical": true,
    "coverage_threshold": 70.0,
    "coverage_drop_threshold": 5.0,
    "allow_breaking_changes": false,
    "require_tests_for_modified": true,
    "max_cyclomatic_increase": 10
}
```

SonarQube is configurable via environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| SONAR_HOST_URL | http://localhost:9000 | SonarQube server URL |
| SONAR_TOKEN | (none) | Authentication token |
| SONAR_PROJECT_KEY | (auto-detect) | Project identifier |
| SONAR_ORGANIZATION | (none) | SolarCloud organization |

---

## Jira Integration

The engine supports **dual GitHub + Jira issue tracking**. When `ENABLE_JIRA=1`, every GitHub Issue automatically gets a matching Jira issue - linked, synced, and closed together. Branch names use the Jira key (`feature/PROJ-123`), PRs are linked to Jira via remote links, and transitions happen automatically (In Progress -> In Review -> Done).

### Dual Workflow (GitHub + Jira)

```
Step 8:  GitHub Issue #42 created
         +-- Jira PROJ-123 created (same title/description)
         +-- Cross-link comment added to both

Step 9:  Branch: feature/proj-123 (from Jira key, not GitHub issue number)

Step 11: PR #15 created
         +-- PR linked to Jira PROJ-123 via remote link
         +-- Jira transitioned to "In Review"
         +-- Commits/PR visible in Jira issue history

Step 12: GitHub Issue #42 closed
         +-- Jira PROJ-123 transitioned to "Done"
         +-- Implementation summary added as comment
```

All Jira operations are **non-blocking** - if Jira is down, the pipeline continues with GitHub only.

### Setup

1. **Jira Cloud:**
   ```bash
   # In your .env file:
   JIRA_URL=https://your-domain.atlassian.net
   JIRA_USER=your-email@company.com
   JIRA_API_TOKEN=your-api-token  # from https://id.atlassian.com/manage-profile/security/api-tokens
   JIRA_API_VERSION=3
   ```

2. **Jira Server/Data Center:**
   ```bash
   JIRA_URL=https://jira.your-company.com
   JIRA_USER=your-username
   JIRA_API_TOKEN=your-personal-access-token
   JIRA_API_VERSION=2
   JIRA_AUTH_METHOD=bearer
   ```

### Available Tools (10)

| Tool | Description |
|------|-------------|
| `jira_create_issue` | Create issue with project key, summary, type, description, labels |
| `jira_get_issue` | Get full issue details by key (e.g., PROJ-123) |
| `jira_search_issues` | Search using JQL (Jira Query Language) |
| `jira_transition_issue` | Move issue through workflow states (e.g., To Do -> In Progress -> Done) |
| `jira_add_comment` | Add comment to an issue |
| `jira_link_pr` | Link a GitHub PR to a Jira issue via remote links |
| `jira_list_projects` | List all accessible Jira projects |
| `jira_get_transitions` | Get available workflow transitions for an issue |
| `jira_update_issue` | Update issue fields (summary, description, labels, assignee) |
| `jira_health_check` | Verify Jira server connectivity |

### Pipeline Integration

| Step | How Jira Is Used |
|------|-----------------|
| Step 8 | Create Jira issue (alternative to GitHub Issue) |
| Step 9 | Branch name uses Jira issue key (e.g., `feature/PROJ-123`) |
| Step 11 | Link PR to Jira issue via `jira_link_pr` |
| Step 12 | Transition issue to "Done" + add implementation comment |

### MCP Registration

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "jira-api": {
      "command": "python",
      "args": ["path/to/mcp-jira-api/server.py"],
      "env": {
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_USER": "your-email@company.com",
        "JIRA_API_TOKEN": "your-token"
      }
    }
  }
}
```

---

## Jenkins Integration

The engine supports Jenkins for build validation and CI/CD operations, complementing or replacing GitHub Actions in Step 11.

### Setup

```bash
# In your .env file:
JENKINS_URL=https://jenkins.your-company.com
JENKINS_USER=your-username
JENKINS_API_TOKEN=your-api-token  # Jenkins > Your Name > Configure > API Token
```

**Generate API Token:**
1. Log into Jenkins
2. Click your username (top-right)
3. Click "Configure"
4. Under "API Token", click "Add new Token"
5. Copy and store securely

### Available Tools (10)

| Tool | Description |
|------|-------------|
| `jenkins_trigger_build` | Trigger a build with optional parameters |
| `jenkins_get_build_status` | Get build result, duration, and status |
| `jenkins_get_console_output` | Get build console log (auto-truncated to 10K chars) |
| `jenkins_list_jobs` | List all Jenkins jobs with last build info |
| `jenkins_get_job_info` | Get detailed job configuration and health |
| `jenkins_list_builds` | List recent builds for a job |
| `jenkins_abort_build` | Stop a running build |
| `jenkins_get_queue_info` | Get build queue status |
| `jenkins_wait_for_build` | Poll build status until complete (configurable timeout) |
| `jenkins_health_check` | Verify Jenkins server connectivity |

### Pipeline Integration

| Step | How Jenkins Is Used |
|------|---------------------|
| Step 10 | Trigger build after implementation |
| Step 11 | Validate build passes before PR (alternative to `github_validate_build`) |
| Step 11 | Get console output for failed builds in code review |

### MCP Registration

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "jenkins-api": {
      "command": "python",
      "args": ["path/to/mcp-jenkins-ci/server.py"],
      "env": {
        "JENKINS_URL": "https://jenkins.your-company.com",
        "JENKINS_USER": "your-username",
        "JENKINS_API_TOKEN": "your-token"
      }
    }
  }
}
```

### Self-Signed Certificates

For Jenkins servers with self-signed SSL certificates:
```bash
JENKINS_VERIFY_SSL=false
```

---

## Figma Integration

The engine supports Figma for design-to-code workflows, extracting design tokens and components at Steps 3, 7, and 11 to inform implementation with accurate UI specifications.

### Setup

```bash
# In your .env file:
ENABLE_FIGMA=1
FIGMA_ACCESS_TOKEN=figd_...   # Figma > Account Settings > Personal Access Tokens
FIGMA_TEAM_ID=                # Optional: your Figma team ID
```

**Generate Access Token:**
1. Log into Figma
2. Click your avatar (top-right) > Account Settings
3. Scroll to "Personal access tokens"
4. Click "Create new token"
5. Copy and store securely

### Pipeline Integration

| Step | How Figma Is Used |
|------|-------------------|
| Step 3 | Extract component list and pages to inform task breakdown |
| Step 7 | Extract design tokens (colors, typography, spacing) and inject as prompt snippet |
| Step 11 | Run design review checklist against implementation summary |

### Available Tools (10)

| Tool | Description |
|------|-------------|
| `figma_get_file_info` | Get file metadata (name, pages, last modified) |
| `figma_get_components` | List all components and component sets in a file |
| `figma_get_styles` | Get named styles (color, text, effect, grid) |
| `figma_extract_design_tokens` | Extract color, typography, spacing, radii, and shadow tokens |
| `figma_get_node` | Get a specific node by ID |
| `figma_get_images` | Export nodes as images (PNG/SVG/PDF) |
| `figma_get_comments` | Get all comments in a file |
| `figma_post_comment` | Post a comment to a file |
| `figma_get_team_projects` | List projects for a team |
| `figma_health_check` | Verify Figma API connectivity and token validity |

### MCP Registration

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "figma-api": {
      "command": "python",
      "args": ["path/to/src/mcp/figma_mcp_server.py"],
      "env": {
        "FIGMA_ACCESS_TOKEN": "figd_your_token_here",
        "FIGMA_TEAM_ID": ""
      }
    }
  }
}
```

### Design Token Extraction

When a Figma URL is detected in the task description, the pipeline automatically:
1. Extracts the file key from the URL (supports `/file/` and `/design/` URL formats)
2. Fetches color, typography, spacing, border-radius, and shadow tokens
3. Formats them as a Markdown snippet and injects it into the Step 7 implementation prompt
4. Runs a design compliance checklist during Step 11 code review

---

## Multi-Language Standards

The pipeline loads language-specific coding standards and injects them into prompts. Level 2 auto-detects your project language and loads the appropriate rules.

| Language | Standards File | Lines | Key Topics |
|----------|---------------|-------|------------|
| Universal | 01-common-standards.md | 469 | 12 categories of universal rules |
| Python/Flask | 02-backend-standards.md | 609 | PEP 8, type hints, async patterns |
| Java/Spring | 03-microservices-standards.md | 868 | Spring Boot, DI, JPA patterns |
| Frontend/React | 04-frontend-standards.md | 858 | Component patterns, state management |
| Security | 05-security-standards.md | 630 | OWASP, auth, encryption |
| TypeScript | 06-typescript-standards.md | 482 | Strict mode, no any, generics |
| Go | 07-go-standards.md | 624 | Error handling, goroutines, interfaces |
| Rust | 08-rust-standards.md | 517 | Ownership, Result/Option, unsafe |
| Swift | 09-swift-standards.md | 616 | Optionals, SwiftUI, protocols |
| Kotlin | 10-kotlin-standards.md | 531 | Coroutines, sealed classes, Compose |
| All (doc governance) | 11-documentation-files.md | — | Permitted root docs: SRS.md, README.md, CLAUDE.md, VERSION, CHANGELOG.md only |
| All (code comments) | 12-docstrings-only.md | — | Docstrings required; inline explanatory comments banned (Python/Java/TypeScript/Kotlin) |

**Total: 6,204+ lines of standards across 12 files, 8 languages.**

Level 2 also runs linter validation (ruff/flake8) when available — violations feed into Step 11 code review.
Rules 11 and 12 are enforced on every session: rule 11 gates doc commits, rule 12 gates all new/modified functions.

---

## Configuration

All configuration is done through environment variables in `.env` (copy from `.env.example`). No hardcoded paths exist anywhere in the codebase - everything resolves through `path_resolver.py`.

### Integration Flags

All external integrations are **disabled by default**. Enable only what you need by setting these flags in your `.env` file. Each flag is independent — you can enable Jira without Figma, Jenkins without SonarQube, etc.

| Flag | Default | Steps Affected | What It Does |
|------|---------|---------------|-------------|
| `ENABLE_JIRA` | `0` | 8, 9, 11, 12 | **Dual GitHub + Jira issue tracking.** When enabled, every GitHub Issue gets a matching Jira issue — linked, synced, and closed together. Branch names use the Jira key (`feature/PROJ-123`). Requires `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`. |
| `ENABLE_FIGMA` | `0` | 0, 10, 11, 12 | **Design-to-code pipeline.** Extracts components and injects design tokens inside Step 0 orchestration template, posts progress comments on Figma frames (Steps 10/12), and adds design fidelity checklist to code review (Step 11). Requires `FIGMA_ACCESS_TOKEN` and `FIGMA_FILE_KEY`. |
| `ENABLE_JENKINS` | `0` | 11 | **Jenkins CI/CD build validation.** Triggers a Jenkins build on PR creation (Step 11) and waits for the result before merging. Requires `JENKINS_URL`, `JENKINS_USER`, `JENKINS_TOKEN`, `JENKINS_JOB_NAME`. |
| `ENABLE_SONARQUBE` | `0` | 10 | **Static analysis + auto-fix loop.** Runs a SonarQube scan after implementation (Step 10). If issues are found, the pipeline attempts auto-fixes and re-scans before continuing. Requires `SONARQUBE_URL`, `SONARQUBE_TOKEN`, `SONARQUBE_PROJECT_KEY`. |
| `ENABLE_CI` | `false` | 11 | **GitHub Actions CI pipeline.** Enables the `.github/workflows/` CI pipeline on PRs. Set to `true` to enable CI checks on every PR. |

**Quick enable example:**

```bash
# In your .env file — enable only what you use:
ENABLE_JIRA=1
ENABLE_FIGMA=1
ENABLE_JENKINS=0   # not using Jenkins
ENABLE_SONARQUBE=0 # not using SonarQube
ENABLE_CI=false
```

> All flags default to `0` (disabled). The pipeline runs fine without any of them — GitHub-only workflow is the baseline.

---

### Pipeline Settings

| Variable | Default | What It Does |
|----------|---------|-------------|
| `CLAUDE_HOOK_MODE` | `1` | **Controls how many steps run.** `1` = Hook Mode (Pre-0, Step 0, Steps 8-9 -- generates prompt + creates issue/branch, you implement). `0` = Full Mode (all 8 active steps including implementation, PR, and issue closure). Use `1` for daily work, `0` for full automation. |
| `CLAUDE_DEBUG` | `0` | **Enables verbose logging.** `1` = prints every LLM call, every state transition, every decision. Useful when a step fails and you need to see exactly what happened. |
| `INFERENCE_MODE` | `auto` | **Which hardware to use for AI inference.** `auto` = smart routing (simple tasks to NPU, complex to GPU). `gpu_only` = only use Ollama GPU. `npu_only` = only use Intel NPU. Most users should leave this as `auto`. |

### LLM Provider Settings

Set your primary provider in `.env`. Ollama is always the default fallback unless you override it with `LLM_FALLBACK`.

| Variable | Default | What It Does |
|----------|---------|-------------|
| `LLM_PROVIDER` | `auto` | **Which AI provider to use.** Options: `auto` (try all), `anthropic`, `openai`, `claude_cli`, `ollama`. When set to a specific provider, Ollama is automatically used as fallback. |
| `LLM_FALLBACK` | _(ollama)_ | **Override the default fallback chain.** Comma-separated: `LLM_FALLBACK=anthropic,ollama`. Leave unset to use Ollama as fallback (recommended). |
| `OLLAMA_ENDPOINT` | `http://localhost:11434` | **Where Ollama GPU server is running.** Change this if Ollama runs on a different port or remote machine. |
| `OLLAMA_MODEL_FAST` | `qwen2.5:7b` | **Ollama model for fast tasks** (classification, JSON, yes/no). |
| `OLLAMA_MODEL_DEEP` | `qwen2.5:14b` | **Ollama model for deep tasks** (planning, complex reasoning). |
| `ANTHROPIC_API_KEY` | _(none)_ | **Your Anthropic API key.** Required for `LLM_PROVIDER=anthropic`. Uses official `anthropic` Python SDK with auto-retry. Get from console.anthropic.com. |
| `ANTHROPIC_MODEL_FAST` | `claude-haiku-4-5` | **Anthropic model for fast tasks.** |
| `ANTHROPIC_MODEL_BALANCED` | `claude-sonnet-4-6` | **Anthropic model for balanced tasks.** |
| `ANTHROPIC_MODEL_DEEP` | `claude-opus-4-6` | **Anthropic model for deep reasoning.** |
| `OPENAI_API_KEY` | _(none)_ | **Your OpenAI API key.** Required for `LLM_PROVIDER=openai`. |
| `OPENAI_MODEL_FAST` | `gpt-4o-mini` | **OpenAI model for fast tasks.** |
| `OPENAI_MODEL_DEEP` | `gpt-4o` | **OpenAI model for deep tasks.** |
| `GITHUB_TOKEN` | _(none)_ | **GitHub personal access token.** Required for Steps 8-12 (issue creation, branch, PR). Without this, the pipeline stops at Step 7. Falls back to `gh auth token` if not set. |

**Quick setup examples:**

```bash
# Use OpenAI, fall back to Ollama if it fails
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Use Anthropic Claude directly, fall back to Ollama
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Use local Ollama only (completely free, no API key)
LLM_PROVIDER=ollama

# Let engine decide (tries Ollama first, then cloud)
LLM_PROVIDER=auto
```

### Path System - Cross-Platform Directory Standard

Every path in the engine follows a strict standard. The golden rule: **never hardcode an absolute path**. All paths resolve through environment variables with cross-platform defaults using `Path.home()` (which returns `C:\Users\<you>` on Windows, `/home/<you>` on Linux, `/Users/<you>` on Mac).

The central authority is `src/utils/path_resolver.py` - a singleton that every module imports. It resolves paths in this priority:

```
1. Environment variable (if set)     -> highest priority, you control it
2. Path.home() based default         -> works on any OS, any username
3. Project-local fallback            -> when nothing else exists
```

#### Claude Directories

These are where Claude Code stores its configuration, scripts, and data.

| Variable | Default | What It Is | Why It Exists |
|----------|---------|-----------|---------------|
| `CLAUDE_HOME` | `~/.claude/` | **Root of all Claude directories.** Everything Claude-related lives under this folder. On Windows: `C:\Users\you\.claude\`, on Linux: `/home/you/.claude/`, on Mac: `/Users/you/.claude/`. | Claude Code creates this automatically. All hooks, settings, memory, and sessions live here. Change this only if you want Claude to use a completely different location (e.g., on an external drive). |
| `CLAUDE_SCRIPTS_DIR` | `~/.claude/scripts/` | **Where hook scripts live.** Contains `3-level-flow.py`, `pre-tool-enforcer.py`, `post-tool-tracker.py`, `stop-notifier.py`. These are the scripts that run on every Claude Code event (user message, tool use, session end). | Hooks reference these scripts by absolute path in `settings.json`. The engine downloads them from the repo to this directory. If you're developing hooks, you might point this to your repo's `scripts/` directory instead. |
| `CLAUDE_POLICIES_DIR` | `~/.claude/policies/` | **Where policy definition files live.** The 49 policy `.md` files that define rules for every pipeline step. | Used by Level 2 (Standards) to load coding standards and enforcement rules. Change if you want to use custom policies for different projects. |
| `CLAUDE_SETTINGS_FILE` | `~/.claude/settings.json` | **Claude Code's main configuration file.** Defines hooks (which scripts run on which events), permissions, and MCP server registrations. | This is read by Claude Code itself, not by the engine. The engine provides a template in `scripts/settings-config.json` that you customize with your paths. |
| `CLAUDE_INSIGHT_DATA_DIR` | `~/.claude/memory/` | **Where all runtime data is stored.** Sessions, logs, flow traces, checkpoints, anomaly records, performance metrics. This is the "database" of the engine. | Has a 3-tier fallback: (1) this env var, (2) `~/.claude/memory/` if it exists, (3) `./data/` in the project root. The IDE launcher sets this to control where data goes. |

#### Log & Data Directories

These are where the pipeline writes telemetry, sessions, cache, and quality data. The monitoring system reads from these paths.

| Variable | Default | Function | What's Stored |
|----------|---------|----------|--------------|
| `CLAUDE_LOGS_DIR` | `~/.claude/logs/` | `get_logs_dir()` | **Root for ALL log data.** Set this ONE variable and all sub-paths below change automatically. Monitoring repo uses this to find data. |
| _(auto)_ | `{LOGS}/sessions/` | `get_session_logs_dir()` | Per-session folders with session.json, flow-trace.json, prompts. **409+ sessions** stored here. |
| _(auto)_ | `{LOGS}/telemetry/` | `get_telemetry_dir()` | Per-step JSONL files with timing, status, LLM calls. Written by Level 1 (5 nodes) + Level 3 (8 active steps). |
| _(auto)_ | `{LOGS}/level/` | `get_level_logs_dir()` | Per-level execution logs (Level -1, 1, 2, 3 status). |
| _(auto)_ | `{LOGS}/cache/` | `get_cache_logs_dir()` | Context cache data (SHA-256 keyed, 24h TTL). **576+ items.** |
| _(auto)_ | `{LOGS}/errors/` | `get_error_logs_dir()` | Error logs with stack traces, severity, recovery actions. |
| _(auto)_ | `{LOGS}/flow-traces/` | `get_flow_traces_dir()` | Pipeline flow execution traces for debugging. |
| _(auto)_ | `{LOGS}/benchmarks/` | `get_benchmarks_dir()` | Performance benchmark history for metrics dashboard. |
| _(auto)_ | `{LOGS}/tool-optimization.jsonl` | `get_tool_opt_log()` | Tool call optimization log (savings %, per-tool stats). |

#### Skill & Agent Directories

| Variable | Default | Function | What's Stored |
|----------|---------|----------|--------------|
| `CLAUDE_SKILLS_DIR` | `~/.claude/skills/` | `get_skills_dir()` | 16 skill definitions (SKILL.md files). Flat structure: `skills/{name}/SKILL.md`. |
| `CLAUDE_AGENTS_DIR` | `~/.claude/agents/` | `get_agents_dir()` | 13 agent definitions (agent.md files). One dir per agent: `agents/{name}/agent.md`. |

#### Complete Directory Tree

```
~/.claude/                              # CLAUDE_HOME
├── logs/                               # CLAUDE_LOGS_DIR
│   ├── sessions/{session_id}/          # get_session_logs_dir()
│   │   ├── session.json                #   Session metadata
│   │   ├── flow-trace.json             #   Pipeline execution trace
│   │   ├── system_prompt.txt           #   Generated prompt (Step 7)
│   │   └── execution-summary.txt       #   Final summary (Step 14)
│   ├── telemetry/{session_id}.jsonl    # get_telemetry_dir()
│   ├── level/                          # get_level_logs_dir()
│   ├── cache/                          # get_cache_logs_dir()
│   ├── errors/                         # get_error_logs_dir()
│   ├── flow-traces/                    # get_flow_traces_dir()
│   ├── benchmarks/                     # get_benchmarks_dir()
│   └── tool-optimization.jsonl         # get_tool_opt_log()
├── scripts/                            # CLAUDE_SCRIPTS_DIR
│   ├── 3-level-flow.py                 #   Pipeline entry point
│   ├── pre-tool-enforcer.py            #   PreToolUse hook
│   ├── post-tool-tracker.py            #   PostToolUse hook
│   └── stop-notifier.py               #   Stop hook
├── policies/                           # CLAUDE_POLICIES_DIR
│   ├── 01-sync-system/                 #   Level 1 policies
│   ├── 02-standards-system/            #   Level 2 policies
│   └── 03-execution-system/            #   Level 3 policies (8 active steps)
├── skills/                             # CLAUDE_SKILLS_DIR (16 skills)
├── agents/                             # CLAUDE_AGENTS_DIR (13 agents)
├── memory/                             # CLAUDE_INSIGHT_DATA_DIR
└── settings.json                       # CLAUDE_SETTINGS_FILE
```

#### How It Works (Single Source of Truth)

```python
# In ANY module - import path_resolver, get the path:
from utils.path_resolver import get_telemetry_dir, get_session_logs_dir

telemetry = get_telemetry_dir()  # ~/.claude/logs/telemetry/ (auto per OS)
sessions = get_session_logs_dir()  # ~/.claude/logs/sessions/

# Override via env var (e.g., for monitoring repo on different machine):
# export CLAUDE_LOGS_DIR=/mnt/shared/claude-logs
# Now get_telemetry_dir() returns /mnt/shared/claude-logs/telemetry/
```

**21 files** in the engine import from `path_resolver.py`. Change one path there = all 21 files automatically update. Zero hardcoded absolute paths in the codebase.

#### Intel AI Directories

These are where GPU and NPU hardware inference runs from. Only needed if you use local AI models (Ollama, Intel AI Boost).

| Variable | Default | What It Is | Why It Exists |
|----------|---------|-----------|---------------|
| `INTEL_AI_PATH` | `~/intel-ai/` | **Root directory for all Intel AI tools and models.** Contains GPU (Ollama), NPU (llama-cli), and model files. On Windows: `C:\Users\you\intel-ai\`, on Linux: `/home/you/intel-ai/`. | This is the base that GPU/NPU/Models paths are built from. Set this once and all sub-paths inherit it. If you installed Intel AI tools in a custom location, just set this one variable. |
| `INTEL_AI_GPU_PATH` | `~/intel-ai/gpu/` | **Directory containing the Ollama GPU server.** Has `ollama.exe` (Windows) or `ollama` (Linux/Mac) and its configuration. | Ollama with Intel Arc GPU drivers for fast local inference. The engine starts and manages this server automatically. |
| `INTEL_AI_NPU_PATH` | `~/intel-ai/npu/` | **Directory containing the Intel AI Boost NPU CLI.** Has `llama-cli-npu.exe` (Windows) for running models on Intel's Neural Processing Unit. | NPU is 2-3x faster than GPU for simple classification tasks. Used for Step 1 (plan decision) and Step 3 (task breakdown) where speed matters more than quality. |
| `INTEL_AI_MODELS_PATH` | `~/intel-ai/models/` | **Where AI model files are stored.** Sub-directories: `gpu/` (Ollama models), `npu/` (GGUF files for NPU), `openvino-npu/` (OpenVINO optimized models). | Model files are large (1-8 GB each). Keeping them in one place makes it easy to manage, backup, or move them. The model discovery system scans this directory to find available models. |
| `INTEL_AI_GPU_EXE` | `~/intel-ai/gpu/ollama[.exe]` | **Exact path to the Ollama executable.** Automatically appends `.exe` on Windows. | Override if your Ollama is installed system-wide (e.g., `/usr/local/bin/ollama` on Linux) instead of in the Intel AI directory. |
| `INTEL_AI_NPU_EXE` | `~/intel-ai/npu/llama-cli-npu[.exe]` | **Exact path to the NPU CLI executable.** Automatically appends `.exe` on Windows. | Override if your NPU tools are in a non-standard location. |

#### How Paths Work Across Platforms

```
Windows user "alice":
  CLAUDE_HOME     = C:\Users\alice\.claude\
  INTEL_AI_PATH   = C:\Users\alice\intel-ai\
  GPU executable  = C:\Users\alice\intel-ai\gpu\ollama.exe

Linux user "bob":
  CLAUDE_HOME     = /home/bob/.claude/
  INTEL_AI_PATH   = /home/bob/intel-ai/
  GPU executable  = /home/bob/intel-ai/gpu/ollama

Mac user "carol":
  CLAUDE_HOME     = /Users/carol/.claude/
  INTEL_AI_PATH   = /Users/carol/intel-ai/
  GPU executable  = /Users/carol/intel-ai/gpu/ollama

Custom override (any OS):
  export INTEL_AI_PATH=/opt/ai-models
  -> GPU path becomes /opt/ai-models/gpu/
  -> NPU path becomes /opt/ai-models/npu/
  -> Models path becomes /opt/ai-models/models/
```

#### Quick Setup Example

```bash
# Minimum required (most users)
cp .env.example .env
# Edit .env: set GITHUB_TOKEN=ghp_your_token

# If Intel AI tools are in a custom location
export INTEL_AI_PATH=/path/to/your/intel-ai

# If Claude home is non-standard
export CLAUDE_HOME=/path/to/your/.claude

# That's it - all other paths derive automatically
```

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v1.14.0** | 2026-04-04 | Step 0 redesign: 2 claude CLI subprocess calls (prompt-gen-expert + orchestrator-agent). Template stored in `level3_execution/templates/`. `call_streaming_script()` helper with inherited stderr for real-time terminal output. Step 2 (Plan Mode) removed. Planning time: ~75s -> ~15s. |
| **v1.13.0** | 2026-04-03 | Level 3 simplification: removed Steps 1,3,4,5,6,7. Pipeline 15 steps -> 9 steps. Step 0 collapsed all planning into 1 template call. `docs/impact_map.md` architecture blueprint created. |
| **v1.12.0** | 2026-04-03 | scripts/ root cleanup: organized 31 files into setup/ (9), bin/ (5), tools/ (17). Path references updated across cli.py, step14, shell scripts. |
| **v1.2.0 - v1.2.1** | 2026-03-18 | CallGraph-driven pipeline intelligence (Steps 2/3/4/10/11), phase-scoped context, 15 MCP servers (split LLM into Ollama + Anthropic + OpenAI + Router), Quality Intelligence Layer (SonarQube API-first, auto-fix, test gen, coverage, quality gates), 5 new language standards (TypeScript, Go, Rust, Swift, Kotlin), user interaction system, dependency resolver, metrics aggregator, dry-run mode, telemetry, plan validation, Level 2 enforcement |
| **7.6.0** | 2026-03-18 | Call graph builder (class-level FQN, impact analysis, 47 tests), path standardization (30+ hardcoded paths removed, env var overrides) |
| 7.5.0 | 2026-03-18 | UML diagram generation (13 types), 12th MCP server (uml-diagram, 15 tools), AST + LLM hybrid, call_graph_analyzer.py (4 pipeline functions) |
| 7.5.0 | 2026-03-17 | Gap analysis fixes, all 49 policies complete, code graph analyzer, Level 1 integration |
| 7.5.0 | 2026-03-16 | RAG integration, 11th MCP server (vector-db), cross-session learning, 109 tools |
| 7.4.0 | 2026-03-16 | Dynamic versioning, SRS rewrite, MCP health checks |
| 7.3.0 | 2026-03-16 | 10 MCP servers (91 tools), hook migration to MCP imports |
| 7.2.0 | 2026-03-15 | 7 design patterns, Anthropic API as 4th LLM provider |
| 5.7.0 | 2026-03-14 | Workflow-only repo (monitoring removed) |
| 5.0.0 | 2026-03-10 | Initial unified policy enforcement framework |

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Maintainers:** TechDeveloper
**Repository:** https://github.com/techdeveloper-org/claude-insight
