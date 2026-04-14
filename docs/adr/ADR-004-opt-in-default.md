# ADR-004: Opt-in Default for Runtime Verification

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Pipeline Architecture Team

---

## Context

Runtime Verification (RV), introduced in v1.18.0, adds contract checks
(preconditions, postconditions, invariants, transition guards) to every active
pipeline node. The feature has real value — it catches bad state early and
produces structured violation reports — but it also introduces new execution
paths, new state fields, and new failure modes that have never run in
production.

The design question for rollout was: **should RV be enabled by default in
v1.18.0, or should it ship disabled and be activated explicitly by operators?**

Context factors:

- The pipeline has been stable since v1.12.0 (~6 months of production use).
- The pipeline runs inside a Claude Code hook environment where silent
  degradation is acceptable but pipeline halt is not — a crashed verifier
  must never prevent user work from progressing.
- RV adds two new FlowState fields (`verification_violations`,
  `verification_report`) that did not exist before.
- Contracts for v1.18.0 are hand-written by the architect and cover all 15
  active nodes. They have not been empirically validated against real
  production runs.
- Some contracts will be wrong on first release — either too strict
  (false positives that would fail healthy runs) or too loose (missing real
  issues). This is unavoidable for a first release.
- Hook mode (`CLAUDE_HOOK_MODE=1`) is the default execution mode for most
  users; any regression would affect every user immediately.

---

## Decision

Ship v1.18.0 with Runtime Verification **disabled by default**. Two
environment variables control the feature:

| Variable | Default | Effect |
|----------|---------|--------|
| `ENABLE_RUNTIME_VERIFICATION` | `0` | RV is completely inert. Decorator returns the original function. No new code paths execute. FlowState fields remain unset. Gate 5 is a no-op. |
| `STRICT_RUNTIME_VERIFICATION` | `0` | Only meaningful when `ENABLE=1`. When `STRICT=0`, violations log warnings but never fail the pipeline. When `STRICT=1`, Gate 5 raises `QualityGateError` on any error-severity violation. |

The rollout ladder is explicit:

1. **v1.18.0 ship (default):** `ENABLE=0, STRICT=0`. Zero user impact.
2. **v1.18.0 shadow mode:** early adopters set `ENABLE=1, STRICT=0` manually.
   Contracts are exercised; violations are logged but never fail builds.
3. **v1.18.1 CI shadow:** CI pipelines set `ENABLE=1, STRICT=0`. Contracts
   are refined based on real violation data.
4. **v1.19.0 strict opt-in:** engineers may set `ENABLE=1, STRICT=1` on
   development branches for aggressive early-detection.
5. **v1.20.0 CI strict:** CI pipelines default to `ENABLE=1, STRICT=1` once
   violation rate stabilises near zero on healthy runs.

At no point in this ladder does the end-user hook-mode default change. Users
who never set the env vars continue to run v1.17.x-identical pipelines.

---

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **On by default, non-strict** (`ENABLE=1, STRICT=0`) | Collects violation data from day one; operators see immediate visibility | Every user gets new code paths and new state fields on first run — hidden regression risk; any contract bug affects all users |
| **On by default, strict** (`ENABLE=1, STRICT=1`) | Maximum early-detection value | Guaranteed to fail healthy builds on day one due to contract bugs; pipeline halt in hook mode would break user workflows |
| **Off by default, env-var toggle** (chosen) | Zero default-path regression; operators opt in when ready; rollout is staged | Slower feedback; no data from the majority of users until they opt in |
| **Config-file flag instead of env var** | Persistent setting, visible in repo | Requires a config-file change to toggle; env var is more ergonomic for CI and local testing |
| **Feature flag service** (e.g., LaunchDarkly) | Dynamic rollout, per-user toggles | Adds external dependency; overkill for a single on/off flag |
| **Separate binary / separate entry point** | Full isolation from main pipeline | Doubles surface area; confuses users about which entry point to run |

The opt-in default was chosen because the pipeline's current stability is a
hard-won asset; the cost of regressing it on a speculative new feature outweighs
the benefit of earlier feedback. The env-var toggle is the cheapest,
fastest-to-remove kill switch available.

---

## Consequences

**Positive:**
- Zero regression risk for v1.17.x → v1.18.0 upgrade path. Users who do
  nothing get identical behavior.
- Contract bugs discovered by early adopters are fixed before strict mode is
  turned on — protects the broader user base.
- Operators retain full control: `ENABLE=0` is a hard kill switch that
  reverts RV to a no-op with zero overhead (the decorator returns the
  original function reference).
- Rollout is monotonically safe — each phase adds opt-in choices without
  removing the ability to disable.

**Negative:**
- Most users will not exercise the verification layer for several weeks or
  months, delaying the feedback loop that would validate and refine
  contracts.
- Two boolean env vars introduce 4 possible configurations
  (`ENABLE/STRICT` in `{0,1}²`) — testers must cover all four.
- Documentation must clearly explain the opt-in model to avoid
  "why isn't verification catching X?" confusion.
- The `NullVerifier` code path must be maintained as first-class (not
  dead code) as long as opt-in is the default — ensures the disabled path
  never bit-rots.

**Risks:**
- An engineer may ship a contract bug that only manifests when `STRICT=1`,
  and the bug goes undetected until v1.19.0 or v1.20.0 when strict becomes
  CI default. Mitigation: shadow-mode phase (step 3 above) runs `ENABLE=1,
  STRICT=0` in CI, so violations are visible in logs and can be triaged.
- Operators may misconfigure (`ENABLE=1, STRICT=1` in production hook mode)
  and experience pipeline halts. Mitigation: documented warning in
  `.env.example`; shadow-mode recommended for 2 release cycles before
  strict.
- The feature becomes "invisible infrastructure" that nobody tests.
  Mitigation: unit tests cover both `NullVerifier` and `RuntimeVerifier`
  paths; integration tests run with `ENABLE=1` for full coverage.
