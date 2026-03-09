# Claude Insight - Claude Code Instructions

**Project:** Claude Insight
**Type:** Python Flask Monitoring Dashboard
**Version:** 5.2.1
**Status:** Active Development

---

## PROJECT OVERVIEW

Claude Insight is a **real-time monitoring dashboard** for the Claude Memory System.
It tracks the 3-Level Architecture execution, policy enforcement, session analytics,
and provides a web UI to visualize Claude Code behavior across sessions.

**Key purpose:** Monitor how Claude follows the 3-level enforcement policies
(Level -1 Auto-Fix, Level 1 Sync, Level 2 Standards, Level 3 Execution with 12 steps).

**Important:** This file provides **ADDITIONAL** project-specific context to Claude.
It does **NOT** override the global `~/.claude/CLAUDE.md` policies.

---

## FUTURE ARCHITECTURE (Approved & Saved)

### Vector DB RAG Implementation (Q2 2026)
**Status:** Designed, approved, saved for future
**Location:** `docs/VECTOR-DB-RAG-FUTURE-PLAN.md`

Permanent solution for context bloat + AI model training readiness:
- Vector Database (Qdrant) with semantic search
- 64-dim quantized embeddings (99% memory reduction)
- 4-week implementation roadmap
- Schema design for tool_calls, sessions, flow_traces

**When to implement:** After Phase 1-3 quick fixes, before custom Claude model training

### Session Bloat Analysis & Solutions
**Location:** `docs/SESSION-BLOAT-ANALYSIS.md`

Root cause analysis and three-phase fix plan:
1. **Phase 1 (Immediate):** Trace rotation + print optimization
2. **Phase 2 (Short-term):** Session metadata cleanup
3. **Phase 3 (Long-term):** Auto-archival system

---

## FIRST TIME SETUP - INSTALL THE MEMORY SYSTEM

Before working on this project, set up the Claude Memory System globally.
This ensures Claude follows the 3-level enforcement architecture automatically.

### Option A: Automatic Setup (Recommended)

