# Claude Workflow Engine

**The first AI tool that follows full SDLC** - from task analysis to merged PR, automatically.

**Version:** 1.4.1 | **Status:** Alpha | **Last Updated:** 2026-03-18

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
  Step 0:  Analyzes task -> Bug Fix, complexity 4/10
  Step 1:  Decides plan mode -> Not needed (simple bug)
  Step 2:  Skipped (no plan needed)
  Step 3:  Breaks into tasks -> 2 tasks with file targets
  Step 4:  Refines context -> TOON with full project state
  Step 5:  Selects skill -> python-core + testing-core
  Step 6:  Validates skills -> Downloaded and ready
  Step 7:  Generates prompt -> system_prompt.txt + user_message.txt
  Step 8:  Creates GitHub issue -> #42 "bugfix: login timeout"
  Step 9:  Creates branch -> bugfix/issue-42
  Step 10: Implements fix -> With full context from Steps 0-7
  Step 11: Creates PR -> Reviews code, retries if needed (max 3x)
  Step 12: Closes issue -> With implementation summary
  Step 13: Updates docs -> CLAUDE.md + execution-docs.md
  Step 14: Final summary -> execution-summary.txt + voice notification
```

**Total time: ~60 seconds for Steps 0-9 (hook mode), ~170 seconds full pipeline.**

---

## Architecture

### 4-Level Pipeline

```
Level -1: AUTO-FIX         3 checks: Unicode, encoding, paths
    |
Level 1:  CONTEXT SYNC     Session + parallel [complexity, context] + TOON compress
    |
Level 2:  STANDARDS         Common + conditional Java + tool optimization + MCP discovery
    |
Level 3:  EXECUTION         15 steps (Step 0-14): Full SDLC automation
```

### 15-Step SDLC Pipeline (Level 3)

| Phase | Steps | What Happens |
|-------|-------|-------------|
| **Analysis & Planning** | 0-2 | Task analysis, complexity scoring, plan mode decision; Step 2: Plan Execution + **CallGraph impact analysis** + plan validation |
| **Preparation** | 3-7 | Step 3: Task Breakdown + **CallGraph file-to-phase mapping**; Step 4: TOON Refinement + **phase-scoped context injection**; skill/agent selection, prompt generation |
| **Issue & Branch Automation** | 8-9 | GitHub Issue + Jira Issue (dual, configurable), branch from Jira key (`feature/PROJ-123`), PR-to-Jira linking |
| **Implementation** | 10 | Implementation + **CallGraph snapshot + context** + SonarQube scan + auto-test generation |
| **Review & Closure** | 11-12 | PR + Code Review + **CallGraph diff + breaking change detection + quality gate**, review loop (max 3 retries), issue closure with summary |
| **Finalization** | 13-14 | Documentation + UML diagram generation (13 types), execution summary + voice notification |

### Execution Modes

```
Hook Mode (default, CLAUDE_HOOK_MODE=1):
  Steps 0-9   -> Pipeline (analysis + prompt + GitHub issue + branch)
  Steps 10-14 -> Skipped (user implements, then runs Full Mode for PR/closure)

Full Mode (CLAUDE_HOOK_MODE=0):
  Steps 0-14  -> All steps execute sequentially
