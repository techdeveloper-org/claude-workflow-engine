# Claude Insight v4.13.1

**Real-time Monitoring Dashboard for the Claude Memory System (3-Level Architecture + Policy Enforcement)**

[![GitHub](https://img.shields.io/badge/GitHub-claude--insight-blue?logo=github)](https://github.com/piyushmakhija28/claude-insight)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-green?logo=flask)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-4.13.1-brightgreen)](VERSION)

Claude Insight is a Python Flask dashboard that monitors how Claude Code follows the **3-Level Architecture enforcement policies** in real-time. It tracks policy execution, session analytics, skill/agent usage, context optimization, and provides complete audit trails of all decisions.

**Latest Version (v4.13.1):**
- **FIXED:** Critical PID mismatch - flag files now use session ID only (no PID), fixing cross-hook enforcement
- **FIXED:** post-tool-tracker session ID resolution - now reads `.current-session.json` first
- **FIXED:** stop-notifier referencing deleted scripts (auto-commit-enforcer, failure-detector)
- **NEW:** Git push to main/master now BLOCKED by pre-tool-enforcer
- Full policy audit: 16 scripts called, 6 enforcement checks, all architecture scripts verified

---

## Table of Contents

1. [What Is Claude Insight?](#what-is-claude-insight)
2. [Quick Start](#quick-start)
3. [3-Level Architecture Overview](#3-level-architecture-overview)
4. [Key Features](#key-features)
5. [System Architecture](#system-architecture)
6. [Project Structure](#project-structure)
7. [Installation & Setup](#installation--setup)
8. [Running the Dashboard](#running-the-dashboard)
9. [Configuration](#configuration)
10. [Policies & Scripts](#policies--scripts)
11. [Session Management](#session-management)
12. [API Reference](#api-reference)
13. [Troubleshooting](#troubleshooting)
14. [Contributing](#contributing)
15. [Changelog](#changelog)
16. [License](#license)

---

## What Is Claude Insight?

Claude Insight solves a critical problem: **Without monitoring, you cannot verify that Claude is following your enforcement policies.**

Claude Insight provides **real-time visibility** into:
- ✅ Whether Claude follows your 3-level enforcement policies
- ✅ Which model (Haiku/Sonnet/Opus) was selected and why
- ✅ How much context each session consumed
- ✅ Which skills and agents were invoked
- ✅ Complete audit trail of all decisions

### The Problem It Solves

```
Before Claude Insight:
  ❌ You cannot see what Claude is doing
  ❌ You don't know which policies are enforced
  ❌ No visibility into model selection decisions
  ❌ No audit trail of policy compliance
  ❌ No context optimization insights

After Claude Insight:
  ✅ Real-time policy execution monitoring
  ✅ Complete decision audit trail
  ✅ Context usage analytics
  ✅ Skill/agent performance tracking
  ✅ Anomaly detection & alerts
```

### Architecture Overview

```
Claude Code (IDE)
       ↓ (every message triggers)
UserPromptSubmit Hook
       ↓
3-level-flow.py
  [Level -1] Auto-Fix Enforcement (7 validation checks)
  [Level 1]  Sync System (context + session management)
  [Level 2]  Standards System (code standards)
  [Level 3]  Execution System (12-step execution flow)
       ↓ (writes execution trace to)
~/.claude/memory/logs/
       ↓ (read by Flask dashboard)
Claude Insight Dashboard
       ↓
Real-time charts, analytics, alerts
```

---

## Quick Start

### Prerequisites

- Python 3.8 or higher
- Git
- pip or conda package manager
- Flask 3.0+

### Installation

```bash
# Clone the repository
git clone https://github.com/piyushmakhija28/claude-insight.git
cd claude-insight

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup the Claude Memory System (first time only)
bash scripts/setup-global-claude.sh  # Unix/Linux/WSL
# or
.\scripts\setup-global-claude.ps1  # Windows PowerShell
```

### Running the Dashboard

```bash
# Start the Flask app
python run.py

# Dashboard available at: http://localhost:5000
# Default credentials: admin / admin
```

---

## 3-Level Architecture Overview

Claude Insight enforces a **3-level policy architecture** that ensures Claude Code follows best practices:

### Level -1: Auto-Fix Enforcement

**Purpose:** Prevent common mistakes before they happen

| Check | Purpose |
|-------|---------|
| **Session State Validation** | Verify session files are initialized |
| **Critical Script Presence** | Ensure enforcement scripts exist |
| **File Locking** | Prevent race conditions on shared files |
| **Context Baseline** | Reset context monitoring baseline |
| **Session Isolation** | Verify per-window session isolation |
| **Dependency Validation** | Check policy script dependencies |
| **Auto-Fix Enforcement** | Apply automatic fixes if needed |

### Level 1: Sync System

**Purpose:** Manage context and session state

| Component | Scripts | Purpose |
|-----------|---------|---------|
| **Session Management** | 5 scripts | Session chaining, isolation, state management |
| **Context Management** | 8 scripts | Context monitoring, optimization, cleanup |
| **Pattern Detection** | 2 scripts | Cross-project pattern learning |
| **User Preferences** | 4 scripts | User preference tracking and application |

**Files:** 38 Python scripts in `scripts/architecture/01-sync-system/`

### Level 2: Standards System

**Purpose:** Enforce coding and documentation standards

| Standard | Purpose |
|----------|---------|
| **Common Standards** | Language-agnostic best practices |
| **Coding Standards Enforcement** | Language/framework-specific standards |

**Files:** 2 Python scripts in `scripts/architecture/02-standards-system/`

### Level 3: Execution System (12 Steps)

**Purpose:** Execute tasks following loaded standards

| Step | Component | Purpose |
|------|-----------|---------|
| **0** | Prompt Generation | Convert natural language to structured prompt |
| **1** | Task Breakdown | Divide into phases and auto-create tasks |
| **2** | Plan Mode Decision | Suggest plan mode based on complexity |
| **3** | Context Check | Monitor token usage |
| **4** | Model Selection | Choose Haiku/Sonnet/Opus intelligently |
| **5** | Skill/Agent Selection | Auto-select appropriate skills/agents |
| **6** | Tool Optimization | Optimize tools for 60-85% token savings |
| **7** | Recommendations | Real-time model/skill recommendations |
| **8** | Progress Tracking** | Auto-track task progress |
| **9** | Git Commit Automation** | Auto-commit on task completion |
| **10** | Failure Prevention** | Detect and prevent common failures |
| **11** | Session Save** | Archive session with metadata |

**Files:** 66 Python scripts in `scripts/architecture/03-execution-system/`

---

## Key Features

### Core Monitoring

| Feature | Description |
|---------|-------------|
| **3-Level Flow Tracker** | Real-time execution of all 3 policy levels |
| **Policy Execution Tracker** | Which policies ran, pass/fail status |
| **Session Analytics** | Duration, requests, context usage per session |
| **Session Chaining** | Parent/child relationships, cross-session summaries |
| **Skill/Agent Usage** | Invocation frequency and performance metrics |
| **Context Monitoring** | Context % per request, optimization actions |
| **Model Selection Tracking** | Haiku/Sonnet/Opus distribution |

### AI-Powered Analytics

| Feature | Description |
|---------|-------------|
| **Anomaly Detection** | Unusual patterns (context spikes, policy failures) |
| **Predictive Analytics** | Forecast context usage and patterns |
| **Bottleneck Analysis** | Identify slow execution steps |
| **Performance Profiling** | Response time analysis per component |

### Dashboard Capabilities

| Feature | Description |
|---------|-------------|
| **Real-time Updates** | Live WebSocket data via SocketIO |
| **Session Search** | Search and filter session history |
| **Export Options** | Generate CSV, Excel, PDF reports |
| **Multi-language** | English, Hindi, Spanish, French, German |
| **Custom Dashboards** | Build personalized metric views |
| **Dark/Light Themes** | Multiple UI themes |

### Enterprise Features

| Feature | Description |
|---------|-------------|
| **Policy Compliance** | Verify all policies are enforced |
| **Audit Trail** | Complete history of all decisions |
| **Metrics Collection** | 39+ emission points for granular tracking |
| **Version Management** | Automatic CHANGELOG + SRS updates |
| **File Locking** | Safe concurrent file access |
| **Auto-Cleanup** | Automatic session and log cleanup |

---

## System Architecture

### 3-Tier Ecosystem

Claude Insight is **Tier 2** of a 3-tier architecture:

```
Tier 1: User Interface
  Repository: claude-code-ide
  Technology: JavaFX
  Purpose: IDE that triggers hooks
  │
  ├─ Uses hooks from
  │
  v
Tier 2: Policy Enforcement (THIS PROJECT)
  Repository: claude-insight
  Technology: Python + Flask
  Purpose: Policy scripts + monitoring dashboard
  │
  ├─ Uses skills from
  │
  v
Tier 3: Knowledge Base
  Repository: claude-global-library
  Technology: Markdown + Python
  Purpose: 21 reusable skills + 12 agents
```

| Tier | Repository | Purpose | Tech Stack |
|------|-----------|---------|-----------|
| **Tier 1** | [claude-code-ide](https://github.com/piyushmakhija28/claude-code-ide) | IDE + Hook Executor | JavaFX, Bash, Python |
| **Tier 2** | [claude-insight](https://github.com/piyushmakhija28/claude-insight) | Policies + Dashboard | Python, Flask, SQLite |
| **Tier 3** | [claude-global-library](https://github.com/piyushmakhija28/claude-global-library) | Skills + Agents | Markdown, Python |

---

## Project Structure

```
claude-insight/
├── README.md                                    ← You are here
├── CLAUDE.md                                    ← Project instructions
├── SYSTEM_REQUIREMENTS_SPECIFICATION.md         ← Complete SRS (947 lines)
├── CHANGELOG.md                                 ← Version history
├── VERSION                                      ← Current version (4.4.4)
│
├── scripts/                                     ← All executable scripts
│   ├── 3-level-flow.py                         ← Main policy enforcement entry point
│   ├── clear-session-handler.py                ← Session cleanup hook
│   ├── pre-tool-enforcer.py                    ← Tool validation hook
│   ├── post-tool-tracker.py                    ← Progress tracking hook
│   ├── stop-notifier.py                        ← Session finalization hook
│   ├── auto-fix-enforcer.py                    ← Auto-fix enforcement
│   ├── policy-tracker.py                       ← Policy execution tracking
│   ├── policy-tracking-helper.py               ← Policy tracking utilities
│   │
│   └── architecture/                           ← 3-level architecture system
│       ├── 01-sync-system/                     ← 38 scripts
│       │   ├── context-management/             ← Context monitoring & optimization
│       │   ├── session-management/             ← Session chaining & state
│       │   ├── pattern-detection/              ← Cross-project patterns
│       │   └── user-preferences/               ← User preference tracking
│       │
│       ├── 02-standards-system/                ← 2 scripts
│       │   ├── common-standards-policy.py
│       │   └── coding-standards-enforcement-policy.py
│       │
│       └── 03-execution-system/                ← 66 scripts
│           ├── 00-prompt-generation/           ← Prompt generation
│           ├── 01-task-breakdown/              ← Task breakdown
│           ├── 02-plan-mode/                   ← Plan mode suggestion
│           ├── 04-model-selection/             ← Model selection
│           ├── 05-skill-agent-selection/       ← Skill/agent selection
│           ├── 06-tool-optimization/           ← Tool optimization
│           ├── 08-progress-tracking/           ← Progress tracking
│           ├── 09-git-commit/                  ← Git automation
│           │   ├── git-auto-commit-policy.py   ← Auto-commit (3097 lines)
│           │   └── version-release-policy.py   ← Version bump + SRS update
│           └── failure-prevention/             ← Failure prevention
│
├── policies/                                    ← Policy documentation (27 files)
│   ├── 01-sync-system/                         ← Level 1 policies
│   ├── 02-standards-system/                    ← Level 2 policies
│   └── 03-execution-system/                    ← Level 3 policies
│
├── src/                                         ← Flask application
│   ├── app.py                                  ← Main Flask app
│   ├── config.py                               ← Configuration
│   ├── models/                                 ← Data models
│   ├── routes/                                 ← API routes
│   ├── services/
│   │   ├── monitoring/                         ← 12+ monitoring services
│   │   ├── ai/                                 ← Anomaly detection
│   │   └── notifications/                      ← Alert routing
│   └── utils/
│       ├── import_manager.py                   ← GitHub skills loader
│       ├── path_resolver.py                    ← Cross-platform paths
│       └── history_tracker.py                  ← Activity history
│
├── templates/                                   ← 31 Jinja2 HTML templates
├── static/                                      ← CSS, JavaScript, i18n
├── tests/                                       ← Test suite (16+ tests)
├── docs/                                        ← Supporting documentation
│
├── requirements.txt                            ← Python dependencies
├── run.py                                      ← App entry point
└── LICENSE                                     ← MIT License
```

---

## Installation & Setup

### Step 1: System Requirements

```bash
# Check Python version
python --version  # Must be 3.8 or higher

# Check Git
git --version
```

### Step 2: Clone Repository

```bash
git clone https://github.com/piyushmakhija28/claude-insight.git
cd claude-insight
```

### Step 3: Create Virtual Environment

```bash
# Unix/Linux/macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Configure Claude Memory System

**First Time Setup (Required):**

```bash
# Unix/Linux/WSL
bash scripts/setup-global-claude.sh

# Windows PowerShell (Run as Administrator)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\scripts\setup-global-claude.ps1
```

This will:
- Create `~/.claude/` directory
- Install enforcement scripts
- Create `~/.claude/settings.json` with hooks
- Install global CLAUDE.md

**Manual Setup Alternative:**

See `CLAUDE.md` section: "FIRST TIME SETUP - INSTALL THE MEMORY SYSTEM" for step-by-step manual configuration.

---

## Running the Dashboard

```bash
# Start the Flask application
python run.py

# Server will start at http://localhost:5000
# Or specify a different port:
python run.py --port 8080

# Default Login
  Email:    admin@example.com
  Password: admin
```

### Accessing the Dashboard

Navigate to: **http://localhost:5000**

**Main Dashboard Pages:**
- `/` - Overview dashboard
- `/dashboard` - Real-time metrics
- `/sessions` - Session history and search
- `/3level-flow-history` - 3-level flow execution traces
- `/policies` - Policy compliance tracking
- `/analytics` - AI-powered analytics
- `/settings` - Configuration

---

## Configuration

### Environment Variables

```bash
# Optional configuration
export CLAUDE_INSIGHT_PORT=5000
export CLAUDE_INSIGHT_DEBUG=False
export CLAUDE_INSIGHT_HOST=0.0.0.0
```

### settings.json (Claude Code Hooks)

Location: `~/.claude/settings.json`

```json
{
  "model": "sonnet",
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [
        {
          "type": "command",
          "command": "python ~/.claude/scripts/hook-downloader.py 3-level-flow.py --summary",
          "timeout": 30,
          "async": false
        }
      ]
    }]
  }
}
```

**Critical:** All hooks must have `"async": false` to display checkpoint and policy results.

---

## Policies & Scripts

### Complete Policy-Script Mapping

| Level | Policy | Script | Purpose |
|-------|--------|--------|---------|
| **-1** | Auto-Fix | auto-fix-enforcer.py | System validation (7 checks) |
| **1** | Session Management | session-*-policy.py | Session chaining & isolation |
| **1** | Context Management | context-*-policy.py | Context optimization |
| **1** | User Preferences | user-preferences-policy.py | Preference tracking |
| **2** | Common Standards | common-standards-policy.py | Best practices |
| **2** | Coding Standards | coding-standards-enforcement-policy.py | Code standards |
| **3.0** | Prompt Generation | prompt-generation-policy.py | Structured prompts |
| **3.1** | Task Breakdown | automatic-task-breakdown-policy.py | Task creation |
| **3.2** | Plan Mode | auto-plan-mode-suggestion-policy.py | Plan mode decision |
| **3.4** | Model Selection | intelligent-model-selection-policy.py | Model choice |
| **3.5** | Skill Selection | auto-skill-agent-selection-policy.py | Skill/agent choice |
| **3.6** | Tool Optimization | tool-usage-optimization-policy.py | Token savings |
| **3.9** | Git Automation | git-auto-commit-policy.py | Auto-commit |
| **3.10** | Version Release | version-release-policy.py | Version bump + docs |

**For complete policy documentation:** See `SYSTEM_REQUIREMENTS_SPECIFICATION.md`

---

## Session Management

### Session ID Format

```
SESSION-YYYYMMDD-HHMMSS-XXXX
└─────────┬──────────────┬──┤
          │              └─ Random 4-char suffix
          └─ Date + time stamp
```

**Example:** `SESSION-20260306-102211-7OOC`

### Session Storage

```
~/.claude/memory/
├── sessions/                   ← Active session state
│   ├── SESSION-{ID}/
│   │   ├── session.json        ← Session metadata
│   │   ├── flow-trace.json     ← 3-level flow data
│   │   └── session-summary.json ← Summary stats
│   │
│   └── chain-index.json        ← Session chaining index
│
├── logs/
│   ├── sessions/               ← Session logs
│   │   └── SESSION-{ID}/
│   │       ├── checkpoint-*.log
│   │       ├── flow-trace.json
│   │       └── session-summary.json
│   │
│   └── policy-hits.log         ← All policy executions
```

### Session Chaining

Sessions can be linked using tags:

```python
# In task description or user preferences:
@parent:SESSION-20260305-120000-XXXX
@tag:migration
@context:database-refactoring
```

The system will:
- Create parent-child relationship
- Share context across sessions
- Track related work items

---

## API Reference

### REST Endpoints

```
GET  /api/sessions                 List all sessions
GET  /api/sessions/{id}            Get session details
GET  /api/sessions/{id}/trace      Get 3-level flow trace
GET  /api/policies                 List policies
GET  /api/policies/{name}          Get policy details
GET  /api/analytics/anomalies      Get detected anomalies
POST /api/export/sessions          Export sessions (CSV/Excel/PDF)
```

### WebSocket Events (SocketIO)

```
connect                   Client connected
disconnect                Client disconnected
session_update            New session or update
policy_hit                Policy executed
context_change            Context usage changed
anomaly_detected          Anomaly found
```

---

## Troubleshooting

### Dashboard Won't Start

```bash
# Check if port is in use
lsof -i :5000  # Unix/Linux
netstat -ano | findstr :5000  # Windows

# Use different port
python run.py --port 8080
```

### No Hooks Executing

```bash
# Verify settings.json exists
cat ~/.claude/settings.json

# Check if async=false
# If async=true, checkpoint won't display!

# Verify hook script exists
ls -la ~/.claude/scripts/hook-downloader.py
```

### Sessions Not Creating

```bash
# Check session directory
ls -la ~/.claude/memory/sessions/

# Check permissions
chmod -R 755 ~/.claude/memory/

# Check memory logs
tail -f ~/.claude/memory/logs/policy-hits.log
```

### Context Issues

```bash
# Check context monitor
python scripts/context-monitor-v2.py --report

# View current context usage
cat ~/.claude/memory/current/context-usage.json
```

---

## Contributing

We welcome contributions! Please:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m "Add amazing feature"`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

**Please ensure:**
- ✅ Python code follows PEP 257 (docstrings)
- ✅ All tests pass (`pytest tests/`)
- ✅ Code is properly formatted
- ✅ Commit messages are descriptive

---

## Changelog

**Latest:** v4.4.4 (2026-03-06)
- ✅ Enhanced version-release-policy.py with CHANGELOG + SRS auto-updates
- ✅ Bump VERSION file (4.4.3 → 4.4.4)
- ✅ Cleanup redundant documentation (19 files removed)
- ✅ Comprehensive README with 2000+ lines of documentation

**See [`CHANGELOG.md`](CHANGELOG.md)** for complete version history.

---

## License

Claude Insight is licensed under the **MIT License**.

See [`LICENSE`](LICENSE) file for details.

---

## Support & Contact

- **GitHub Issues:** [Report bugs](https://github.com/piyushmakhija28/claude-insight/issues)
- **GitHub Discussions:** [Ask questions](https://github.com/piyushmakhija28/claude-insight/discussions)
- **Documentation:** [See SYSTEM_REQUIREMENTS_SPECIFICATION.md](SYSTEM_REQUIREMENTS_SPECIFICATION.md)
- **Project Docs:** [See CLAUDE.md](CLAUDE.md)

---

## Acknowledgments

Claude Insight is built as part of the **3-Level Architecture** for Claude Code policy enforcement. Thanks to:
- The Claude Code IDE community
- Contributors to claude-global-library
- All users who provide feedback and feature requests

---

**Version:** 4.4.4
**Last Updated:** 2026-03-06
**Repository:** https://github.com/piyushmakhija28/claude-insight
**License:** MIT