**Windows (PowerShell):**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\scripts\setup-global-claude.ps1
```

**Unix / macOS / Linux / WSL:**
```bash
chmod +x scripts/setup-global-claude.sh
./scripts/setup-global-claude.sh
```

**What the automatic setup does:**
1. Creates `~/.claude/` directory if it does not exist
2. Installs core enforcement scripts to `~/.claude/memory/current/`
3. Creates `~/.claude/settings.json` with 3-level flow hooks
4. Installs the global CLAUDE.md (3-level architecture, no project-specific info)
5. Hooks activate automatically when you reopen Claude Code

### Option B: Manual Setup

1. **Create the directory:**
   ```bash
   mkdir -p ~/.claude/memory/current
   ```

2. **Copy enforcement scripts:**
   ```bash
   cp scripts/3-level-flow.py ~/.claude/memory/current/
   cp scripts/auto-fix-enforcer.sh ~/.claude/memory/current/
   cp scripts/session-start.sh ~/.claude/memory/current/
   cp scripts/per-request-enforcer.py ~/.claude/memory/current/
   cp scripts/context-monitor-v2.py ~/.claude/memory/current/
   cp scripts/blocking-policy-enforcer.py ~/.claude/memory/current/
   cp scripts/session-id-generator.py ~/.claude/memory/current/
   cp scripts/session-logger.py ~/.claude/memory/current/
   cp scripts/clear-session-handler.py ~/.claude/memory/current/
   cp scripts/stop-notifier.py ~/.claude/memory/current/
   ```

3. **Copy all hook scripts:**
   ```bash
   cp scripts/clear-session-handler.py ~/.claude/memory/current/
   cp scripts/stop-notifier.py ~/.claude/memory/current/
   cp scripts/pre-tool-enforcer.py ~/.claude/memory/current/
   cp scripts/post-tool-tracker.py ~/.claude/memory/current/
   ```

4. **Install global CLAUDE.md:**
   ```bash
   cp scripts/global-claude-md-template.md ~/.claude/CLAUDE.md
   ```
   NOTE: If you already have `~/.claude/CLAUDE.md`, manually merge the
   3-level architecture section from the template into your existing file.
   Do NOT replace personal configurations - just prepend the 3-level section.

5. **Install hooks in `~/.claude/settings.json`** (all 4 hook types):
   ```json
   {
     "model": "sonnet",
     "hooks": {
       "UserPromptSubmit": [{
         "hooks": [
           {
             "type": "command",
             "command": "python ~/.claude/memory/current/clear-session-handler.py",
             "timeout": 15,
             "statusMessage": "Level 1: Checking session state..."
           },
           {
             "type": "command",
             "command": "python ~/.claude/memory/current/3-level-flow.py --summary",
             "timeout": 30,
             "statusMessage": "Level -1/1/2/3: Running 3-level architecture check..."
           }
         ]
       }],
       "PreToolUse": [{
         "hooks": [{
           "type": "command",
           "command": "python ~/.claude/memory/current/pre-tool-enforcer.py",
           "timeout": 10,
           "statusMessage": "Level 3.6/3.7: Tool optimization + failure prevention..."
         }]
       }],
       "PostToolUse": [{
         "hooks": [{
           "type": "command",
           "command": "python ~/.claude/memory/current/post-tool-tracker.py",
           "timeout": 10,
           "statusMessage": "Level 3.9: Tracking task progress..."
         }]
       }],
       "Stop": [{
         "hooks": [{
           "type": "command",
           "command": "python ~/.claude/memory/current/stop-notifier.py",
           "timeout": 20,
           "statusMessage": "Level 3.10: Session save + voice notification..."
         }]
       }]
     }
   }
   ```

   **Hook type summary:**
   | Hook | Trigger | What It Enforces |
   |------|---------|------------------|
   | `UserPromptSubmit` | Every new message | Level -1, 1, 2, 3 (full 3-level flow) |
   | `PreToolUse` | Before every tool | Level 3.6 hints + 3.7 blocking |
   | `PostToolUse` | After every tool | Level 3.9 progress tracking |
   | `Stop` | After every response | Level 3.10 session save |

6. **Restart Claude Code** - hooks activate on next launch.

### After Setup - What You Will See

Every message you send will trigger the 3-level flow automatically:
```
[LEVEL -1] AUTO-FIX ENFORCEMENT (BLOCKING)  [OK] All 7 checks passed
[LEVEL 1] SYNC SYSTEM                        [OK] Context: 80% | Session: SESSION-...
[LEVEL 2] STANDARDS SYSTEM                   [OK] 15 standards, 156 rules loaded
[LEVEL 3] EXECUTION SYSTEM (12 steps)        [OK] All steps verified
```

---

## HOW GLOBAL vs PROJECT CLAUDE.MD WORKS

```
~/.claude/CLAUDE.md          <- GLOBAL (installed by setup script)
  - 3-level architecture       Non-bypassable enforcement rules
  - Skill/agent registry       21 skills + 12 agents mapped
  - Windows Unicode rules      Mandatory on Windows
  - Context optimization       Auto-applied every request

<your-project>/CLAUDE.md     <- PROJECT (this file)
  - Project overview           What this project is
  - Project structure          File organization
  - Dev commands               How to run/test/build
  - Project conventions        Coding style for this project
