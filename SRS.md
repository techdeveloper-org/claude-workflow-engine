# System Requirements Analysis

**Project:** Claude Workflow Engine
**Version:** 2.1.0
**Date:** 2026-09-13
**Author:** Claude Workflow Engine Team

---

## Executive Summary


Claude Workflow Engine is a LangGraph-based 3-level pipeline that automates the full Software Development Life Cycle (SDLC) — from task analysis to merged PR closure — using LLM inference, template-driven orchestration, AST-based call graph analysis, and 13 MCP servers (295 tools). It is the only AI tool that automates all 8 active SDLC steps including GitHub Issues, branch creation, code review, PR merge, Jira tracking, Figma design-to-code, Jenkins CI/CD, SonarQube scanning, UML generation, and documentation updates.

---

## 1. Purpose
Claude Workflow Engine automates software development lifecycle tasks that normally require human coordination across multiple tools (GitHub, Jira, Figma, Jenkins, SonarQube, LLM APIs). A developer provides a natural language task description; the engine handles everything from analysis to delivery.

The system aims to:
- Automate the full SDLC pipeline from task intake to issue closure
- Enforce project-specific coding standards at every step via 63 policy files
- Reduce LLM inference costs by 60-85% through template-driven orchestration and token optimization
- Support multi-project, multi-language codebases (20+ languages, 15+ frameworks)
- Provide pluggable, extensible architecture so individual steps/levels can be added or removed

---

## 2. Scope

### Included
- Python 3.8+ pipeline execution on Windows/Linux/macOS
- LangGraph StateGraph orchestration (Level 0 through Level 2)
- 13 FastMCP servers (295 tools) for GitHub, Jira, Figma, Jenkins, Git, LLM, etc.
- Template-driven orchestration (single LLM call for full planning phase)
- Hybrid LLM inference (Claude CLI → Anthropic API)
- AST-based call graph analysis (Python/Java/TypeScript/Kotlin)
- 13 UML diagram types (Mermaid + PlantUML + Kroki.io rendering)
- Hook system (UserPromptSubmit, PreToolUse, PostToolUse, Stop)

---

## 3. Requirements

### 3.1 Functional Requirements


#### FR-1: 3-Level Pipeline Execution

**Description:** Pipeline must execute 3 levels in order: Level 0 (Pre-Flight Sanity Guard), Level 1 (Session & Context Synchronization), Level 2 (SDLC Execution Core). Each level must be independently removable or bypassable. Standards loading (project type/framework detection, policy loading) is an always-on, disk-loaded mechanism -- not a numbered pipeline level; it has never had pipeline nodes of its own.
**Priority:** Critical
**Status:** Implemented
**Key Module:** `orchestrator.py`

#### FR-2: 9-Step SDLC Automation (Level 2)

**Description:** Level 2 (SDLC Execution Core) must execute 9 active steps (Steps 0-8) with optional Hook Mode (Steps 0-3 only) via `CLAUDE_HOOK_MODE` env var.

| Step | Action |
|------|--------|
| Step 0 | Pre-Analysis & CallGraph Scan: CallGraph scan, template fast-path detection |
| Step 1 | Task Orchestration & Planning: template fill (prompt_gen_expert_caller) + orchestration execution |
| Step 2 | Issue Tracking: GitHub Issue + Jira Issue creation (dual, cross-linked) |
| Step 3 | Branch & Workspace Setup (from Jira key if ENABLE_JIRA) |
| Step 4 | Implementation & Code Generation + Jira "In Progress" + Figma "started" |
| Step 5 | Pull Request & Automated Review: PR creation + code review + Jira "In Review" + Figma fidelity check |
| Step 6 | Issue & Ticket Closure: GitHub + Jira "Done" + Figma "complete" |
| Step 7 | Documentation & UML Generation: doc update + 13 UML diagram types |
| Step 8 | Final Telemetry & Summary Report + voice notification |

**Priority:** Critical
**Status:** Implemented
**Key Module:** `sdlc_pipeline/subgraph.py`

#### FR-3: AST-Based Call Graph Analysis

**Description:** Full class-level call graph supporting Python (AST), Java, TypeScript, Kotlin (regex). Used at Steps 0, 1, 4, and 5 for impact analysis, implementation context, and PR review.
**Priority:** High
**Status:** Implemented
**Key Modules:** `parsers/` (Abstract Factory), `call_graph_builder.py`, `call_graph_analyzer.py`

#### FR-4: Integration Lifecycle Management

**Description:** All integrations follow Create → Update → Close lifecycle. Jira and Figma are toggled via env flags. Operations are non-blocking (failure of one integration does not stop others).

| Integration | Flag | Lifecycle Steps |
|-------------|------|----------------|
| Jira | `ENABLE_JIRA=1` | Create (2), Branch (3), In Progress (4), In Review (5), Done (6) |
| Figma | `ENABLE_FIGMA=1` | Extract (Step 1 template), Comment started (4), Review (5), Comment done (6) |
| Jenkins | `ENABLE_JENKINS=1` | Trigger (4), Validate (5) |
| SonarQube | `ENABLE_SONARQUBE=1` | Scan (4), Auto-fix loop |

**Priority:** Medium
**Status:** Implemented
**Key Module:** `integrations/` (Abstract Factory + Template Method)

#### FR-5: Modular Pipeline Construction

**Description:** Pipeline must be constructable via `PipelineBuilder` chainable API. Individual levels must be addable/removable without modifying orchestrator.
**Priority:** High
**Status:** Implemented
**Key Module:** `orchestrator.py` (`create_flow_graph`)

```python
# Levels are wired in the single canonical factory:
create_flow_graph(hook_mode=True)   # Level 0 + Level 1 + Level 2 (Steps 0-3)
create_flow_graph(hook_mode=False)  # full run (Steps 0-8)
```

#### FR-6: 13 MCP Servers (295 Tools)

**Description:** All external service operations (GitHub, Jira, Figma, Jenkins, Git, LLM, etc.) must be accessible as MCP tools registered in `~/.claude/settings.json`.
**Priority:** High
**Status:** Implemented
**Key Location:** `src/mcp/`

#### FR-7: Multi-Project Standards Enforcement

**Description:** The always-on, non-numbered Standards mechanism must auto-detect project type (language, framework) and load appropriate coding standards from 63 policy files, read directly from `policies/` on disk (no pipeline nodes involved).
**Priority:** High
**Status:** Implemented
**Key Module:** `langgraph_engine/standards/`

#### FR-8: Hybrid LLM Inference

**Description:** LLM calls must follow fallback chain: Claude CLI → Anthropic API. Model selection must be complexity-based.
**Priority:** High
**Status:** Implemented
**Key Module:** `langgraph_engine/llm_call.py`

#### FR-9: Hook System

**Description:** Pipeline must integrate with Claude Code's 4 hook types (UserPromptSubmit, PreToolUse, PostToolUse, Stop) for automated trigger and enforcement.
**Priority:** High
**Status:** Implemented
**Key Scripts:** `hooks/pre-tool-enforcer.py`, `hooks/post-tool-tracker.py`, `hooks/stop-notifier.py`, `scripts/3-level-flow.py` (UserPromptSubmit)

---

#### v2.0.0 Functional Requirements (APPENDED 2026-08-01, per rules/44 section 4.1)

**Numbering.** FR-1 through FR-9 above are unchanged and unedited. The next available number in this
file is FR-10, so this block runs FR-10 through FR-38 (29 entries).

> **Count corrected 2026-08-01.** This line read "FR-10 through FR-37 (28 entries)" -- written before
> FR-38 was appended for the resolver defect, and not updated when it was. Verified by enumeration:
> 29 entries, FR-10..FR-38 inclusive.

**NAMING COLLISION WARNING -- read before citing any FR number from this block.** The source document
`docs/phase-0-requirements/prd-v2.md` has its own independent FR-1..FR-24 series. SRS FR-10..FR-37
are NOT the same requirements as PRD FR-10..FR-24. Every entry below names its PRD source explicitly
on its `Source:` line. Any downstream citation of "FR-N" must state which document it comes from.
This collision is unavoidable under rules/44 section 4.1 (which mandates the next available number in
this file) and is documented rather than worked around.

**Build status.** Except where a line says otherwise, every requirement in this block is DESIGNED,
NOT BUILT as of 2026-08-01. Verified absent on disk on 2026-08-01:
`docs/reports/policy-implementation-audit-v2.md`, `docs/architecture/ADR-006-hook-free-execution.md`,
`.claude-plugin/plugin.json`, `.mcp.json`, `docs/guides/uninstall-residue.md`, and any `commands/`
directory. The single exception is FR-27, whose artifact
`docs/phase-1-architecture/plugin_schema_spike.md` exists.

**Scope.** These 29 entries are the v2.0.0 MVP boundary per
`docs/phase-0-requirements/product-sequencing-v2.md` section 4. PRD FR-19
(`get_policies_dir()` four-branch resolver) is deliberately NOT carried over -- it defers to v2.1,
blocked on the ADR-009b five-policy human sign-off. See the appended Out of Scope subsection.

---

**FR-10:** The system SHALL produce a line-by-line read-and-internalise audit of all 46 policy
documents, each row citing a `file:line` evidence reference or an explicit `NONE`.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-1 (Deliverable D1)
- Added: 2026-08-01
- Status: D1 gate APPROVED 2026-08-01 per `product-sequencing-v2.md` section 0. **Artifact status
  CORRECTED 2026-08-02, disclosed rather than silently amended:** as first appended on 2026-08-01
  this line read "DESIGNED, NOT BUILT (verified absent 2026-08-01)". That was true when checked and
  is now FALSE. `docs/reports/policy-implementation-audit-v2.md` **EXISTS** -- 507 lines, 28,780
  bytes, commit `bf92747`, written later the same day, after this pass's existence check ran. It is
  BUILT and is being reshaped to satisfy the re-scoped acceptance criterion (see the appended
  "Revised Acceptance Criterion for FR-10" in section 4). Anyone reading this entry must not close
  FR-10 against the artifact's current shape, and must not treat the artifact as absent.
- Requirement wording superseded 2026-08-02: the phrase "line-by-line read-and-internalise" above is
  retained as originally written but is NO LONGER the standard of done. It was measured
  unsatisfiable. See the revised AC-10.

**FR-11:** The system SHALL maintain a policy implementation matrix with 7 populated columns for all
46 policy rows, including a "Post-plugin plan" column drawn from the fixed vocabulary
`keep-as-is` / `port-to-plugin` / `port-to-MCP` / `demote-to-advisory` / `delete`.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-2 (Deliverable D1)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT

**FR-12:** The system SHALL record a decided disposition, with a one-sentence rationale, for every
policy whose sole enforcement mechanism is a PreToolUse block (15 policies).
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-3 (Deliverable D1)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT

