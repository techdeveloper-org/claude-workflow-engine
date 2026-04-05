# Getting Started with Claude Workflow Engine

**Version:** 1.15.1 | **Status:** Active

---

## What Is This?

Claude Workflow Engine automates the Software Development Life Cycle using a
3-level LangGraph orchestration pipeline. From a single natural language prompt,
it handles task analysis, GitHub issues, branching, PR creation, code review,
documentation, and issue closure.

---

## Current Pipeline (v1.15.1)

```
Level -1: Auto-Fix (Unicode, encoding, paths)
Level 1:  Context Sync (complexity, session)
Level 2:  Standards Loading (common, Java, tool-opt, MCP discovery)
Level 3:  Execution
  Pre-0:  Call graph scan + template fast-path detection
  Step 0: Task Analysis (prompt-gen-expert + orchestrator-agent chain)
  Step 8: GitHub Issue Creation
  Step 9: Branch Creation
  Step 10: Implementation
  Step 11: PR Creation & Review (with retry loop)
  Step 12: Issue Closure
  Step 13: Documentation Update
  Step 14: Final Summary
```

**Steps 1, 3, 4, 5, 6, 7 were removed in v1.13.0** -- collapsed into Step 0's
orchestration template call. See `CLAUDE.md` for the full architecture.

---

## Quick Start

```bash
python scripts/3-level-flow.py --task "your task description"
```

## Full Documentation

See the root `CLAUDE.md` for complete architecture, configuration, and development
guidelines.