```

**Core rule:** Global policies are ALWAYS active. Project CLAUDE.md ADDS context,
never overrides. You cannot disable the 3-level architecture from a project file.

**CRITICAL - Never put these in global CLAUDE.md:**
- Project-specific credentials or API keys
- Internal company paths or server addresses
- Business-specific logic or domain knowledge
- Personal preferences specific to your workflow only

---

## PROJECT STRUCTURE

```
claude-insight/
├── CLAUDE.md                       <- This file (project context)
├── README.md                       <- Full documentation
├── IMPORTS.md                      <- Import patterns & GitHub URLs
├── CHANGELOG.md                    <- Version history
├── run.py                          <- App entry point
├── requirements.txt                <- Python dependencies
│
├── src/                            <- Application Code (Flask)
│   ├── __init__.py
│   ├── app.py                      <- Flask app, routes, SocketIO
│   ├── config.py                   <- Dev/Prod/Test configuration
│   ├── auth/                       <- Authentication (bcrypt)
│   ├── models/                     <- Data models
│   ├── routes/                     <- Route handlers
│   ├── middleware/                 <- Request logging middleware
│   ├── mcp/                        <- MCP enforcement server
│   ├── services/
│   │   ├── monitoring/             <- Core monitoring services
│   │   │   ├── three_level_flow_tracker.py
│   │   │   ├── policy_execution_tracker.py
│   │   │   ├── session_tracker.py
│   │   │   ├── metrics_collector.py
│   │   │   ├── log_parser.py
│   │   │   └── skill_agent_tracker.py
│   │   ├── ai/                     <- AI analytics (anomaly, prediction)
│   │   └── notifications/          <- Alert routing system
│   └── utils/
│       ├── import_manager.py       <- GitHub & local imports (NEW)
│       ├── path_resolver.py        <- Cross-platform path resolution
│       └── history_tracker.py      <- Activity history
│
├── templates/                      <- 31 Jinja2 HTML templates
├── static/                         <- CSS, JS, i18n files
│
├── scripts/                        <- All Executable Scripts (40 total, main hooks)
│   ├── setup-global-claude.sh      <- Unix automatic setup
│   ├── setup-global-claude.ps1     <- Windows automatic setup
│   ├── 3-level-flow.py             <- Main hook entry script
│   ├── clear-session-handler.py    <- Session state hook
│   ├── pre-tool-enforcer.py        <- Tool validation hook
│   ├── post-tool-tracker.py        <- Progress tracking hook
│   ├── stop-notifier.py            <- Session finalization hook
│   ├── session-chain-manager.py    <- Session chaining
│   ├── session-summary-manager.py  <- Per-session summaries
│   └── architecture/               <- 3-Level Architecture System (107 files)
│       ├── 01-sync-system/         <- Context & session management, patterns (38 files)
│       │   ├── context-management/ (11 files)
│       │   ├── session-management/ (8 files)
│       │   ├── pattern-detection/  (2 files)
│       │   └── user-preferences/   (4 files)
│       ├── 02-standards-system/    <- Standards & rules (3 files)
│       └── 03-execution-system/    <- Execution flows & task tracking (66 files)
│           ├── 00-prompt-generation/
│           ├── 01-task-breakdown/
│           ├── 02-plan-mode/
│           ├── 04-model-selection/
│           ├── 05-skill-agent-selection/
│           ├── 06-tool-optimization/
│           ├── 07-recommendations/
│           ├── 08-progress-tracking/
│           ├── 09-git-commit/
│           └── failure-prevention/
│
├── policies/                       <- Policy Documentation (.md only - 34+ files)
│   ├── 01-sync-system/
│   ├── 02-standards-system/
│   └── 03-execution-system/
│
├── docs/                           <- Architecture docs & templates (no operational reports)
│   ├── templates/                  <- Setup templates
│   │   └── global-claude-md-template.md <- Public CLAUDE.md template for installation
│   └── archive/                    <- Archived operational reports (11 files)
├── config/                         <- Runtime configuration JSONs
└── tests/                          <- Test suite (16+ test files)
```

---

## IMPORTS & MODULE LOADING

### Local Imports (Same Project)
All imports within the project use relative paths:

```python
# ✅ CORRECT - Relative imports from src/
from services.monitoring.metrics_collector import MetricsCollector
from services.ai.anomaly_detector import AnomalyDetector
from utils.import_manager import ImportManager
```

### External Imports (claude-global-library)
Use `ImportManager` for GitHub-hosted resources:

```python
from utils.import_manager import ImportManager

# Load skills
docker_skill = ImportManager.get_skill('docker')

# Load agents
orchestrator = ImportManager.get_agent('orchestrator-agent')

# GitHub URL directly (if needed)
# https://raw.githubusercontent.com/piyushmakhija28/claude-global-library/main/skills/docker/skill.md
```

**See `IMPORTS.md` for complete import patterns and GitHub URLs.**

---

## DEVELOPMENT COMMANDS

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard (port 5000)
python run.py

# Run tests
python -m pytest tests/ -v

# Check specific test
python -m pytest tests/test_policy_integration.py -v

# Bump version
python scripts/bump-version.py --patch
```

