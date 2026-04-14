# Contributing to Claude Workflow Engine

Thank you for your interest in contributing! This document explains how to get started, what the codebase expects, and how to submit good contributions.

---

## Table of Contents

- [Before You Start](#before-you-start)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Issue Reporting](#issue-reporting)
- [What NOT to Contribute](#what-not-to-contribute)

---

## Before You Start

- Check [open issues](../../issues) — your idea may already be tracked.
- For significant changes, **open an issue first** to align on approach before writing code.
- For bug fixes, feel free to go straight to a PR.

---

## Getting Started

### Prerequisites

- Python 3.8+
- `pip install -r requirements.txt`
- Claude Code CLI (`claude`) installed and on your PATH
- A valid `ANTHROPIC_API_KEY` in your environment

### Setup

```bash
git clone https://github.com/techdeveloper-org/claude-workflow-engine
cd claude-workflow-engine
pip install -r requirements.txt
cp .env.example .env
# Fill in your ANTHROPIC_API_KEY and GITHUB_TOKEN in .env
```

### Run the engine (Hook Mode — recommended for development)

```bash
python scripts/3-level-flow.py --task "your task description here"
```

### Run tests

```bash
pytest tests/
```

---

## Project Structure

```
scripts/langgraph_engine/   # Core engine — LangGraph pipeline nodes
hooks/                      # Claude Code hook scripts (PreToolUse, PostToolUse, Stop)
policies/                   # Pipeline policies (.md files, no code)
src/mcp/                    # In-engine copy of session-mgr MCP server
tests/                      # 75 test files
docs/                       # Architecture docs
rules/                      # 34 coding standard definitions
```

Key entry point: `scripts/3-level-flow.py`
Pipeline definition: `scripts/langgraph_engine/orchestrator.py`
Level 3 steps: `scripts/langgraph_engine/level3_execution/`

---

## Development Workflow

1. **Fork the repo** and create a branch: `git checkout -b feature/my-feature` or `fix/issue-123`
2. **Write code** — follow the coding standards below
3. **Write tests** — every new function needs a test
4. **Run the full suite**: `pytest tests/` — must stay at 100% pass rate
5. **Open a PR** against `main`

### Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Bug fix | `fix/<issue>-short-desc` | `fix/211-step10-impl` |
| Feature | `feature/short-desc` | `feature/gcp-provider` |
| Refactor | `refactor/short-desc` | `refactor/state-cleanup` |
| Docs | `docs/short-desc` | `docs/contributing-guide` |

---

## Coding Standards

### Python Style

- Python 3.8+ syntax only
- PEP 8 formatting (use `ruff format` before committing)
- ASCII-only in all `.py` files (Windows cp1252 safe — no Unicode literals)
- Always use `path_resolver.py` for file paths — never hardcode paths
- Lazy imports at function level to avoid import-time side effects

### What We Enforce (ruff)

```bash
ruff check .         # lint
ruff format .        # format
```

The CI runs both. PRs must pass clean with zero ruff errors.

### No `# ruff: noqa: F821`

**Do not add file-level `# ruff: noqa: F821` suppressors.** This has caused multiple production bugs in this repo (see [Known Issues](README.md#known-issues-and-cleanup-history)). If ruff reports F821 on a line that is a genuine false positive (e.g., try/except import pattern), use a targeted inline suppressor on that specific line only:

```python
FlowState = dict  # noqa: F821 -- fallback when langgraph_engine not on path
```

### Cross-Platform Path Rule

```python
# Wrong
path = "/home/user/.claude/memory"

# Right
from utils.path_resolver import get_memory_dir
path = get_memory_dir()
```

---

## Testing

### Requirements

- All new public functions need at least one unit test
- Tests go in `tests/test_<module_name>.py`
- Use `pytest` fixtures — no `unittest.TestCase`
- Do not add `pytest.mark.skip` without a comment explaining why and linking an issue

### Running specific suites

```bash
pytest tests/                                      # all
pytest tests/test_call_graph_builder.py            # specific file
pytest tests/ -k "test_complexity"                 # by keyword
pytest tests/ --cov=langgraph_engine               # with coverage
```

### Test expectations

- New code: aim for 70%+ coverage on the touched module
- The full suite must stay at **100% pass rate** (currently 793/793)
- MCP server tests live in their separate repos — do not add them here

---

## Submitting a Pull Request

### PR Checklist

- [ ] `ruff check .` passes with zero errors
- [ ] `pytest tests/` — 100% pass rate maintained
- [ ] New public functions have tests
- [ ] No `# ruff: noqa: F821` file-level suppressors added
- [ ] No hardcoded file paths — use `path_resolver.py`
- [ ] ASCII-only in `.py` files
- [ ] PR description explains **what** and **why**

### PR Description Template

Use the PR template (`.github/pull_request_template.md`) — it will be pre-filled automatically when you open a PR.

### Review process

- One maintainer review required before merge
- CI must pass (ruff + pytest)
- We aim to review PRs within 3 business days

---

## Issue Reporting

Use the issue templates:
- **Bug report** — for crashes, wrong behavior, test failures
- **Feature request** — for new capabilities or integrations

Please include:
- Python version and OS
- Full error traceback (if applicable)
- Minimal reproduction steps

---

## What NOT to Contribute

To keep the scope focused, we are **not accepting** PRs that:

- Add new LLM providers (the engine uses `claude_cli` + `anthropic` only — Dead LLM provider purge was intentional in v1.15.3)
- Add new pipeline levels without prior issue discussion
- Modify `policies/` files without a linked discussion issue
- Add `# ruff: noqa: F821` file-level suppressors
- Break Windows cp1252 compatibility (no non-ASCII literals in `.py` files)
- Add dependencies to `requirements.txt` without justification (use `requirements-optional.txt` for heavy/conflicting deps)

---

## Questions?

Open a [Discussion](../../discussions) or file an issue with the `question` label.
