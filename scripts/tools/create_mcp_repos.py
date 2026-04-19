"""
create_mcp_repos.py - Automates creation of individual MCP repos under techdeveloper-org.

Each repo:
  - Contains the MCP server file (as server.py)
  - Includes a copy of the shared base/ package
  - Includes mcp_errors.py, input_validator.py, rate_limiter.py utilities
  - Has comprehensive README.md and CLAUDE.md
  - Is private, with main as default branch

Usage:
    python scripts/create_mcp_repos.py

Prerequisites:
    - gh CLI authenticated (gh auth status)
    - Git configured with user name/email
"""

import shutil
import subprocess
from pathlib import Path

# -- Paths ---------------------------------------------------------------------
WORKSPACE = Path("C:/Users/techd/Documents/workspace-spring-tool-suite-4-4.27.0-new")
ENGINE_ROOT = WORKSPACE / "claude-workflow-engine"
MCP_SRC = ENGINE_ROOT / "src" / "mcp"
BASE_SRC = MCP_SRC / "base"
ORG = "techdeveloper-org"

# -- MCP Server Definitions ----------------------------------------------------
# Each entry: (repo_name, source_file, description, tools, extra_deps, engine_dep)
SERVERS = [
    {
        "repo": "mcp-pre-tool-gate",
        "file": "pre_tool_gate_mcp_server.py",
        "description": "Pre-execution policy enforcement gate for Claude Code. Validates all tool calls before execution, enforces 8 policy checks, provides dynamic skill hints, and detects failure patterns. Consolidates 2,027 LOC from pre-tool-enforcer.py into a FastMCP server.",
        "tools": [
            ("validate_tool_call", "Run all 8 pre-execution policy checks on a proposed tool call"),
            ("check_task_breakdown", "Verify task has been broken into trackable phases/steps"),
            ("check_skill_selected", "Confirm appropriate skill has been selected for the task"),
            ("check_level_completion", "Check Level 1/2 pipeline stages are complete"),
            ("get_enforcer_state", "Retrieve current enforcement flags and session state"),
            ("check_failure_patterns", "Match against known failure patterns to provide hints"),
            ("get_dynamic_skill_hint", "Return dynamic skill recommendation for current context"),
            ("reset_enforcer_flags", "Reset all enforcement flags for a new task cycle"),
        ],
        "env_vars": [
            ("CLAUDE_SESSION_DIR", "Path to session storage directory (default: ~/.claude/sessions)"),
            ("CLAUDE_POLICIES_DIR", "Path to policies directory (default: auto-detected)"),
        ],
        "benefits": [
            "Prevents common mistakes before they happen (fail-fast at tool call time)",
            "Enforces workflow discipline: task breakdown, skill selection, level completion",
            "Provides actionable skill hints rather than cryptic errors",
            "Saves context window by catching issues before they cascade",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-post-tool-tracker",
        "file": "post_tool_tracker_mcp_server.py",
        "description": "Post-execution tool tracking and session progress monitoring for Claude Code. Tracks every tool call, updates session progress metrics, estimates context window usage, enforces task update frequency, and determines commit readiness.",
        "tools": [
            ("track_tool_usage", "Record tool call with metadata (name, args, result, duration)"),
            ("increment_progress", "Increment step progress counter for current session"),
            ("clear_enforcement_flag", "Clear a specific enforcement flag after completion"),
            ("get_progress_status", "Get full session progress: steps, tools used, context estimate"),
            ("get_tool_stats", "Aggregate tool usage stats grouped by tool name"),
            ("check_commit_readiness", "Determine if accumulated changes are ready for git commit"),
        ],
        "env_vars": [
            ("CLAUDE_SESSION_DIR", "Path to session storage directory"),
            ("CLAUDE_TOOL_LOG", "Path to JSONL tool usage log file"),
        ],
        "benefits": [
            "Full audit trail of every tool call within a session",
            "Context window estimation prevents silent truncation surprises",
            "Complexity-aware phase execution (tracks multi-phase task progress)",
            "Commit readiness signal integrates with git-ops MCP",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-standards-loader",
        "file": "standards_loader_mcp_server.py",
        "description": "Project type detection and coding standards loading with conflict resolution. Detects project language/framework automatically, loads standards from 4 priority sources (custom > team > framework > language), resolves conflicts, and caches with file modification tracking.",
        "tools": [
            ("detect_project_type", "Auto-detect project language (Python/Java/TypeScript/Kotlin/etc.)"),
            ("detect_framework", "Detect active framework (Spring Boot/FastAPI/React/Angular/etc.)"),
            ("load_standards", "Load ordered standards for detected project/framework combination"),
            ("resolve_standard_conflicts", "Detect and resolve conflicting rules from multiple standards"),
            ("get_active_standards", "Return currently loaded standards with their sources"),
            ("list_available_standards", "List all standards files available in the standards directory"),
            ("reload_standards", "Force reload of standards cache (after rules/ directory changes)"),
        ],
        "env_vars": [
            ("CLAUDE_STANDARDS_DIR", "Path to standards/rules directory (default: rules/)"),
            ("CLAUDE_PROJECT_ROOT", "Root of the project to scan (default: CWD)"),
        ],
        "benefits": [
            "Zero-config standard detection -- no manual flags needed",
            "Priority ordering prevents team standards from being overridden by defaults",
            "File-modification-based cache invalidation (no stale standards)",
            "Conflict resolution surfaces rule clashes before they cause confusion",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-figma",
        "file": "figma_mcp_server.py",
        "description": "Figma design file operations via REST API for design-to-code workflows. Fetches file metadata, nodes, styles, components, design tokens (colors/typography/spacing), frame layouts, and exports. Adds implementation comments. Uses stdlib urllib only -- no heavy SDK dependency.",
        "tools": [
            ("figma_get_file_info", "Fetch Figma file metadata (name, version, last modified)"),
            ("figma_get_node", "Retrieve a specific node by ID with full properties"),
            ("figma_get_styles", "List all styles defined in the file (colors, text, effects)"),
            ("figma_get_components", "List all reusable components with metadata"),
            ("figma_extract_design_tokens", "Extract design tokens: colors, typography, spacing, border-radius"),
            ("figma_get_frame_layout", "Get frame layout properties (auto-layout, constraints, grid)"),
            ("figma_export_image", "Export a frame/node as PNG/SVG/PDF"),
            ("figma_get_comments", "List all comments on the file"),
            ("figma_add_comment", "Add an implementation comment to a frame/component"),
            ("figma_health_check", "Verify Figma API token and connectivity"),
        ],
        "env_vars": [
            ("FIGMA_ACCESS_TOKEN", "Figma personal access token (required)"),
            ("FIGMA_FILE_KEY", "Default Figma file key (optional, can be passed per-call)"),
        ],
        "benefits": [
            "Design tokens injection into prompts ensures pixel-accurate implementation",
            "Component extraction for UI task breakdown (Step 3 of pipeline)",
            "Implementation lifecycle comments keep Figma in sync with code progress",
            "No heavy Figma SDK -- pure stdlib urllib keeps dependencies minimal",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-policy-enforcement",
        "file": "enforcement_mcp_server.py",
        "description": "Policy enforcement, compliance tracking, and comprehensive system health monitoring. Tracks enforcement status per session, logs tool usage, verifies compliance with required workflow steps, records flow traces, and provides multi-layer health checks (MCPs, databases, LLM providers, disk).",
        "tools": [
            ("check_enforcement_status", "Check current policy enforcement status for session"),
            ("enforce_policy_step", "Mark a policy step as enforced/completed"),
            ("log_tool_usage", "Append a tool usage record to the session log"),
            ("verify_compliance", "Verify all required policy steps are complete"),
            ("list_policies", "List all policy definitions from policies/ directory"),
            ("record_policy_execution", "Record policy execution result with timestamp"),
            ("get_session_id", "Get or create a session ID for current context"),
            ("get_flow_trace_summary", "Get execution flow trace summary for session"),
            ("check_module_health", "Check health of a specific pipeline module"),
            ("check_all_mcp_servers_health", "Health-check all registered MCP servers in parallel"),
            ("check_system_health", "Full system health: MCPs + DB + LLM + disk"),
        ],
        "env_vars": [
            ("CLAUDE_SESSION_DIR", "Session storage directory"),
            ("CLAUDE_POLICIES_DIR", "Policies directory (default: policies/)"),
            ("CLAUDE_MCP_CONFIG", "Path to MCP config JSON (default: ~/.claude/settings.json)"),
        ],
        "benefits": [
            "Parallel MCP health checks complete in <2s (concurrent.futures ThreadPool)",
            "Flow trace gives full visibility into which pipeline steps ran",
            "Compliance gate prevents partial workflow executions from polluting state",
            "System health aggregates subsystems into a single dashboard call",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-git-ops",
        "file": "git_mcp_server.py",
        "description": "Structured Git operations via GitPython (no subprocess shell injection risk). Manages branches, commits, push/pull, stash, log, diff, and post-merge cleanup. Provides safe, exception-aware Git primitives for pipeline automation.",
        "tools": [
            ("git_status", "Get working tree status (modified, untracked, staged files)"),
            ("git_branch_create", "Create a new branch (optionally from a base branch)"),
            ("git_branch_switch", "Switch to an existing branch"),
            ("git_branch_list", "List all local and remote branches"),
            ("git_branch_delete", "Delete a branch (local only, with safety check)"),
            ("git_commit", "Stage files and create a commit with message"),
            ("git_push", "Push current branch to remote (with upstream tracking)"),
            ("git_pull", "Pull latest changes from remote"),
            ("git_diff", "Show diff for staged, unstaged, or between branches"),
            ("git_stash", "Stash or pop working directory changes"),
            ("git_log", "Get commit log with author, date, message (configurable depth)"),
            ("git_fetch", "Fetch from remote without merging"),
            ("git_post_merge_cleanup", "Delete merged branches and prune remote tracking refs"),
            ("git_get_origin_url", "Get the remote origin URL for the repository"),
        ],
        "env_vars": [
            ("GIT_REPO_PATH", "Path to git repository root (default: CWD)"),
            ("GIT_DEFAULT_BRANCH", "Default branch name (default: main)"),
        ],
        "benefits": [
            "GitPython library calls instead of subprocess -- no shell injection risk",
            "Structured exceptions instead of raw stderr parsing",
            "Post-merge cleanup automates branch housekeeping in CI workflows",
            "Safe branch deletion checks for unmerged commits before deleting",
        ],
        "pip_deps": ["mcp", "fastmcp", "gitpython"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-github-api",
        "file": "github_mcp_server.py",
        "description": "GitHub repository operations via PyGithub with gh CLI fallback for merge operations. Creates and manages issues, pull requests, comments, labels, and runs full merge cycles with optional build validation gates.",
        "tools": [
            ("github_create_issue", "Create a GitHub issue with title, body, labels, assignees"),
            ("github_close_issue", "Close an issue with a closing comment"),
            ("github_add_comment", "Add a comment to an issue or PR"),
            ("github_create_pr", "Create a pull request from a branch with title and body"),
            ("github_merge_pr", "Merge a PR (squash/merge/rebase strategies supported)"),
            ("github_list_issues", "List open/closed issues with filters"),
            ("github_get_pr_status", "Get PR status: checks, reviews, mergability"),
            ("github_create_issue_branch", "Create a branch named from an issue number"),
            ("github_auto_commit_and_pr", "Commit staged changes and open a PR automatically"),
            ("github_validate_build", "Wait for CI checks to pass before proceeding"),
            ("github_label_issue", "Add or remove labels from an issue"),
            ("github_full_merge_cycle", "Full cycle: build validate -> merge PR -> close issue -> cleanup"),
        ],
        "env_vars": [
            ("GITHUB_TOKEN", "GitHub personal access token (required)"),
            ("GITHUB_REPO", "Default repo in owner/repo format (optional)"),
        ],
        "benefits": [
            "Full SDLC integration: issue -> branch -> PR -> merge -> close in one pipeline",
            "Build validation gate prevents merging broken code",
            "PyGithub library provides rich object model; gh CLI handles edge cases",
            "auto_commit_and_pr reduces 5 manual steps to 1 tool call",
        ],
        "pip_deps": ["mcp", "fastmcp", "PyGithub"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-jenkins-ci",
        "file": "jenkins_mcp_server.py",
        "description": "Jenkins CI/CD integration via REST API. Supports Basic auth with API tokens (CSRF-exempt endpoints), parameterized builds, build status polling, console log streaming, and queue management. Pure stdlib urllib -- no jenkinsapi dependency.",
        "tools": [
            ("jenkins_trigger_build", "Trigger a build (with optional parameters dict)"),
            ("jenkins_get_build_status", "Get build result: SUCCESS/FAILURE/ABORTED/IN_PROGRESS"),
            ("jenkins_get_console_output", "Stream console log for a build (tail N lines)"),
            ("jenkins_list_jobs", "List all jobs in a folder or root"),
            ("jenkins_get_job_info", "Get job config: description, parameters, last build"),
            ("jenkins_list_builds", "List recent builds with timestamps and durations"),
            ("jenkins_abort_build", "Abort a running build"),
            ("jenkins_get_queue_info", "Get queue items (blocked, pending, why-blocked reason)"),
            ("jenkins_wait_for_build", "Poll until build completes (configurable timeout/interval)"),
            ("jenkins_health_check", "Verify Jenkins connectivity and API token validity"),
        ],
        "env_vars": [
            ("JENKINS_URL", "Jenkins server URL (required)"),
            ("JENKINS_USER", "Jenkins username for Basic auth"),
            ("JENKINS_TOKEN", "Jenkins API token (preferred over password)"),
            ("JENKINS_CRUMB_DISABLED", "Set to 1 if CSRF crumbs are disabled on server"),
        ],
        "benefits": [
            "Pipeline-native CI integration: trigger build after PR, wait, validate before merge",
            "Console log streaming helps debug pipeline failures without opening Jenkins UI",
            "Queue visibility explains why builds are blocked (agent availability, etc.)",
            "Pure stdlib -- no heavy jenkinsapi package, works in restricted environments",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-jira-api",
        "file": "jira_mcp_server.py",
        "description": "Jira integration supporting both Cloud (v3, ADF document format) and Server/Data Center (v2, plain text). Creates, searches, transitions, and links issues. Automatically wraps Cloud comments in ADF document format. JQL-powered issue search.",
        "tools": [
            ("jira_create_issue", "Create a Jira issue (project, type, summary, description, priority)"),
            ("jira_get_issue", "Get full issue details by key (PROJ-123)"),
            ("jira_search_issues", "JQL search with field projection and pagination"),
            ("jira_transition_issue", "Transition issue to new status (To Do/In Progress/Done)"),
            ("jira_add_comment", "Add a comment (auto ADF-wrapped for Cloud)"),
            ("jira_link_pr", "Link a pull request URL to an issue as a remote link"),
            ("jira_list_projects", "List all accessible Jira projects"),
            ("jira_get_transitions", "Get available transitions for an issue"),
            ("jira_update_issue", "Update issue fields (summary, description, assignee, labels)"),
            ("jira_health_check", "Verify Jira URL, credentials, and API version"),
        ],
        "env_vars": [
            ("JIRA_URL", "Jira server URL (required)"),
            ("JIRA_EMAIL", "Jira account email (for Cloud Basic auth)"),
            ("JIRA_API_TOKEN", "Jira API token (Cloud) or password (Server)"),
            ("JIRA_DEFAULT_PROJECT", "Default project key (optional)"),
        ],
        "benefits": [
            "Cloud + Server support with automatic API version detection",
            "ADF auto-wrapping means plain text comments work on Cloud without format errors",
            "PR linking creates bi-directional traceability (Jira issue <-> GitHub PR)",
            "Full lifecycle: create -> in progress -> in review -> done",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-session-mgr",
        "file": "session_mcp_server.py",
        "description": "Session lifecycle management for multi-step Claude Code workflows. Creates sessions, accumulates task/tool/file activity, finalizes with summaries, supports tagging for categorization, and inter-session linking for chaining related sessions. Generates comprehensive statistics.",
        "tools": [
            ("session_create", "Create a new session with task description and metadata"),
            ("session_accumulate", "Accumulate activity: tool calls, file edits, task steps"),
            ("session_finalize", "Finalize session and generate summary with statistics"),
            ("session_tag", "Add tags to a session for categorization and search"),
            ("session_link", "Link sessions for chaining (parent -> child, prerequisite -> followup)"),
            ("session_get_status", "Get current session status, progress, and budget estimate"),
            ("session_list", "List sessions with filters (tag, date, status, project)"),
            ("session_export_summary", "Export full session summary as structured JSON"),
        ],
        "env_vars": [
            ("CLAUDE_SESSION_DIR", "Session storage directory (default: ~/.claude/sessions)"),
            ("CLAUDE_SESSION_ID", "Current session ID (auto-generated if not set)"),
            ("CLAUDE_PROJECT", "Project identifier for session grouping"),
        ],
        "benefits": [
            "Session chaining enables multi-conversation task continuity",
            "Tool/file accumulation provides full audit trail per session",
            "Tag-based search enables finding related sessions across projects",
            "Export summary integrates with external reporting and dashboards",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-token-optimizer",
        "file": "token_optimization_mcp_server.py",
        "description": "Context optimization delivering 60-85% token reduction for Claude Code sessions. Provides AST-based code navigation (read only the function you need), pre-execution tool optimization, context deduplication, and detailed optimization metrics tracking.",
        "tools": [
            ("optimize_tool_call", "Optimize a pending tool call to reduce token usage"),
            ("ast_navigate_code", "Navigate to specific function/class without reading full file"),
            ("smart_read_analyze", "Analyze what to read from a file given the current task"),
            ("deduplicate_context", "Remove duplicate content from accumulated context"),
            ("dedup_estimate", "Estimate deduplication savings before running"),
            ("context_budget_status", "Get current context token usage vs budget"),
            ("get_optimization_stats", "Aggregate optimization metrics across current session"),
            ("log_optimization", "Log an optimization event for metrics"),
            ("optimize_read_params", "Suggest optimal offset/limit params for a Read call"),
            ("optimize_grep_params", "Suggest optimal Grep params to minimize results"),
        ],
        "env_vars": [
            ("CLAUDE_TOKEN_BUDGET", "Max context tokens before compression (default: 150000)"),
            ("CLAUDE_OPTIMIZATION_LOG", "Path to optimization JSONL log"),
        ],
        "benefits": [
            "AST navigation reads only the function body you need (80-95% savings vs full file)",
            "Context deduplication removes repeated file reads that accumulate silently",
            "Optimization stats show exactly how much context was saved per session",
            "Integrates with pre-tool-gate: optimize before validation, not after",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": False,
    },
    {
        "repo": "mcp-uml-diagram",
        "file": "uml_diagram_mcp_server.py",
        "description": "Auto-generate 13 UML diagram types from codebase using AST analysis and LLM synthesis. Tier 1 (AST-only): Class, Package, Component. Tier 2 (AST+LLM): Sequence, Activity, State. Tier 3 (LLM): Use Case, Object, Deployment, Communication, Composite, Interaction, Call Graph. Renders via Kroki.io.",
        "tools": [
            ("generate_class_diagram", "Generate UML class diagram from Python/Java/TS/Kotlin AST"),
            ("generate_package_diagram", "Generate package/module dependency diagram"),
            ("generate_component_diagram", "Generate component diagram showing system boundaries"),
            ("generate_sequence_diagram", "Generate sequence diagram for a flow (AST + LLM)"),
            ("generate_activity_diagram", "Generate activity diagram for a process flow"),
            ("generate_state_diagram", "Generate state machine diagram from transition logic"),
            ("generate_usecase_diagram", "Generate use case diagram (LLM-synthesized)"),
            ("generate_object_diagram", "Generate object instance diagram"),
            ("generate_deployment_diagram", "Generate deployment/infrastructure diagram"),
            ("generate_communication_diagram", "Generate communication/collaboration diagram"),
            ("generate_composite_structure_diagram", "Generate composite structure diagram"),
            ("generate_interaction_overview_diagram", "Generate interaction overview"),
            ("generate_call_graph_diagram", "Generate call graph from AST method calls"),
            ("generate_all_diagrams", "Generate all 13 diagram types in one call"),
            ("render_diagram", "Render Mermaid/PlantUML markup to PNG/SVG via Kroki.io"),
        ],
        "env_vars": [
            ("ANTHROPIC_API_KEY", "Required for Tier 2/3 LLM-assisted diagrams"),
            ("UML_OUTPUT_DIR", "Directory for generated diagram files (default: uml/)"),
            ("KROKI_SERVER", "Kroki rendering server URL (default: https://kroki.io)"),
        ],
        "benefits": [
            "13 diagram types from a single codebase scan -- no manual diagram maintenance",
            "3-tier approach: fast AST for structural diagrams, LLM only when needed",
            "Call graph diagram reflects actual method call chains, not guessed architecture",
            "Kroki.io rendering produces shareable PNG/SVG without local Graphviz install",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": True,
        "engine_note": "Depends on langgraph_engine/uml_generators.py and diagrams/ package from claude-workflow-engine",
    },
    {
        "repo": "mcp-drawio-diagram",
        "file": "drawio_mcp_server.py",
        "description": "Generate editable .drawio files for all SDLC diagram types. Produces mxGraph XML that opens directly in draw.io/diagrams.net without any API key or Graphviz install. Generates shareable app.diagrams.net URLs and supports GitHub raw URL embedding.",
        "tools": [
            ("generate_drawio_diagram", "Generate a .drawio file for a specified diagram type"),
            ("generate_all_drawio", "Generate all SDLC diagram types as .drawio files"),
            ("get_shareable_url", "Generate app.diagrams.net URL for an existing .drawio file"),
            ("list_drawio_diagrams", "List all generated .drawio files with last modified dates"),
            ("convert_mermaid_to_drawio", "Convert Mermaid diagram markup to .drawio format"),
        ],
        "env_vars": [
            ("DRAWIO_OUTPUT_DIR", "Output directory for .drawio files (default: drawio/)"),
            ("GITHUB_RAW_BASE_URL", "GitHub raw URL base for shareable URL generation"),
        ],
        "benefits": [
            "Fully editable diagrams -- stakeholders can open in draw.io and customize",
            "No API key needed -- mxGraph XML is generated locally",
            "Shareable URLs work without exporting images (open directly in browser)",
            "Mermaid conversion bridges LLM-generated diagrams to editable format",
        ],
        "pip_deps": ["mcp", "fastmcp"],
        "engine_dep": True,
        "engine_note": "Depends on langgraph_engine/diagrams/ package and call_graph_builder.py from claude-workflow-engine",
    },
]

# -- Shared utility files to copy into each server repo -----------------------
SHARED_UTILS = ["mcp_errors.py", "input_validator.py", "rate_limiter.py"]

# -- .gitignore template -------------------------------------------------------
GITIGNORE = """__pycache__/
*.py[cod]
*$py.class
*.so
.env
.env.*
!.env.example
venv/
.venv/
env/
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
*.log
*.jsonl
sessions/
"""


# -- requirements.txt template -------------------------------------------------
def make_requirements(pip_deps):
    base = ["mcp>=1.0.0", "fastmcp>=0.1.0"]
    extras = [d for d in pip_deps if d not in ("mcp", "fastmcp")]
    return "\n".join(base + extras) + "\n"


# -- README.md template --------------------------------------------------------
def make_readme(server):
    tools_table = "\n".join(f"| `{name}` | {desc} |" for name, desc in server["tools"])
    env_table = "\n".join(f"| `{var}` | {desc} |" for var, desc in server["env_vars"])
    benefits_list = "\n".join(f"- {b}" for b in server["benefits"])
    pip_deps_str = " ".join(server["pip_deps"])

    engine_note_block = ""
    if server.get("engine_dep"):
        engine_note_block = f"""
## Engine Dependency

> **Note:** This server depends on `claude-workflow-engine` internals.
>
> {server.get('engine_note', '')}
>
> Ensure `claude-workflow-engine` is cloned alongside this repo and its
> `scripts/` directory is on your `PYTHONPATH`.

```bash
export PYTHONPATH=/path/to/claude-workflow-engine/scripts:$PYTHONPATH
```
"""

    return f"""# {server['repo']}

A FastMCP server providing **{server['repo'].replace('mcp-', '').replace('-', ' ').title()}** capabilities for Claude Code workflows.

---

## Overview

{server['description']}

---

## Tools

| Tool | Description |
|------|-------------|
{tools_table}

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/techdeveloper-org/{server['repo']}.git
cd {server['repo']}
```

### 2. Install dependencies

```bash
pip install {pip_deps_str}
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
{env_table}

---

## Usage in Claude Code

Add to your `~/.claude/settings.json`:

```json
{{
  "mcpServers": {{
    "{server['repo'].replace('mcp-', '')}": {{
      "command": "python",
      "args": [
        "/path/to/{server['repo']}/server.py"
      ],
      "env": {{}}
    }}
  }}
}}
```
{engine_note_block}
---

## Benefits

{benefits_list}

---

## Requirements

- Python 3.8+
- `{pip_deps_str}`
- See `requirements.txt` for pinned versions

---

## Project Context

This MCP server is part of the **Claude Workflow Engine** ecosystem -- a LangGraph-based
orchestration pipeline for automating Claude Code development workflows.

Related repos:
- [`claude-workflow-engine`](https://github.com/techdeveloper-org/claude-workflow-engine) -- Main pipeline
- [`mcp-base`](https://github.com/techdeveloper-org/mcp-base) -- Shared base utilities used by all MCP servers

---

## License

Private -- techdeveloper-org
"""


# -- CLAUDE.md template --------------------------------------------------------
def make_claude_md(server):
    tools_list = "\n".join(f"- `{name}` -- {desc}" for name, desc in server["tools"])
    env_list = "\n".join(f"- `{var}` -- {desc}" for var, desc in server["env_vars"])

    engine_section = ""
    if server.get("engine_dep"):
        engine_section = f"""
## Engine Dependency

{server.get('engine_note', '')}

Set PYTHONPATH to include the workflow engine scripts directory before running:

```bash
export PYTHONPATH=/path/to/claude-workflow-engine/scripts:$PYTHONPATH
```
"""

    return f"""# {server['repo']} -- Claude Project Context

**Type:** FastMCP Server
**Transport:** stdio
**Python:** 3.8+

---

## What This Server Does

{server['description']}

---

## Entry Point

```
server.py
```

Run via `python server.py` -- communicates over stdio using the MCP protocol.

---

## Available Tools

{tools_list}

---

## Shared Utilities (in this repo)

- `base/` -- Shared MCP infrastructure package (response builder, decorators, persistence, clients)
- `mcp_errors.py` -- Structured error response helpers
- `input_validator.py` -- Null-byte strip, length limits, prompt injection detection
- `rate_limiter.py` -- Token bucket rate limiter (enable via ENABLE_RATE_LIMITING=1)
{engine_section}
---

## Environment Variables

{env_list}

---

## Development

### Running locally

```bash
# Install deps
pip install -r requirements.txt

# Run the MCP server (stdio mode)
python server.py
```

### Testing a tool call manually

```python
import subprocess, json

proc = subprocess.Popen(
    ["python", "server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
)
# Send MCP initialize + tool call via stdin
```

### File structure

```
{server['repo']}/
+-- server.py          # Main FastMCP server (entry point)
+-- base/              # Shared base package (response, decorators, persistence, clients)
+-- mcp_errors.py      # Error helpers
+-- input_validator.py # Input validation
+-- rate_limiter.py    # Rate limiting
+-- requirements.txt
+-- .gitignore
+-- README.md
+-- CLAUDE.md
```

---

## Key Rules

1. Do NOT edit `base/` directly -- it is a copy from `mcp-base` repo
2. To update shared utilities, edit in `mcp-base` and re-copy
3. Keep `server.py` as the single entry point
4. All tool handlers must use `@mcp_tool_handler` decorator for consistent error handling
5. All responses must use `success()` / `error()` / `MCPResponse` builder from `base.response`

---

**Last Updated:** 2026-03-31
"""


# -- .env.example template ----------------------------------------------------
def make_env_example(server):
    lines = [f"# {var} -- {desc}" + f"\n{var}=your_value_here" for var, desc in server["env_vars"]]
    return "\n\n".join(lines) + "\n"


# -- Helpers -------------------------------------------------------------------
def run(cmd, cwd=None, check=True):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout.strip():
        print(f"    {result.stdout.strip()[:200]}")
    if result.returncode != 0 and check:
        print(f"  ERROR: {result.stderr.strip()[:300]}")
        raise RuntimeError(f"Command failed: {cmd}")
    return result


def write_file(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# -- Main ----------------------------------------------------------------------
def create_repo(server):
    repo_name = server["repo"]
    repo_dir = WORKSPACE / repo_name
    print(f"\n{'='*60}")
    print(f"Creating: {repo_name}")
    print(f"{'='*60}")

    # 1. Create directory
    if repo_dir.exists():
        print("  Directory already exists, skipping mkdir")
    else:
        repo_dir.mkdir(parents=True)

    # 2. Copy server file as server.py
    src_file = MCP_SRC / server["file"]
    if src_file.exists():
        shutil.copy2(src_file, repo_dir / "server.py")
        print(f"  Copied {server['file']} -> server.py")
    else:
        print(f"  WARNING: Source file not found: {src_file}")

    # 3. Copy base/ package
    base_dest = repo_dir / "base"
    if base_dest.exists():
        shutil.rmtree(base_dest)
    shutil.copytree(BASE_SRC, base_dest)
    print("  Copied base/ package")

    # 4. Copy shared utilities
    for util in SHARED_UTILS:
        src = MCP_SRC / util
        if src.exists():
            shutil.copy2(src, repo_dir / util)
            print(f"  Copied {util}")

    # 5. Write generated files
    write_file(repo_dir / "README.md", make_readme(server))
    write_file(repo_dir / "CLAUDE.md", make_claude_md(server))
    write_file(repo_dir / "requirements.txt", make_requirements(server["pip_deps"]))
    write_file(repo_dir / ".gitignore", GITIGNORE)
    write_file(repo_dir / ".env.example", make_env_example(server))
    print("  Generated README.md, CLAUDE.md, requirements.txt, .gitignore, .env.example")

    # 6. Git init + initial commit
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        run("git init -b main", cwd=str(repo_dir))
        run('git config user.email "piyush@techdeveloper-org"', cwd=str(repo_dir))
        run('git config user.name "Piyush Makhija"', cwd=str(repo_dir))
    run("git add -A", cwd=str(repo_dir))
    run(
        f'git commit -m "feat: initial commit -- {repo_name} FastMCP server"',
        cwd=str(repo_dir),
    )
    print("  Git commit done")

    # 7. Create GitHub repo (private, techdeveloper-org)
    result = run(
        f"gh repo create {ORG}/{repo_name} --private --source . --remote origin --push",
        cwd=str(repo_dir),
        check=False,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        if "already exists" in err.lower() or "Name already exists" in err:
            print("  Repo already exists on GitHub, pushing to existing...")
            run(
                "git remote add origin https://github.com/{}/{}.git".format(ORG, repo_name),
                cwd=str(repo_dir),
                check=False,
            )
            run("git push -u origin main", cwd=str(repo_dir))
        else:
            print(f"  GITHUB ERROR: {err}")
            raise RuntimeError(f"Failed to create repo {repo_name}")
    else:
        print(f"  GitHub repo created: https://github.com/{ORG}/{repo_name}")

    print(f"  DONE: {repo_name}")
    return True


def create_mcp_base_repo():
    """Create the shared mcp-base repo."""
    repo_name = "mcp-base"
    repo_dir = WORKSPACE / repo_name
    print(f"\n{'='*60}")
    print(f"Creating: {repo_name} (shared base package)")
    print(f"{'='*60}")

    repo_dir.mkdir(parents=True, exist_ok=True)

    # Copy base/ package as mcp_base/ package
    base_dest = repo_dir / "mcp_base"
    if base_dest.exists():
        shutil.rmtree(base_dest)
    shutil.copytree(BASE_SRC, base_dest)

    # Copy shared utilities
    for util in SHARED_UTILS:
        src = MCP_SRC / util
        if src.exists():
            shutil.copy2(src, repo_dir / util)

    # Also copy session_hooks.py as a bonus utility
    hooks_src = MCP_SRC / "session_hooks.py"
    if hooks_src.exists():
        shutil.copy2(hooks_src, repo_dir / "session_hooks.py")

    # Write README
    readme = """# mcp-base

Shared base infrastructure package for all `techdeveloper-org` MCP servers.

---

## Overview

`mcp-base` provides reusable OOP foundations that eliminate boilerplate across all custom
MCP servers. Every MCP server in the `techdeveloper-org` ecosystem includes a copy of this
package for self-contained deployment.

---

## Package Contents

### `mcp_base/` -- Core Package

| Module | Pattern | Purpose |
|--------|---------|---------|
| `response.py` | Builder | `MCPResponse` fluent builder + `success()` / `error()` helpers |
| `decorators.py` | Decorator | `@mcp_tool_handler` -- eliminates 109 identical try/except blocks |
| `persistence.py` | Repository | `AtomicJsonStore`, `JsonlAppender`, `SessionIdResolver` |
| `clients.py` | Singleton/Lazy | `GitRepoClient`, `GitHubApiClient` |

### Shared Utilities

| File | Purpose |
|------|---------|
| `mcp_errors.py` | Structured error response helpers (backward-compat with `base.response`) |
| `input_validator.py` | Input validation: null-byte strip, length limits, prompt injection detection |
| `rate_limiter.py` | Token bucket rate limiter (enabled via `ENABLE_RATE_LIMITING=1`) |
| `session_hooks.py` | Python bridge to session MCP without subprocess overhead |

---

## Usage

### In MCP server repos (copy approach)

Each MCP server repo includes a `base/` copy of `mcp_base/`:

```python
from base.response import success, error, MCPResponse
from base.decorators import mcp_tool_handler
from base.persistence import AtomicJsonStore, SessionIdResolver
from base.clients import GitRepoClient
```

### As an installed package (pip approach)

```bash
pip install git+https://github.com/techdeveloper-org/mcp-base.git
```

```python
from mcp_base.response import success, error
from mcp_base.decorators import mcp_tool_handler
```

---

## Key Design Patterns

- **Builder** -- `MCPResponse.ok().data("key", val).message("done").build()`
- **Decorator** -- `@mcp_tool_handler` wraps all tools with consistent error handling
- **Repository** -- `AtomicJsonStore` for safe concurrent JSON file access
- **Singleton/Lazy** -- `LazyClient` for shared resource initialization (GitHub, Git)

---

## Requirements

- Python 3.8+
- `gitpython` (for `GitRepoClient`)
- `PyGithub` (for `GitHubApiClient`)

Install only what you need based on which clients your server uses.

---

## Project Context

Part of the **Claude Workflow Engine** MCP ecosystem.
See [`claude-workflow-engine`](https://github.com/techdeveloper-org/claude-workflow-engine) for the full pipeline.

---

## License

Private -- techdeveloper-org
"""
    write_file(repo_dir / "README.md", readme)

    claude_md = """# mcp-base -- Claude Project Context

**Type:** Shared base package for all MCP servers
**Python:** 3.8+

---

## What This Package Provides

Reusable OOP foundations for all custom MCP servers in the techdeveloper-org ecosystem.
Eliminates duplicated boilerplate across servers.

## Package: mcp_base/

- `response.py` -- MCPResponse builder + success()/error() convenience functions
- `decorators.py` -- @mcp_tool_handler decorator (replaces 109 try/except blocks)
- `persistence.py` -- AtomicJsonStore, JsonlAppender, SessionIdResolver
- `clients.py` -- LazyClient, GitRepoClient, GitHubApiClient
- `__init__.py` -- Public API re-exports

## Shared Utilities

- `mcp_errors.py` -- Error response helpers
- `input_validator.py` -- Input sanitization
- `rate_limiter.py` -- Token bucket rate limiting
- `session_hooks.py` -- Direct session MCP bridge (no subprocess)

## Key Rule

Each MCP server repo copies this package as `base/` for self-contained deployment.
To update shared code: edit here, then re-copy to affected server repos.

**Last Updated:** 2026-03-31
"""
    write_file(repo_dir / "CLAUDE.md", claude_md)
    write_file(repo_dir / ".gitignore", GITIGNORE)
    write_file(repo_dir / "requirements.txt", "gitpython\nPyGithub\n")

    # Git init + commit
    if not (repo_dir / ".git").exists():
        run("git init -b main", cwd=str(repo_dir))
        run('git config user.email "piyush@techdeveloper-org"', cwd=str(repo_dir))
        run('git config user.name "Piyush Makhija"', cwd=str(repo_dir))
    run("git add -A", cwd=str(repo_dir))
    run('git commit -m "feat: initial commit -- mcp-base shared infrastructure package"', cwd=str(repo_dir))

    result = run(
        f"gh repo create {ORG}/{repo_name} --private --source . --remote origin --push",
        cwd=str(repo_dir),
        check=False,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        if "already exists" in err.lower():
            print("  Repo already exists, pushing...")
            run("git push -u origin main", cwd=str(repo_dir), check=False)
        else:
            print(f"  GITHUB ERROR: {err}")
    else:
        print(f"  GitHub repo created: https://github.com/{ORG}/{repo_name}")

    print(f"  DONE: {repo_name}")


def main():
    print("Claude Workflow Engine -- MCP Repos Creator")
    print(f"Organization: {ORG}")
    print(f"Workspace: {WORKSPACE}")
    print(f"Total repos to create: {len(SERVERS) + 1} (1 base + {len(SERVERS)} servers)")

    # Create mcp-base first
    create_mcp_base_repo()

    # Create all server repos
    success_count = 0
    failed = []
    for server in SERVERS:
        try:
            create_repo(server)
            success_count += 1
        except Exception as exc:
            print(f"  FAILED {server['repo']}: {exc}")
            failed.append(server["repo"])

    print(f"\n{'='*60}")
    print(f"COMPLETE: {success_count + 1}/{len(SERVERS) + 1} repos created")
    if failed:
        print(f"FAILED: {failed}")
    else:
        print("All repos created successfully!")

    # Print settings.json update instructions
    print("\n--- settings.json paths to update ---")
    for server in SERVERS:
        new_path = str(WORKSPACE / server["repo"] / "server.py").replace("\\", "/")
        print(f'  "{server["repo"].replace("mcp-", "")}": "{new_path}"')


if __name__ == "__main__":
    main()