**FR-13:** The system SHALL remove the `PreToolUse` and `PostToolUse` hook registrations from
`~/.claude/settings.json` entirely.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` FR-4 (Deliverable D6); ADR-006
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. This requirement is what falsifies SRS FR-9's original acceptance
  criterion; see the revised AC-9 in section 4.

**FR-14:** The system SHALL carry a recorded blast-radius measurement of hook deletion together with
its three named capability-level consequences (SRS FR-9 supersession, version-push-gate bypass
reopening, per-tool-call progress loss).
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-4a
- Added: 2026-08-01
- Status: Measurement DONE (135 of 2,218 nodes, 6.09 percent, zero surviving cross-boundary edges);
  the three consequences are un-actioned as of 2026-08-01

**FR-15:** The system SHALL remove `UserPromptSubmit` from the every-prompt hot path, so
`scripts/3-level-flow.py` is no longer invoked on every user prompt.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` FR-5 (Deliverable D6); ADR-006
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT

**FR-16:** The system SHALL publish the ADR-006 hook-free-execution trade-off as a committed document
at `docs/architecture/ADR-006-hook-free-execution.md`, with its "Consequence" section stating that
enforcement becomes opt-in and cross-referencing the three FR-14 consequences.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-6 (Deliverable D2)
- Added: 2026-08-01
- Status: Content exists in `docs/orchestration_prompt.md`; the file is DESIGNED, NOT BUILT
  (verified absent 2026-08-01)

**FR-17:** The system SHALL provide explicit slash-command entry points covering plan/decompose,
implement, review, document and release, plus one command that runs Steps 0-8 end to end.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-7 (Deliverable D6)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT (no `commands/` directory exists, verified 2026-08-01)

**FR-18:** The system SHALL keep the `Stop` and `Notification` hooks as user-level registrations that
the plugin neither owns, installs, nor modifies.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-8 (Deliverable D6); ADR-010
- Added: 2026-08-01
- Status: Decision SETTLED (keep both, conditional on FR-19); no code change required to keep them

**FR-19:** The system SHALL instrument the Stop hook over 20 consecutive real invocations, record a
per-capability keep-or-retire decision, and retire the reference for every capability not selected
for rebuild.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-8a (Deliverable D6)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. Scope note: the DECISION, the instrumentation, and reference
  retirement ship in v2.0.0; REBUILDING any selected capability defers to v2.1
  (`product-sequencing-v2.md` section 3).

**FR-20:** The system SHALL reconcile the `claude-global-library` master graph counts so that
`knowledge-graph/_master/master_graph.md`, `README.md` and the filesystem directory counts all agree.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-9 -- "library count drift" (Deliverable D3)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. The fix executes inside `claude-global-library`, not this repo.

**FR-21:** The system SHALL replace every silent file-count cap in code-graph discovery with a
coverage-complete contract, at all four known truncation sites, or formally retire the site.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-9a (Deliverable D4); ADR-013
- Added: 2026-08-01
- Status: Root-caused, DESIGNED, NOT BUILT.

  **Site list, CORRECTED 2026-08-01 against source -- the correction is disclosed rather than made
  silently.** As first appended on 2026-08-01 this entry named
  `langgraph_engine/parsers/config.py:11` as the first of four truncation sites, quoting `hld_v2.md`
  OAQ 4. **That citation is wrong, and it is wrong in 19 files across every phase of this project,
  which is why it is corrected here rather than passed on a twentieth time.** VERIFIED against the
  working tree: `parsers/config.py:11` does define `MAX_FILES = 300`, but it is DEAD CODE -- its only
  importer is `langgraph_engine/parsers/__init__.py:22`, which merely re-exports it (and lists it in
  `__all__` at `:131`). No consumer reads it. The cap that actually binds is
  `langgraph_engine/parsers/call_graph_builder_legacy.py:64`, which defines its own `MAX_FILES = 300`,
  passes it as the default of `CallGraphBuilder.__init__` at `:76`, stores it at `:79`, and enforces
  it at **`:107` and `:118`**. A fix applied to `config.py` would change nothing.

  The four sites, as corrected: (1) `langgraph_engine/parsers/call_graph_builder_legacy.py:64`,
  enforced at `:107` and `:118` -- the binding cap, VERIFIED here; (2)
  `langgraph_engine/sdlc_pipeline/architecture/00-code-graph-analysis/code_graph_analyzer.py:73`
  (`MAX_FILES = 500`, enforced at `:154` and `:169`); (3)
  `scripts/architecture/03-execution-system/00-code-graph-analysis/code-graph-analyzer.py:68`
  (`MAX_FILES = 500`, enforced at `:137` and `:152`); (4) `langgraph_engine/parsers/config.py:11`,
  retained in the list as a DEAD-CODE cleanup item only, NOT as a functional truncator -- deleting it
  removes the trap that produced the 19-file error, but changes no behaviour. Sites 2 and 3 were
  confirmed present at those lines by this pass. A fifth cap at
  `langgraph_engine/build_dependency_resolver/parsers.py:682` is deliberately deferred to v2.1 as a
  different defect class.

  **Scope note, MEASURED 2026-08-01.** `parsers/config.py:17` declares `SUPPORTED_EXTENSIONS` as
  `.py`, `.java`, `.ts`, `.tsx`, `.kt`. A repository scan excluding `.venv/`, `.git/` and
  `node_modules/` finds **411 `.py` files and ZERO `.java`, `.ts`, `.tsx` or `.kt` files**. Any
  coverage figure that treats this as a four-language codebase is describing a capability, not a
  measured corpus. This SRS pass verified the current tree only; it did NOT and could not verify the
  2026-03 tree from which the published four-language figures originate. Note that pre-existing
  four-language claims elsewhere in this document (section 2 "Included", FR-3, FR-3's acceptance
  criterion, and the Implementation Status checklist) are NOT edited here -- rules/44 forbids editing
  existing SRS content, so they are flagged in `docs/phase-5-srs/srs_update_report.md` and left for
  their owner.

  **Dependency.** FR-21 is discovery. FR-38 is resolution. Fixing FR-21 alone yields a larger graph
  that is still misleading; see FR-38.

**FR-22:** The system SHALL select agents and skills by querying the knowledge graph, with zero agent
or skill name appearing as a string literal anywhere on the selection code path outside test fixtures.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` FR-10 (Deliverable D4)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. Blocked on FR-21 -- a selector built on a truncated call graph would
  pass its own tests against worthless inputs.

**FR-23:** The system SHALL emit, for every agent the selector picks, the agent name, source domain,
matched skills, knowledge-graph edge path and confidence score.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-11 (Deliverable D4)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT

**FR-24:** The system SHALL define an explicit fallback path for the no-match and low-confidence
selection outcomes, rather than returning an unexplained empty result.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-12 (Deliverable D4)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT

**FR-25:** The system SHALL conform to the model fallback protocol (haiku -> sonnet -> opus ->
escalate) when a selected model is rate-limited.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-13 (Deliverable D4); `~/.claude/rules/model-fallback.md`
- Added: 2026-08-01
- Status: The rule exists as a standing behavioural contract at `~/.claude/rules/model-fallback.md`
  (global only -- no repo-relative copy). Selector-side conformance is DESIGNED, NOT BUILT.

**FR-26:** The system SHALL ship an installable plugin manifest at `.claude-plugin/plugin.json` with
an explicit semver `version`, bundling commands, agents and skills only.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` FR-14 (Deliverable D5); ADR-008, ADR-019
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. Scope amendment recorded explicitly rather than absorbed silently:
  under ADR-019 one-step install covers commands, agents and skills only. MCP-backed capabilities
  (the FR-35 push gate, the progress writer) require the separate FR-37 `register-mcp` step. No
  hand-edited `settings.json` is involved either way, so "no manual surgery" still holds in full,
  but "one step" no longer covers the complete capability set.

**FR-27:** The system SHALL resolve, by empirical measurement rather than inference, the five plugin
schema unknowns that gate packaging design.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-14a (Deliverable D5)
- Added: 2026-08-01
- Status: BUILT AND COMPLETE. All 5 items MEASURED, none provisional;
  `docs/phase-1-architecture/plugin_schema_spike.md` exists (verified 2026-08-01). This is the only
  entry in this block that is not designed-but-unbuilt.

**FR-28:** The system SHALL contain zero home-directory string defaults classified as CODE by an
AST-based classifier, excluding `src/utils/path_resolver.py` itself, and zero absolute path literals.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-15 (Deliverable D5)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT, AND DELIBERATELY UNSIZED. Two differently-derived measurements of the
  remediation surface (13 live-code sites via AST, roughly 95 via a line-oriented grep) remain
  unreconciled; `hld_v2.md` OAQ 6 leaves this UNRESOLVED BY DESIGN. No count is asserted here. The
  classifier's own output is the evidence artifact.

**FR-29:** The system SHALL bundle library routing registries and dispatchable-agent personas as a
pinned build-time snapshot, not a live workspace checkout and not a duplicate of all agent
directories, with a `CLAUDE_PLUGIN_DEV_MODE=1` escape hatch.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-16 (Deliverable D5); ADR-007
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT

