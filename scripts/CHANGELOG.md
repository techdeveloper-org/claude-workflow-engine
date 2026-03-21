# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
- RAG integration (Qdrant, 4 collections, step-specific thresholds)
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
