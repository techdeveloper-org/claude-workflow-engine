# ADR-003: Decorator Pattern for Runtime Verification

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Pipeline Architecture Team

---

## Context

Before v1.18.0 the LangGraph pipeline had no structured way to assert that a
node's inputs and outputs matched the contract its downstream consumers
expected. Failures manifested as attribute errors, None propagation, or silent
empty-string outputs several steps downstream from the actual broken node —
typically in Step 11 code review or Step 13 documentation where the root cause
was Step 0 producing a truncated `orchestration_prompt`.

The v1.18.0 Runtime Verification feature introduces an explicit contract layer
(preconditions, postconditions, invariants) enforced against each node. The
design question was: **how do we attach these checks to existing nodes without
rewriting any of them?**

The non-negotiable constraint from the project owner:

> This feature MUST NOT rewrite any existing node function. The verifier is
> purely additive: existing pipeline behavior is unchanged when
> `ENABLE_RUNTIME_VERIFICATION=0`.

The pipeline has ~15 active nodes across Level -1, Level 1, and Level 3. Each
node is a pure function `(state: FlowState) -> dict`. Nodes are registered with
the LangGraph `StateGraph` object in `pipeline_builder.py` via `add_node()`
calls. Some nodes are already wrapped by `core/step_decorator.py`
(`@create_step_node`) for logging and error handling.

---

## Decision

Use the **Decorator Pattern** to attach verification to nodes. A new decorator
`@verify_node(node_name)` in
`langgraph_engine/runtime_verification/decorators.py` wraps a node callable
and produces a thin wrapper that:

1. Looks up the `NodeContract` by `node_name` in the contract registry.
2. Evaluates preconditions against the input state.
3. Delegates to the original node function unchanged.
4. Evaluates postconditions and invariants against the return value.
5. Appends any violations to `state['verification_violations']`.
6. Returns the original return value unchanged.

The decorator is composable with existing decorators (e.g.,
`@create_step_node`) — the outermost decorator runs first. Application happens
in one of two places:

- **Import-time wrap** for nodes whose definition lives alongside the
  contract import.
- **Build-time wrap** inside `PipelineBuilder.add_level*()` methods, where the
  builder wraps the node with `verify_node(name)` before calling
  `graph.add_node(name, wrapped)`.

When `ENABLE_RUNTIME_VERIFICATION=0` (the default), the decorator short-circuits
and returns the **original function reference** — not a wrapper. This gives
zero runtime overhead when the feature is off.

---

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Subclassing nodes** (turn each node into a `VerifiedNode` class with `pre()`, `run()`, `post()` hooks) | OO-pure; easy to read per-class | Requires rewriting every node from function to class — violates the "no rewrite" constraint; doubles LOC; disrupts LangGraph's expected `(state) -> dict` signature |
| **Aspect-oriented programming (AOP) via `wrapt` / `functools`** | Can intercept arbitrary callables at the module level | Adds `wrapt` dependency; more magic than a plain decorator; harder for engineers to reason about; test mocking is less obvious |
| **Middleware in LangGraph** (use LangGraph's own callback hooks if they exist) | Leverages framework; no decorator needed | LangGraph 0.2.x does not expose per-node callbacks in a stable API; future versions may change; risk of framework coupling |
| **Modify `create_step_node` in-place** to call the verifier | Reuses existing wrapping layer; only one decorator stack | `create_step_node` is used by most but not all nodes; modifying it changes its semantics for every caller; mixes concerns (logging + error handling + verification) |
| **Standalone "verify" utility called inside each node body** | Simple, no decorator magic | Requires editing every node function — directly violates the "no rewrite" constraint |
| **Decorator pattern** (chosen) | No node changes; composable with existing decorators; zero overhead when disabled; familiar to all Python engineers; easy to unit test in isolation | One more layer in the call stack; requires discipline to register contracts in one place |

The decorator pattern was chosen because it is the only option that satisfies
the "no rewrite" constraint while also remaining framework-agnostic and
zero-overhead when disabled.

---

## Consequences

**Positive:**
- Zero modification to existing node functions. All 15 active nodes ship
  unchanged into v1.18.0.
- Zero overhead in the default (disabled) mode: the decorator returns the
  original function reference, so there is no wrapper on the call stack.
- Verification logic is isolated in one package
  (`runtime_verification/`) — easy to audit, easy to remove if rolled back.
- Decorators compose naturally with existing `@create_step_node` and any
  future wrapping layers.
- Unit tests for nodes remain unchanged; verification can be tested
  independently by unit-testing the decorator against a fake node.
- The decorator is a well-known, widely-understood Python pattern — no new
  vocabulary for the team to learn.

**Negative:**
- Adds one layer to the call stack when enabled — stack traces during
  verification failures are one frame deeper.
- Contracts and node definitions live in different files; drift is possible
  if a node signature changes without updating the contract. Mitigation:
  code-review rule requires contract update alongside node change.
- Decorator-based checks are post-hoc — they cannot short-circuit a node
  before it executes. (Preconditions still run first, but they log
  violations; they do not prevent the node from running. This is intentional
  to preserve the "no behavior change" guarantee.)

**Risks:**
- An engineer might forget to apply `@verify_node` to a new node. Mitigation:
  `pipeline_builder.py` centralises node registration — a linter rule can
  enforce that every `add_node()` call is preceded by a `verify_node()` wrap.
- The decorator uses shallow `dict(state)` copy for the post-state snapshot;
  deeply nested mutations within a node that modifies-in-place would be
  missed. Mitigation: documented constraint that nodes return new dicts, not
  mutated inputs — already the de facto convention in the pipeline.