```

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

**4. Better Skill Selection (Step 5)**

The call graph reveals the **actual architecture** - not what the README says, but what the code actually does:
- Heavy use of async/await? Select `asyncio` patterns
- Deep inheritance trees? Needs OOP expertise
- Method complexity > 20? Needs refactoring skill
- Cross-class coupling > 10? Needs architectural skill

**5. Precise Code Review (Step 11)**

The PR review loop uses the call graph to check:
- Did the change touch a bottleneck method? Flag for extra review
- Does the new code introduce circular dependencies?
- Is the method complexity within acceptable bounds?
- Are all affected callers still compatible with the change?

**6. Complete UML Diagrams (Step 13)**

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
| `analyze_impact_before_change(method_fqn)` | Step 2 | Pre-plan risk assessment - returns all callers, call depth, and blast radius before any code change |
| `get_implementation_context(method_fqn)` | Step 10 | Caller/callee awareness during implementation - gives full context of what calls the target and what it calls |
| `review_change_impact(before_snapshot, after_snapshot)` | Step 11 | Before/after graph comparison for code review - detects new call edges, removed edges, and breaking changes |
| `snapshot_call_graph()` | Step 10 | Captures serializable call graph state for diff comparison in Step 11 |

The data flow across steps:
```
Step 2:  analyze_impact_before_change() -> risk score -> informs plan complexity
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
| RAG Integration | rag_integration.py | Vector DB decision caching, cross-session learning |
| Call Graph Analyzer | call_graph_analyzer.py | Pipeline impact analysis (6 functions for Steps 2/3/4/10/11) |
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

### LangGraph Orchestration (90 modules)

- StateGraph with 200+ typed state fields
- Parallel execution via `Send()` API (Level 1: 4 concurrent tasks)
- Conditional routing (plan mode, Java detection, PR retry loop)
- Checkpoint recovery (resume from any step after crash)
- Signal handling (Ctrl+C graceful recovery)

### 18 MCP Servers (313 tools)

All servers use FastMCP protocol (stdio JSON-RPC), registered in `~/.claude/settings.json`:

| Server | File | Tools | Purpose |
|--------|------|-------|---------|
| git-ops | git_mcp_server.py | 14 | Git operations (branch, commit, push, pull, stash, diff, fetch, cleanup) |
| github-api | github_mcp_server.py | 12 | GitHub (issue, PR, merge, label, build validate, full merge cycle) |
| session-mgr | session_mcp_server.py | 14 | Session lifecycle (create, chain, tag, accumulate, finalize, work items) |
| policy-enforcement | enforcement_mcp_server.py | 11 | Policy compliance, flow-trace, module health, system health |
| llm-router | llm_router_mcp_server.py | 4 | Intelligent LLM routing, step classification, model selection |
| llm-provider | llm_mcp_server.py | 8 | LLM access (4 providers, hybrid GPU-first, model selection) (legacy, kept for backward compat) |
| ollama-provider | ollama_mcp_server.py | 5 | Local Ollama GPU inference, model discovery, pull |
| anthropic-provider | anthropic_mcp_server.py | 4 | Direct Anthropic Claude API, cost estimation |
| openai-provider | openai_mcp_server.py | 4 | Direct OpenAI GPT API, cost estimation |
| token-optimizer | token_optimization_mcp_server.py | 10 | Token reduction (AST navigation, smart read, dedup, 60-85% savings) |
| pre-tool-gate | pre_tool_gate_mcp_server.py | 8 | Pre-tool validation (8 policy checks, skill hints) |
| post-tool-tracker | post_tool_tracker_mcp_server.py | 6 | Post-tool tracking (progress, commit readiness, stats) |
| standards-loader | standards_loader_mcp_server.py | 7 | Standards (project detect, framework detect, hot-reload) |
| skill-manager | skill_manager_mcp_server.py | 8 | Skill lifecycle (load, search, validate, rank, conflicts) |
| vector-db | vector_db_mcp_server.py | 11 | Vector RAG (Qdrant, 4 collections, semantic search, node decisions) |
| uml-diagram | uml_diagram_mcp_server.py | 15 | UML generation (13 diagram types, AST + LLM, Mermaid/PlantUML, Kroki.io rendering) |
| jira-api | jira_mcp_server.py | 10 | Jira (create/get/search/transition issues, add comments, link PRs, Cloud + Server) |
| jenkins-api | jenkins_mcp_server.py | 10 | Jenkins CI/CD (trigger/abort builds, console output, job info, queue, build polling) |

### RAG Integration (Vector DB Decision Caching)

