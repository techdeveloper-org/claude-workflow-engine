# ADR-006: Hook-Free Execution Model

**Status:** Accepted (SETTLED at the STEP 0.5 consultation gate; pre-committed by the project owner and not open for re-litigation)
**Date:** 2026-08-01
**Deciders:** Project owner (decision), solution-architect (recording)
**Target release:** v2.0.0
**Implements:** PRD FR-6 (`docs/phase-0-requirements/prd-v2.md`, Deliverable D2) / SRS FR-16 (`SRS.md`)
**Build status of the decision itself:** EXECUTED 2026-08-04. This document records a decision, and
as of 2026-08-04T10:05:54Z the hook removal it decides (SRS FR-13, SRS FR-15) has been performed on
the project owner's live machine by commit `2e371f6`. What was removed was the three *registrations*,
not the hook source files. See section 4.2 "What actually executed" and the revised section 5.

---

## 1. Context

The pipeline integrates with four Claude Code hook types -- `UserPromptSubmit`, `PreToolUse`,
`PostToolUse` and `Stop` (`SRS.md` FR-9 "Hook System", line 133 as of 2026-08-02). A `Notification`
hook additionally exists as a user-level registration outside that set
(`docs/phase-1-architecture/hld.md` section 1 hook inventory table, Notification row, line 52 as of
2026-08-02).

Two of the four, `PreToolUse` and
`PostToolUse`, are registered on `matcher: ""`, so they fire on every tool call. Each fires a
synchronous Python process spawn with a 60s timeout, and the user's global instruction mandates
`async: false` for all hooks. The worst case is up to 120s of blocking before Claude sees any prompt,
and a hook crash blocks the tool call outright.

The question at the STEP 0.5 consultation gate was whether v2.0.0 keeps that model, narrows it, or
removes it.

This document is the standalone record of that decision at the path PRD FR-6 and SRS FR-16 require.
The decision text is not authored here. It is pre-committed by the project owner in
`docs/orchestration_prompt.md` section 5, under the heading `ADR-006: Hook-Free Execution Model`
(line 803 as of 2026-08-02), and recorded in the HLD at
`docs/phase-1-architecture/hld.md` section 4.1, heading `#### ADR-006: Hook-Free Execution Model
(SETTLED)` (line 213 as of 2026-08-02). `docs/phase-2-validation/hld_v2.md` is the Phase 2 copy of
the same HLD content.

---

## 2. Decision

**Chosen:** Remove `PreToolUse` and `PostToolUse` entirely; take `UserPromptSubmit` off the hot path.

That is two hook events removed, enumerated: (1) `PreToolUse`, (2) `PostToolUse`. A third,
`UserPromptSubmit`, is retained but moved off the every-prompt hot path (SRS FR-15). The `Stop` and
`Notification` hooks are unaffected by this ADR and remain user-level registrations that the plugin
neither owns, installs, nor modifies (SRS FR-18; ADR-010).

**What was executed departs from that text on one point, and the departure is recorded rather than
absorbed.** Three registrations were removed, not two: `PreToolUse`, `PostToolUse` and
`UserPromptSubmit`. The third went by project-owner ruling, not by any issue's written criteria --
V2-027's criteria name only the first two, and V2-028's criterion needs `UserPromptSubmit` gone but
was forbidden from writing settings and deferred it. Left to the written criteria alone, nobody would
have removed it. "Retained but moved off the hot path" and "registration deleted" are not the same
end state; the executed end state is the latter, and SRS FR-15's wording still describes the former.
See section 4.2.

**Why:** Two synchronous Python process spawns per tool call on `matcher: ""` with 60s timeouts each;
up to 120s blocking before Claude sees any prompt. Dominant latency on long tasks and a single-point
failure surface -- a hook crash blocks the tool call.

Source: `docs/orchestration_prompt.md` section 5, ADR-006 `Chosen:` and `Why:` lines (lines 804-807
as of 2026-08-02); `docs/phase-1-architecture/hld.md` section 4.1, ADR-006 `Chosen` and `Why` bullets
(lines 215-218 as of 2026-08-02).

---

## 3. Alternatives Rejected

Two alternatives were considered and rejected. Enumerated:

| # | Alternative | Why rejected |
|---|---|---|
| 1 | Keep hooks but set `async: true` | The user's global instruction mandates `async: false` for all hooks. It also does not remove the process-spawn cost; it only hides its latency. |
| 2 | Narrow the matcher instead of deleting | Reduces but does not eliminate per-call overhead, and leaves the 60s timeout failure mode intact. |

