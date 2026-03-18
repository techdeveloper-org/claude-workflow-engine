# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [7.6.0] - 2026-03-18

### Added
- Call graph analyzer module (call_graph_analyzer.py) with 4 pipeline-ready functions
- 13th UML diagram type: Call Graph Diagram (method-to-method with class grouping)
- CallGraph-driven Step 2: pre-change impact analysis with risk assessment
- CallGraph-driven Step 10: implementation context + pre-change snapshot
- CallGraph-driven Step 11: post-change diff with breaking change detection
- Class-aware sequence diagrams with FQN participant mapping
- 9 new flow_state fields for CallGraph pipeline data
- 50 new tests (20 analyzer + 30 UML integration)

### Changed
- UML generators now use CallGraph as single data source (unified from duplicate AST)
- generate_all() produces all 13 diagram types (was 7-8)
- Step 13 documentation refresh now includes 5 diagrams (was 3)
- uml-diagram MCP server expanded to 15 tools (was 14)

### Architecture
- call_graph_builder.py: AST NodeVisitor with class stack, FQN edges, call paths, impact map
- call_graph_analyzer.py: Pipeline integration layer (impact, context, review, snapshot)
- uml_generators.py: CallGraph adapters (_classes_from_call_graph, _dep_graph_from_call_graph, _call_chains_from_call_graph)
- level3_execution_v2.py: Steps 2/10/11 now graph-aware

---

## [Unreleased]

### Added
- Custom exception hierarchy (`WorkflowEngineError` and subclasses)
- Structured MCP error responses (`mcp_errors.py`)
- Architecture module smoke tests
- Corrupted session recovery (`safe_load_session`)
- Orchestration timeout (300s) in 3-level-flow.py
- Environment validation on startup

### Changed
- Pinned critical dependency versions in requirements.txt
- Migrated MCP servers to path_resolver (5 servers)
- Cleaned .env.example (removed Flask/dashboard references)

### Fixed
- 5 broken test files (path issues, removed imports, missing functions)
- 9 bare `except:` blocks replaced with specific exception types
- Hardcoded .env path commented out

### Removed
- Backup files (3-level-flow.py.backup, 3-level-flow.py.backup.v4)

---

## [7.4.0] - 2026-03-16

### Added
- Dynamic versioning via `sync-version.py`
- SRS document complete rewrite
- MCP health check tool in enforcement server
- Auto-doc generator (`generate-mcp-docs.py`)

### Changed
- Hook scripts migrated from subprocess to MCP direct imports (6 calls eliminated)
- Updated README.md and CLAUDE.md with full MCP server tables
- Dead code removed (enforcement_server.py)

---

## [7.3.0] - 2026-03-16

### Added
- 10 FastMCP servers (91 tools, 7,235 LOC) replacing 24+ scattered scripts
- Session hooks bridge (`session_hooks.py`) for direct Python imports
- Auto-save hook integration with session MCP
- Token optimization MCP server (custom, 6th server)
- Pre-tool gate + post-tool tracker MCP servers (7th & 8th)
- Standards-loader MCP server (9th) + LLM enhanced (4->8 tools)
- Skill-manager MCP server (10th) + GitHub enhanced (7->12 tools)

### Changed
- 476 tests ALL PASSING across 11 test files
- Dynamic skill/agent filtering (zero hardcoded lists)

---

## [7.2.0] - 2026-03-15

### Added
- 7 design patterns implemented (Builder, Decorator, Registry, Memoize, Facade, Strategy, StepKeys)
- Strategy pattern for LLM providers (interface + 3 implementations)
- Anthropic API as 4th LLM provider (direct Claude API)

### Changed
- Smart pre-filter skills/agents by project type before LLM call
- Voice mode now configurable (disabled by default)
- Debounced auto-ship (60s idle + clean tree)

---

## [7.0.0] - 2026-03-14

### Added
- Ollama health check at import
- LLM-powered commit messages
- Shared `generate_llm_commit_title` utility

### Changed
- Major performance optimizations
- StepKeys constants, Facade migration, git optimization, N+1 fix

---

## [5.0.0] - 2026-03-14

### Added
- LangGraph 3-level orchestration pipeline
- Session management with checkpointing
- 15-step execution system (Step 0-14) (WORKFLOW.md compliant)
- GitHub integration (issue, PR, merge cycle)

### Removed
- Entire Flask monitoring dashboard (~350+ files, 88K+ lines)
- Repository now contains ONLY the workflow engine

---

## [0.1.0] - 2026-03-01

### Added
- Initial project setup
- Core infrastructure
- Basic documentation

---

[Unreleased]: https://github.com/techdeveloper-org/claude-insight/compare/v7.4.0...HEAD
[7.4.0]: https://github.com/techdeveloper-org/claude-insight/compare/v7.3.0...v7.4.0
[7.3.0]: https://github.com/techdeveloper-org/claude-insight/compare/v7.2.0...v7.3.0
[7.2.0]: https://github.com/techdeveloper-org/claude-insight/compare/v7.0.0...v7.2.0
[7.0.0]: https://github.com/techdeveloper-org/claude-insight/compare/v5.0.0...v7.0.0
[5.0.0]: https://github.com/techdeveloper-org/claude-insight/compare/v0.1.0...v5.0.0
[0.1.0]: https://github.com/techdeveloper-org/claude-insight/releases/tag/v0.1.0
