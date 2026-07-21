# Session Chaining Policy

**Version:** 1.0.0
**Last Updated:** 2026-02-23
**Category:** Sync System > Session Management

---

## Overview

Sessions are linked in a chain. Each session knows its parent, children, related sessions, and tags. Combined with per-session summaries, this gives Claude full context continuity across /clear boundaries.

## Architecture

```
Session Chain:
  SESSION-A (grandparent)
      |
  SESSION-B (parent) - summary: "worked on docker config"
      |
  SESSION-C (current) - summary: "fixing k8s deployment"
```

## Data Flow

### On Every Request (3-level-flow.py):
1. **Accumulate** - Add prompt/skill/model/complexity to session-summary.json
2. **Auto-tag** - Extract tags from prompt, skill, task type, project dir
3. **Auto-relate** - Link sessions with 2+ shared tags
4. **Display chain** - Show ancestors/related in flow output

### On /clear (clear-session-handler.py):
1. **Finalize summary** - Generate session-summary.md from accumulated data
2. **Update chain** - Summary text pushed to chain-index.json
3. **Link sessions** - New session linked as child of old session
4. **Context loaded** - Previous session context printed for Claude

## Data Model

### chain-index.json (Central Index)
```json
{
  "sessions": {
    "SESSION-ID": {
      "parent": "PARENT-SESSION-ID",
      "children": ["CHILD-SESSION-IDs"],
      "related": ["RELATED-SESSION-IDs"],
      "tags": ["spring-boot", "docker"],
      "project": "techdeveloper-scheduler",
      "skill": "java-spring-boot-microservices",
      "task_type": "Implementation",
      "summary": "3 requests | project: X | type: Y | started: Z"
    }
  },
  "tag_index": {
    "spring-boot": ["SESSION-IDs"],
    "docker": ["SESSION-IDs"]
  }
}
```

### session-summary.json (Per-Session Accumulator)
```json
{
  "session_id": "SESSION-ID",
  "status": "ACTIVE|COMPLETED",
  "request_count": 5,
  "requests": [
    {
      "timestamp": "2026-02-23T13:35:18",
      "prompt": "user message",
      "task_type": "Implementation",
      "skill": "java-spring-boot-microservices",
      "complexity": 7,
      "model": "SONNET",
      "cwd": "/path/to/project"
    }
  ],
  "skills_used": ["java-spring-boot-microservices"],
  "task_types": ["Implementation"],
  "models_used": ["SONNET"],
  "projects_touched": ["techdeveloper-scheduler"],
  "max_complexity": 7,
  "summary_text": "5 requests | project: X | type: Y"
}
```

### session-summary.md (Human-Readable)
Generated on session close. Contains:
- Session metadata (created, updated, status)
- Projects, skills, task types, models used
- Request timeline with prompts and context
- TL;DR one-liner summary

## File Locations

| File | Location | When Created |
|------|----------|--------------|
| chain-index.json | ~/.claude/memory/sessions/ | First link/tag |
| session-summary.json | ~/.claude/memory/logs/sessions/SESSION-ID/ | First request |
| session-summary.md | ~/.claude/memory/logs/sessions/SESSION-ID/ | On /clear |

## Scripts

| Script | Purpose | Called By |
|--------|---------|----------|
| session-chain-manager.py | Chain links, tags, context | clear-session-handler, 3-level-flow |
| session-summary-manager.py | Accumulate, finalize, read | 3-level-flow, clear-session-handler |

## Tag Auto-Extraction

Tags are extracted from:
- **Task type** -> e.g., "implementation", "system-script"
- **Skill name** -> e.g., "java-spring-boot-microservices"
- **Project directory** -> e.g., "techdeveloper-scheduler"
- **Prompt keywords** -> e.g., "spring boot", "docker", "kubernetes"

## Auto-Relate Rules

- Sessions with 2+ shared tags are automatically linked as "related"
- Bidirectional: A related to B means B related to A
- Runs after every tagging operation

## How Claude Uses This

1. **New session starts** -> Read chain context -> See what parent session did
2. **Same topic across sessions** -> Tag-related shows similar sessions
3. **Context continuity** -> Summary gives rich understanding of past work
4. **Search by topic** -> Find all sessions about "docker", "spring-boot", etc.

## Integration Points

### 3-level-flow.py (after session JSON update):
- Calls `session-chain-manager.py auto-tag`
- Calls `session-summary-manager.py accumulate`
- Loads and displays chain context in output

### clear-session-handler.py (on /clear):
- Calls `session-summary-manager.py finalize`
- Calls `session-chain-manager.py link`

## Enforcement

- Chain operations are NON-BLOCKING (never fail the flow)
- Summary accumulation is NON-BLOCKING
- All operations wrapped in try/except with logging
- Timeout: 5s for accumulate/tag, 10s for finalize/link