Source: `docs/orchestration_prompt.md` section 5, ADR-006 `Rejected:` block (lines 808-812 as of
2026-08-02); `docs/phase-1-architecture/hld.md` section 4.1, ADR-006 `Rejected` bullet (lines 219-222
as of 2026-08-02).

A third option -- keeping a reduced `PostToolUse` hook purely for checkpointing -- was raised later,
during ADR-011, and rejected there on the grounds that it violates this ADR and reinstates the
per-tool-call process spawn this project exists to remove
(`docs/phase-1-architecture/hld.md` ADR-011 `Rejected` bullet, line 330 as of 2026-08-02). It is
listed here for completeness and is not one of the two alternatives weighed at the original gate.

---

## 4. Consequence

The pre-committed consequence text, quoted verbatim and not softened:

> Consequence (MUST be stated in the ADR, not softened): enforcement becomes opt-in. Policies do not
> apply on sessions where the plugin is never invoked. Accepted by the user.

-- `docs/orchestration_prompt.md` section 5, ADR-006 `Consequence` lines (lines 813-814 as of
2026-08-02).

The HLD states the same consequence at full strength, quoted verbatim:

> **Consequence, stated plainly and not softened:** **Enforcement becomes opt-in. Policies do not
> apply on any session where the plugin is never invoked.** A developer who never types the slash
> command gets no policy enforcement at all -- no PreToolUse block, no push gate, no standards
> injection, no progress tracking. Coverage becomes a function of user habit rather than a property
> of the system. This is not a risk to be mitigated away; it is the accepted price of removing
> involuntary per-tool-call execution. Accepted by the user.

-- `docs/phase-1-architecture/hld.md` section 4.1, ADR-006 `Consequence` bullet (lines 223-228 as of
2026-08-02).

This design does not make enforcement better. It makes enforcement opt-in. That is the accepted cost
of ADR-006 (`docs/phase-1-architecture/hld.md` section 1.4 "The governing trade-off", lines 80-81 as
of 2026-08-02). It is recorded as an accepted risk, not an open item, in `docs/REVIEW-INDEX.md`
section 3 "ACCEPTED RISKS", row "Enforcement becomes opt-in" (line 62 as of 2026-08-02).

### 4.1 The three named consequences (PRD FR-4a / SRS FR-14)

PRD FR-6 and SRS FR-16 require this document to cross-reference all three capability-level
consequences that survived the blast-radius measurement. Per SRS FR-16's acceptance criterion, a
consequence recorded only in `docs/orchestration_prompt.md` does not satisfy the requirement, so all
three are stated here in full.

There are exactly three. Enumerated: (1) SRS FR-9 supersession, (2) version-push-gate bypass
reopening, (3) per-tool-call progress loss.

They are named in `docs/phase-1-architecture/hld.md` section 4.1, ADR-006 bullet "Required
cross-reference in the ADR-006 document (FR-6)" (lines 229-231 as of 2026-08-02) and in `SRS.md`
FR-14 (lines 210-212 as of 2026-08-02).

**Structural context, so the three are not mistaken for a wider breakage claim.** The three
consequences below are capability-level, not structural, and the two must not be conflated. The
structural measurement, re-measured for this record rather than carried forward, is in section 4.1.1.

#### 4.1.1 The blast-radius measurement, re-measured

Method: recomputed on 2026-08-04 directly from the Phase 0.1 snapshot
`docs/phase-0-reverse-engineering/ast_call_graph.json` (2,218 nodes, 9,378 edges, 335 files parsed,
CHA -> RTA -> Andersen). Every figure below is labelled measured or carried forward. Nothing is both.

**Node count -- MEASURED, and it confirms the recorded figure.** 135 of 2,218 nodes, 6.087 percent,
which is the recorded 6.09 percent. The prior records state the total without saying which paths
compose it; the decomposition is recorded here so the next reader does not have to rediscover it:

| Path | Nodes |
|---|---|
| `hooks/pre_tool_enforcer/` (package) | 74 |
| `hooks/pre-tool-enforcer.py` (entry shim) | 14 |
| `hooks/post_tool_tracker/` (package) | 32 |
| `hooks/post-tool-tracker.py` (entry shim) | 7 |
| `hooks/policy_tracking_helper.py` (hook-only helper) | 8 |
| **Total** | **135** |

