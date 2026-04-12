# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.16.1] - 2026-04-07

### Changed — Diagram Output Restructure + Configurable Paths

- **`uml/` moved to project root** — previously `docs/uml/`, now at `<target_project>/uml/` (top-level, not nested under docs)
- **`drawio/` moved to project root** — previously `docs/drawio/`, now at `<target_project>/drawio/` (top-level)
- **`UML_OUTPUT_DIR` env var** — overrides the UML output directory; relative paths resolved against target project root, absolute paths used as-is; defaults to `uml/`
- **`DRAWIO_OUTPUT_DIR` env var** — overrides the draw.io output directory; same resolution logic; defaults to `drawio/`
- **`.env.example`** — added `DIAGRAM OUTPUT DIRECTORIES` section documenting both new env vars
- **`rules/11-documentation-files.md`** — exemption list updated: `uml/` and `drawio/` at root are now auto-generated exempt dirs

### Files Updated

| File | Change |
|------|--------|
| `langgraph_engine/diagrams/legacy_generator.py` | `__init__` reads `UML_OUTPUT_DIR`; absolute/relative path logic |
| `langgraph_engine/level3_execution/documentation_manager.py` | `_generate_drawio_diagrams()` reads `DRAWIO_OUTPUT_DIR`; relative path in return values |
| `scripts/architecture/generate_system_diagram.py` | `__main__` block reads `DRAWIO_OUTPUT_DIR` |
| `scripts/tools/create_mcp_repos.py` | Fixed stale `DRAWIO_OUTPUT_DIR` default (`docs/diagrams/` → `drawio/`) |
| `tests/test_uml_generators.py` | Updated test assertions to expect `uml/` not `docs/uml/` |
| `CLAUDE.md`, `README.md`, `rules/11-documentation-files.md` | Directory layout references updated |

### Why

Diagram output directories belong at the target project root alongside source code, not buried inside `docs/`. This matches the convention for auto-generated artifacts. Env var configurability allows different projects to direct output wherever needed (e.g. `diagrams/uml`, `/tmp/preview`, a custom CI artifacts path).

---

## [1.8.0] - 2026-03-28

### Added — Orchestration Template Fast-Path

- **`--orchestration-template=PATH` CLI flag** in `3-level-flow.py` — accepts a pre-filled JSON template that bypasses Steps 0-5 entirely and routes directly to Step 6 (skill validation)
- **`_load_orchestration_template(path)`** — validates required fields (`task_type`, `complexity`, `skill`/`skills`, `agent`/`agents`) and returns parsed dict; raises `ValueError` on malformed input
- **Template fast-path node logic** in `orchestration_pre_analysis_node` — when template is detected, injects all step 0-5 FlowState fields and returns early (before call graph scan)
- **`template_fast_path` routing** in `route_pre_analysis` — two-way priority routing: Template (→ `level3_step6`) > miss (→ `level3_step0_0`)
- **`orchestration_template` and `template_fast_path` FlowState fields** in `state_definition.py`
- **`level3_step6` conditional edge** added to `orchestrator.py` pre-analysis routing map
- **`orchestration_template.example.json`** — fully annotated example template with all supported fields
- **README: Orchestration Template Fast-Path section** — full explanation with before/after comparison, decision tree, field reference, and fail-safe behavior
- **README: Pre-Analysis Decision Tree updated** — now shows two-priority routing with Template as highest priority

### Performance Impact

| Metric | Before (full pipeline) | After (template fast-path) |
|--------|----------------------|---------------------------|
| LLM calls (hook mode) | 7-8 calls | **1 call** (Step 10 only) |
| Hook mode latency | ~60 seconds | **~15 seconds** |
| LLM cost reduction | baseline | **~87% reduction** |
| Pipeline determinism | LLM-dependent | **Fully deterministic** (Steps 0-5) |

### Changed

- `route_pre_analysis` — extended from 1-way to 2-way routing (template > normal)
- `orchestrator.py` conditional edges map — added `"level3_step6"` target
- `README.md` — "How the Engine Reduces LLM Calls" table updated with Template Fast-Path as new top entry
- `README.md` — Running the Pipeline section updated with `--orchestration-template` usage

### Fail-Safe Design

Template fast-path is fail-open: any error (file not found, invalid JSON, missing fields, runtime exception) logs a warning and falls through to the normal pipeline. No pipeline interruption.

---

## [1.5.0] - 2026-03-21

