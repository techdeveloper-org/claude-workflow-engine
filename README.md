# Claude Workflow Engine

**The first AI tool that follows full SDLC** - from task analysis to merged PR, automatically.

**Version:** 7.6.0 | **Status:** Alpha | **Last Updated:** 2026-03-18

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
| **Analysis & Planning** | 0-2 | Task analysis, complexity scoring, plan mode decision, plan execution |
| **Preparation** | 3-7 | Task breakdown, TOON refinement, skill/agent selection, prompt generation |
| **GitHub Automation** | 8-9 | Issue creation with semantic labels, branch creation with stash safety |
| **Implementation** | 10 | Code execution with system prompt context (95%+ quality with full context) |
| **Review & Closure** | 11-12 | PR creation with code review loop (max 3 retries), issue closure with summary |
| **Finalization** | 13-14 | Documentation + UML diagram generation, execution summary + voice notification |

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

### LangGraph Orchestration (78 modules)

- StateGraph with 200+ typed state fields
- Parallel execution via `Send()` API (Level 1: 4 concurrent tasks)
- Conditional routing (plan mode, Java detection, PR retry loop)
- Checkpoint recovery (resume from any step after crash)
- Signal handling (Ctrl+C graceful recovery)

### 12 MCP Servers (123 tools)

All servers use FastMCP protocol (stdio JSON-RPC), registered in `~/.claude/settings.json`:

| Server | Tools | Purpose |
|--------|-------|---------|
| git-ops | 14 | Git operations (branch, commit, push, pull, stash, diff, fetch, cleanup) |
| github-api | 12 | GitHub (issue, PR, merge, label, build validate, full merge cycle) |
| session-mgr | 14 | Session lifecycle (create, chain, tag, accumulate, finalize, work items) |
| policy-enforcement | 11 | Policy compliance, flow-trace, module health, system health |
| llm-provider | 8 | LLM access (4 providers, hybrid GPU-first, model selection) |
| token-optimizer | 10 | Token reduction (AST navigation, smart read, dedup, 60-85% savings) |
| pre-tool-gate | 8 | Pre-tool validation (8 policy checks, skill hints) |
| post-tool-tracker | 6 | Post-tool tracking (progress, commit readiness, stats) |
| standards-loader | 7 | Standards (project detect, framework detect, hot-reload) |
| skill-manager | 8 | Skill lifecycle (load, search, validate, rank, conflicts) |
| vector-db | 11 | Vector RAG (Qdrant, 4 collections, semantic search, node decisions) |
| uml-diagram | 14 | UML generation (12 diagram types, AST + LLM, Mermaid/PlantUML, Kroki.io rendering) |

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

### Policy System (49 policies)

```
policies/
+-- 01-sync-system/        Level 1: Session, context, preferences, patterns (11 files)
+-- 02-standards-system/   Level 2: Common + conditional standards (3 files)
+-- 03-execution-system/   Level 3: All 15 steps + failure prevention (34 files)
+-- testing/               Test case policies (2 files)
```

---

## Current Status: What's Built vs What's Remaining

### BUILT (v7.6.0 - Alpha)

| Component | Status | Details |
|-----------|--------|---------|
| **15-Step Pipeline** | COMPLETE | All steps produce real output (not stubs) |
| **4-Level Architecture** | COMPLETE | Level -1 through Level 3 fully operational |
| **11 MCP Servers** | COMPLETE | 109 tools, all tested and registered |
| **RAG Integration** | COMPLETE | 4 Vector DB collections, step-specific thresholds |
| **Hook System** | COMPLETE | Pre/post tool enforcement with blocking |
| **Policy System** | COMPLETE | 49 policies covering all 15 steps |
| **Multi-Project Detection** | COMPLETE | 20+ languages/frameworks auto-detected |
| **Hybrid LLM Inference** | COMPLETE | 4-provider fallback chain |
| **Token Optimization** | COMPLETE | AST navigation, dedup, 60-85% savings |
| **Session Management** | COMPLETE | Chaining, TOON compression, archival |
| **GitHub Integration** | COMPLETE | Issue, branch, PR, merge, review loop |
| **Standards Enforcement** | COMPLETE | Common + framework-specific with 5 hooks |
| **Cross-Session Learning** | COMPLETE | RAG pattern detection + skill selection boost |
| **Test Suite** | COMPLETE | 46 test files, 1366+ tests, integration tests for all 15 steps |
| **Documentation** | COMPLETE | 40 docs, architecture diagrams, guides |
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

#### Phase 5: Enterprise Features (Priority: LOW - Future)

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
|   +-- langgraph_engine/             # Core orchestration (78 modules)
|   |   +-- orchestrator.py           # Main StateGraph pipeline
|   |   +-- flow_state.py             # TypedDict state (200+ fields)
|   |   +-- rag_integration.py        # Vector DB decision caching
|   |   +-- call_graph_builder.py     # Class-level call stack (FQN, impact analysis)
|   |   +-- subgraphs/               # Level -1, 1, 2, 3 implementations
|   +-- architecture/                 # Helper scripts (sync, standards, execution)
|   +-- 3-level-flow.py               # Entry point
|   +-- pre-tool-enforcer.py          # PreToolUse hook
|   +-- post-tool-tracker.py          # PostToolUse hook
|   +-- stop-notifier.py              # Stop hook (voice notification)
|
+-- src/mcp/                          # 12 FastMCP servers (123 tools)
+-- policies/                         # 49 policy definitions
+-- tests/                            # 48 test files (1450+ tests)
+-- docs/                             # 40 documentation files
+-- docs/uml/                         # Auto-generated UML diagrams (12 types)
+-- rules/                            # 5 coding standard definitions
|
+-- VERSION                           # Single source of truth (7.5.0)
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
| MCP Servers | 12 |
| MCP Tools | 123 |
| LangGraph Engine Modules | 78 (72 root + 6 subgraphs) |
| Policy Files | 49 (48 .md + 1 .json) |
| Test Files | 48 |
| Test Functions | 1450+ |
| Total Python Files | 261+ |
| UML Diagram Types | 12 |
| Documentation Files | 40 |
| RAG Collections | 4 |
| Supported Languages | 20+ |
| Supported Frameworks | 15+ |

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
| **7.6.0** | 2026-03-18 | Call graph builder (class-level FQN, impact analysis, 47 tests), path standardization (30+ hardcoded paths removed, env var overrides) |
| 7.5.0 | 2026-03-18 | UML diagram generation (12 types), 12th MCP server (uml-diagram, 14 tools), AST + LLM hybrid |
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
