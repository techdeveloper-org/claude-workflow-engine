# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.19.0] - 2026-04-15

### Added — CI & Distribution

- **GitHub Actions CI** (`.github/workflows/ci.yml`) — auto-triggers on push/PR to `main`; paths-ignore for docs/uml/drawio/md; Python 3.9 + 3.11 matrix; `concurrency: cancel-in-progress`
- **Hard CI gates** — `secrets_check.py` exit-1 gate runs first; unit tests and integration tests are mandatory (no `continue-on-error`)
- **32 offline integration tests** (`tests/integration/`) — uses `responses` mock library; covers full GitHub PR lifecycle (issue → branch → PR → merge → close); runs in ~0.3s, no GitHub token required
- **PyPI packaging** — `pyproject.toml` (hatchling, PEP 621), `MANIFEST.in` (includes policies/, rules/, templates/), `requirements-dev.txt` (responses, pytest-cov, ruff)
- **PyPI publish workflow** (`.github/workflows/publish.yml`) — fires automatically on GitHub Release; `pip install claude-workflow-engine`
- **`langgraph_engine/__init__.py`** — `__version__ = "1.19.0"` added; importable package version
- **`sync-version.py` extended** — now keeps `__version__` in `langgraph_engine/__init__.py` in sync on version bumps

### Files Added

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Auto-CI on push/PR to main |
| `.github/workflows/publish.yml` | PyPI publish on GitHub Release |
| `pyproject.toml` | Package metadata (hatchling, PEP 621) |
| `MANIFEST.in` | sdist asset inclusion (policies/, rules/, templates/) |
| `requirements-dev.txt` | Dev deps: responses, pytest-cov, ruff |
| `tests/integration/conftest.py` | Mock GitHub API fixtures (responses library) |
| `tests/integration/test_github_integration.py` | 27 offline endpoint tests |
| `tests/integration/test_github_pr_workflow.py` | 5 lifecycle tests (issue→PR→close) |
| `langgraph_engine/__init__.py` | `__version__ = "1.19.0"` |
| `scripts/tools/sync-version.py` | Extended to sync `__version__` on bumps |

---

## [1.18.0] - 2026-04-14

### Added — Runtime Verification
- Runtime Verification package (`langgraph_engine/runtime_verification/`)
- `NodeContract` DSL: `PreconditionSpec`, `PostconditionSpec`, `InvariantSpec`, `Violation`, `NodeContract` dataclasses
- `RuntimeVerifier` + `NullVerifier` -- Registry + Null Object + Singleton patterns; <5ms per-node overhead
- `@verify_node(contract)` decorator -- non-invasive wrapping, zero overhead when `ENABLE_RUNTIME_VERIFICATION=0`
- Level transition guards for 4 pipeline boundaries (`level_minus1->level1`, `level1->level3`, `pre_analysis->step0`, `step0->step8`)
- `schema_verifier`: `verify_orchestration_prompt()`, `verify_orchestrator_result()` for LLM output validation
- `VerificationReport` dataclass with `to_dict()` for JSON-serialisable FlowState storage
- `QualityGate` Gate 5: `verification_gate` -- non-strict by default, halts on `STRICT_RUNTIME_VERIFICATION=1`
- `FlowState` keys: `verification_report: Optional[Dict]`, `verification_violations: List[str]`
- Env vars: `ENABLE_RUNTIME_VERIFICATION=0`, `STRICT_RUNTIME_VERIFICATION=0`, `VERIFICATION_LOG_LEVEL=WARNING`
- **34 unit tests** — `test_runtime_verifier` (15), `test_level_transition_guards` (8), `test_schema_verifier` (7), `test_quality_gate_verification` (4)
- **E2E tests** — `tests/e2e/test_hook_mode_runtime_verification.py` (11 tests, Hook Mode), `tests/e2e/test_full_mode_runtime_verification.py` (9 tests, Full Mode)
- **7 integration tests** — `tests/integration/test_runtime_verification_integration.py`

### Added — Observability Exposure
- **`/health` endpoint** — `verification` snapshot block added: `enabled`, `total_violations`, `critical_violations`, `last_run_ms`
- **Prometheus counter** — `verification_violations_total` (9th metric); labels: `level`, `node`; incremented on every violation
- **OpenTelemetry spans** — `runtime_verification.verify_node` span wraps every `@verify_node` call; 4 attributes: `node.name`, `contract.name`, `violations.count`, `violations.critical`

### Architecture
- ADR-003: Decorator pattern over node subclassing
- ADR-004: Opt-in default (`ENABLE_RUNTIME_VERIFICATION=0`)
- ADR-005: No LLM/network/I/O calls in verifier (enforces <5ms latency contract)

---

## [1.17.0] - 2026-04-10

### Added — Open Source Readiness

- **Community files** — `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, issue templates, PR template
- **GitHub Discussions enabled** — feature requests, integration questions, workflow sharing, Q&A
- **All 13 MCP server repos made public** under [techdeveloper-org](https://github.com/orgs/techdeveloper-org/repositories)
- **README rewrite** — full open-source-grade documentation (architecture, benchmarks, MCP table, community section)

### Fixed — F821 Undefined-Name Audit (issues #212–#216)

- `hooks/stop_notifier/` — 30 F821 errors fixed; missing imports restored (#212)
- `langgraph_engine/level3_execution/nodes/` — 17 F821 errors fixed (#213)
- `langgraph_engine/diagrams/drawio/converter.py` — ~80 F821 errors fixed; `S_*` constants + logger imported (#214)
- `scripts/github_pr_workflow/` — 12 F821 errors fixed; missing `git_ops` imports restored (#215)
- 4 files — stale `# ruff: noqa: F821` suppressors removed after fixes (#216)

### Changed

- `ruff check .` — passes clean with zero suppressors across all fixed files

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

[1.19.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.18.0...v1.19.0
[1.18.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.17.0...v1.18.0
[1.17.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.16.1...v1.17.0
[1.16.1]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.8.0...v1.16.1
[1.8.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.5.0...v1.8.0
[1.5.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/techdeveloper-org/claude-workflow-engine/compare/v1.0.0...v1.3.0
[1.0.0]: https://github.com/techdeveloper-org/claude-workflow-engine/releases/tag/v1.0.0
