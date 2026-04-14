# ADR-005: No LLM Calls in the Verifier Hot Path

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Pipeline Architecture Team

---

## Context

Runtime Verification (RV), introduced in v1.18.0, wraps every active pipeline
node with a decorator that evaluates preconditions, postconditions, and
invariants against `FlowState`. Because the decorator runs on every node call
and on every level transition, its per-call overhead compounds across the
~15 active nodes in a typical pipeline run.

During design discussions, one tempting idea was to let contracts include
**semantic checks powered by an LLM** — e.g.:

- "Assert that `orchestration_prompt` is coherent with `task_description`."
- "Classify whether `pre_analysis_result.risk_level` is consistent with the
  changes the plan proposes."
- "Verify that the implementation plan produced by Step 0 is actionable."

Such checks would be powerful, but each one requires an LLM round trip (1-10
seconds for Claude, ~0.5-2 seconds for smaller models), introduces network
failure modes, and consumes budget on every pipeline run.

The design question was: **should the verifier be allowed to make LLM calls
inside contract evaluation, or should it be restricted to pure in-memory
predicates?**

---

## Decision

**The verifier MUST NOT call any LLM, make any network request, perform any
disk I/O, or spawn any subprocess.** This is an architectural constraint,
enforced by:

1. **No LLM client imports** in the `runtime_verification/` package. The
   package has zero dependencies on `anthropic`, `langchain`,
   `llm_inference`, `claude_cli_subprocess`, or any client module.
2. **No file I/O** in the verifier, its decorators, or its spec evaluation.
3. **No network libraries** (`requests`, `httpx`, `urllib`) imported
   anywhere in the package.
4. **No subprocess spawns** — `subprocess`, `os.system`, `multiprocessing`
   are banned.
5. **A latency contract** of ≤ 5 ms per `verify_node` invocation (including
   pre + execute + post phases). Violations are logged as warnings and
   surfaced via Prometheus metrics.
6. **Spec evaluation is pure**: `isinstance`, comparison operators, `in`
   checks, `len()`, and user-supplied `custom_check` callables. Custom
   checks inherit the same no-I/O contract by convention and are reviewed
   as code, not data.

The concrete latency targets are:

| Contract shape | Typical overhead | Worst-case |
|----------------|------------------|------------|
| 3 pre + 2 post + 1 invariant | 0.3 – 0.8 ms | 1.5 ms |
| 10 pre + 10 post + 5 invariants | 1.0 – 2.0 ms | 3.0 ms |
| Latency budget (hard warning threshold) | — | 5.0 ms |

When the budget is exceeded, `RuntimeVerifier.record_latency()` logs a
warning and increments a Prometheus counter; it does NOT fail the pipeline.

Semantic checks that genuinely require an LLM (for example: "does this
orchestration plan make sense?") are **out of scope** for the verifier.
They belong in a separate quality-review stage (e.g., a dedicated
reviewer agent invoked asynchronously, or the existing Step 11 code
review), not inside the hot path of node execution.

---

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Allow LLM calls inside `custom_check`** | Maximum expressive power; semantic checks possible | Unbounded latency (1-10s per check); network failures; LLM cost per pipeline run; destroys the <5ms contract; makes RV indistinguishable from Step 11 review |
| **Allow LLM calls with a timeout** (e.g., 500 ms) | Bounded worst case | Still adds network dependency; still adds cost; 500 ms per check × 10 nodes = 5s of overhead; adds async complexity to a synchronous decorator |
| **Allow LLM calls only in an async "post-run" phase** | No hot-path impact | Duplicates functionality with Step 11; requires new state persistence; blurs the line between verification and review |
| **Pure in-memory predicates only** (chosen) | Deterministic; zero latency impact; zero cost; zero network failure modes; <5ms achievable | No semantic checks; purely structural validation |
| **Hybrid: pure fast-path + async slow-path** | Best of both worlds in theory | Massive complexity increase; two verification stages to reason about; unclear which violations fail which gate |

The pure in-memory approach was chosen because the verifier's role is
**structural invariant enforcement**, not semantic quality review. These are
different problems with different latency, cost, and determinism requirements.
Conflating them produces a verifier that is expensive, slow, and still
requires a separate fast-path — worse than either option alone.

---

## Consequences

**Positive:**
- The verifier has a deterministic, measurable latency contract that fits
  inside any pipeline step without perceptible overhead.
- Zero network dependencies — RV cannot fail due to API outage, timeout, or
  rate limiting. It always runs locally with the same code.
- Zero cost per pipeline run. RV adds no LLM spend to the project budget.
- Simple failure modes: a verifier bug can only raise Python exceptions, and
  these are caught and logged. There is no "flaky network retry" loop.
- Contract authors cannot accidentally create performance cliffs. The spec
  language is small enough that every check's cost is obvious on
  inspection.
- Unit testing is trivial — no network mocks, no LLM stubs, no async.
- Compatible with air-gapped / offline environments.

**Negative:**
- Semantic checks are impossible. "Is this prompt coherent?" cannot be
  expressed as a contract. These checks must live elsewhere (Step 11, or
  a dedicated reviewer agent).
- Contract authors must express intent through structural predicates
  (`field_name`, `type`, `min_val`, `max_val`, `allowed_values`,
  `custom_check`). Some real bugs escape structural checks — e.g., a
  non-empty but garbage `orchestration_prompt`.
- `custom_check` callables are the only escape hatch for domain-specific
  logic. They are Python code and can technically call out to network
  services, violating the contract. This is a policy boundary, not a
  technical enforcement — code review must catch violations.

**Risks:**
- An engineer may add a `custom_check` that calls an LLM for convenience.
  Mitigation: code review rule; unit test that imports the
  `runtime_verification` package with a module-level patch that raises on
  any `requests` / `httpx` / `anthropic` import; documented ban in
  `runtime_verification/__init__.py` docstring.
- Users may expect the verifier to catch semantic bugs (e.g., "my prompt
  is garbage") and be disappointed when it only catches structural ones.
  Mitigation: clear documentation on what RV is and is not; pointer to
  Step 11 review for semantic quality.
- The <5ms contract may be violated by a slow `custom_check` callable.
  Mitigation: per-node latency warning logged when the 5 ms budget is
  exceeded; Prometheus counter; architect review on any contract with
  more than 15 specs.
