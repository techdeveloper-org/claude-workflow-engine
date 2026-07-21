# High-Level Design (Delta HLD) — claude-workflow-engine ↔ claude-global-library Integration

**Mode:** Phase 1 Brownfield (Mode B — Delta HLD)
**Author:** solution-architect (Domain 5, architecture-quality)
**Date:** 2026-07-21
**Engine version at time of design:** 1.20.0 (per `VERSION`)
**Status:** DRAFT — pending review checkpoint
**Scope:** FR-1 through FR-9 (nine developer-recon items treated as requirements). No product-facing scope.

> **Nature of this system.** `claude-workflow-engine` is a single-developer / small-team local
> developer tool: a LangGraph-based SDLC orchestration engine driven by Claude Code hooks. It has
> **no end users, no public API, no PII, no multi-tenant runtime, no India regulatory exposure**
> (`india_regulatory_flag = false`). Traditional product NFRs (QPS, DAU, SLA, capacity) are **not
> applicable** and are **not fabricated** in this document. Sections 9 and 12 are reframed / marked
> N/A accordingly, per the Brownfield NFR-scoping rule.

---

## 1. Purpose & Context

This Delta HLD covers a bounded set of integration-correctness fixes between the engine
(`claude-workflow-engine`) and its sibling knowledge library (`claude-global-library`). The two
repositories live side-by-side on disk:

```
workspace-spring-tool-suite-4-4.27.0-new/
├── claude-workflow-engine/      ← this repo (the engine)
└── claude-global-library/       ← sibling (skills/, agents/, knowledge-graph/)
```

The central problem, verified against the source (Section 2), is that **the engine barely uses the
library it is supposed to be driven by**: it fetches skills/agents over GitHub HTTP even though the
library is a sibling folder on disk, its sync mechanism is dead, and its Step-0 routing performs a
raw LLM guess that **never once consults** the library's decision tree, Master KG, or 294-agent
catalog. This HLD designs the delta to close that gap.

### 1.1 Verification summary — recon vs. reality

Every FR claim was checked against the actual source with Read/Grep/Glob. Results:

| FR | Recon claim | Verdict | Evidence |
|----|-------------|---------|----------|
| FR-1 | `skills/manager.py` + `import_manager.py` fetch via GitHub HTTP; never check local sibling | **CONFIRMED** | `SkillManager._download_with_retry` → `urllib` to `raw.githubusercontent.com`; disk cache is `~/.claude/skills/` (via `get_skills_dir()`), **not** `../claude-global-library/`. `ImportManager.get_skill/get_agent` are pure GitHub HTTP with **no** local path at all. |
| FR-2 | `hook-downloader.py` referenced in 3 places but does not exist → sync 100% broken | **CONFIRMED** | `scripts/tools/sync-library.py` calls `script_dir / "hook-downloader.py"`; that file does not exist anywhere in the repo. Referenced by `sync-library.bat`, `sync-workflow-engine.bat`, `update-status.bat`, README, two policy docs. |
| FR-3 | Step-0 routing is a raw LLM guess; never consults decision tree / Master KG / agent catalog. "Steps 5/6" selection logic deleted | **CONFIRMED (decisive)** | Grep for `knowledge-graph\|decision_nodes\|patterns.json\|Master KG` across the **entire** `langgraph_engine/` → **0 files**. `prompt_generator.py` = LLM picks task_type/complexity/model only. `todo_decomposer.py` = claude CLI names agents from its own guess. Stale-numbering corroboration: `decision_explainer.py` still documents "Skill Selection Decision (Step 5)". |
| FR-4 | `standards/selector.py` has hand-written content for Flask/Django/Spring only; FastAPI/React/Angular/Vue/Express return empty | **PARTIALLY WRONG** | Selector hand-writes **nothing** — it reads `docs/*.md`. `load_framework_standards()` returns empty for **every** framework (no framework-specific docs bundled for anyone, including Flask/Django/Spring). All frameworks fall back to **language-level** docs. The real gap: zero framework-level depth for all frameworks. The FR *intent* (source framework depth from the library) is still valid; the *premise* is not. |
| FR-5 | Flask/FastAPI/Django/Spring-MockMvc generators are literal `pass # TODO` | **PARTIALLY WRONG** | They are **not** unimplemented — each emits a structured, commented test skeleton ending in `pass # TODO: configure <fw> test client and route`. Deliberate stub templates, not empty functions. Path-based generation is fully implemented. Enhancement (runnable templates from library skills) is valid but **lower urgency** than recon implied. |
| FR-6 | `scripts/pre_tool_enforcer/` and `hooks/pre_tool_enforcer/` both exist; one is dead | **CONFIRMED** | Both exist. `hooks/pre-tool-enforcer.py` is a shim that loads `hooks/pre_tool_enforcer/` → **`hooks/` is LIVE**. `scripts/pre_tool_enforcer/` is referenced only by two `docs/*.md` files (zero live code) and lacks the newest policy `agent_persona.py` → **dead duplicate, safe to delete.** |
| FR-7 | SRS version stuck at 1.15.1 vs shipped 1.20.0 | **CONFIRMED** | `SRS.md` header: `Version: 1.15.1`, dated 2026-03-21. `VERSION` file: `1.20.0`. (Note: a second SRS also exists at `docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md`.) |
| FR-8 | CLAUDE.md/SRS describe a `policies/` tree that doesn't exist; real content is in `docs/` | **CONFIRMED (nuanced)** | `CLAUDE.md` documents a `policies/{00-auto-fix,01-sync,02-standards,03-execution,testing}` tree. On disk `policies/` contains **exactly one** file (`policies/03-execution-system/failure-prevention/failure-kb.json`). The ~60 `*-policy.md` files live in `docs/`. Standards loader reads team policies from `~/.claude/policies/` (home), not repo `policies/`. Repo `policies/` is vestigial. |
| FR-9 | `cli.py` and `decision_explainer.py` reference deleted "Step 1/5" numbering | **PARTIALLY WRONG** | `decision_explainer.py` → **CONFIRMED** (documents Step 1 / Step 5 / Step 10). `scripts/cli.py` → **NO** Step references found. Only `decision_explainer.py` carries the stale numbering. |