Every pipeline node stores its decision in Vector DB. Before LLM calls, the pipeline checks RAG for similar past decisions. If confidence >= step-specific threshold, RAG result replaces LLM call (saving inference time and cost).

| Step | Threshold | Rationale |
|------|-----------|-----------|
| Step 0 (Task Analysis) | 0.85 | Needs high match for accurate classification |
| Step 1 (Plan Decision) | 0.80 | Binary decision, easier to cache |
| Step 5 (Skill Selection) | 0.82 | Moderate - needs context match |
| Step 7 (Final Prompt) | 0.90 | Near-exact match needed |
| Step 14 (Summary) | 0.75 | Low stakes, summary is flexible |

**Collections:** `node_decisions`, `sessions`, `flow_traces`, `tool_calls`

### Hybrid LLM Inference (4 providers)

```
GPU-first: Ollama (local) -> Claude CLI -> Anthropic API -> OpenAI API
```

- Complexity-based model selection (simple=fast model, complex=powerful model)
- Automatic fallback chain when primary provider is unavailable
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
+-- 03-execution-system/   Level 3: All 15 steps + failure prevention
```

---

## Current Status: What's Built vs What's Remaining

### BUILT (v7.6.0 - Alpha)

| Component | Status | Details |
|-----------|--------|---------|
| **15-Step Pipeline** | COMPLETE | All steps produce real output (not stubs) |
| **4-Level Architecture** | COMPLETE | Level -1 through Level 3 fully operational |
| **16 MCP Servers** | COMPLETE | 293 tools, all tested and registered |
| **RAG Integration** | COMPLETE | 4 Vector DB collections, step-specific thresholds |
| **Hook System** | COMPLETE | Pre/post tool enforcement with blocking |
| **Policy System** | COMPLETE | 63 policies covering all 15 steps |
| **Multi-Project Detection** | COMPLETE | 20+ languages/frameworks auto-detected |
| **Hybrid LLM Inference** | COMPLETE | 4-provider fallback chain |
| **Token Optimization** | COMPLETE | AST navigation, dedup, 60-85% savings |
| **Session Management** | COMPLETE | Chaining, TOON compression, archival |
| **GitHub Integration** | COMPLETE | Issue, branch, PR, merge, review loop |
| **Standards Enforcement** | COMPLETE | Common + framework-specific with 5 hooks |
| **Cross-Session Learning** | COMPLETE | RAG pattern detection + skill selection boost |
| **Test Suite** | COMPLETE | 64 test files, integration tests for all 15 steps |
| **Documentation** | COMPLETE | 46 docs, architecture diagrams, guides |
| **Installation** | COMPLETE | setup.py, requirements.txt, .env.example |

### REMAINING (Roadmap to v1.0.0 Production)

#### Phase 1: Hardening (Priority: HIGH)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| Code coverage measurement | Add `pytest --cov`, set 70% threshold | 2 hrs | Know actual test coverage % |
| Input validation layer | Sanitize user prompts, length limits, injection prevention | 3 hrs | Security for production use |
| Checkpoint recovery testing | Test resume-from-crash at every step in staging | 4 hrs | Reliability guarantee |
| Error message standardization | Consistent error codes across all 15 steps | 3 hrs | Better debugging |

#### Phase 2: CI/CD & Automation (Priority: HIGH)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| GitHub Actions pipeline | Run tests on push, coverage reports, security scan | 4 hrs | Automated quality gates |
| Docker containerization | Dockerfile + docker-compose for easy deployment | 3 hrs | One-command setup |
| Version auto-bump | Semantic versioning on merge to main | 2 hrs | Release automation |
| Pre-commit hooks | Lint, format, type-check before commit | 2 hrs | Code quality enforcement |

#### Phase 3: Validation (Priority: MEDIUM)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| Multi-project testing | Test on 10+ real projects (Python, Java, JS, Go, Rust) | 1 week | Prove multi-project readiness |
| Load testing | 100 concurrent pipeline executions | 2 days | Performance baseline |
| Fallback chain testing | Test all 4 LLM providers with intentional failures | 1 day | Reliability proof |
| Checkpoint disaster drill | Kill process at each step, verify resume | 1 day | Recovery confidence |

#### Phase 4: Release (Priority: MEDIUM)

| Task | Description | Effort | Impact |
|------|-------------|--------|--------|
| PyPI package publish | `pip install claude-workflow-engine` | 1 day | Easy distribution |
| CLI interface | `cwe run "fix the bug"` command | 2 days | User-friendly entry point |
| Configuration wizard | Interactive setup for first-time users | 1 day | Onboarding experience |
| Release notes + changelog | v1.0.0 announcement | 1 day | Community awareness |

#### Phase 5: Quality Intelligence (Priority: HIGH - Next)

| Task | Description | Impact |
|------|-------------|--------|
| SonarQube integration | Auto-scan code after implementation, parse findings, auto-create issues | Self-healing code quality |
| Auto-fix SonarQube issues | Claude picks up scan findings and fixes bugs/vulnerabilities/smells autonomously | Zero manual quality work |
| Unit test auto-generation | Generate language-specific unit tests for every modified method using call graph | Coverage never drops |
| Integration test generation | Generate cross-service/API tests for modified call paths | End-to-end validation |
| Language-aware test patterns | Python: pytest+fixtures, Java: JUnit5+Mockito, TS: Jest, Go: table-driven | Idiomatic tests per language |
| Coverage-driven test scope | Use call graph to find untested methods and generate tests for them | Smart test targeting |
| Quality gate enforcement | Block PR merge until SonarQube gate passes + coverage threshold met | Production-grade quality |

#### Phase 6: Enterprise Features (Priority: LOW - Future)

| Task | Description | Impact |
|------|-------------|--------|
| Metrics dashboard | Real-time pipeline execution monitoring | Observability |
| Team collaboration | Multi-user sessions with role-based access | Team use |
| Custom policy editor | UI for creating/editing policies | Customization |
| Webhook integrations | Slack, Teams, Discord notifications | Enterprise workflow |
| Audit trail | Complete compliance logging | Enterprise compliance |
| Plugin system | Third-party skill/agent marketplace | Ecosystem growth |

---

## Quick Start

### Prerequisites

- Python 3.8+
- GitHub CLI (`gh`) installed and authenticated
- Ollama (optional, for local GPU inference)
- Qdrant (optional, for RAG vector storage)

### Installation

```bash
git clone https://github.com/techdeveloper-org/claude-insight.git
cd claude-insight
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Running the Pipeline