### Added — Modular Architecture (9 New Packages)

- `core/` — Cross-cutting abstractions: LazyLoader, get_logger, node_error_handler, safe_execute, NodeResult, create_integration_hook, get_infra, create_step_node, StepExecutionContext
- `state/` — FlowState split into 6 modules: state_definition, step_keys, reducers, toon_format, context_optimizer, __init__
- `routing/` — All 7 routing functions extracted from orchestrator.py, split by pipeline level
- `helper_nodes/` — 11 helper node functions split by concern (context, output, step, standards, level_minus1)
- `diagrams/` — Strategy Pattern: DiagramFactory + 13 AbstractDiagramGenerator subclasses (class, sequence, activity, state, component, package, usecase, object, deployment, communication, composite, interaction + AST analyzer + Kroki renderer)
- `parsers/` — Abstract Factory: ParserRegistry + 4 language parsers (PythonASTParser, JavaRegexParser, TypeScriptRegexParser, KotlinRegexParser)
- `sonarqube/` — Facade: SonarQubeScanner + api_client, lightweight_scanner, result_aggregator, auto_fixer, config
- `integrations/` — Abstract Factory + Template Method: IntegrationRegistry + AbstractIntegration (Create/Update/Close lifecycle) + GitHub, Jira, Figma, Jenkins concrete adapters
- `pipeline_builder.py` — Builder Pattern: PipelineBuilder with chainable add_level_minus1(), add_level1(), add_level2(), add_level3(), build() + create_flow_graph() convenience function

### Changed

- `flow_state.py` — Reduced to 27-line backward-compat shim (re-exports from `state/`)
- `uml_generators.py` — Backward-compat note added; DiagramFactory is new entry point
- `call_graph_builder.py` — Backward-compat note added; ParserRegistry is new entry point
- VERSION bumped: 1.4.1 → 1.5.0
- Total Python files: 295+ → 360+ (65 new files in 9 packages)
- LangGraph Engine modules: 92 → 155+
- SRS (`scripts/System_Requirement_Analysis.md`) — Complete rewrite with proper project content

### Design Patterns Applied

- Factory Method — create_integration_hook, create_step_node, PipelineBuilder.add_level*
- Abstract Factory — ParserRegistry (4 languages), IntegrationRegistry (4 services)
- Strategy — DiagramFactory (13 diagram types, swappable at runtime)
- Decorator — node_error_handler, safe_execute
- Builder — NodeResult fluent builder, PipelineBuilder chain
- Facade — SonarQubeScanner (api + lightweight + aggregator unified)
- Template Method — AbstractIntegration lifecycle (create/on_branch/update/on_review/close)
- Registry (DSA) — DiagramFactory, ParserRegistry, IntegrationRegistry hash maps

### Tests

- 1,608 tests passing (133 core modularization tests verified)

---

## [1.4.1] - 2026-03-18

### Added

- Step 10 transitions and updates for Jira + Figma workflows
- Figma MCP server + design-to-code pipeline integration
- CLI interface, setup wizard, and getting started guide

### Changed

- Full integration lifecycle (Create → Update → Close) for Jira and Figma

---

## [1.4.0] - 2026-03-15

### Added

- Jira integration (dual GitHub+Jira issue tracking, Steps 8/9/11/12)
- Jenkins CI/CD integration (Steps 10/11)
- SonarQube scanner with auto-fix loop
- Quality gate enforcement (4 gates)
- Unit test auto-generation (4 languages)
- Integration test generation (CallGraph call-path based)
- Coverage analyzer (AST-based, risk-prioritized)

---

## [1.3.0] - 2026-03-10

### Added

- Call graph v2.0 (class-level FQN, 578 classes, 3,985 methods, 4 languages)
- UML generators (13 diagram types, CallGraph-powered)
- Metrics aggregator + dashboard

---

## [1.0.0] - 2026-03-01

### Added

- 4-Level pipeline architecture (Level -1, 1, 2, 3)
- 15-step SDLC automation
- 19 MCP servers (323 tools)
- GitHub integration (issue, branch, PR, merge, review)
- Policy system (63 policies)
- Hook system (UserPromptSubmit, PreToolUse, PostToolUse, Stop)
- Hybrid LLM inference (4 providers)
- Session management + TOON compression

---

[1.5.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.0.0...v1.3.0
[1.0.0]: https://github.com/techdeveloper-org/claude-workflow-engine/releases/tag/v1.0.0