**Net:** 5 of 9 confirmed as-stated (FR-1, FR-2, FR-3, FR-6, FR-7); FR-8 confirmed with nuance;
FR-4, FR-5, FR-9 have inaccurate premises but a valid underlying concern. FR-3 is the load-bearing
finding and is confirmed decisively.

---

## 2. Current-State Architecture (as-verified)

### 2.1 Library-access layer (FR-1, FR-2)

Two independent, overlapping resource loaders exist, both GitHub-first:

- **`langgraph_engine/skills/manager.py :: SkillManager`** — retry+cache skill provisioner. Order:
  in-memory cache → disk cache (`~/.claude/skills/`) → GitHub raw HTTP (5-attempt backoff). The
  sibling `../claude-global-library/` is never consulted. Casing note: builds candidate URLs for
  both `skill.md` and `SKILL.md`.
- **`src/utils/import_manager.py :: ImportManager`** — static GitHub-only loader for skills, agents,
  and policies. `get_skill()` fetches `.../skills/{name}/skill.md` (**lowercase** `skill.md` — the
  library actually ships `SKILL.md`, so this call path is latently broken against the real library;
  `get_agent()` correctly uses `agent.md`).

Sync tooling: `scripts/tools/sync-library.py` → subprocess to a non-existent `hook-downloader.py`.
Every sync entry point (`.py`, `.bat` × 3) is therefore a no-op error today.

### 2.2 Step-0 routing / planning layer (FR-3)

`level3_execution/architecture/`:
- `00-prompt-generation/prompt_generator.py :: TaskAnalyzer` — single LLM call returning
  `{task_type, complexity, suggested_model, reasoning}`. **No agent or skill selection.**
- `todo_decomposer.py` — reads an orchestration prompt file, asks the `claude` CLI to split it into
  TODOs, each naming "a specific agent from the orchestration plan." The agent names originate from
  the LLM's own training knowledge, not from any catalog.
- `todo_executor.py`, `prompt_gen_expert_caller.py` — downstream execution.

There is **no** component that traverses the decision tree, resolves a domain, or reads an agent
roster. The library's `knowledge-graph/_orchestration-decision-tree/` (23 decision nodes, 82
branches, 36 patterns, all validated) and per-domain `agents.json`/`relationships.json` are entirely
unused by the engine.

### 2.3 Standards layer (FR-4)

`standards/selector.py` — language + framework detection, then priority-ordered loading
(`custom(4) > team(3) > framework(2) > language(1)`). Framework tier reads
`docs/{lang}-{fw}-standards.md` / `docs/{fw}-standards.md` — **none exist** → empty for all
frameworks. Language tier reads `docs/{lang}-standards.md` for python/js/ts/go/rust/java/csharp.

### 2.4 Test-generation layer (FR-5)

`level3_execution/integration_test_generator.py` — template-based (no LLM). Path tests fully
implemented; per-framework API tests are intentional commented stubs.

### 2.5 Hook enforcement (FR-6) & docs drift (FR-7/8/9)

Live hook chain loads from `hooks/pre_tool_enforcer/`. `scripts/pre_tool_enforcer/` is an orphaned
copy. `SRS.md`, `CLAUDE.md`, `decision_explainer.py` carry stale version/structure/step references.

---

## 3. KEEP / CHANGE / NEW / DEPRECATE Classification

Per Mode B rules, every component touched by FR-1…FR-9 is classified. Design/DSA effort in later
sections applies to **NEW** and **CHANGE** only.

| # | Component | Path | Class | FR | Rationale |
|---|-----------|------|-------|----|-----------|
| C1 | `SkillManager` | `langgraph_engine/skills/manager.py` | **CHANGE** | FR-1 | Insert local-sibling tier ahead of GitHub; keep retry/cache. |
| C2 | `ImportManager` | `src/utils/import_manager.py` | **CHANGE** | FR-1 | Add local-sibling tier; fix `skill.md`→`SKILL.md` casing bug. |
| C3 | `LibraryResolver` (resolver port + local/github/hard-fail chain) | `langgraph_engine/library/resolver.py` (new) | **NEW** | FR-1 | Single Strategy/Chain-of-Responsibility resolver both C1 and C2 delegate to. Removes duplicated fetch logic (DRY). |
| C4 | `sync-library.py` | `scripts/tools/sync-library.py` | **CHANGE** | FR-2 | Replace dead `hook-downloader.py` subprocess with thin "verify sibling exists + optional `git pull`" wrapper. |
| C5 | `hook-downloader.py` references | `sync-library.bat`, `sync-workflow-engine.bat`, `update-status.bat` | **DEPRECATE** | FR-2 | Remove/redirect references to the eliminated script. |
| C6 | `hook-downloader.py` | (absent) | **NEW (thin) — see ADR-2** | FR-2 | NOT rebuilt as a full downloader; replaced by C4 wrapper. |
| C7 | `KGRouter` node | `langgraph_engine/routing/kg_router.py` (new) | **NEW** | FR-3 | Deterministic pre-LLM node: decision-tree traversal → domain → agent → persona/skill grounding. |
| C8 | `DecisionTreeTraverser` + `DomainKGReader` | `langgraph_engine/routing/kg_lookup.py` (new) | **NEW** | FR-3 | Pure-Python KG readers (ports) behind C7. |
| C9 | `prompt_generator.py` (TaskAnalyzer) | `.../00-prompt-generation/prompt_generator.py` | **CHANGE** | FR-3 | Consume `state["routing"]` as grounding; stop guessing agents. |
| C10 | `todo_decomposer.py` | `.../architecture/todo_decomposer.py` | **CHANGE** | FR-3 | Inject the resolved real agent roster + skill list into the orchestration prompt. |
| C11 | `load_framework_standards` | `standards/selector.py` | **CHANGE** | FR-4 | Add a library-skill-backed loader (via C3) between framework and language tiers. |
| C12 | `LibrarySkillStandardsAdapter` | `langgraph_engine/standards/library_adapter.py` (new) | **NEW** | FR-4 | Adapter: framework name → library skill → extracted standards section. |
| C13 | integration test framework stubs | `level3_execution/integration_test_generator.py` | **CHANGE (P2, low)** | FR-5 | Enrich stubs from library quality-testing/backend skills; keep template (no-LLM) approach. |
| C14 | `scripts/pre_tool_enforcer/` | dir | **DEPRECATE (delete)** | FR-6 | Dead duplicate; zero live references. |
| C15 | `hooks/pre_tool_enforcer/` | dir | **KEEP** | FR-6 | Live enforcement package. |
| C16 | `SRS.md` | root | **CHANGE** | FR-7 | Version 1.15.1 → 1.20.0. Also delete/redirect the duplicate `docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md` in favor of the canonical root `SRS.md` (mandated by `rules/11-documentation-files.md` + `rules/44-srs-lifecycle.md`). |
| C17 | `CLAUDE.md` | root | **CHANGE** | FR-8 | Correct `policies/` tree description to match disk (content in `docs/`). |
| C18 | `decision_explainer.py` | `langgraph_engine/` | **CHANGE** | FR-9 | Update stale Step 1/5/10 numbering to current node names. |
| C19 | `scripts/cli.py` | scripts | **KEEP** | FR-9 | No stale Step references found — recon was wrong; no change. |
| C20 | `langgraph_engine/skills/manager.py` shim + `integration_test_generator.py` shim | — | **KEEP** | — | Backward-compat re-export shims stay. |

