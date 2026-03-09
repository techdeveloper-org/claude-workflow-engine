# Scripts Directory

This directory contains all executable scripts and hook configuration for Claude Insight.

## Configuration Files

### `settings-config.json`
**Source of truth for Claude Code hook configuration**

This file defines the 3-level enforcement hooks that run automatically in Claude Code:
- **UserPromptSubmit** - Level -1/1/2/3 enforcement (every prompt)
- **PreToolUse** - Level 3.6/3.7 tool optimization + blocking (before each tool)
- **PostToolUse** - Level 3.9-3.12 progress tracking (after each tool)
- **Stop** - Level 3.10 session save (after response)

**How it's used:**
1. Setup scripts (`.sh` / `.ps1`) read this file
2. Generated as `~/.claude/settings.json` during installation
3. Hook-downloader.py in claude-code-ide automatically syncs from here
4. When this file is updated, all new installations use the latest version

**DO NOT edit** `~/.claude/settings.json` directly - always update this file instead.

### Matchers & Tool Grouping

**PreToolUse - Unified Enforcement Matcher**
```
^(Write|Edit|NotebookEdit|Bash|Read|Grep|Glob)$
├─ Write/Edit/Bash: Code modification enforcement
├─ Read: Offset/limit mandatory for files >500 lines
├─ Grep: head_limit mandatory for large result sets
├─ Glob: Optimization patterns mandatory
└─ ALL: BLOCKING if optimization policy violated
```

**PostToolUse - Two tracking matchers**
```
Matcher 1: ^(Write|Edit|NotebookEdit|Bash|TaskCreate|TaskUpdate|Skill|Task)$
  └─ Full progress + GitHub integration (Level 3.9-3.12)

Matcher 2: ^(Read|Grep|Glob|WebFetch|WebSearch)$
  └─ Lightweight progress tracking (Level 3.9)
```

**Non-matched tools** (pass through without hooks):
- WebFetch, WebSearch, Agent, Task, etc.
- External APIs where optimization not applicable

## Executable Scripts

### Hook Entry Points

- **3-level-flow.py** - Main UserPromptSubmit hook (all 3 levels)
- **github_issue_manager.py** - GitHub issue creation (UserPromptSubmit)
- **pre-tool-enforcer.py** - Level 3.6/3.7 enforcement (PreToolUse)
- **post-tool-tracker.py** - Level 3.9-3.12 tracking (PostToolUse)
- **stop-notifier.py** - Level 3.10 session save (Stop hook)

### Setup Scripts

- **setup-global-claude.sh** - Unix/Linux/macOS setup
- **setup-global-claude.ps1** - Windows PowerShell setup

**Both read from:** `settings-config.json`

### Session Management

- **session-chain-manager.py** - Multi-session chaining
- **session-summary-manager.py** - Per-session summaries

## Architecture Directory

**scripts/architecture/** contains 107 files implementing the 3-level system:
- **01-sync-system/** - Level 1: Context & session management (38 files)
- **02-standards-system/** - Level 2: Standards & rules (3 files)
- **03-execution-system/** - Level 3: Execution flows (66 files)

## Important: Source of Truth

Claude Insight's `scripts/settings-config.json` is the **ONLY** source of truth for hook configuration.

- ✅ Commit changes here
- ✅ Update from here to ~/.claude/settings.json
- ❌ Do NOT edit ~/.claude/settings.json directly
- ❌ Do NOT have separate configs in different places

## Workflow

1. **Update settings:** Edit `scripts/settings-config.json`
2. **Commit changes:** `git add scripts/settings-config.json && git commit`
3. **Run setup:** `./scripts/setup-global-claude.sh` (reads from config)
4. **Auto-sync:** claude-code-ide hook-downloader.py syncs automatically
5. **Verify:** Check `~/.claude/settings.json` matches the config

---

**Version:** 5.2.1
**Last Updated:** 2026-03-09
**Status:** Unified Hook Enforcement Active