The recorded phrase "entirely inside the three deleted packages" is loose: measured, the set is two
packages, their two entry shims, and one standalone helper module -- five paths, not three packages.
The arithmetic is right; the descriptor is not.

**Cross-boundary edges -- MEASURED, and the recorded count of 26 does not reproduce.** The correct
figure for the deletion set that yields the co-recorded 135 nodes is **12**, not 26. Measured over
the same snapshot, that set has 417 edges crossing its boundary in total: 405 outbound (deletion set
calling out, which break nothing outside because the caller leaves with them) and 12 inbound
(outside code calling in, the only direction that can break a survivor). Neither 12 nor 417 is 26.
Nor does 26 appear under the neighbouring definitions: packages-only gives 29 inbound, all-of-`hooks/`
gives 21, and adding `stop_notifier/` still gives 12.

**The recorded conclusion survives the correction and is in fact stronger than recorded.** All 12
inbound edges are `confidence: LOW` with `resolution_method: cha_only`, and all 12 land on just two
methods -- 9 on `PolicyRegistry.__init__` and 3 on `PolicyRegistry.register`. Every one of the 9 has
an exception subclass or an integration-class constructor as its source, which is exactly the
`super().__init__()` bare-name collision the prior record cites as its spot-check example. All 12
are enumerated rather than spot-checked, so the "4 were manually spot-checked" caveat is retired.
One claim in the prior record is false as written, though harmlessly: "all were `cha_only`/LOW
confidence" holds for the 12 inbound edges but not for the full crossing set, 12 of whose 417 members
are MEDIUM confidence. All 12 MEDIUM edges are outbound.

**The measurement describes a deletion that did not happen -- MEASURED.** Both figures above measure
the *removal of the hook source files*. That is not what executed. Commit `2e371f6` deleted zero
files (1,589 insertions, 5 deletions, no file removals), and all five paths in the table above are
present on disk today, verified 2026-08-04. Deliberately so: ADR-017 forbids the CI assertion from
asserting on `hooks/pre_tool_enforcer/`, and keeping the files present keeps the equivalence tests
running instead of self-skipping. **No node went dark.** What was removed is the registrations that
made these nodes reachable from a Claude Code event, so the correct statement of the executed blast
radius is that 135 nodes became *unreachable from any hook entry point* while remaining present,
importable and testable. A structural-breakage measurement was the right instrument for the change
that was designed and is the wrong instrument for the change that shipped; nothing structural could
break, because nothing structural moved.

**The measurement also does not span what executed -- MEASURED.** The 135 covers the `PreToolUse`
and `PostToolUse` deletion set only. `scripts/3-level-flow.py`, the `UserPromptSubmit` entry point
whose registration was also removed, contributes 13 further nodes and is not in the 135. The
deletion set that matches what actually executed is 148 of 2,218, 6.673 percent. Its inbound
cross-boundary count is unchanged at 12.

**Carried forward, not re-measured:** the "16 PreToolUse components (14 policy gates plus the daemon
and registry mechanism)" ledger figure. Two of its three parts were checked in passing and hold --
`hooks/pre_tool_enforcer/policies/` contains exactly 14 gate modules besides `__init__.py`, and
`daemon.py` and `registry.py` both exist -- but the full 27-row capability ledger it belongs to was
not recomputed here and is owned elsewhere (PRD NFR-4).

#### Consequence 1 -- the change set violates the project's own SRS

`SRS.md` FR-9 (Hook System) and its acceptance criterion state that all four hook events fire and
that a blocking policy returns exit code 2 from the `PreToolUse` hook so the tool call does not
proceed. Deleting `PreToolUse` and `PostToolUse` falsifies this for two of the four events.

Per `rules/44` (`~/.claude/rules/44-srs-lifecycle.md`; the repo copy was removed in #320) the SRS is
append-only, so FR-9 cannot be quietly edited in place. The
required handling is a superseding append that retires FR-9's four-event guarantee, states the v2.0.0
replacement guarantee, and adds a Change Log row. An agent that silently rewrites FR-9 in place is in
violation of `rules/44` and its output must be rejected.

- Owning requirement: PRD FR-22 / SRS FR-34.
- Status: **PARTIALLY SATISFIED, and the blocking condition has now cleared.** The superseding append
  and the revised AC-9 are already in `SRS.md`. The one outstanding element was SRS FR-34's
  acceptance criterion requiring a Change Log row dated to the PR that deletes
  `PreToolUse`/`PostToolUse`; `SRS.md` held a placeholder row beginning "PENDING -- date of the PR
  that deletes" rather than back-dating it. That deletion has since landed as commit `2e371f6`
  (2026-08-04), so the date the placeholder was waiting for now exists. Filling the row is not done
  here: `SRS.md`'s Change Log is owned by V2-030 (#286), and this ADR reports the unblock rather
  than writing into another node's file.
- Executed-scope note: the change set falsifies FR-9 for **three** of the four hook events, not two.
  `UserPromptSubmit` was also removed. Any supersession text scoped to "two of the four events" is
  now narrower than what happened.
- Sources: `docs/orchestration_prompt.md` FR-4a, paragraph beginning "*Consequence 1 -- the change set
  violates the project's own SRS.*" (lines 156-162 as of 2026-08-02); `SRS.md` FR-34 (lines 418-428
  as of 2026-08-02).