**Default credentials:** admin / admin (change in production)
**Dashboard URL:** http://localhost:5000

---

## PROJECT-SPECIFIC CONVENTIONS

1. **No daemon scripts** - No background process files in this project
2. **No Windows Unicode** - All Python files use ASCII only (cp1252 safe)
3. **Path resolution** - Always use `path_resolver.py` for cross-platform paths
4. **Services** - Business logic in `src/services/`, never in routes or templates
5. **Templates** - All HTML in `templates/`, extend from `base.html`
6. **Config** - All config via `src/config.py`, no hardcoded values anywhere
7. **Monitoring** reads `~/.claude/memory/logs/` - memory system must be installed

---

## WHAT CLAUDE INSIGHT MONITORS

| What | From | Dashboard |
|------|------|-----------|
| 3-level flow execution | `~/.claude/memory/logs/sessions/*/flow-trace.json` | /3level-flow-history |
| Policy enforcement | `~/.claude/memory/logs/policy-hits.log` | /policies |
| Session analytics | `~/.claude/memory/sessions/` | /sessions |
| Session chaining | `~/.claude/memory/sessions/chain-index.json` | /sessions |
| Session summaries | `~/.claude/memory/logs/sessions/*/session-summary.json` | /sessions |
| Skill/agent usage | flow-trace.json data | /analytics |
| Context usage % | Context monitor logs | /dashboard |

---

---

## Settings Configuration (v5.2.1+)

**Source of Truth:** `scripts/settings-config.json`

Claude Insight now maintains settings as a version-controlled JSON file:
- **Location:** `claude-insight/scripts/settings-config.json`
- **Purpose:** Single source of truth for hook configuration
- **Usage:** Setup scripts read from this file and generate `~/.claude/settings.json`
- **Auto-sync:** claude-code-ide hook-downloader automatically pulls from this repo

**Never edit** `~/.claude/settings.json` directly. Always update `scripts/settings-config.json` and rerun setup.

For complete settings documentation, see `scripts/README.md`.

---

## Nested Hooks Architecture (v5.2.1+)

**Unified Enforcement:** Matchers for granular control with Level 3.6 optimization mandatory.

### Structure

**UserPromptSubmit** (no matcher) — Runs on every prompt
```
3-level-flow.py (Level -1/1/2/3)
github_issue_manager.py (issue tracking)
```

**PreToolUse** (1 unified matcher for enforcement)
```
Matcher: ^(Write|Edit|NotebookEdit|Bash|Read|Grep|Glob)$
  └─ pre-tool-enforcer.py → Level 3.6/3.7 (tool optimization + blocking)
     ├─ Read: enforce offset/limit for large files (>500 lines)
     ├─ Grep: enforce head_limit for large result sets
     ├─ Write/Edit/Bash: full code enforcement + blocking
     └─ BLOCKING: All tools must comply with optimization policy

No matcher: WebFetch, WebSearch, Agent, Task → pass through, no hook
```

**PostToolUse** (2 matchers for different tracking scopes)
```
Matcher 1: ^(Write|Edit|NotebookEdit|Bash|TaskCreate|TaskUpdate|Skill|Task)$
  └─ post-tool-tracker.py → Level 3.9-3.12 (progress + GitHub + flags)

Matcher 2: ^(Read|Grep|Glob|WebFetch|WebSearch)$
  └─ post-tool-tracker.py → Level 3.9 (progress tracking only)

No matcher: Agent, etc. → pass through, no hook
```

**Stop** (no matcher) — Runs once per response
```
stop-notifier.py (Level 3.10 session save + voice)
```

### Benefits
- **Unified Enforcement:** Single matcher, same blocking policy for all tools
- **Optimization Mandatory:** Read/Grep/Glob must follow optimization rules (not optional)
- **Clarity:** Status message "Level 3.6/3.7" applies to all matched tools
- **Efficiency:** WebFetch/WebSearch/Agent pass through (no unnecessary overhead)
- **GitHub Integration:** Full workflow only on code/task tools

---

**Version:** 5.2.1 (Unified Hook Enforcement)
**Last Updated:** 2026-03-09 10:45
**Source:** https://github.com/piyushmakhija28/claude-insight