**Counts:** KEEP = 3 (C15, C19, C20) · CHANGE = 10 (C1, C2, C4, C9, C10, C11, C13, C16, C17, C18) ·
NEW = 5 (C3, C6, C7, C8, C12) · DEPRECATE = 3 (C5, C14, and the `hook-downloader.py` full-rebuild
option superseded by C6).

---

## 4. Target-State Architecture (delta)

### 4.1 Component boundaries (hexagonal framing)

The new library-integration surface is designed as an **application-core port with swappable
adapters** (Clean/Hexagonal, per skill guidance). The engine core depends on ports, never on
`urllib` or filesystem details directly.

```
                    ┌─────────────────────────────────────────────┐
                    │              Engine core (LangGraph)          │
                    │                                               │
   task ──▶ [KGRouter node] ──▶ [prompt_generator] ──▶ [todo_decomposer] ──▶ ...
                    │  (NEW, deterministic)   (CHANGE)      (CHANGE)         │
                    │        │                                              │
                    │        ▼ depends on ports:                           │
                    │   ┌──────────────────┐    ┌──────────────────────┐   │
                    │   │ ResourceResolver │    │ KG lookup ports      │   │
                    │   │  (port, FR-1)    │    │ DecisionTreeTraverser│   │
                    │   └──────────────────┘    │ DomainKGReader (FR-3)│   │
                    └──────────┬───────────────  └──────────┬───────────┘  │
                               │ adapters                    │ adapters
              ┌────────────────┼─────────────┐               │
              ▼                ▼             ▼                ▼
     LocalSiblingAdapter  GitHubAdapter  HardFail     LocalSiblingAdapter (reuse)
     ../claude-global-    raw.github…    (raise        reads
     library/ (rolling)   (opt-in)       SetupError)   ../claude-global-library/
                                                        knowledge-graph/…
```

Both the resource resolver (FR-1) and the KG readers (FR-3) resolve library files through the **same
local-sibling adapter** — one place that knows where the sibling library is on disk.

### 4.2 Sibling-path discovery (shared primitive)

A single `locate_library_root()` helper resolves the sibling once and memoizes it:

