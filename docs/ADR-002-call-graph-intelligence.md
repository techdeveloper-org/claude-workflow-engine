# ADR-002: AST-Based Call Graph for Pipeline Intelligence

**Status:** Accepted
**Date:** 2026-03-18
**Deciders:** Pipeline Architecture Team

---

## Context

Before v1.5.0 the pipeline generated implementation plans and code reviews
without any knowledge of the codebase's call structure. This caused cascading
failures in multi-step implementations:

- Step 2 (plan) suggested changes to a utility function without knowing that
  28 other methods called it, leading to breaking changes in unrelated features.
- Step 11 (code review) could not detect orphaned methods or newly introduced
  circular dependencies because it had no pre-change baseline.
- Multi-phase implementations (Phase A writes files, Phase B reviews) used the
  same cached graph snapshot from before Phase A, making Phase B reviews
  unreliable.

The team needed a way to give the LLM real structural context — which methods
call what, which files are hot nodes, and what the blast radius of a proposed
change would be — before generating plans or reviews.

---

## Decision

Build an AST-based call graph from the project source at pipeline start and
inject its analysis at three critical steps:

**Step 2 (Plan):** `analyze_impact_before_change()`
- Returns `risk_level`, `danger_zones`, and `affected_methods`
- The planner knows what could break before suggesting changes
- Complexity score from the call graph boosts the LLM prompt weight for
  high-risk tasks

**Step 10 (Implementation):** `snapshot_call_graph()` + `get_implementation_context()`
- Captures the pre-change graph state as a baseline
- Injects caller/callee awareness so the LLM generates compatible code
- Sets `call_graph_stale = True` after files are written

**Step 11 (Review):** `review_change_impact()`
- Diffs pre-change vs. post-change graph snapshots
- Detects breaking changes, orphaned methods, and new risk paths

The call graph builder (`call_graph_builder.py`) supports four languages:
Python (full AST), Java, TypeScript, and Kotlin (regex-based for the latter
three). The graph contains 578 classes and 3,985 methods across the engine
codebase.

A stale-graph guard (`refresh_call_graph_if_stale` in `call_graph_analyzer.py`)
ensures multi-phase implementations always use a post-write graph for later
phases, not the pre-implementation snapshot.

UML diagrams (13 types) consume the same call graph as a single data source via
adapter functions in `uml_generators.py`, replacing duplicate AST analysis that
previously ran separately for diagram generation.

---

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **LLM-only analysis** (original) | No tooling required | Hallucinated call paths; no real baseline; O(tokens) not O(code) |
| **Static import graph only** | Fast; language-agnostic | Import graph != call graph; misses dynamic dispatch, method-level granularity |
| **Sourcegraph / code intel API** | Accurate; multi-language | Paid; external service; setup overhead; privacy concerns for private repos |
| **tree-sitter** | Accurate AST; all languages | Complex setup; additional C extension dependency |
| **Python `ast` module + regex for others** (chosen) | Zero extra deps; fast; accurate for Python | Regex-based Java/TS/Kotlin is approximate; may miss some dynamic patterns |

Pure AST for Python was chosen because Python is the primary language. Regex
approximations for Java/TypeScript/Kotlin are good enough for impact analysis
(method-level accuracy ~90%) without adding heavy dependencies.

---

## Consequences

**Positive:**
- Step 2 risk assessment prevents 80%+ of cascading failures observed before v1.5.0
  (measured by comparing PR revert rate before and after).
- Step 11 reviews detect orphaned methods automatically — previously this required
  manual code review.
- UML diagrams are always consistent with actual call structure, not LLM-hallucinated
  class diagrams.
- Multi-language support means Java microservice calls are visible to the planner.

**Negative:**
- Initial call graph build adds ~2-5 seconds to pipeline startup for large codebases.
- The stale-graph guard adds one rebuild cycle (~2-3 seconds) after Step 10 writes.
- Regex-based parsers for Java/TypeScript/Kotlin miss anonymous functions and
  lambda callbacks — these show as unresolved edges in the graph.
- The 578-class / 3,985-method graph is held in memory for the duration of the run
  (~8 MB peak); this is acceptable but would need pruning for very large monorepos.

**Risks:**
- If `call_graph_stale` is not set after Step 10 (e.g., due to a node crash), the
  stale guard never fires and Step 11 uses an outdated snapshot silently.
  Mitigation: `FORCE_GRAPH_REBUILD=1` env var bypasses the flag and always rebuilds.
