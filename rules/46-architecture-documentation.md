---
description: "Level 2.3 - Architecture documentation lifecycle: when to update CLAUDE.md and README.md architecture sections"
priority: high
---

# Architecture Documentation Lifecycle Rule (Level 2.3)

**PURPOSE:** Define what counts as an architectural change, which documentation files must be updated, and what each update must contain. This rule drives Step 13 documentation updates — scripts execute, but this rule decides what triggers an architecture doc update.

---

## 1. Architecture Documents

Two files contain architecture documentation that must be kept current:

| File | Section | Owner |
|------|---------|-------|
| `CLAUDE.md` | `## Architecture & Structure` | Step 13 pipeline |
| `README.md` | `## Architecture` or link to `docs/architecture` | Step 13 pipeline |

Both files are at the project root and are subject to `rules/11-documentation-files.md` governance.

---

## 2. Architectural Change Detection

An architectural change has occurred when the current task introduced ANY of the following:

### 2.1 Structural Changes (always update)

- New top-level package/module added or removed
- New pipeline level (e.g., Level -2, Level 4)
- New integration point (new MCP server, new external API, new database)
- New entry point added (e.g., new `scripts/*.py`, new CLI command)
- Service split or merge (microservice boundary changed)
- New `__init__.py` that creates a new public package surface

### 2.2 Data Flow Changes (update if significant)

- New state fields added to `FlowState` or equivalent
- New routing path in the pipeline graph
- New LLM provider registered
- New queue, topic, or event bus added
- New caching layer introduced

### 2.3 Skip Conditions (do NOT update architecture docs)

- Only existing files were modified (no new files/packages)
- Task type is `fix`, `test`, `chore`
- Change is only in `tests/`, `docs/`, `uml/`, `drawio/`, `rules/`, `policies/`
- A configuration value changed (env var, constant) with no structural impact

---

## 3. CLAUDE.md Update Rules

### 3.1 What to Update

Update the `## Architecture & Structure` section (required section per `rules/11`).

Specifically:

**Pipeline Flow diagram** — update if a new node, step, or level was added:
- Add the new node in the correct position in the ASCII/Mermaid pipeline diagram
- Label it with its version tag if it's a new pipeline step

**Directory Layout tree** — update if new directories or key files were added:
- Add new directories/files in the correct position in the tree
- Mark auto-generated directories with `← auto-generated`

**Key Components table** — update if a new component with its own module was added:
- Add one row: `| Component Name | path/to/file.py | One-line purpose |`

**MCP Servers table** — update only if a new MCP server was added or removed:
- Add/remove the row in the MCP Servers section

### 3.2 What NOT to Update in CLAUDE.md

- `## Latest Execution Insight` — updated by Step 14, not Step 13
- `## Development Guidelines` — only update if setup or test commands changed
- Version numbers in `| **Version** |` header table — updated by VERSION file, not manually
- Any section not directly impacted by the current change

### 3.3 Update Format

```markdown
<!-- Each added entry must end with the version tag where it was introduced -->
| New Component | path/to/new_file.py | Purpose description | [v{X.Y.Z}] |
```

Add a comment block above any changed section:

```markdown
<!-- Updated: {YYYY-MM-DD} | Task: {task_title} | Change: {one-line description} -->
```

---

## 4. README.md Update Rules

### 4.1 What to Update

Update the `## Architecture` section or the architecture link in README.

If the project uses a Mermaid diagram in README:
- Update the diagram to reflect the new structural element
- Add the new node/service in the correct layer

If the project links to `docs/architecture`:
- Update the linked file with the new component description
- Add one bullet point: `- **{Component}** ({path}): {one-line description}`

### 4.2 What NOT to Update in README.md

- `## Installation` / `## Setup` — only if setup steps changed
- `## Usage` — only if a new CLI command or API endpoint was added
- Badge URLs, version shields — these update automatically
- Any section unrelated to architecture

---

## 5. Version Tagging in Architecture Docs

When adding a new architectural element, tag it with the current version:

```markdown
<!-- Introduced in v{MAJOR.MINOR.PATCH} -->
```

Read the current version from `VERSION` file at project root. If `VERSION` does not exist, use `0.0.0`.

---

## 6. Staleness Detection

Architecture docs are considered stale if:
- A new package directory exists in source but is not mentioned in CLAUDE.md `## Architecture & Structure`
- A new `scripts/*.py` entry point exists but is not in the Directory Layout tree
- The MCP server count in CLAUDE.md does not match the actual count of registered servers

When staleness is detected at Step 13, log a `WARNING` with:
```
Architecture docs stale: {file}:{section} missing {element}. Updating now.
```

---

## 7. Separation of Concerns

| Concern | Where defined | Where executed |
|---------|--------------|----------------|
| WHAT triggers an architecture update | This rule (§2) | `documentation_manager.py` reads it |
| WHICH sections to update | This rule (§3, §4) | `documentation_manager.py` reads it |
| HOW to parse and write Markdown | `documentation_manager.py` | Script logic |
| HOW to detect new directories | `documentation_generator.py` | Script logic |
| WHEN Step 13 runs | Pipeline routing | `level3_execution/routing.py` |

---

## 8. What This Rule Replaces

This rule replaces hardcoded logic in:
- `langgraph_engine/level3_execution/documentation_manager.py` → `update_existing_docs()` and `_update_claude_md()` methods
- `langgraph_engine/level3_execution/documentation_generator.py` → CLAUDE.md template architecture section
- `scripts/tools/post-merge-version-updater.py` → architecture section update logic

---

**ENFORCEMENT:** Level 2.3 — ACTIVE at Step 13. Violations logged with `rule=46-architecture-documentation`.
