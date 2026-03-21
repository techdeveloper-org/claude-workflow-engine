# Claude Workflow Engine - Scripts Directory Context

**Project:** Claude Workflow Engine
**Version:** 1.5.0
**Type:** LangGraph Orchestration Pipeline with RAG
**Last Updated:** 2026-03-21

> For full project context, architecture, and development guidelines see the root `CLAUDE.md`.

---

## Scripts Directory Overview

This directory contains the pipeline entry point, hook scripts, and the core `langgraph_engine/` package.

### Key Files

| File | Purpose |
|------|---------|
| `3-level-flow.py` | Main pipeline entry point |
| `pre-tool-enforcer.py` | PreToolUse hook — blocks Write/Edit until Level 1/2 complete |
| `post-tool-tracker.py` | PostToolUse hook — progress tracking, GitHub integration |
| `stop-notifier.py` | Stop hook — voice notification on session end |
| `sync-version.py` | Syncs version from VERSION file to all MCP servers |
| `CHANGELOG.md` | Full project changelog |
| `System_Requirement_Analysis.md` | SRS document |

### langgraph_engine/ Package Structure (v1.5.0)

```
langgraph_engine/
+-- core/           # Cross-cutting: LazyLoader, ErrorHandler, NodeResult, create_step_node
+-- state/          # FlowState, StepKeys, reducers, ToonObject, WorkflowContextOptimizer
+-- routing/        # Routing functions split by pipeline level
+-- helper_nodes/   # Helper node functions split by concern
+-- diagrams/       # Strategy Pattern: DiagramFactory + 13 UML generators
+-- parsers/        # Abstract Factory: ParserRegistry + 4 language parsers
+-- sonarqube/      # Facade: api_client + lightweight + aggregator + auto_fixer
+-- integrations/   # Lifecycle: AbstractIntegration + GitHub/Jira/Figma/Jenkins
+-- pipeline_builder.py  # Builder: PipelineBuilder chainable API
+-- orchestrator.py      # Main StateGraph construction
+-- flow_state.py        # Compat shim -> state/
+-- uml_generators.py    # Compat shim -> diagrams/
+-- call_graph_builder.py # Compat shim -> parsers/
+-- subgraphs/           # Level -1, 1, 2, 3 implementations
```

### Running the Pipeline

```bash
# From project root:
python scripts/3-level-flow.py --task "your task description"

# Hook mode (Steps 0-9 only):
CLAUDE_HOOK_MODE=1 python scripts/3-level-flow.py --task "fix login bug"

# Full mode (all 15 steps):
CLAUDE_HOOK_MODE=0 python scripts/3-level-flow.py --task "add user profile feature"
```

### Testing

```bash
# All tests (from project root):
pytest tests/

# Core modularization tests:
pytest tests/test_call_graph_builder.py tests/test_call_graph_analyzer.py tests/test_cache_system.py

# MCP server tests:
pytest tests/test_*mcp*.py
```

### Adding a New Pipeline Level

```python
# 1. Create subgraph in subgraphs/my_level.py
# 2. Add routing in routing/my_level_routes.py
# 3. Register in pipeline_builder.py:
class PipelineBuilder:
    def add_my_level(self):
        # add nodes + edges
        return self

# 4. Use it:
PipelineBuilder().add_level_minus1().add_level1().add_my_level().build()
```

---

**Last Updated:** 2026-03-21