#### Consequence 2 -- deletion re-opens a bypass that was deliberately closed

Among the lost `PreToolUse` policy gates is the version-push gate,
`hooks/pre_tool_enforcer/policies/push_gate.py`, covered by `tests/test_push_gate.py`. Commit
`1bb4303` ("fix: generate the SRS where it is read, and close a bypass in the version push rule
(#251)") is recent, deliberate governance work, and removing `PreToolUse` discards its enforcement
permanently. Re-opening a bypass someone explicitly closed is not an acceptable silent outcome of a
refactor.

The gate's disposition is therefore MANDATORY `port-to-MCP`, not `demote-to-advisory` and not one of
four open options.

**Consequence 2a -- the ordering constraint is not self-enforcing.** The port must land BEFORE
`PreToolUse` is deleted. At present that is a sequencing statement in a document; nothing mechanical
enforces it. An out-of-order merge silently re-opens the bypass and no test fails, because the gate
stops existing rather than starting to misbehave. The required control is a CI assertion, landed as
part of the port and before the deletion, that fails the build if the `PreToolUse` registration is
absent while no equivalent MCP-side version-push gate is reachable. It must be an
existence-and-reachability check on the REPLACEMENT, not a check that the old hook is still present,
otherwise it would block the very deletion this project is delivering.

- Owning requirement: PRD FR-23 / SRS FR-35; the CI assertion is ADR-017.
- Status: **BUILT, and the ordering held.** The port landed as an MCP tool (`0900fff`), the ADR-017
  reachability assertion landed as `verify_push_gate_reachable` (`f893fd2`), and only then were the
  registrations removed (`2e371f6`). Measured 2026-08-04 on the live machine: `push-gate` is present
  in `mcpServers` (26 entries) and the registered hook events are `Stop` and `Notification` only.
  Carried forward from V2-027, not re-measured here: that the replacement was proven reachable by
  spawning the process the settings entry names and completing a real `tools/call` returning
  `ALLOWED`, and that `push-gate` was **absent** from the machine beforehand (25 entries) -- meaning
  deleting `PreToolUse` first would have left no push gate at all, the exact lapse this consequence
  exists to prevent.
- Residual, and it is not closed: the deletion is **not durable**. `scripts/settings-config.json`,
  the template the live settings file is bootstrapped from, still registers all three removed hooks;
  measured 2026-08-04, its hook events are `PostToolUse`, `PreToolUse`, `Stop`, `UserPromptSubmit`.
  A machine bootstrapped from it re-creates exactly what was deleted, and re-creating `PreToolUse`
  re-creates the hook-side push gate alongside it. Reported at `docs/REVIEW-INDEX.md` row 46 and not
  re-litigated here.
- Sources: `docs/orchestration_prompt.md` FR-4a, paragraphs beginning "*Consequence 2 -- deletion
  re-opens a bypass that was deliberately closed.*" and "*Consequence 2a -- the ordering constraint
  that protects the push gate is not enforced by anything*" (lines 164-184 as of 2026-08-02);
  `SRS.md` FR-35 (lines 430-439 as of 2026-08-02).

#### Consequence 3 -- per-tool-call progress loss (NFR-3, as re-scoped)

**Read the correction before the claim.** The original Phase 0 framing of this consequence was WRONG
and was superseded on 2026-08-01. It asserted that `post-tool-tracker.py` is the sole writer of
session-progress and checkpoint state, and therefore that hook deletion loses crash recovery. Direct
verification showed that sentence conflates two separate state systems.

The corrected position, which is what this ADR records:

1. **Step-boundary crash recovery SURVIVES, hook-independent.**
   `langgraph_engine/checkpoint_manager.py::CheckpointManager` is driven at every step boundary by
   `langgraph_engine/core/step_decorator.py`, with a real resume entry point at
   `orchestrator.py::resume_flow` delegating to `quality/recovery_handler.py::resume_from_checkpoint`.
   None of this lives under `hooks/`. The SRS "resume from any step after crash" guarantee is written
   at step granularity and is backed by this system, so it is NOT at risk from hook deletion.

   **Read this as scoped to the deletion, not as a statement that crash recovery works.** V2-031
   (`463451e`) measured that the durable checkpointer does not exist at runtime: the SQLite saver
   falls back to an in-memory saver, and the degradation is silent. Confirmed independently here on
   2026-08-04 -- both `langgraph.checkpoint.sqlite` and `langgraph_checkpoint_sqlite` raise
   `ModuleNotFoundError`, and `langgraph_engine/checkpointer.py`'s `_SQLITE_SAVER_AVAILABLE` is
   `False`. So the correct claim is narrow: hook deletion did not take crash recovery away. Something
   else had already taken its durability, for an unrelated reason, and V2-031's contract bounds how
   much of this consequence the checkpoint record can absorb.
2. **Per-tool-call progress tracking DIES with `PostToolUse`.** This is the hook-owned system
   (`hooks/post_tool_tracker/progress_tracker.py`) and it is the genuine loss. It is at per-tool-call
   granularity, finer than any SRS step guarantee.

   **Name the surface that actually stopped.** Earlier framings attribute the loss to the fallback
   constant `~/.claude/memory/logs/session-progress.json`. That attribution would misstate what
   happened: measured 2026-08-04, that file's last write is **2026-07-30 14:17:33**, five days
   before the deletion. It was already stale, so nothing about the deletion stopped it and citing it
   would credit the removal with a death that predates it. The live surface was
   `~/.claude/memory/logs/tool-tracker.jsonl` (plus a session-scoped file). Measured 2026-08-04: it
   holds 70,994 lines and 18,867,916 bytes, its mtime is 2026-08-04 15:35:54 +0530 --
   2026-08-04T10:05:54Z, the deletion instant to the second -- and its final entry is the very
   command that performed the removal:
   `python scripts/remove_hook_registrations.py --json`. Line count, byte count and mtime were
   unchanged across every tool call made while writing this section, more than five hours later. The
   writer stopped mid-sentence on its own removal, and that is the loss, stated at the file that
   actually carried it.

The loss is therefore closer to the original "telemetry loss" framing than to the escalated "crash
recovery loss" framing. The escalation was an orchestrator error propagated from a Phase 0.2 claim
that named a single sole writer where two independent writers exist.

The replacement is the existing `mcp-post-tool-tracker` MCP server (`increment_progress`,
`track_tool_usage`), called explicitly by the pipeline at defined boundaries, and required to be a
projection of the checkpoint record rather than an independent second writer -- otherwise checkpoint
and progress become a dual write that can disagree after a crash.

**Warm daemon, correctly attributed.** The warm-daemon fast path is at
`hooks/pre_tool_enforcer/daemon.py`. It is a `PreToolUse` asset, not a `PostToolUse` one; earlier text
attributed it to `PostToolUse`. It is lost either way, because both hooks are deleted, but it belongs
to the `PreToolUse` deletion. Its replacement is structural: an MCP stdio server is already a warm,
long-lived process, so the warm-path benefit returns through the MCP transport.

- Owning requirement: PRD NFR-3 / SRS NFR-9; the ownership decision is ADR-011.
- Status: **DESIGNED, NOT BUILT.** The replacement writer is not a new component and already exists,
  but three durability defects and the progress-projection port are unbuilt: (i) the checkpoint-save
  failure currently swallowed with a warning must instead raise or set a `checkpoint_degraded` flag
  the resume path refuses to trust; (ii) the progress replacement must be a projection of the
  checkpoint record, never an independent second writer; (iii) replay must be idempotent on a
  session-id-plus-step-number key for side-effecting steps.
- Executed-scope note: this is the one of the three consequences that is now a **live gap rather
  than a projected one**. The other two were discharged or controlled before the deletion landed --
  Consequence 1 by the supersession append, Consequence 2 by the port and the ADR-017 assertion.
  Consequence 3's replacement was not built first, so the writer stopped on 2026-08-04 with nothing
  in its place. Per-tool-call telemetry is absent from that instant until the port lands.
- Sources: `docs/orchestration_prompt.md` FR-4a, paragraphs beginning "*Consequence 3 -- SUPERSEDED
  2026-08-01.*" and "*Consequence 3a -- warm daemon mis-attributed*" (lines 186-217 as of
  2026-08-02); `docs/phase-1-architecture/hld.md` section 12, heading "### OAQ 1 -- NFR-3
  crash-recovery replacement -- **RESOLVED**" (lines 1455-1507 as of 2026-08-02); `SRS.md` NFR-9
  (lines 616-630 as of 2026-08-02).

---

### 4.2 What actually executed

This section exists because everything above section 4.1.1 was written while the deletion was
prospective, and it is no longer. Recorded so the difference between the decision and the event is
not lost.

**When.** 2026-08-04T10:05:54Z, by `scripts/remove_hook_registrations.py`, on the project owner's
live machine. The script is the one landed by commit `2e371f6`, but the run preceded the commit:
the settings mutation is at 10:05:53.76Z and the commit at 10:57:39Z, so "executed by commit
`2e371f6`" would invert the order. Two independent clocks agree on the mutation instant --
`~/.claude/settings.json` mtime, and the final line of `tool-tracker.jsonl` at 10:05:54.079Z, which
is the log of the removal command itself and is the last thing that writer ever recorded.

**What changed.** `~/.claude/settings.json` sha256 went from `479cbcfe...631353` to
`8ae2a426...89b27b2` (the latter measured as the current value on 2026-08-04 and used as the
baseline for this document's own work).

**Verified end state, measured 2026-08-04.** Registered hook events are `Stop` and `Notification`
only. `mcpServers` holds 26 entries and includes `push-gate`, where it held 25 and did not.

**Three registrations were removed, not two.** `PreToolUse`, `PostToolUse`, and `UserPromptSubmit`.
The third by owner ruling; see the note in section 2.

**Nothing was deleted from the repository.** Commit `2e371f6` removed no files. The hook source
packages, their entry shims and `hooks/policy_tracking_helper.py` are all present on disk. This is
deliberate: ADR-017 forbids the CI assertion from asserting on `hooks/pre_tool_enforcer/`, and
keeping the sources present keeps the equivalence tests executing rather than self-skipping. The
consequence for this document is section 4.1.1's central correction -- the recorded blast radius
measures a file deletion that has not occurred and is not planned in this form.

**Not durable.** See the residual note under Consequence 2.

---

## 5. Build status of everything referenced here

Six items. Four have since been built; this table was previously headed "Nothing in this ADR
describes shipped behaviour", which is no longer true.

| # | Item | Owning requirement | Status |
|---|---|---|---|
| 1 | Delete `PreToolUse` and `PostToolUse` | SRS FR-13 | **EXECUTED 2026-08-04** (`2e371f6`); registrations only, source files retained |
| 2 | Take `UserPromptSubmit` off the hot path | SRS FR-15 | **EXECUTED 2026-08-04**, and it exceeded the requirement -- the registration was removed outright, not merely moved off the hot path |
| 3 | SRS FR-9 supersession append | SRS FR-34 | PARTIALLY SATISFIED; the cutover Change Log row is now unblocked (its PR exists) and is owned by V2-030 |
| 4 | Version-push gate ported to MCP | SRS FR-35 | **BUILT** (`0900fff`); registered and reachable on the live machine |
| 5 | CI assertion enforcing port-before-delete ordering | ADR-017 | **BUILT** (`f893fd2`), landed before the deletion; ordering held |
| 6 | Progress writer as a projection of the checkpoint record, plus the three durability fixes | SRS NFR-9 / ADR-011 | DESIGNED, NOT BUILT -- and now a live gap, because the writer it replaces stopped on 2026-08-04 |

Item 6 is the one open consequence with no replacement in place. Between the deletion and that port,
per-tool-call telemetry is simply absent.

This document itself (PRD FR-6 / SRS FR-16) is the deliverable being satisfied by its own creation.

---

## 6. Citation note

Line numbers in this document are dated hints, valid as of 2026-08-02; material added on 2026-08-04
(sections 4.1.1, 4.2, and the revised statuses) cites by commit hash, file path and measured value
rather than by line number, so it does not decay the same way. `SRS.md` and
`docs/phase-2-validation/hld_v2.md` both grew during earlier correction passes, which invalidated
line-number-only citations elsewhere in this project. Every citation above therefore leads with a
stable anchor -- a section number, a heading, an FR or ADR number, or a quoted sentence opening --
and carries the line number only as a secondary aid. Resolve by anchor first.