1. `CLAUDE_GLOBAL_LIB_PATH` env var, if set (explicit override — CI, non-standard layouts).
2. `Path(engine_root).parent / "claude-global-library"` (the default sibling layout).
3. Return `None` if neither exists (triggers the resolver's fallback chain).

This helper is the DIP seam: everything else (skills, agents, decision tree, domain KGs) is a
relative path under the resolved root.

---

## 5. Architecture Decision Records (ADRs)

> ADRs follow `ADR_TEMPLATE.md` (Phase 1 standard format). `india_regulatory_flag = false` for this
> project, so every India Regulatory Layer resolves to N/A.

### ADR-1 — Local-path bridge: resolution order, versioning, and fallback

**Status:** PROPOSED
**Date:** 2026-07-21
**Decider:** solution-architect
**Reviewed by:** consensus-agent (pending re-review)
**Satisfies:** FR-1

#### Context
`SkillManager` and `ImportManager` both fetch from GitHub HTTP and ignore the on-disk sibling. Two
sub-decisions were left to the architect: (a) the fallback policy when the sibling is absent, and
(b) whether to pin the library to a git ref or read rolling disk state. The operator's stated
preference is fail-loud (no silent degradation) with hard-fail as the terminal.

#### Decision
**Chosen: A 3-tier Chain-of-Responsibility resolver — (1) local sibling read at rolling disk state, (2) opt-in GitHub HTTP (default off, ref-pinnable), (3) hard-fail with a typed `LibrarySetupError`.**

#### Rationale
1. **Zero-network determinism on the happy path.** The sibling is the operator's own working copy; reading it at rolling disk state means no network call and no git operation on the normal dev flow, and the exact bytes on disk are what execute.
2. **Fail-loud, not silent.** Gating the GitHub tier behind `CLAUDE_ALLOW_GITHUB_FALLBACK=1` (default off) means a missing/misconfigured sibling raises `LibrarySetupError` immediately (fail-fast, per error-handling-patterns) instead of silently turning into a network fetch of possibly-different content — exactly the operator's requirement.
3. **CI reproducibility preserved at the right tier.** Rolling state is correct for the local tier, while reproducibility for CI / a different machine is retained at the remote tier, which is pinnable via the existing `CLAUDE_SKILL_REPO_URL` ref — so local = rolling, remote fallback = pinnable.

#### Alternatives Rejected

| Alternative | Rejection Reason |
|------------|-----------------|
| Pin the local tier to a specific git ref | Forces the bridge to shell out to git and re-introduces the network/complexity coupling the bridge exists to remove; the sibling is a live working copy, so pinning is the wrong abstraction for the local tier. |
| Keep GitHub HTTP as a silent middle tier (status-quo behaviour) | Violates the fail-loud requirement — a missing sibling would silently become a network fetch of possibly-diverged content, hiding a setup error. |
| Auto-clone the sibling on miss | Explicitly rejected by the operator; a hidden side effect that writes to the parent directory and can pull an unexpected ref without consent. |

#### Consequences

**Accepted trade-offs:**
- Rolling local state can silently serve a stale sibling (a correctness, not security, risk) — mitigated by FR-2's `--pull` wrapper and by the operator owning both repos.

**Risks and Mitigations:**
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Stale sibling serves outdated skills/agents | Medium | Low | FR-2 verify+`git pull --ff-only` wrapper; operator owns both repos. |
| Operator forgets to check out the sibling on a new machine | Medium | Low | Hard-fail tier 3 prints the exact expected path + override env var. |

#### India Regulatory Layer
N/A (`india_regulatory_flag = false`; no PII, no data-residency or CERT-In exposure).

#### FR/NFR Traceability
- Satisfies: FR-1
- Enables: C1 `SkillManager`, C2 `ImportManager`, C3 `LibraryResolver` in HLD Section 3.
- Supersedes: the previously-undocumented implicit decision "always fetch skills/agents from GitHub" embedded in `SkillManager`/`ImportManager`. → **SUPERSEDED-BY ADR-1.**

---

### ADR-2 — Sync mechanism: eliminate `hook-downloader.py`, add thin verify+pull wrapper

**Status:** PROPOSED
**Date:** 2026-07-21
**Decider:** solution-architect
**Reviewed by:** consensus-agent (pending re-review)
**Satisfies:** FR-2

#### Context
`hook-downloader.py` is referenced from 4 entry points but does not exist; sync is 100% broken. With
ADR-1's local bridge in place, skills/agents are read directly from the sibling at runtime, so on a
dev box there is nothing to "download" — only freshness matters.

#### Decision
**Chosen: Delete the `hook-downloader.py` references and replace `sync-library.py` with a thin wrapper that verifies the sibling exists and optionally runs `git pull --ff-only`; no new downloader is created.**

#### Rationale
1. **Nothing to download in a sibling layout.** ADR-1 reads the library directly from disk; the only real operation is keeping the sibling fresh, which a `git pull` wrapper does in ~40 lines.
2. **DRY and no re-coupling.** A full re-downloader would duplicate ADR-1's resolution logic and re-introduce the network coupling the local bridge removes.
3. **Testable and honest.** A verify+pull wrapper is unit-testable and names the operation truthfully ("verify + optionally pull"), rather than a fictitious "sync/download" against a sibling that is already on disk.

#### Alternatives Rejected

| Alternative | Rejection Reason |
|------------|-----------------|
| Rebuild a full `hook-downloader.py` | Duplicates ADR-1's fetch/resolution logic and re-introduces the exact network coupling the local bridge was designed to eliminate. |
| No sync tooling at all — rely on manual `git pull` | Leaves stale-sibling risk entirely to operator memory, gives no actionable error when the sibling is absent, and leaves the 3 dead `.bat` entry points in place as misleading no-ops. |

#### Consequences

**Accepted trade-offs:**
- "Sync" is downgraded to "verify + optionally pull" — the honest operation for a sibling layout, but users expecting a network download must use ADR-1's opt-in HTTP tier instead.

**Risks and Mitigations:**
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| `.bat` callers still reference the old contract | Low | Low | Update/remove the 3 `.bat` files as part of C5. |
| `--pull` fails on a non-fast-forward sibling | Low | Low | `--ff-only` fails cleanly with exit 3 + message; operator resolves manually. |

#### India Regulatory Layer
N/A (`india_regulatory_flag = false`).

#### FR/NFR Traceability
- Satisfies: FR-2
- Enables: C4 `sync-library.py` wrapper, C5 `.bat` reference cleanup, C6 thin wrapper in HLD Section 3.
- Supersedes: the implicit "sync via `hook-downloader.py`" contract. → **SUPERSEDED-BY ADR-2.**

---

### ADR-3 — KG routing integration: new deterministic node vs. rewrite existing step

**Status:** PROPOSED (recommendation firm; user confirmation invited — see Section 11)
**Date:** 2026-07-21
**Decider:** solution-architect
**Reviewed by:** consensus-agent (pending re-review)
**Satisfies:** FR-3

#### Context
Step-0 selects agents/skills via LLM guess with no KG lookup. The library ships a validated decision
tree (23 nodes / 82 branches / 36 patterns) and per-domain agent rosters. Two integration options
were left open: (A) a new deterministic node before the LLM step, or (B) rewriting the LLM step's
internals to call the KG inline.

#### Decision
**Chosen: Option A — a new deterministic `KGRouter` node inserted before `prompt_generator`, writing a `routing` grounding object into `FlowState`; the existing LLM steps run afterwards and consume it as ground truth.**

The node (1) derives a primary-domain signal, (2) traverses the decision tree from D01 to the D14
collaboration pattern, (3) reads `patterns.json[N]` for `lead_domain`/`lead_agent`/`lead_math`,
(4) reads that domain's `agents.json` + `relationships.json` for the concrete agent + skills,
(5) loads the `agent.md` persona via the ADR-1 resolver, (6) writes `FlowState["routing"]` + the
explainable path trace.

#### Rationale
1. **SRP + offline testability.** Deterministic routing is isolated from LLM analysis; `KGRouter` is a pure function unit-testable with in-memory fakes — no LLM or network in tests (hexagonal M5).
2. **OCP + backward compatibility.** Routing is added as an additive node plus an additive `FlowState["routing"]` field; the existing LLM steps are not rewritten and the pipeline runs unchanged if the node is disabled.
3. **Explainability + fail-safe degradation.** The decision tree emits a native `Path: D## → Branch → Outcome` trace, and an unresolved domain yields `status=unresolved` + the legacy LLM path — it never forces a wrong agent.

#### Alternatives Rejected

| Alternative | Rejection Reason |
|------------|-----------------|
| Option B — rewrite `prompt_generator`/`todo_decomposer` internals to call KG lookups inline | Mixes deterministic lookup and LLM call in one node (violates SRP), requires mocking the LLM to test routing, and imposes higher regression risk on two working hot-path files. |
| No deterministic routing — keep the pure LLM guess (status quo) | This *is* the verified defect: it never consults the validated decision tree or 294-agent catalog, is non-deterministic and unexplainable, and silently routes to hallucinated agent names. |

#### Consequences

**Accepted trade-offs:**
- Adds one node + two readers and a small edit to two consumers; the domain-signal heuristic must be maintained.

**Risks and Mitigations:**
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Domain-signal keyword match is ambiguous for some tasks | Medium | Low | `status=unresolved` → legacy LLM path; optional single-shot classifier behind a flag (OAQ #2). |
| Library/decision-tree schema drift breaks readers | Low | Medium | Defensive parse → `status=unresolved`, never a pipeline abort (Section 9.1 / 10). |

#### India Regulatory Layer
N/A (`india_regulatory_flag = false`).

#### FR/NFR Traceability
- Satisfies: FR-3
- Enables: C7 `KGRouter`, C8 KG readers, C9 `prompt_generator` change, C10 `todo_decomposer` change in HLD Section 3.
- Supersedes: the implicit "LLM guesses the agent" routing decision (the former "Step 5/6" selection removed in a prior version, per `decision_explainer.py`'s stale references). → **SUPERSEDED-BY ADR-3.**

---

### ADR-4 — Standards content sourced from library skills

**Status:** PROPOSED
**Date:** 2026-07-21
**Decider:** solution-architect
**Reviewed by:** consensus-agent (pending re-review)
**Satisfies:** FR-4

#### Context
`load_framework_standards()` returns empty for all frameworks; only language-level docs exist. Recon's
premise (hand-written Flask/Django/Spring) was inaccurate, but the underlying gap (no framework depth)
is real. The library already carries `frontend-engineering` and backend-domain skills with
framework-relevant content.

#### Decision
**Chosen: A `LibrarySkillStandardsAdapter` tier at priority 1.5 (between framework=2 and language=1) that maps a framework name to a library skill, reads that `SKILL.md` via the ADR-1 resolver, and extracts the standards-relevant sections.**

#### Rationale
1. **DRY / single source of truth.** Reuse the library's maintained skill content instead of hand-authoring more `docs/*.md`, so framework standards do not fork and drift.
2. **Selector stays an orchestrator.** Content lives in the library; `standards/selector.py` only routes and merges — no framework knowledge is hard-coded into the engine.
3. **No new network dependency + correct precedence.** The adapter reads the local sibling (ADR-1), and priority 1.5 lets an explicit bundled `docs/{fw}-standards.md` still override while beating the language fallback.

#### Alternatives Rejected

| Alternative | Rejection Reason |
|------------|-----------------|
| Hand-author `docs/{fw}-standards.md` per framework in the engine | Duplicates content the library already maintains, drifts out of sync, and imposes unbounded per-framework maintenance in the wrong repo. |
| Reuse priority slot 2 (same tier as bundled framework docs) | Creates ambiguous precedence when both a bundled doc and a library skill exist for one framework; the distinct 1.5 slot makes the bundled doc authoritatively win. |

#### Consequences

**Accepted trade-offs:**
- A small framework→skill map must be maintained (additive); an unmapped framework simply falls back to language standards (no regression).

**Risks and Mitigations:**
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| A framework has no mapped library skill | Medium | Low | Adapter returns `[]`; behaviour is unchanged (language fallback). |
| Extracted skill section is too broad/noisy | Low | Low | Extract only standards-relevant headings; keep language-level doc as the floor. |

#### India Regulatory Layer
N/A (`india_regulatory_flag = false`).

#### FR/NFR Traceability
- Satisfies: FR-4
- Enables: C11 `load_framework_standards` change, C12 `LibrarySkillStandardsAdapter` in HLD Section 3.
- Supersedes: nothing formally documented (framework tier was simply empty). No SUPERSEDE.

---

## 6. DSA Choices & Design Patterns (NEW / CHANGE only)

Per Mode B scoping, this covers only new/changed components — predominantly the lookup structures for
KG routing and the resolver patterns.

### 6.1 Data structures

| Concern | Structure | Complexity | Notes |
|---------|-----------|-----------|-------|
| Decision-tree branches by source node | `dict[node_id → list[branch]]` (adjacency list) built once from `decision_branches.json` | Build O(B), traverse O(depth) | B=82 branches, depth ≤ ~11 (D01→…→D20). Traversal is trivially cheap. |
| Pattern lookup | `dict[pattern_id → {lead_domain, lead_agent, lead_math}]` | O(1) | 36 patterns; direct index. |
| Domain→agents | `dict[domain_slug → list[agent]]` from `agents.json` (per-domain file, loaded lazily) | O(1) domain hit, O(A_d) scan | Only the **one** matched domain's file is read (few KB), never the 432 KB `agents_all.json`. |
| Agent→skills | `dict[agent_id → list[skill_id]]` from `relationships.json` `AGENT_USES_SKILL` edges | O(1) | Per-domain edge file, small. |
| Domain-signal match | keyword set → domain, linear scan over `patterns.json` `lead_domain` labels | O(P) | P=36; negligible. Mirrors D14's own keyword routing. |
| Sibling-root memo | cached `Path` (module-level `functools.lru_cache`/sentinel) | O(1) after first | Resolve once per process. |

**Decision-tree traversal complexity:** the tree is a DAG rooted at D01 with a single terminal.
Auto-traversal follows exactly one branch per decision node until D14/terminal, so worst-case work is
**O(depth)** node visits with O(1) branch selection each — bounded by the ~23-node spine. No search,
no backtracking. This is why no opus-level complexity analysis is warranted: the routing cost is
constant-order relative to a request and dwarfed by a single LLM call it replaces the *guesswork* of.

### 6.2 Design patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Strategy** | `ResourceResolver` adapters (Local / GitHub / HardFail) | Swap resolution backend without touching callers (SkillManager, ImportManager, KG readers, standards adapter). |
| **Chain of Responsibility** | ADR-1 tier chain (local → github(opt-in) → hard-fail) | Ordered fallback with a definite terminal; each tier decides handle-or-pass. |
| **Adapter** | `LibrarySkillStandardsAdapter` (C12); `DomainKGReader` mapping JSON→routing object | Translate library artifacts into engine-domain objects (Anti-Corruption Layer between the library's KG schema and the engine's `FlowState`). |
| **Facade** | `KGRouter` over `DecisionTreeTraverser` + `DomainKGReader` + resolver | One node-level entry point hides the multi-step lookup. |
| **Port/Adapter (Hexagonal)** | `ResourceResolver`, `DecisionTreeTraverser`, `DomainKGReader` as ports; filesystem/HTTP as adapters | Engine core testable with in-memory fakes; no I/O in unit tests (M5 testability). |

Patterns deliberately **not** used: no event/CQRS/saga (no async or eventing here — event-driven-
architecture skill reviewed and found non-load-bearing for this task); no Observer/pub-sub; no
Repository aggregate modeling (there are no mutable domain aggregates, only read-only library files).

---

## 7. Interface Contracts (NEW / CHANGE boundaries)

### 7.1 `ResourceResolver` port (FR-1)

**FROM:** engine core callers — C1 `SkillManager`, C2 `ImportManager`, C8 KG readers, C12 standards adapter.
**TO:** the filesystem local-sibling adapter (default) or the GitHub HTTP adapter (opt-in).
**ASSUMES:** `locate_library_root()` has been attempted; `CLAUDE_GLOBAL_LIB_PATH` and `CLAUDE_ALLOW_GITHUB_FALLBACK` env vars have been read at composition.

```python
class ResourceResolver(Protocol):
    def fetch_skill(self, skill_name: str) -> ResolvedResource: ...
    def fetch_agent(self, agent_name: str) -> ResolvedResource: ...
    def fetch_kg_file(self, relpath: str) -> ResolvedResource: ...   # e.g. "knowledge-graph/_orchestration-decision-tree/patterns.json"

# ResolvedResource: {name: str, content: str, source: "local"|"github", path_or_url: str}
# On total failure: raises LibrarySetupError(expected_local_path, override_env_var)
```

- **Casing contract:** resolver tries `SKILL.md` first, then `skill.md` (fixing the C2 `import_manager`
  lowercase bug). Agents use `agent.md`.
- **Determinism contract:** with a present local sibling, `source` is always `"local"` and no network
  call occurs.
- **MUST NOT:** callers MUST NOT read library files via `urllib`/`open()` directly, bypassing the
  resolver; the resolver MUST NOT fall through to the GitHub tier when a local sibling is present, and
  MUST NOT silently return empty content on failure (it raises `LibrarySetupError` instead).

### 7.2 KG lookup ports (FR-3)

**FROM:** the C7 `KGRouter` node.
**TO:** `DecisionTreeTraverser` + `DomainKGReader`, which read sibling JSON through the `ResourceResolver` (§7.1).
**ASSUMES:** the sibling library is present (ADR-1 tier 1) or the opt-in HTTP tier is enabled; the decision-tree and per-domain JSON files parse as valid JSON.

```python
class DecisionTreeTraverser(Protocol):
    def route(self, signals: RoutingSignals) -> DecisionPath: ...
    # DecisionPath: {pattern_id, trace: list[str], stopped_at_human: bool}

class DomainKGReader(Protocol):
    def agents_for_domain(self, domain_slug: str) -> list[AgentRef]: ...
    def skills_for_agent(self, domain_slug: str, agent_id: str) -> list[str]: ...
    # AgentRef: {id, name, agent_md_relpath, model, role}
```

- **MUST NOT:** these readers MUST NOT load the Master KG's large `_all.json` registries
  (`agents_all.json` / `skills_all.json` / `edges_all.json`) or `super_graph.json` — only the ONE
  matched domain's per-domain files; and MUST NOT raise on a parse/lookup miss (they return an empty
  result so `KGRouter` can emit `status=unresolved`).

### 7.3 KGRouter → downstream contract (`FlowState["routing"]`)

**FROM:** the C7 `KGRouter` node (sole writer).
**TO:** C9 `prompt_generator` and C10 `todo_decomposer` (readers).
**ASSUMES:** `FlowState` carries an additive `routing` key (default `{}`); readers gate on `status`.

The single grounding object the KGRouter writes and the downstream steps read:

```json
{
  "status": "resolved | unresolved | library_missing",
  "domain": "domain-slug or null",
  "pattern_id": "pattern:N or null",
  "lead_agent": {
    "id": "agent:foo", "name": "foo-agent",
    "agent_md_relpath": "agents/foo-agent/agent.md",
    "model": "sonnet|opus", "role": "..."
  },
  "lead_math_agent": "agent:...",
  "skills": ["skill-a", "skill-b"],
  "persona_markdown": "<contents of agent.md, or null if unresolved>",
  "trace": "Path: D01 -> B# -> D14 -> Outcome: pattern:N",
  "resolver_source": "local | github",
  "notes": "human-readable reason when unresolved"
}
```

**Consumer contract (backward-compatible):**
- `prompt_generator` (C9): if `status=="resolved"`, prepend `lead_agent`/`skills`/`persona_markdown`
  to its analysis context; else behave exactly as today (legacy LLM guess).
- `todo_decomposer` (C10): if resolved, the orchestration prompt's "name a specific agent" instruction
  is bound to `lead_agent.name` and the skill list; else legacy.
- The key is `status` — existing callers that don't yet read `routing` are unaffected (additive
  FlowState field).
- **MUST NOT:** consumers MUST NOT treat `lead_agent`/`skills`/`persona_markdown` as populated when
  `status != "resolved"` (they are `null`/empty in `unresolved`/`library_missing`); and MUST NOT
  substitute a self-guessed agent when `status != "resolved"` — they fall back to the documented
  legacy LLM path, not to a fabricated agent name.

### 7.4 Standards adapter contract (FR-4)

**FROM:** `select_standards()` in `standards/selector.py` (C11).
**TO:** `LibrarySkillStandardsAdapter` (C12) → `ResourceResolver` (§7.1) → the library `SKILL.md`.
**ASSUMES:** a `(project_type, framework)` → library-skill map entry exists; otherwise the adapter returns `[]`.

```python
class LibrarySkillStandardsAdapter:
    def load(self, project_type: str, framework: str) -> list[StandardDict]:
        # returns [] when no framework->skill mapping exists (safe, additive)
        # StandardDict priority = 1.5 (between framework=2 and language=1)
```

- **MUST NOT:** the adapter MUST NOT raise on an unmapped framework (it returns `[]`, preserving the
  language-level fallback), and MUST NOT emit standards at a priority that overrides an explicit
  bundled `docs/{fw}-standards.md` (its slot is 1.5 < framework 2).

### 7.5 Sync wrapper contract (FR-2)

**FROM:** the operator CLI and the 3 `.bat` entry points.
**TO:** the filesystem sibling and, with `--pull`, `git`.
**ASSUMES:** for `--pull`, the sibling is a git working tree with a clean fast-forwardable state.

```
sync-library.py [--pull]
  exit 0  : sibling present (and pulled if --pull)
  exit 2  : sibling absent  -> prints LibrarySetupError message (expected path + override var)
  exit 3  : --pull requested but sibling is not a git repo / pull failed (non-ff)
```

- **MUST NOT:** the wrapper MUST NOT perform a non-fast-forward merge or write to the sibling beyond
  `git pull --ff-only`, and MUST NOT fabricate a "download" (there is nothing to download in a sibling
  layout — freshness only).

---

## 8. FlowState Impact

One additive field: `routing: dict` (Section 7.3), default `{}`. No existing field changes type.
Because it is additive and keyed by `status`, existing nodes are unaffected (LSP-safe extension of the
state contract). Reducer: last-writer-wins (only KGRouter writes it).

---

## 9. Non-Functional Concerns (reframed — no product NFRs apply)

Product NFRs (QPS/latency/SLA/capacity) are N/A. The non-functional concerns that actually matter for
this delta:

| Concern | Requirement | How the design meets it |
|---------|-------------|-------------------------|
| **Routing reliability** | Never silently route to a wrong agent. | KGRouter is deterministic; on any resolution gap it emits `status=unresolved` + trace and forces **no** agent (legacy LLM path), rather than fabricating one. Explainable `Path: D##` trace on every resolve. |
| **Zero network on happy path** | No HTTP when the sibling is present. | ADR-1 local tier resolves purely from disk; GitHub tier is opt-in and off by default. |
| **Fail-fast on misconfiguration** | Missing library must be loud, not silent. | ADR-1 tier 3 raises typed `LibrarySetupError` naming the expected path + override var; sync wrapper exits non-zero with the same message. |
| **Backward compatibility** | Existing hook invocation + FlowState contracts unchanged. | `routing` is an additive FlowState field; `prompt_generator`/`todo_decomposer` gate on `status`; hook chain (`hooks/pre_tool_enforcer/`) untouched (C15 KEEP). |
| **Testability** | Routing + resolution unit-testable offline. | Ports + in-memory fakes (hexagonal); KGRouter and traverser are pure functions; no LLM/network needed to test (M5). |
| **Determinism/reproducibility** | Same task → same route. | JSON lookups only; no randomness; rolling local state is the single source (ADR-1b). |
| **Idempotent sync** | Re-running sync is safe. | `git pull --ff-only`; no destructive ops. |

### 9.1 Failure-mode coverage (retry policy + escalation boundary)

**Retry policy for local-FS reads.** The local reads of `patterns.json`, `decision_*.json`,
`agents.json`, `relationships.json`, `agent.md`, and `SKILL.md` performed by `KGRouter` /
`DecisionTreeTraverser` / `DomainKGReader` / `ResourceResolver` use **no automatic retry** — a local
`open()` either succeeds or the file is genuinely absent/corrupt, so retrying cannot help and would
only mask a setup/corruption error; these fail immediately (fail-fast). Retry-with-backoff applies
**only** to the opt-in GitHub HTTP tier, which retains `SkillManager`'s existing 5-attempt exponential
backoff for transient network errors — i.e. **retry is a network concern, never a local-FS concern.**

**Escalation boundary for `LibrarySetupError`.** `LibrarySetupError` is raised at the
`ResourceResolver` boundary and caught at the **`KGRouter` node level** (the outermost engine layer
that invokes resolution). The node converts it into a clean, actionable operator message — naming the
expected sibling path, the `CLAUDE_GLOBAL_LIB_PATH` override, and the `CLAUDE_ALLOW_GITHUB_FALLBACK`
opt-in flag — plus a non-zero pipeline signal; it never surfaces a raw traceback. The FR-2 sync
wrapper prints the same actionable message on its exit-2 path, so the operator sees one consistent
setup error regardless of entry point.

---

## 10. Security Threat Surface (local dev tool — real threats only)

Enterprise threat modeling (multi-tenant, authn/z, network perimeter) does **not** apply. Real,
in-scope threats:

| Threat | Vector | Mitigation |
|--------|--------|-----------|
| **Path traversal** | `skill_name`/`agent_name`/`domain_slug` used to build a filesystem path in the local adapter. A crafted `../../..` could read arbitrary files. | Validate names against `^[a-z0-9][a-z0-9-]*$` before path composition; resolve final path and assert it is within the library root (`Path.resolve()` prefix check). Applies to C1, C2, C3, C8, C12. |
| **Supply-chain (HTTP fallback)** | The opt-in GitHub tier fetches executable-adjacent markdown over the network. | Tier is off by default; when on, pin the ref via `CLAUDE_SKILL_REPO_URL`; content is treated as prompt text, never `exec`'d. TLS via `https` only. |
| **Stale-library correctness risk** | Rolling local state (ADR-1b) can silently serve outdated skills/agents. | Not a security issue per se; mitigated by FR-2 `--pull` wrapper. Documented trade-off. |
| **JSON parsing of library files** | Malformed `patterns.json`/`agents.json` could crash the router. | Defensive parse with typed errors → `status=unresolved` rather than pipeline abort (see §9.1). |

No secrets, credentials, or PII are introduced or handled by this delta.

---

## 11. Open Architectural Questions

> Resolved during this revision (previously listed as an OAQ): the **duplicate SRS** is not an open
> question — `rules/11-documentation-files.md` and `rules/44-srs-lifecycle.md` mandate a single
> canonical root `SRS.md`. Resolution: keep root `SRS.md` canonical and **delete/redirect**
> `docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md` (folded into C16, Section 3). No user decision required.

1. **ADR-3 confirmation (recommendation firm).** Option A (new deterministic `KGRouter` node) is
   recommended over Option B (rewrite existing steps). This is resolvable from the codebase, but
   because it defines the engine's core routing seam, **user confirmation is invited** before Phase B.
2. **Domain-signal derivation.** KGRouter needs to map a free-text task to a `lead_domain`. The MVP
   uses keyword matching mirroring D14. Open: should this itself be a small LLM classification (one
   cheap call) when keywords are ambiguous, or stay purely lexical? Recommendation: lexical first;
   add an optional single-shot classifier behind a flag if miss-rate proves high. Not blocking.
3. **Standards priority slot (ADR-4).** Recommended `1.5` (library framework skill loses to an
   explicit bundled `docs/{fw}-standards.md`, beats language). Confirm the numeric slot vs. reusing
   `2`.
4. **`policies/` directory fate (FR-8).** The repo `policies/` holds a single JSON. Open: delete it
   and relocate `failure-kb.json` under `docs/`, or keep `policies/` and correct CLAUDE.md to describe
   its *actual* (minimal) contents? Recommendation: correct the docs to match disk; leave the one
   live JSON where code references expect it (verify `failure_kb.py` load path before moving).
5. **FR-5 priority.** Given the stubs are functional-by-design, confirm FR-5 stays P2/low and is not
   pulled forward.

---

## 12. Capacity Estimation

**N/A.** This is a single-developer / small-team local tool triggered by Claude Code hooks; there is
no concurrent load, no request volume, no storage-growth or throughput dimension to size. The only
runtime cost added by this delta (decision-tree traversal + a few small JSON reads from a sibling
folder) is constant-order per task and negligible beside the LLM calls already in the pipeline.

---

## 13. Recommended Implementation Order

Dependency analysis confirms the operator's proposed 1→2→3→4 spine, with refinements:

1. **FR-1 (C1, C2, C3)** — local-path bridge + `ResourceResolver`. *Foundation:* FR-2, FR-3, FR-4 all
   consume the resolver / `locate_library_root()`. Build first.
2. **FR-2 (C4, C5, C6)** — sync wrapper. Small; depends on FR-1's `locate_library_root()`. Do second
   so the sibling is verifiably present/fresh for everything after.
3. **FR-3 (C7, C8, C9, C10)** — KGRouter + KG readers + consumer edits. The main value-add; depends on
   FR-1's resolver for reading `patterns.json`/`agents.json`/`agent.md`.
4. **FR-4 (C11, C12)** — standards-from-library. Depends on FR-1's resolver; independent of FR-3.
5. **FR-5 (C13)** and **FR-6 (C14)** — parallelizable, independent of each other and of 1–4. FR-6 is a
   pure deletion (fast); FR-5 is a low-priority enhancement.
6. **FR-7, FR-8, FR-9 (C16, C17, C18)** — documentation/version reconciliation. Anytime; zero code
   risk. Best done last so they capture the structure introduced by FR-1…FR-4 (e.g., the new
   `langgraph_engine/routing/` and `langgraph_engine/library/` packages should be reflected in
   CLAUDE.md's architecture section per rule 46, and SRS version bump per rule 44).

**Endorsement:** the recon's 1→2→3→4 then 5/6 parallel then 7–9 ordering is **sound and endorsed**,
with the one adjustment that FR-7/8/9 documentation updates should *follow* FR-1…FR-4 so they document
the final structure rather than being redone.

---

## Appendix A — Mode B Migration Notes

- **KEEP register:** `hooks/pre_tool_enforcer/` (live enforcement), `scripts/cli.py` (no stale steps —
  recon wrong), backward-compat shims (`skills/manager.py` callers via `langgraph_engine.*`,
  `integration_test_generator.py` root shim).
- **SUPERSEDED (undocumented prior decisions now formalized):** "always fetch from GitHub"
  (→ADR-1), "sync via hook-downloader.py" (→ADR-2), "LLM guesses the agent / former Step 5-6
  selection" (→ADR-3).
- **Migration timeline:** additive and reversible. Phases 1–2 (resolver + sync) are drop-in behind
  existing method signatures. Phase 3 (KGRouter) is an additive node + additive FlowState field —
  the pipeline runs unchanged if the node is disabled. No data migration, no breaking API change, no
  rollback script needed; reverting = removing the new node + packages.