**FR-30:** The system SHALL pass an explicit `encoding=` argument at every text-mode `open()` call
site, including the mode-less `open(path)` form, across the 19 confirmed sites.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-17 (Deliverable D5)
- Added: 2026-08-01
- Status: BUILT and MEASURED 2026-08-03 (V2-019, #275). The 19-site count is no longer quoted: an
  AST scan re-derived it repository-wide -- wider than the scope the figure was originally taken at
  -- and returned exactly 19, matching the enumerated list in
  `docs/phase-0-reverse-engineering/path_violations.md` one for one. All 19 now pass `encoding=`.
  `scripts/verify_open_encoding.py` enforces this and is wired into CI; it reports UNDECIDABLE
  rather than passing silently on a dynamic mode or `**kwargs`.

**FR-31:** The system SHALL leave zero plugin-attributable functional residue after
`claude plugin uninstall` -- no MCP tool the plugin registered remains callable in a fresh session.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-18 (Deliverable D5)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT, AND NARROWED. The original bar ("no orphaned files, MCP registrations,
  or settings entries") was measured unachievable by any plugin design: `claude plugin uninstall`
  empties `enabledPlugins` and `extraKnownMarketplaces` to `{}` rather than removing them, and leaves
  an `.orphaned_at`-marked cache directory that `claude plugin prune` does not reclaim. Both are
  Claude-Code-owned behaviours with no plugin-side interception point. The residue is covered by
  FR-36 instead of asserted absent.

**FR-32:** The system SHALL record a non-empty post-plugin disposition for each of the 14 genuine
policy orphans that map to no SRS requirement.
- Priority: Medium
- Source: `docs/phase-0-requirements/prd-v2.md` FR-20 (Deliverable D1)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. Residual polish beyond what D1's approved audit already recorded
  defers to v2.1.

**FR-33:** The system SHALL bring each of the 7 dead Stop-hook script references to exactly one of
two recorded end states -- the script exists and its guard evaluates true, or the reference is deleted
and the lost capability carries a disposition in the FR-12/NFR-10 ledger. A dangling reference to an
absent file is not an acceptable end state.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-21 (Deliverable D6)
- Added: 2026-08-01
- Status: Root-caused, DESIGNED, NOT BUILT. `hooks/stop_notifier/core.py` exists on disk (verified
  2026-08-01); the claim that 7 of its 9 referenced scripts are absent is quoted from `prd-v2.md`
  and was not independently re-verified by this SRS pass.

**FR-34:** The system SHALL append to `SRS.md` a superseding record that retires SRS FR-9's
four-hook-event guarantee and states the v2.0.0 replacement guarantee, without editing FR-9's
original text.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` FR-22 (Deliverable D6)
- Added: 2026-08-01
- Status: PARTIALLY SATISFIED BY THIS APPEND. The FR entries, the NFR entries, the revised AC-9 and
  this Change Log entry are delivered here. One element of FR-34's own acceptance criterion is NOT
  yet satisfiable: it requires a Change Log row "dated to the PR that deletes PreToolUse/PostToolUse",
  and that PR does not exist as of 2026-08-01. That row remains outstanding and must be appended at
  cutover.

**FR-35:** The system SHALL make the version-push gate reachable as a named MCP tool, with the
existing assertions in `tests/test_push_gate.py` passing against the MCP code path, in a commit that
lands BEFORE the commit deleting `hooks/pre_tool_enforcer/`.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` FR-23 (Deliverable D6); ADR-017
- Added: 2026-08-01
- Status: Disposition MANDATED (`port-to-MCP`, no other value passes review); port is DESIGNED, NOT
  BUILT. Both `hooks/pre_tool_enforcer/policies/push_gate.py` and `tests/test_push_gate.py` exist on
  disk (verified 2026-08-01). Ordering is enforced by ADR-017's CI assertion on
  replacement-reachability, which is itself DESIGNED, NOT BUILT.

**FR-36:** The system SHALL publish a user-run uninstall-residue runbook naming, by exact path, every
item that survives `claude plugin uninstall`, with manual removal steps for each.
- Priority: Low
- Source: `docs/phase-0-requirements/prd-v2.md` FR-24 (Deliverable D5)
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT (`docs/guides/uninstall-residue.md` verified absent 2026-08-01). This
  is deliberately a documentation deliverable, not an executable command: no plugin-side execution
  point exists after uninstall completes.

**FR-37:** The system SHALL provide a `register-mcp` command that writes user-scope MCP server
registrations by merge-against-fresh-read, and a matching `unregister-mcp` command that reverses it.
- Priority: Critical
- Source: `docs/phase-2-validation/hld_v2.md` ADR-019, sized as mandatory v2.0.0 scope in
  `docs/phase-0-requirements/product-sequencing-v2.md` section 2c. NOT a numbered PRD requirement --
  it has no FR number in `prd-v2.md` and is carried here because the MVP boundary makes it mandatory.
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT -- zero lines of code exist. Under ADR-019 this is the ONLY path to any
  MCP-backed capability, because the plugin ships no `.mcp.json`.

**FR-38:** The system SHALL NOT bind an ambiguous bare method-name call target to an arbitrary
first-match candidate, and SHALL report a high-confidence edge count alongside the raw fan-in count
wherever fan-in is consumed as a risk signal.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` FR-9b (Deliverable D4). Numbered FR-9b in the PRD, not
  FR-25, because FR-25 is already claimed by a proposed CI check in
  `docs/phase-2-validation/advisory_items.json`, and because FR-9a is call-graph DISCOVERY blindness
  while FR-9b is call-graph RESOLUTION incorrectness -- same engine, same fix window.
- Added: 2026-08-01
- Status: Root-caused and source-verified 2026-08-01; fix DESIGNED, NOT BUILT.

  **Mechanism, VERIFIED against source by this pass.** `langgraph_engine/parsers/graph_model.py:265`
  returns `candidates[0]` when a bare simple method name matches multiple known method FQNs and none
  is in the caller's file. That is an arbitrary first-match bind with no disambiguation and no
  confidence marker. The neighbouring `len(candidates) == 1` branches at `:253-254` and `:263-264`
  are legitimate; `:265` is the defect. The dotted-target path at `:243-255` correctly returns the
  target unresolved when ambiguous, so the defect is specific to bare names.

  **Measured consequences.** MEASURED at runtime by two independent agents that encountered this
  separately; NOT re-derived by this SRS pass. `list.append()` binds to `JsonlAppender.append`
  (`src/mcp/base/persistence.py:222`) at in-degree 1592. `str.format()` binds to
  `ErrorMessages.format` (`langgraph_engine/error_messages.py:568`) at in-degree 755-756 -- the two
  agents measured 755 and 756, and the one-edge discrepancy is recorded as a range rather than
  resolved to a single figure this pass cannot adjudicate. `dict.get()` and `dict.set()` bind to
  `_MemoryLayer.get` and `_MemoryLayer.set` (`langgraph_engine/cache_system.py:101` and `:113`).
  All three target classes were confirmed to exist at those paths by this pass. 55.5 percent of
  cross-file "resolved" call edges are name-collision artifacts. Of 26,114 total edges: 18,608
  unresolved plus 2,853 dropped for builtin-name collision plus 433 dropped for cross-file ambiguity
  equals 21,894, leaving 4,220 high-confidence. That enumeration reconciles to the stated total
  exactly (26,114 minus 21,894 equals 4,220) and the arithmetic was checked here; the underlying
  measurements were not re-run.

  **Why this is v2.0.0 scope and not cosmetic, VERIFIED against source by this pass.**
  `langgraph_engine/sdlc_pipeline/call_graph_analyzer.py:56-67` (`_classify_risk`) classifies risk
  PURELY by caller count -- low 0-2, medium 3-7, high 8+ -- with no other input. `danger_zones`
  (built at `:303`) and `hot_nodes` (built at `:1197`) are likewise caller-count-only. Precision
  correction to the defect as originally relayed: `_classify_risk`'s 8+ threshold sets the per-method
  `risk` label (`:292`) and the overall risk verdict, whereas the `danger_zones` and `hot_nodes`
  membership gate is a separate `n >= 5`. Both are caller-count-only, which is the load-bearing
  point, but they are not the same threshold. Those counts derive from an impact map built over
  `graph.get_edges()` (`:155`, `:455`, `:600`, `:1209`), and `get_edges()`
  (`graph_model.py:282-286`) returns `_resolved_edges` when populated, which
  `langgraph_engine/parsers/call_graph_builder_legacy.py:96` does populate on every build. The
  collided edges therefore reach the analyzer. From there
  `langgraph_engine/sdlc_pipeline/architecture/prompt_gen_expert_caller.py:179-182` reads
  `risk_level`, `danger_zones`, `affected_methods` and `hot_nodes`, and substitutes them into the
  Step 1 orchestration template at `:204-207`. Consequence: `JsonlAppender.append` currently ranks as
  the codebase's top danger zone on the strength of every `list.append()` call in the repo, and the
  planning prompt has been receiving noise as risk signal.

  **FR-21 alone is INSUFFICIENT.** SRS FR-21 (PRD FR-9a) fixes discovery -- which files the builder
  sees. Fixing discovery without fixing resolution produces a LARGER graph that is still misleading:
  more files feeding the same broken resolver, and a higher collided in-degree on the same wrong
  nodes. FR-38 does not supersede FR-21 and FR-21 does not subsume FR-38. Both must land, and FR-38
  must not be scheduled after FR-21 on the assumption that a bigger graph is a better one.

  **Consumer trap, named separately and explicitly NOT part of this defect.**
  `resolve_edges()` (`graph_model.py:194-223`) writes its output to `self._resolved_edges` (`:222`)
  and never back to `graph.edges`, so any consumer reading `graph.edges` directly receives raw
  unresolved edges. This divergence does NOT affect shipping code -- the analyzer reads
  `get_edges()`, which returns `_resolved_edges` -- and is recorded here only so that a future
  consumer does not reach for `.edges` and silently get a different graph. It must not be conflated
  with the FR-38 defect.

---

### 3.2 Non-Functional Requirements


#### NFR-1: Performance

- **Hook Mode target:** Steps 0-3 complete in < 60 seconds
- **Full Mode target:** All 9 active steps complete in < 170 seconds
- **Template fast-path:** Bypasses Step 1 entirely, jumps directly to Step 2
- **Token savings:** 60-85% reduction via AST navigation + dedup
- **Status:** Implemented

#### NFR-2: Extensibility

- Adding a new pipeline level: implement subgraph, call `PipelineBuilder().add_my_level()`
- Adding a new routing rule: add function to `routing/` package, register in orchestrator
- Adding a new integration: extend `AbstractIntegration` in `integrations/`
- Adding a new UML diagram: extend `AbstractDiagramGenerator` in `diagrams/`
- Adding a new language parser: extend `AbstractLanguageParser` in `parsers/`
- **Status:** Implemented via 9 modular packages (v1.5.0)

#### NFR-3: Reliability

- Checkpoint recovery: pipeline can resume from any step after crash
- Signal handling: Ctrl+C triggers graceful recovery with checkpoint save
- Non-blocking integrations: Jira/Figma/Jenkins failure does not abort pipeline
- Error propagation: `node_error_handler` decorator standardizes all node failures
- **Status:** Implemented

#### NFR-4: Backward Compatibility

- All existing imports continue to work unchanged:
  - `from langgraph_engine.flow_state import FlowState` (shim re-exports from `state/`)
  - `from langgraph_engine.uml_generators import generate_all` (shim re-exports from `diagrams/`)
  - `from langgraph_engine.call_graph_builder import CallGraphBuilder` (shim re-exports from `parsers/`)
- **Status:** Implemented

#### NFR-5: Platform Compatibility

- Python 3.8+ on Windows (cp1252-safe ASCII-only source files), Linux, macOS
- Cross-platform paths via `path_resolver.py`
- UTF-8 encoding throughout; no non-ASCII characters in `.py` files
- **Status:** Implemented

#### NFR-6: Security

- API keys read from `.env` file, never hardcoded
- Input sanitization before LLM calls
- GitHub tokens scoped to minimum required permissions
- **Status:** Implemented (hardening ongoing)

---

#### v2.0.0 Non-Functional Requirements (APPENDED 2026-08-01, per rules/44 section 4.1)

**Numbering.** NFR-1 through NFR-6 above are unchanged and unedited. Next available is NFR-7, so this
block runs NFR-7 through NFR-12 (6 entries). The same collision warning applies as for the FR block:
`docs/phase-0-requirements/prd-v2.md` has its own independent NFR-1..NFR-5 series, which are NOT the
same requirements as SRS NFR-1..NFR-5. Each entry names its source.

**Build status.** All 6 entries below are DESIGNED, NOT BUILT as of 2026-08-01.

**NFR-7 (Performance / Resource):** The system SHALL contribute zero processes attributable to the
plugin in an idle session, measured as an OS-level process-list delta taken before and after 10 tool
calls in a fresh session with the plugin installed but never invoked.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` NFR-1; ADR-018, ADR-019
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. Two binding measurement constraints: (a) the count is attributed per
  component, and exactly one exclusion is permitted -- the retained user-level Stop and Notification
  hooks, which the plugin never owned; (b) the measurement window must not span a response-turn
  boundary, because the retained Stop hook fires every turn. The plugin bundles ZERO MCP servers
  (ADR-019); a `.mcp.json` at the plugin root containing any server entry fails this requirement
  outright regardless of the process count, because bundled stdio servers were MEASURED to spawn
  eagerly on plugin enable with zero tool calls made.

**NFR-8 (Reliability / Liveness):** The system SHALL contain no unconditional fixed wall-clock timeout
on the long-running pipeline path. Liveness SHALL instead be enforced by five non-temporal mechanisms:
an attempt-count or iteration bound, lease renewal, a convergence (no-progress) signal, a per-
dependency circuit breaker with non-fixed reopen-wait, and full-jitter retry.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` NFR-2; ADR-016
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT, AND WIDER IN SCOPE THAN HOOK DELETION. Deleting the hooks satisfies
  only the hook half of this defect. `hld_v2.md` ADR-016 names 6 application sites across 5 engine
  files plus 3 definition sites that are on the pipeline path and untouched by hook deletion,
  including a composed 75-second wall-clock abort on the Step 1 path. Those line references are
  quoted from `hld_v2.md` and were not re-verified against source by this SRS pass. Exactly one
  exception is permitted: a single-call socket or HTTP level I/O timeout that raises a retryable
  error into the circuit breaker rather than aborting the enclosing pipeline task.

**NFR-9 (Reliability / Durability):** The system SHALL preserve the "resume from any step after
crash" guarantee across hook deletion, and SHALL NOT back that guarantee with a best-effort write.
- Priority: Critical
- Source: `docs/phase-0-requirements/prd-v2.md` NFR-3; ADR-011
- Added: 2026-08-01
- Status: The writer is NOT a new component. `langgraph_engine/checkpoint_manager.py::CheckpointManager`
  already exists, is already wired at every step boundary by `langgraph_engine/core/step_decorator.py`,
  and survives hook deletion untouched -- what dies with PostToolUse is per-tool-call progress
  telemetry, which is finer-grained than any SRS step guarantee. Three durability defects are
  DESIGNED, NOT BUILT: (1) `step_decorator.py:169` currently swallows a checkpoint-save failure with
  a warning and continues, and must instead raise or set a `checkpoint_degraded` flag the resume path
  refuses to trust; (2) the progress replacement must be a projection of the checkpoint record, never
  an independent second writer; (3) replay must be idempotent on a session-id-plus-step-number key
  for side-effecting steps. All component and line references in this entry are quoted from
  `hld_v2.md` OAQ 1 and were not re-verified against source by this SRS pass.

**NFR-10 (Governance / Traceability):** The system SHALL record a decided, non-"disappeared"
disposition for every one of the 25 capabilities enumerated in the capability-loss ledger, verified by
a script that fails if any name is missing or its disposition cell is empty.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` NFR-4
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. Precondition satisfied (the ledger exists and names 25 capabilities);
  none of the 25 yet carries a decided disposition.
- Count superseded 2026-08-02 (owner ruling): the figure "25" above is retained as originally written
  but is NO LONGER correct. The ledger enumerates **27** capabilities (16 + 9 + 2), and the PreToolUse
  table is **16 PreToolUse components (14 policy gates plus the daemon and registry mechanism)**, not
  14. See the revised NFR-10 in section 4. The "none yet carries a decided disposition" clause is
  unaffected and still holds.

**NFR-11 (Testability):** The system SHALL have three independent automated lifecycle tests --
install, invoke and uninstall -- each asserting on plugin-attributable delta only, never on whole-file
equality against a pre-install snapshot.
- Priority: High
- Source: `docs/phase-0-requirements/prd-v2.md` NFR-5
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT, but UNBLOCKED -- the blocking spike (FR-27) is complete. The invoke
  test SHALL exercise two steps, not one: `/plugin install` followed by `register-mcp` (FR-37), and
  SHALL confirm the FR-35 push gate is unreachable after step one alone and reachable only after
  step two.

**NFR-12 (Security / Governance):** The system SHALL protect the migration's one genuinely unsafe
transition -- `PreToolUse` deleted while no MCP push gate is registered -- with a mechanical control
wherever an interception point exists, and SHALL NOT rely on runbook wording alone.
- Priority: Critical
- Source: `docs/phase-2-validation/hld_v2.md` ADR-020, with the runbook at `hld_v2.md` section 10.
  NOT a numbered PRD requirement -- ADR-020 post-dates `prd-v2.md` and is carried here because it is
  the security control that FR-13's deletion makes necessary.
- Added: 2026-08-01
- Status: DESIGNED, NOT BUILT. Three layers, each matched to what its path permits, and NONE of the
  three currently exists as code:
  1. PREVENT on the path the plugin owns: `unregister-mcp` (FR-37) refuses by default when
     `PreToolUse` is absent from `settings.json`, names the consequence, and proceeds only under an
     explicit acknowledgement flag.
  2. DETECT on the manual-edit path, which has no interception point: a `doctor` command plus a cheap
     start-up precondition check in every FR-17 command, emitting one unmissable line when
     `PreToolUse` is absent and no MCP push gate is registered.
  3. PREVENT THE HARM rather than the configuration state: a git `pre-push` hook (proposed, not
     required) blocking the non-compliant push regardless of configuration, with ADR-017's CI
     assertion as the detective repository-level backstop.
- Residual risk, stated rather than rounded away: on the manual-edit path, at the moment of the edit,
  documentation genuinely is the only available control -- no interception point exists and none can
  be created without reintroducing a hook, which ADR-010 forbids. Layer 2 bounds how long the
  undetected state persists to a single plugin invocation; it does not prevent it.
- Unmeasured assumption carried forward: the `/plugin uninstall` path is INFERRED safe, not measured
  safe. No entry written by `register-mcp` was present during the measured uninstall, because
  `register-mcp` does not exist yet. If the inference is wrong, that path has no available control at
  all -- neither prevention nor detection -- and the git `pre-push` hook must be promoted from
  proposed to required. A verification task is attached to whoever implements `register-mcp`.

---

## 4. Acceptance Criteria

One criterion per functional requirement, per rules/44 section 2.

| Requirement | Acceptance Criterion |
|---|---|
| FR-1 | `create_flow_graph()` builds Level 0, Level 1 and Level 2 in order, and a run with any single level removed still reaches a terminal node. |
| FR-2 | A full-mode run executes Steps 0-8 in order; with `CLAUDE_HOOK_MODE=1` it stops after Step 3 and reports the remaining steps as skipped. |
| FR-3 | The call graph resolves classes and methods for Python, Java, TypeScript and Kotlin sources, and Steps 0 and 5 read impact data from it rather than rebuilding it. |
| FR-4 | With an integration flag unset its steps are skipped without error; with it set the Create -> Update -> Close transitions all fire, and a failure in one integration does not abort the others. |
| FR-5 | Levels can be added or removed by editing `create_flow_graph` alone, with no change to any node module. |
| FR-6 | Every registered MCP server starts over stdio and reports its documented tool count. |
| FR-7 | Project type and framework are detected from the working tree, and the matching policy files are loaded from `policies/` before any code change is written. |
| FR-8 | An LLM call falls through Claude CLI to the Anthropic API, and returns None rather than raising when no provider is available. |
| FR-9 | All four hook events fire, and a blocking policy returns exit code 2 from the PreToolUse hook so the tool call does not proceed. |

---

### Revised Acceptance Criterion for FR-9 (APPENDED 2026-08-01, per rules/44 section 4.2)

The FR-9 row in the table above is retained verbatim and is NOT deleted. It is superseded, not
corrected: it was accurate for v1.21.x and becomes false the moment FR-13 lands. Recorded here so
that the falsification is deliberate and dated rather than silent.

**AC-9 (Updated 2026-08-01):** From v2.0.0 onward, of the four hook events named in FR-9, exactly one
-- `Stop` -- remains registered and firing; it is engine-owned and user-level, and the plugin neither
installs nor modifies it (ADR-010). `PreToolUse` and `PostToolUse` are absent from
`~/.claude/settings.json` (FR-13), and `UserPromptSubmit` is no longer the every-prompt entry point
(FR-15). The exit-code-2 blocking guarantee that FR-9's original criterion asserted is therefore no
longer available from any hook, and is replaced by three compensating controls, all of which are
DESIGNED, NOT BUILT as of 2026-08-01: (a) the version-push gate reachable as a named MCP tool once
the user has run `register-mcp` (FR-35, FR-37); (b) ADR-017's CI-side replacement-reachability
assertion, which runs in CI rather than on the user's machine and therefore protects the shared
repository regardless of any individual user's local configuration; and (c) ADR-020's refuse-by-
default guard in `unregister-mcp` plus a start-up precondition check in every FR-17 command (NFR-12).
Enforcement is opt-in per ADR-006: no policy blocks any tool call on a session where no plugin
command is invoked. This is the accepted price of removing involuntary per-tool-call execution, not a
regression to be mitigated away.

**Scope of the falsification, stated precisely.** FR-13 deletes 2 of the 4 events outright. FR-15
affects a third, `UserPromptSubmit`, by taking it off the every-prompt hot path; whether its
`settings.json` registration is deleted outright or repointed is NOT specified by any Phase 0, 1 or 2
artifact reviewed for this append, and is therefore left open here rather than guessed. The fourth,
`Stop`, is unaffected.

---

### Acceptance Criteria for the v2.0.0 Requirements (APPENDED 2026-08-01)

One criterion per appended requirement, per rules/44 section 2. Every criterion below is a target;
none is currently met, with the single exception of FR-27.

| Requirement | Acceptance Criterion |
|---|---|
| FR-10 | `docs/reports/policy-implementation-audit-v2.md` exists with exactly 46 policy rows, each carrying a non-empty Evidence cell that cites a `file:line` or an explicit `NONE`. |
| FR-11 | All 46 rows have 7 non-empty columns; a row with an empty "Post-plugin plan" cell fails. |
| FR-12 | All 15 PreToolUse-only-enforced policies carry a disposition with a one-sentence rationale; the `push_gate.py` row reads `port-to-MCP` and no other value passes review. |
| FR-13 | A fresh session shows no `PreToolUse` and no `PostToolUse` entry in `~/.claude/settings.json`, and no tool call is intercepted by either. |
| FR-14 | The ADR-006 document body cross-references all three named consequences; a consequence recorded only in `docs/orchestration_prompt.md` does not satisfy this. |
| FR-15 | A user prompt no longer invokes `scripts/3-level-flow.py`; pipeline execution begins only from an explicit FR-17 command. |
| FR-16 | The file exists on disk, its Consequence section is present and unedited from the pre-committed text, and `git log` shows it was added rather than templated with the section left blank. |
| FR-17 | Each of the 6 named entry points is invocable by name and reaches its pipeline steps; the full-pipeline command executes Steps 0 through 8 in order. |
| FR-18 | An install/uninstall cycle leaves the pre-existing user-level `Stop` and `Notification` entries byte-identical to their pre-install state. |
| FR-19 | A committed instrumentation script reports, for 20 consecutive real Stop-hook invocations, the exact subprocess count, the wall-clock duration, and which referenced scripts ran versus hit a failed existence guard; the reduced design's regression test asserts a per-turn spawn count of at most 2 unless a named exception is documented with a rationale. |
| FR-20 | The master graph header counts, the README counts and the filesystem directory counts are all three equal, and the library's validator and invariant checker both exit 0. All three numbers must match, not two of three. |
| FR-21 | Each of the 4 named sites reaches exactly one recorded end state -- migrated to the coverage-complete contract, or formally retired with the removal recorded. "Fixed the one site Phase 0 named" is explicitly NOT an acceptable end state. The regression test's canary assertion confirms the `langgraph_engine/sdlc_pipeline` package appears in builder output at its full file count. |
| FR-22 | A grep for agent-name or skill-name string literals across the selection code path returns zero matches outside test fixtures, and each of 10 sample task descriptions returns a ranked agent set where every entry carries a non-empty knowledge-graph edge path, never an empty array. |
| FR-23 | For every agent selected during a full pipeline run, the log emits all five fields; a run with any field missing or empty fails. |
| FR-24 | A task description with no viable match returns the defined fallback outcome with a stated reason, never an unexplained empty result and never a silent default pick. |
| FR-25 | A rate-limited model invocation retries at the next tier in the documented chain and escalates to the user at the top tier, rather than failing the step. |
| FR-26 | `.claude-plugin/plugin.json` exists and validates against the confirmed schema contract with an explicit semver version, and a search of the plugin tree for a `hooks/` directory or any `hooks.json` returns zero results, enforced as a CI gate at CRITICAL. Split by capability class: (a) a fresh install with `register-mcp` NOT run confirms commands, agents and skills are functional and confirms the FR-35 push gate is NOT reachable -- expected, not a defect; (b) after `register-mcp` runs, the push gate and the progress writer become reachable. |
| FR-27 | `docs/phase-1-architecture/plugin_schema_spike.md` exists with all 5 items resolved to MEASURED, none provisional. SATISFIED as of 2026-08-01. |
| FR-28 | An AST-based classifier partitions every home-directory occurrence in `langgraph_engine/`, `hooks/`, `scripts/` and `src/` into CODE, DOCSTRING or COMMENT by enclosing node type, emitting one record per occurrence; after remediation the CODE count is zero, excluding `src/utils/path_resolver.py`, which is the canonical source of these strings and is not a violation. A separate check confirms zero absolute path literals. The classifier output is the committed evidence artifact; the total and the three-way split are reported as MEASURED values and never asserted against a pre-committed number. |
| FR-29 | The plugin functions on a machine with no `claude-global-library` checkout; a staleness check against the library VERSION fires when the snapshot is behind; the release script FAILS if `CLAUDE_PLUGIN_DEV_MODE` is set in the publishing environment. |
| FR-30 | A scan for mode-less `open(` and explicit text-mode `open()` calls lacking `encoding=` returns zero matches across the confirmed sites; binary-mode calls remain excluded by the same scan's exemption list. |
| FR-31 | After uninstall, no MCP tool the plugin registered is callable in a fresh session. The test asserts the `settings.json` delta attributable to the plugin, never whole-file equality against a pre-install snapshot. The emptied bookkeeping keys and the orphaned cache directory are explicitly out of scope for this criterion and are covered by FR-36. |
| FR-32 | All 14 orphan-policy rows have a non-empty Post-plugin plan value; a script comparing the 46-row matrix against the 14-name orphan list confirms zero name mismatches and zero empty dispositions. |
| FR-33 | For each of the 7 references, either the script file exists and its guard evaluates true in a test run, or the reference is removed from `hooks/stop_notifier/core.py` and the lost capability appears with a disposition in the FR-12/NFR-10 ledger. A post-remediation grep for the 7 filenames inside `hooks/stop_notifier/` returns either a real file or zero references, never a dangling reference to an absent file. |
| FR-34 | `SRS.md` carries a new appended FR entry, not a replacement of FR-9's text, whose acceptance criterion states the v2.0.0 replacement guarantee for the removed hook events, AND `SRS.md`'s Change Log has a row dated to the PR that deletes `PreToolUse`/`PostToolUse` referencing that FR by number. The first clause is satisfied by this append; the second is NOT and cannot be until that PR exists. |
| FR-35 | The push-gate logic is reachable as a named MCP tool, the existing assertions in `tests/test_push_gate.py` or their direct equivalents pass against the MCP code path, and commit ordering verifies this landed BEFORE the PR that deletes `hooks/pre_tool_enforcer/`. |
| FR-36 | A committed runbook names, by exact path, every item measured as surviving uninstall, with manual removal steps for each; the NFR-11 uninstall test asserts the runbook exists and that its named paths match the plugin's actual marketplace and plugin name strings, with no stale placeholder text. |
| FR-37 | `register-mcp` writes user-scope registrations by merge-against-fresh-read and is reversible by `unregister-mcp`; a capability unreachable before the command becomes reachable after it, and unreachable again after the inverse. |
| FR-38 | Three assertions, all mechanically checkable. (1) A committed check enumerates every method FQN appearing in `danger_zones` or `hot_nodes` for a full-repo analysis run and FAILS if any entry's simple name collides with a Python builtin or stdlib method name AND its fan-in does not survive once collided edges are excluded. The collision list is derived from `builtins` plus the `str`/`list`/`dict`/`set` method sets, not hand-maintained. An entry whose fan-in survives exclusion is legitimate and passes -- the check is on the collision, not on the name. (2) The high-confidence edge count is reported alongside the raw count as two distinct fields at every point fan-in is consumed: `_classify_risk`'s input, `danger_zones.callers_count`, `hot_nodes.callers_count`, and all four `graph.get_edges()` consumers at `call_graph_analyzer.py:155`, `:455`, `:600` and `:1209`. A consumer that reads only one of the two numbers fails review. (3) `graph_model.py:265` no longer returns `candidates[0]` for an ambiguous bare name -- it returns either the unresolved target or a resolution explicitly marked ambiguous -- and a unit test asserts that a bare name matching 2 or more FQNs with no same-file candidate does NOT produce a confident edge. The AC deliberately does NOT assert that the 55.5 percent collision rate must fall to any specific figure: no post-fix rate has been measured, and pre-committing a target number would be a fabrication. It asserts the rate is REPORTED, and that assertions (1) and (3) hold. |
| NFR-7 | Cold and warm process counts are reported as two separate numbers, never blended; pass is a delta of 0 processes attributable to the plugin. A `.mcp.json` at the plugin root containing any server entry fails outright regardless of the count. |
| NFR-8 | A static scan for fixed timeouts returns zero unconditional matches across both bundled plugin code and the engine pipeline path; any surviving timeout is configurable and defaults to unbounded or user-overridable; the regression test asserts all 5 liveness mechanisms are present. |
| NFR-9 | A kill-the-process-mid-pipeline test confirms resume picks up at the correct step boundary using the existing checkpoint writer; a second test confirms the progress surface is a projection of the checkpoint record rather than a second writer; a third confirms replaying a side-effecting step with the same session-id-plus-step-number key produces no duplicate external effect. |
| NFR-10 | A script cross-checks all 25 capability names against the audit matrix and fails if any is missing or carries an empty or "disappeared" disposition. |
| NFR-11 | Three tests exist and pass. The install test asserts the plugin ships NO `.mcp.json` at all. The invoke test exercises two steps and asserts the reachability flip described in FR-26. The uninstall test asserts plugin-attributable delta only. |
| NFR-12 | `unregister-mcp` refuses by default when `PreToolUse` is absent and proceeds only under an explicit acknowledgement flag; a `doctor` command and every FR-17 command's start-up check emit one actionable line in the unsafe state; the idle-session process count is unaffected by the check, so NFR-7 still passes with it present. |

---

### Revised Acceptance Criterion for FR-10 (APPENDED 2026-08-02, per rules/44 section 4.2)

The `| FR-10 |` row in the table above is retained verbatim and is NOT deleted or edited. So is
FR-10's requirement statement in section 3.1, including its now-superseded "line-by-line" wording.
Both are retained because other artifacts still reference them and a reader needs the disposition,
not an absence.

**Why it was superseded: the original was UNSATISFIABLE, and not because of any shortfall in work
produced.** The requirement demanded a line-by-line read of `~/.claude/policies/` while the matrix it
feeds is keyed to `docs/policies/`. MEASURED 2026-08-02: `docs/policies/` holds **46** `.md` files;
`~/.claude/policies/` holds **44** `.md` files across 4 subdirectories, resolving to **35 distinct
basenames**; the trees share **28** basenames, so **18 of the 46 are absent from the `~/.claude/`
tree**. 46 - 28 = 18 and 28 + 18 = 46. No line-by-line read of that tree can produce evidence for 46
rows. (A figure correction is recorded with this ruling: the `~/.claude/` tree was described as
holding 32 documents; it holds 44 files / 35 distinct basenames. The 18-absent conclusion derives
from the 28-basename overlap and is unaffected.)

**Authoritative corpus, stated so no implementer has to guess.** `docs/policies/` -- 46 files,
in-repo, version-controlled -- is authoritative per ADR-009 and is what the 46 rows count.
`~/.claude/policies/` is a PARTIAL MIRROR and is not the audit's corpus.

**Runtime resolver, stated rather than assumed.** `get_policies_dir()`
(`src/utils/path_resolver.py:255-261`, module wrapper at `:389-395`) returns `{CLAUDE_HOME}/policies`,
overridable by `CLAUDE_POLICIES_DIR`. Executed on 2026-08-02, it resolves to `~/.claude/policies` --
the partial mirror -- NOT to `docs/policies/`. The ADR-009a four-branch resolver that would make
`docs/policies/` canonical is PRD FR-19, DEFERRED TO v2.1. **This criterion therefore does not depend
on the runtime resolver at all**, and an implementer must not use `get_policies_dir()` to enumerate
the corpus.

**AC-10 (Updated 2026-08-02) -- POLICY-TO-CODE MAPPING VERIFICATION.** The intent of the superseded
clause was never "read every file"; it was "prove the status classification is grounded in code
rather than asserted". This criterion tests that intent, is machine-checkable, and requires NO
re-audit of 46 policies by hand -- the evidence already exists in
`docs/phase-0-reverse-engineering/policy_enforcement_raw.json` (MEASURED 2026-08-02: `count` field
46, `records` array 46 entries). A committed verification script SHALL assert:

- **(1) Row-set identity.** The set of Policy cells in the matrix EQUALS the set of `.md` basenames in
  `docs/policies/` -- empty symmetric difference, checked as a set, not as a count of 46.
- **(2) Every row carries a Verification label** from the closed set `MEASURED` / `CITED` /
  `INFERRED`. This is the audit document's OWN already-published vocabulary
  (`docs/reports/policy-implementation-audit-v2.md:22-25`), not a new one invented here. No empty
  cell; no value outside the set.
- **(3) MEASURED rows must resolve.** Every row labelled `MEASURED` carries an Evidence cell with at
  least one `path:line` reference; the script confirms the path exists in the repository and that the
  file has at least that many lines. **This is the "grounded in code, not asserted" test**, and it is
  mechanical.
- **(4) CITED rows must attribute.** Every row labelled `CITED` names its source artifact and the
  script confirms that file exists on disk.
- **(5) `NONE` is explicit, never blank.** A row with no code grounding carries the literal `NONE` in
  Evidence, and such a row may not be labelled `MEASURED`.
- **(6) Coverage is reported honestly, and this criterion asserts on the label's PRESENCE AND
  CORRECTNESS, never on its value.** The matrix header reports the MEASURED/CITED/INFERRED split and
  the script asserts the reported split equals the split recomputed from the rows. **No minimum
  number of MEASURED rows is set, deliberately.** The audit's own disclosure (`:460`, `:506`) is that
  41 of the 46 classifications remain CITED and were not re-verified, 5 having been spot-verified
  (41 + 5 = 46). An AC demanding 46 MEASURED rows would be unsatisfiable in a new way -- which is the
  defect being corrected, not a standard to aspire to.

**Artifact status.** `docs/reports/policy-implementation-audit-v2.md` EXISTS (507 lines, 28,780
bytes, commit `bf92747`). It is BUILT and being reshaped to satisfy this criterion. It does not yet
contain a single 46-row matrix -- it currently carries several grouped tables -- so this criterion is
NOT yet satisfied, but the gap is a reshape, not a rebuild.

---

### Revised Acceptance Criterion for FR-21 (APPENDED 2026-08-01, per rules/44 section 4.2)

The `| FR-21 |` row in the table above is retained verbatim and is NOT deleted or edited. It is
superseded by the criterion below on an owner ruling dated 2026-08-01. It is retained because other
artifacts still reference its wording and a reader needs the disposition, not an absence.

**Why it was superseded, stated plainly.** The original criterion asserted on the end states of FOUR
named constants. One of the four (`langgraph_engine/parsers/config.py:11`) is dead code read by
nothing, and the criterion OMITTED `langgraph_engine/parsers/graph_model.py:43` entirely -- a cap
that binds and that survives any fix to the file cap. An implementer working strictly to the original
criterion would have fixed four sites, one of them dead, watched every assertion pass, and left a
binding truncation in production. The original also asserted on *constants*, and constant-inspection
is exactly the failure mode that produced this defect: reading `config.py:11` and concluding the cap
had been found is what 19 files across every phase did.

**AC-21 (Updated 2026-08-01):** Every assertion below is on the OUTPUT of an actual in-process build.
No assertion may be satisfied by inspecting the value of a constant. A committed regression test
SHALL construct the builder against the project root, run `.build()`, and assert:

- **(A) Discovery is coverage-complete.** The set of files in the builder's analysed set EQUALS the
  set of eligible source files independently enumerated by the test's own oracle -- set equality with
  an empty symmetric difference, not a comparison against a hardcoded number.
- **(B) The named canary is whole.** The symmetric difference between the enumerated
  `langgraph_engine/sdlc_pipeline/` files and the analysed `langgraph_engine/sdlc_pipeline/` files is
  empty. MEASURED baseline 2026-08-01: that tree holds 45 files and the shipping builder analyses
  **0 of 45** -- the entire Level 2 SDLC Execution Core is invisible. The 300-file budget is
  exhausted five files before the tree begins (first `sdlc_pipeline` file at discovery index 304).
- **(C) No traversal truncation is emitted.** Log capture over the
  `langgraph_engine.parsers.graph_model` logger during the build contains ZERO records matching
  `hit max_paths=` and `limit; results truncated`. **This is the load-bearing assertion and the
  reason this correction exists:** that warning fired on BOTH probe runs, including the run with the
  file cap fully lifted. A fix satisfying (A), (B) and (D) but not (C) is precisely the half-fix this
  correction was written to prevent, and must fail the gate.
- **(D) Regression floor, grounded in MEASURED post-fix figures.** With the caps lifted the probe
  measured `files_analyzed=411`, `total_classes=480`, `total_methods=3506` (also `functions=1340`,
  `call_edges=26114`, `resolved_edges=7004`). The test asserts `>= 411`, `>= 480`, `>= 3506` -- a
  floor rather than equality, so legitimately adding source files cannot fail the suite while any
  regression toward the truncated shipping figures (300 files, 449 classes, 2,844 methods) does. The
  exact 2026-08-01 values are recorded in the test as the documented baseline.
- **(E) The silent-no-op trap is closed.** The test SHALL NOT establish the fix by rebinding the
  module global `call_graph_builder_legacy.MAX_FILES`. The probe MEASURED that rebinding the module
  attribute is a silent no-op -- still 300 files -- because `max_files=MAX_FILES` binds at def-time,
  whereas the constructor kwarg and `__init__.__defaults__` patching both reach 411. A fix
  implemented as a module-global edit, or a test that "proves" the fix that way, fails this criterion.
- **(F)** "Fixed the one site Phase 0 named" remains NOT an acceptable end state -- carried forward
  from the superseded criterion, which was correct on this point.

**Assertion target, corrected.** The two sites that bind are
`langgraph_engine/parsers/call_graph_builder_legacy.py:64` (`MAX_FILES = 300`, defaulted into
`CallGraphBuilder.__init__` at `:76`, stored at `:79`, enforced at `:107` and `:118`) and
`langgraph_engine/parsers/graph_model.py:43`
(`DEFAULT_MAX_PATHS = _env_int("CLAUDE_CG_MAX_PATHS", 500)`, applied at `:320-321`, enforced at
`:354`, `:357` and `:388`, warning emitted at `:390-392`). Both were re-verified on disk by this
pass. `langgraph_engine/parsers/config.py:11` is DROPPED from the assertion set -- it may be deleted
as dead-code cleanup, but deleting it asserts nothing and must not be counted as progress.

**Site accounting, so the count matches its enumeration.** 17 distinct truncation sites exist; 2
bind. The 15 that do not: 1 dead file-count cap (`parsers/config.py:11`); 1 dormant duplicate with no
importers (`sdlc_pipeline/architecture/00-code-graph-analysis/code_graph_analyzer.py:73`); 1
live-but-non-binding file-count cap above the corpus size and off the UML path
(`scripts/architecture/03-execution-system/00-code-graph-analysis/code-graph-analyzer.py:68`, value
500 against 411 files on disk); 4 file-size caps with MEASURED-ZERO impact, since no source file in
the repo exceeds 100 KB; 1 non-binding traversal cap (`graph_model.py:42`, `DEFAULT_MAX_DEPTH = 30`,
observed depths 11 and 7); 2 different-class truncators that do not participate in call-graph
construction (`build_dependency_resolver/parsers.py:681-682`, `sdlc_pipeline/code_explorer.py:453`);
and 5 downstream diagram truncators that sit after discovery. 1 + 1 + 1 + 4 + 1 + 2 + 5 = 15;
15 + 2 = 17.

**Sizing impact, FLAGGED and deliberately NOT applied here.** `docs/phase-6-sprint/github_issues.json`
issue V2-009 carries size 5 (`size_provenance: SOURCED`, WSJF 4.60), estimated against a two-site
constant-change assumption. Assertions (A), (B), (C) and (E) add a runtime probe harness, an
independent enumeration oracle, log capture, and a negative test for the def-time binding trap. This
pass judges that 5 no longer holds. It is not re-pointed here; re-sizing is product-manager-agent's
call.

**Interaction with FR-38.** FR-21 is discovery, FR-38 is resolution. Satisfying this criterion alone
produces a LARGER graph that is still misleading, because the same ambiguous-name resolver runs over
more files. Both must land.

---

### Revised Acceptance Criterion for NFR-10 (APPENDED 2026-08-02, per rules/44 section 4.2)

The `| NFR-10 |` row in the table above is retained verbatim and is NOT deleted or edited. So is
NFR-10's requirement statement in section 3.2, including its now-superseded figure of 25. Both are
retained because other artifacts still reference them and a reader needs the disposition, not an
absence.

**Why it was superseded: the capability count was WRONG, and the descriptor that produced it was
wrong in the same way.** MEASURED 2026-08-02 against
`docs/phase-0-reverse-engineering/capability_loss.md`, which is machine-generated, carries a
do-not-edit-manually banner, and is itself CORRECT: the ledger holds three tables whose data rows are

| Table | Owner package | Data rows |
|---|---|---|
| PreToolUse capabilities lost | `hooks/pre_tool_enforcer/` | 16 |
| PostToolUse capabilities lost | `hooks/post_tool_tracker/` | 9 |
| Cross-cutting capability lost | `hooks/policy_tracking_helper.py` | 2 |

16 + 9 + 2 = **27**. The superseded figure computed 14 + 9 + 2 = 25. It counted only the **14 policy
gates** in the PreToolUse table and dropped two further full table rows that carry their own owner
and requirement cells:

- `capability_loss.md:33` -- **warm-daemon fast path**, owner `daemon.py`
  (`ensure_daemon_running`, `run_daemon`, `try_daemon_fast_path`), Requirement **NFR-1
  (Performance)**.
- `capability_loss.md:34` -- **PolicyRegistry**, ordered fail-open policy-check dispatch, owner
  `registry.py`, Requirement **FR-9 (mechanism)**.

The ledger is internally consistent and states the composition in its own prose at `:36`: *"All 14
policy checks plus the daemon and registry mechanism that runs them go dark together."* The citation
chain read that "plus 2" as the cross-cutting section and dropped these two rows.

**The descriptor is corrected, not only the total.** Wherever the composition is described it now
reads **16 PreToolUse components (14 policy gates plus the daemon and registry mechanism)**. The
phrase "14 PreToolUse gates" is what generated the undercount; correcting 25 to 27 while leaving that
descriptor standing would regenerate the same error at the next recomputation. A related descriptor
in `docs/REVIEW-INDEX.md` read "14 PreToolUse gates, 9 PostToolUse capabilities", which totals 23,
and is corrected by the same ruling.

**NFR-10 (Updated 2026-08-02):** A script cross-checks all **27** capability names against the audit
matrix and fails if any is missing or carries an empty or "disappeared" disposition. The 27 names are
the union of the three tables above; the script SHALL derive them by enumerating the ledger's table
rows, never from a hardcoded total, so that a future row added to `capability_loss.md` cannot pass
unnoticed.

**Gate status, stated so nobody misreads this correction as a completion.**
`scripts/verify_policy_capability_dispositions.py` already derives 27 by enumeration and correctly
FAILS on the 25 citation; it was not edited by this ruling, because changing a gate to agree with a
document is backwards. It exits 1 today and continues to exit 1 after this correction: the
capabilities still lacking a decided disposition are a separate owner decision and are NOT part of
this count correction.

---

## 5. Out of Scope

Explicitly excluded, to prevent scope creep:
- Web UI / GUI (CLI-only)
- Direct database writes (all DB access via MCP tools)
- Custom LLM training or fine-tuning
- Real-time collaboration between multiple users simultaneously

### Deferred out of v2.0.0 to v2.1 (APPENDED 2026-08-01)

Recorded so that a reader does not assume these ship with the appended v2.0.0 requirement set. Source:
`docs/phase-0-requirements/product-sequencing-v2.md` section 4, "Defers to v2.1" (5 items).

1. The four-branch `get_policies_dir()` resolver (`prd-v2.md` FR-19). Deliberately NOT given an SRS FR
   number in this append. It is blocked on a human sign-off with no target date -- the five-policy
   merge decision, which includes 3 permanent deletions totalling 1,864 irrecoverable lines outside
   git -- and canonicalising the resolver before that merge would make the affected files unreachable
   by any branch. It has no effect on NFR-7 and no gate depends on it.
2. REBUILDING (not retiring) any of the 5 dead Stop-hook capabilities that the FR-19 decision session
   selects for rebuild. The decision itself, the instrumentation, and retirement of every capability
   not selected all ship in v2.0.0.
3. Rebuild (not retirement) of the session-memory, session-pruning and git-auto-commit maintenance
   policies. Retirement of the broken reference, which is what closes the correctness defect, ships
   in v2.0.0.
4. Residual orphan-disposition polish beyond what the approved D1 audit already recorded.
5. Marketplace listing polish beyond bare install and uninstall mechanics.

Also deferred, on a different basis: the fifth discovery truncation site at
`langgraph_engine/build_dependency_resolver/parsers.py:682`. It returns a truncated boolean from a
directory-detection helper rather than a truncated graph, is ruled a different defect class by
`hld_v2.md` OAQ 4, and its absence from FR-21's four-site closure requirement is deliberate, not an
oversight.

---

## 6. Change Log

| Date | Version | Task | Change Summary | Status |
|------|---------|------|----------------|--------|
| 2026-07-30 | 1.21.2 | Restructure SRS to rules/11 + rules/44 | Numbered sections adopted; Acceptance Criteria, Out of Scope and this Change Log added; three claims corrected against the working tree (TOON removed in v1.15.2, `pipeline_builder.py` deleted in favour of `create_flow_graph`, hook entry points live in `hooks/`). | Done |
| 2026-08-01 | 1.21.5 | v2.0.0 requirement append -- functional requirements (Phase 5, `prd-v2.md` FR-22) | Appended FR-10 through FR-38 (29 entries) covering the v2.0.0 MVP boundary. 27 map to a numbered requirement in `docs/phase-0-requirements/prd-v2.md`; FR-37 (`register-mcp`/`unregister-mcp`) has no PRD number and is carried from `hld_v2.md` ADR-019 because `product-sequencing-v2.md` section 2c makes it mandatory v2.0.0 scope; FR-38 (call-graph resolver defect) was added 2026-08-01 by owner ruling after this row was first written. PRD FR-19 deliberately not carried -- deferred to v2.1. Nothing above FR-9 was edited or removed. All 29 are DESIGNED, NOT BUILT except FR-27 (plugin schema spike, complete). **Count corrected 2026-08-02:** this row read "FR-10 through FR-37 (28 entries)" and "All 28", written before FR-38 was appended and not updated when it was. Verified by enumeration: 29 entries, FR-10..FR-38 inclusive. | Done |
| 2026-08-01 | 1.21.5 | v2.0.0 requirement append -- non-functional requirements (Phase 5) | Appended NFR-7 through NFR-12 (6 entries). NFR-7..NFR-11 map to `prd-v2.md` NFR-1..NFR-5. NFR-12 is new: the ADR-020 three-layer push-gate precondition control (prevent where the plugin owns the action, detect where it does not, prevent the harm via a git pre-push hook), carried because it is the security control that FR-13's hook deletion makes necessary and it post-dates `prd-v2.md`. All 6 are DESIGNED, NOT BUILT; NFR-12's three layers have zero lines of code. Nothing above NFR-6 was edited or removed. | Done |
| 2026-08-01 | 1.21.5 | Supersede SRS FR-9's four-hook-event acceptance criterion (Phase 5, `prd-v2.md` FR-22) | Appended a revised AC-9 per rules/44 section 4.2. The original FR-9 row in section 4 is retained verbatim and was NOT deleted. FR-13 deletes 2 of FR-9's 4 hook events outright, which falsifies the original criterion; FR-15 affects a third by taking it off the hot path, with its exact end state left open rather than guessed. The exit-code-2 blocking guarantee is replaced by three compensating controls, all recorded as DESIGNED, NOT BUILT. Also appended acceptance criteria for FR-10..FR-37 and NFR-7..NFR-12, and a v2.1 deferral list under section 5. | Done |
| 2026-08-01 | 1.21.5 | Add FR-38 -- call-graph resolution correctness (Phase 5 follow-up, `prd-v2.md` FR-9b) | The project owner ruled a newly-found defect IN v2.0.0 scope. Appended SRS FR-38 and its acceptance criterion. Defect: `langgraph_engine/parsers/graph_model.py:265` binds an ambiguous bare method name to `candidates[0]`, so `list.append()` resolves to `JsonlAppender.append` (in-degree 1592), `str.format()` to `ErrorMessages.format` (in-degree 755-756), and `dict.get()`/`set()` to `_MemoryLayer`. 55.5 percent of cross-file resolved edges are collision artifacts. Because `call_graph_analyzer.py:56-67` classifies risk purely by caller count and feeds `danger_zones`/`hot_nodes` into the Step 1 planning template via `prompt_gen_expert_caller.py:204-207`, the planning prompt has been receiving noise as risk signal. Numbered FR-9b in the PRD, not FR-25 (already claimed in `advisory_items.json`). All source claims verified against the working tree by this pass; the runtime edge counts were measured by two other agents and are labelled as not re-derived. FR-21 alone is recorded as INSUFFICIENT. A `resolve_edges()`/`graph.edges` divergence is named as a consumer trap and marked as NOT affecting shipping code. | Done |
| 2026-08-01 | 1.21.5 | Correct the FR-21 truncation-site citation (Phase 5 follow-up) | IN-PLACE CORRECTION, disclosed rather than silent, and confined strictly to content this same pass appended earlier today -- no content that predates 2026-08-01 was edited. FR-21's status line originally cited `langgraph_engine/parsers/config.py:11` as the binding truncation site, quoting `hld_v2.md` OAQ 4. VERIFIED wrong: that constant is dead code, re-exported by `parsers/__init__.py:22` and read by nothing. The binding cap is `parsers/call_graph_builder_legacy.py:64`, enforced at `:107` and `:118`. The same wrong citation appears in 19 files across every phase; only this document's own line was corrected, and the other 18 are reported as unowned in `docs/phase-5-srs/srs_update_report.md`. Also added to FR-21 a MEASURED scope note: 411 `.py` files and ZERO `.java`/`.ts`/`.tsx`/`.kt` files exist in this repo, so four-language coverage figures describe a capability, not a corpus. Pre-existing four-language claims elsewhere in this document were NOT edited, per rules/44. | Done |
| 2026-08-01 | 1.21.5 | Supersede FR-21's acceptance criterion; require runtime proof (Phase 6 owner ruling) | Appended a revised AC-21 per rules/44 section 4.2. The original `| FR-21 |` row in the acceptance-criteria table is retained VERBATIM and was neither deleted nor edited. Reason for supersession: the original asserted on four constants, one of which (`parsers/config.py:11`) is dead code, and omitted `parsers/graph_model.py:43` (`DEFAULT_MAX_PATHS`, default 500) -- a cap that binds and survives fixing the file cap, so an implementer working to the original would have passed every assertion and shipped a binding truncation. The revised criterion asserts on the OUTPUT of an in-process build, never on a constant: set-equality discovery oracle, the `langgraph_engine/sdlc_pipeline` 45-file canary (0 of 45 today), a log-capture assertion that no `hit max_paths=... limit; results truncated` record is emitted (load-bearing -- it fired on BOTH probe runs even with the file cap lifted), a regression floor of 411 files / 480 classes / 3,506 methods, and a negative test closing the silent-no-op trap where rebinding the module global does nothing because defaults bind at def-time. 17 truncation sites total, 2 binding, 15 non-binding enumerated. Figures sourced from `docs/phase-5-uml/callgraph_coverage_probe.md` (MEASURED-RUNTIME); both binding sites re-verified on disk here. V2-009's 5-point size is flagged as no longer sufficient and deliberately not re-pointed. | Done |
| 2026-08-02 | 1.21.5 | Re-scope FR-10's acceptance criterion; correct a stale artifact status (Phase 8 owner ruling) | Appended a revised AC-10 per rules/44 section 4.2. The original `| FR-10 |` row in the acceptance-criteria table and FR-10's requirement statement in section 3.1 are both retained VERBATIM; neither was deleted or reworded. Reason: the original demanded a line-by-line read of `~/.claude/policies/` while the matrix it feeds is keyed to `docs/policies/`. MEASURED 2026-08-02: `docs/policies/` = 46 files, `~/.claude/policies/` = 44 files / 35 distinct basenames, overlap 28, so 18 of the 46 are absent from that tree and the two clauses could not both be satisfied. Replaced with a POLICY-TO-CODE MAPPING VERIFICATION of 6 machine-checkable assertions that test the original intent -- that a classification is grounded in code rather than asserted -- and require no hand re-audit. The criterion asserts on the presence and correctness of a `MEASURED`/`CITED`/`INFERRED` label, never on its value, and sets no minimum MEASURED count, because the audit itself discloses 41 of 46 remain CITED. Records that `docs/policies/` is authoritative and that `get_policies_dir()` resolves to the partial mirror (verified by execution), so the criterion does not depend on the runtime resolver. **Separately, an IN-PLACE CORRECTION confined to content this same author appended on 2026-08-01:** FR-10's status line asserted the audit artifact was "verified absent 2026-08-01". That was true when checked and is now FALSE -- `docs/reports/policy-implementation-audit-v2.md` exists at 507 lines / 28,780 bytes, commit `bf92747`, written later the same day. Corrected in place with the supersession disclosed inline, so nobody closes FR-10 against a false premise of absence. No content predating 2026-08-01 was touched. | Done |
| 2026-08-02 | 1.21.5 | Correct the capability count from 25 to 27, and the descriptor that produced the error (Phase 8 owner ruling) | Appended a revised NFR-10 per rules/44 section 4.2. The original `| NFR-10 |` row in the acceptance-criteria table and NFR-10's requirement statement in section 3.2 are both retained VERBATIM; neither was deleted or reworded, and a dated supersession pointer was appended beneath the requirement's Status bullet. Reason: MEASURED 2026-08-02 against `docs/phase-0-reverse-engineering/capability_loss.md`, the ledger's three tables hold 16 + 9 + 2 = **27** data rows, not 25. The 25 figure computed 14 + 9 + 2 -- it counted only the 14 policy gates in the PreToolUse table and dropped two further full rows carrying their own owner and requirement cells: `daemon.py` (warm-daemon fast path, NFR-1, ledger line 33) and `registry.py` (PolicyRegistry ordered fail-open dispatch, FR-9 mechanism, ledger line 34). The ledger states the composition correctly in its own prose at line 36 and was NOT edited -- it is machine-generated, carries a do-not-edit-manually banner, and is the source that proves 27. **The descriptor was corrected alongside the total, which is the load-bearing half of this ruling:** "14 PreToolUse gates" is what generated the undercount, so every document describing the composition now reads "16 PreToolUse components (14 policy gates plus the daemon and registry mechanism)"; correcting the total alone would regenerate the error on the next recomputation. A related descriptor in `docs/REVIEW-INDEX.md` totalling 23 was corrected by the same ruling. `scripts/verify_policy_capability_dispositions.py` was NOT edited -- it already derives 27 by enumeration and correctly fails on the 25 citation; it exits 1 before and after, because the capabilities still lacking a decided disposition are a separate owner decision outside this correction. | Done |
| PENDING -- date of the PR that deletes PreToolUse/PostToolUse | 2.0.0 | FR-34 completion row (NOT YET ADDED) | `prd-v2.md` FR-22's acceptance criterion requires a Change Log row dated to the PR that deletes `PreToolUse`/`PostToolUse`, referencing the superseding FR by number (SRS FR-34). That PR does not exist as of 2026-08-01, so this row cannot be dated and is recorded here as an explicit outstanding obligation rather than being back-dated or omitted. | OUTSTANDING |
| 2026-08-04 | 1.21.5 | FR-34 completion row -- hook-registration deletion executed (V2-030, GitHub #286) | **Discharges the OUTSTANDING obligation in the row immediately above, which is retained VERBATIM and was NOT edited** -- rules/44 section 4.3 is append-only, that row was appended 2026-08-01 by a different pass, and this document's in-place-correction carve-out extends only to content the same author appended the same day. `prd-v2.md` FR-22's acceptance criterion (`prd-v2.md:149`) asks for a row "dated to the PR that deletes PreToolUse/PostToolUse", referencing the superseding FR by number: SRS **FR-34**. **NO PULL REQUEST EXISTS, AND NONE IS CITED HERE.** The deletion landed as a direct commit on branch `docs/segregate-docs-tree`: commit `2e371f6` ("feat: delete the hook registrations, gate the pipeline on explicit invocation"), authored and committed 2026-08-04T16:27:39+05:30 = 2026-08-04T10:57:39Z, both timestamps read from `git log`. This row is dated to that commit rather than to a PR, and no PR number is invented, because a fabricated citation is unverifiable and worse than an absent one. **The DATE is not in dispute under any reading:** the settings mutation itself is MEASURED at `~/.claude/settings.json` mtime 2026-08-04T10:05:53.76Z; the commit is at 2026-08-04T10:57:39Z; and a PR raised from this branch cannot carry a date earlier than the commit it contains, so 2026-08-04 is a floor. Only the identifier, not the date, is lost by the PR's absence. **When a PR is opened, append a follow-up row citing its number -- do not edit this row.** **THE CRITERION SAYS "the two removed hook events" AND THAT IS UNDERSTATED: THREE registrations were removed** -- `PreToolUse` and `PostToolUse` (FR-13) plus `UserPromptSubmit` (FR-15). The third went by project-owner ruling rather than by issue text: V2-027's criteria name only the first two, and V2-028's criterion needs `UserPromptSubmit` gone but was forbidden from touching settings; both authors found that gap independently. Recording only two would make this SRS disagree with the machine, so three are recorded and the criterion is reported as needing amendment. This also CLOSES the question the revised AC-9 above deliberately left open ("whether its `settings.json` registration is deleted outright or repointed is NOT specified ... and is therefore left open here rather than guessed"): it was deleted outright. AC-9 is NOT falsified by that -- its assertion that `UserPromptSubmit` "is no longer the every-prompt entry point" holds -- so AC-9 is under-specified rather than wrong, and is deliberately NOT edited or re-superseded here. **Live end state MEASURED 2026-08-04 by reading `~/.claude/settings.json` read-only (this pass wrote no settings file):** `hooks` contains `Stop` and `Notification` ONLY; `mcpServers` holds 26 entries with `push-gate` present, so the FR-35 replacement was reachable before the gate it replaces was removed, which is the ordering ADR-017 exists to enforce. Hook SOURCE FILES were deliberately NOT deleted -- only registrations -- so `hooks/pre_tool_enforcer/` remains on disk and the equivalence tests keep running instead of self-skipping. The Version cell reads 1.21.5 because `VERSION` still reads 1.21.5 (measured 2026-08-04); the pending row above anticipated 2.0.0 and that bump has NOT occurred. | Done |

---

## Project Context
- **Domain:** Software Development Automation / DevOps
- **Target Users:** Solo developers, engineering teams using Claude Code CLI
- **Deployment:** Local machine, triggered by Claude Code hooks on every user prompt
- **Integration Points:** GitHub, Jira (Cloud+Server), Figma, Jenkins, SonarQube, Anthropic API

---

## Architecture & Design


### System Architecture

```
User Prompt
    |
    v
[UserPromptSubmit Hook] -> scripts/3-level-flow.py
    |
    v
[LangGraph StateGraph] (orchestrator.py)
    |
    +-- Level 0: Pre-Flight Sanity Guard (Unicode, encoding, path checks)
    |
    +-- Level 1:  Session & Context Synchronization (session, complexity scoring)
    |
    +-- Standards (non-numbered, always-on): project detection, policy loading from disk
    |
    +-- Level 2:  SDLC Execution Core (9-step pipeline)
            |
            +-- Step 0: CallGraph pre-analysis + template fast-path detection
            +-- Step 1: Template fill + orchestration execution (2 subprocess calls)
            +-- Integration lifecycle (Jira/Figma/Jenkins/SonarQube)
            +-- MCP tool calls (13 servers, 295 tools)
```

### Technology Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Orchestration | LangGraph | 0.2.0+ | Stateful graph execution with conditional routing |
| LLM Framework | LangChain | 0.1.0+ | LLM abstraction, prompt templates |
| MCP Protocol | FastMCP (mcp) | 1.0+ | Stdio JSON-RPC tool protocol |
| Language | Python | 3.8+ | Primary implementation language |
| Testing | pytest | 7.0+ | 75 test files, 1,608 passing tests |
| AST Analysis | Python ast | stdlib | Call graph extraction for Python |

### Package Architecture (v1.5.0 Modularization)

| Package | Pattern | Files | Replaces |
|---------|---------|-------|---------|
| `core/` | Decorator + Factory | 7 | 25+ copy-pasted loguru blocks, 9 integration hooks, 15+ step wrappers |
| `state/` | — | 6 | `flow_state.py` (1,131 lines monolith) |
| `routing/` | — | 5 | Routing functions embedded in `orchestrator.py` |
| `helper_nodes/` | — | 6 | Helper node functions embedded in `orchestrator.py` |
| `diagrams/` | Strategy | 15 | `uml_generators.py` (1,556 lines monolith) |
| `parsers/` | Abstract Factory | 8 | `call_graph_builder.py` (1,419 lines monolith) |
| `sonarqube/` | Facade | 6 | `sonarqube_scanner.py` (1,639 lines monolith) |
| `integrations/` | Abstract Factory + Template | 7 | Scattered lifecycle code in 3+ files |
| `pipeline_builder.py` | Builder | 1 | `create_flow_graph()` inline in orchestrator |

---

## Implementation Status


### Completed Features (v1.15.1)

- [x] 4-Level pipeline (Level -1, 1, 2, 3)
- [x] 8-step active SDLC automation (Pre-0, Step 0, Steps 8-14)
- [x] 13 MCP servers (295 tools)
- [x] Template-driven orchestration (single planning LLM call)
- [x] Hybrid LLM inference (2 providers: claude_cli, anthropic)
- [x] AST call graph analysis (4 languages)
- [x] 13 UML diagram types
- [x] Jira full lifecycle integration
- [x] Figma design-to-code integration
- [x] Jenkins CI/CD integration
- [x] SonarQube scan + auto-fix loop
- [x] Hook system (4 hook types)
- [x] Policy system (63 policies)
- [x] Token optimization (60-85% savings)
- [x] Session management + TOON compression
- [x] Checkpoint recovery
- [x] **Modular architecture: 9 packages, design patterns** (v1.5.0)
- [x] Backward-compatible shims for all refactored modules

### In Progress

- [ ] Code coverage measurement (pytest --cov, 70% threshold)
- [ ] GitHub Actions CI pipeline
- [ ] Docker containerization

### Planned

- [ ] PyPI package (`pip install claude-workflow-engine`)
- [ ] CLI interface (`cwe run "fix the bug"`)
- [ ] Configuration wizard for first-time setup
- [ ] Multi-region / team deployment

---

## Testing Strategy


### Unit Testing

- Framework: pytest
- Test files: 75
- Passing: 1,608 tests
- Coverage target: 70%+

### Integration Testing

- Full pipeline integration tests at `tests/integration/`
- MCP server tests: `pytest tests/test_*mcp*.py`
- CallGraph tests: `pytest tests/test_call_graph_builder.py tests/test_call_graph_analyzer.py`

### Known Failing Tests (Pre-existing)

- `tests/test_recovery_handler.py::test_save_step_checkpoint_success` — pre-existing fixture issue

---

## Deployment & Operations


### Deployment Process

1. Developer runs `git clone` and `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, fill in API keys
3. Run `python scripts/sync-mcp-servers.py` to register MCP servers in `~/.claude/settings.json`
4. Pipeline triggers automatically via Claude Code hook on every user prompt

### Operational Requirements

- **Monitoring:** Per-step JSONL telemetry, metrics aggregator CLI (`metrics_aggregator.py`)
- **Logging:** Structured loguru / stdlib logging throughout
- **Recovery:** Checkpoint at every step boundary; resume via `--resume` flag
- **Backup:** Session data backed up to `BackupManager` on each checkpoint

---

## Risks & Mitigation


| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| All LLM providers fail | High | Low | 4-provider fallback chain; pipeline halts gracefully |
| Jira/Figma API unavailable | Low | Medium | Non-blocking; pipeline continues without that integration |
| Large codebase exceeds CallGraph limits | Medium | Low | MAX_FILES=300, MAX_FILE_SIZE_KB=100 in `parsers/config.py` |
| Windows encoding issues | Medium | Low | ASCII-only .py files; path_resolver.py for cross-platform paths |

---

**Last Updated:** 2026-09-13
**Next Review:** 2026-06-21

---
