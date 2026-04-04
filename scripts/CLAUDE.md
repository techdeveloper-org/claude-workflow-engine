# Claude Workflow Engine - Scripts Directory Context

**Project:** Claude Workflow Engine
**Version:** 1.14.0
**Type:** LangGraph Orchestration Pipeline with RAG
**Last Updated:** 2026-04-04

> For full project context, architecture, and development guidelines see the root `CLAUDE.md`.

---

## Scripts Directory Overview

This directory contains the pipeline entry point, hook scripts, and the core `langgraph_engine/` package.

### Key Files

| File | Purpose |
|------|---------|
| `3-level-flow.py` | Main pipeline entry point |
| `pre-tool-enforcer.py` | PreToolUse hook entry point (shim -> pre_tool_enforcer/) |
| `post-tool-tracker.py` | PostToolUse hook entry point (shim -> post_tool_tracker/) |
| `stop-notifier.py` | Stop hook entry point (shim -> stop_notifier/) |
| `ide_paths.py` | Path constants — imported by hook packages as bare module |
| `project_session.py` | Session utilities — imported by hook packages as bare module |
| `policy_tracking_helper.py` | Policy tracking — imported by hook packages as bare module |
| `setup/` | One-time environment setup scripts (setup_wizard.py, install-auto-hooks.sh, etc.) |
| `bin/` | Windows .bat operational launchers |
| `tools/` | Developer utilities: sync-version.py, release.py, metrics-emitter.py, voice-notifier.py, etc. |
| `/CHANGELOG.md` | Full project changelog (root) |
| `/SRS.md` | System Requirements Specification (root) |

### langgraph_engine/ Package Structure (v1.14.0)

```
langgraph_engine/
+-- core/           # Cross-cutting: LazyLoader, ErrorHandler, NodeResult, create_step_node
+-- state/          # FlowState, StepKeys, reducers, ToonObject, WorkflowContextOptimizer
+-- routing/        # Routing functions split by pipeline level
+-- helper_nodes/   # Helper node functions split by concern
+-- diagrams/       # Strategy Pattern: DiagramFactory + 13 UML generators
+-- parsers/        # Abstract Factory: ParserRegistry + 4 language parsers
+-- integrations/   # Lifecycle: AbstractIntegration + GitHub/Jira/Figma/Jenkins
+-- pipeline_builder.py  # Builder: PipelineBuilder chainable API
+-- orchestrator.py      # Main StateGraph construction
+-- flow_state.py        # Compat shim -> state/
+-- uml_generators.py    # Compat shim -> diagrams/
+-- call_graph_builder.py # Compat shim -> parsers/
+-- level_minus1/        # Level -1 package (policies/)
+-- level1_sync/         # Level 1 package (3 modules + policies/ + architecture/)
+-- level2_standards/    # Level 2 package (2 modules + policies/ + architecture/)
+-- level3_execution/    # Level 3 package (subgraph.py + nodes/ + sonarqube/ + policies/ + architecture/)
|   +-- subgraph.py      # v2 subgraph builder (canonical entry point)
|   +-- nodes/           # v2 step wrapper nodes (orchestration, pre_nodes, step_wrappers_*)
+-- [60+ shared modules] # Cross-level utilities (LLM, caching, metrics, git, etc.)
```

### Running the Pipeline

```bash
# From project root:
python scripts/3-level-flow.py --task "your task description"

# Hook mode (Pre-0, Step 0, Steps 8-9 only):
CLAUDE_HOOK_MODE=1 python scripts/3-level-flow.py --task "fix login bug"

# Full mode (Pre-0, Step 0, Steps 8-14):
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
# 1. Create level package in langgraph_engine/my_level/
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

**Last Updated:** 2026-04-04