```bash
# Full 15-step pipeline
python scripts/3-level-flow.py --task "your task description"

# Hook mode (Steps 0-9 only, default)
CLAUDE_HOOK_MODE=1 python scripts/3-level-flow.py --task "fix login bug"

# Full mode (all 15 steps)
CLAUDE_HOOK_MODE=0 python scripts/3-level-flow.py --task "add user profile feature"

# Debug mode
CLAUDE_DEBUG=1 python scripts/3-level-flow.py --task "your task" --summary
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
claude-insight/
|
+-- scripts/
|   +-- langgraph_engine/             # Core orchestration (90 modules)
|   |   +-- orchestrator.py           # Main StateGraph pipeline
|   |   +-- flow_state.py             # TypedDict state (200+ fields)
|   |   +-- rag_integration.py        # Vector DB decision caching
|   |   +-- call_graph_builder.py     # Class-level call stack (FQN, impact analysis)
|   |   +-- call_graph_analyzer.py   # Pipeline-ready analysis (impact, context, review)
|   |   +-- subgraphs/               # Level -1, 1, 2, 3 implementations
|   +-- architecture/                 # Helper scripts (sync, standards, execution)
|   +-- 3-level-flow.py               # Entry point
|   +-- pre-tool-enforcer.py          # PreToolUse hook
|   +-- post-tool-tracker.py          # PostToolUse hook
|   +-- stop-notifier.py              # Stop hook (voice notification)
|
+-- src/mcp/                          # 16 FastMCP servers (293 tools)
+-- policies/                         # 63 policy definitions (62 .md + 1 .json)
+-- tests/                            # 64 test files (61 root + 3 integration)
+-- docs/                             # 46 documentation files
+-- docs/uml/                         # Auto-generated UML diagrams (13 types)
+-- rules/                            # 10 coding standard definitions
|
+-- VERSION                           # Single source of truth (1.4.1)
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
| MCP Servers | 18 (313 tools) |
| MCP Tools | 313 |
| LangGraph Engine Modules | 90 (84 root + 6 subgraphs) |
| Policy Files | 63 (62 .md + 1 .json) |
| Standards Files | 10 |
| Test Files | 64 (61 root + 3 integration) |
| Total Python Files | 226 |
| Call Graph | 578 classes, 3,985 methods, 4 languages (Python/Java/TS/Kotlin) |
| UML Diagram Types | 13 (CallGraph-powered) |
| Documentation Files | 40+ |
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
| **Multi-language standards (8 langs)** | Yes (3,400+ lines of rules) | No | No | No | No |
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
| SONAR_ORGANIZATION | (none) | SonarCloud organization |

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
      "args": ["path/to/src/mcp/jira_mcp_server.py"],
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
      "args": ["path/to/src/mcp/jenkins_mcp_server.py"],
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

**Total: 6,204 lines of standards across 10 files, 8 languages.**

Level 2 also runs linter validation (ruff/flake8) when available - violations feed into Step 11 code review.

---

## Configuration

All configuration is done through environment variables in `.env` (copy from `.env.example`). No hardcoded paths exist anywhere in the codebase - everything resolves through `path_resolver.py`.

### Pipeline Settings

| Variable | Default | What It Does |
|----------|---------|-------------|
| `CLAUDE_HOOK_MODE` | `1` | **Controls how many steps run.** `1` = Hook Mode (Steps 0-9 only, generates prompt + creates issue/branch, you implement). `0` = Full Mode (all 15 steps including implementation, PR, and issue closure). Use `1` for daily work, `0` for full automation. |
| `CLAUDE_DEBUG` | `0` | **Enables verbose logging.** `1` = prints every LLM call, every state transition, every decision. Useful when a step fails and you need to see exactly what happened. |
| `INFERENCE_MODE` | `auto` | **Which hardware to use for AI inference.** `auto` = smart routing (simple tasks to NPU, complex to GPU). `gpu_only` = only use Ollama GPU. `npu_only` = only use Intel NPU. Most users should leave this as `auto`. |

### LLM Provider Settings

| Variable | Default | What It Does |
|----------|---------|-------------|
| `LLM_PROVIDER` | `auto` | **Which AI provider to use.** `auto` = tries all in order: Ollama (free, local) -> Claude CLI -> Anthropic API -> OpenAI API. Set to a specific provider name to force it. |
| `OLLAMA_ENDPOINT` | `http://localhost:11434` | **Where Ollama GPU server is running.** Change this if you run Ollama on a different port or remote machine. |
| `ANTHROPIC_API_KEY` | _(none)_ | **Your Claude API key.** Only needed if Ollama is not available and you want to use Claude directly. Get from console.anthropic.com. |
| `GITHUB_TOKEN` | _(none)_ | **GitHub personal access token.** Required for Steps 8-12 (issue creation, branch, PR). Without this, the pipeline stops at Step 7. Falls back to `gh auth token` if not set. |
| `OPENAI_API_KEY` | _(none)_ | **OpenAI API key.** Last fallback in the LLM chain. Only used if all other providers fail. |

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
| _(auto)_ | `{LOGS}/telemetry/` | `get_telemetry_dir()` | Per-step JSONL files with timing, status, LLM calls. Written by Level 1 (5 nodes) + Level 3 (15 steps). |
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
│   └── 03-execution-system/            #   Level 3 policies (15 steps)
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
