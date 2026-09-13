# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Removed
- **`docs/standards/` (52 files).** It duplicated the Claude rules in `~/.claude/rules/` and had drifted: 8 files were older than the live rules, and 6 existed only in the repo. The 6 repo-only files (java, csharp, django, flask, spring-boot, TOOL-OPTIMIZATION) moved to `~/.claude/rules/` with `paths:` frontmatter. `load_framework_standards()` and `load_language_standards()` in `standards/selector.py` now read `~/.claude/rules/`, and `TestRuleFilePaths` reads it too, skipping where it is not installed. (#320)

## [2.1.0] - 2026-08-07

**Step 1 emits its prompt instead of executing it, and three things that were only
documented became things that are also checked.** The engine runs inside a hook
subprocess, so it cannot act in the session it is serving -- it can only hand that
session something to run. Phase 2's TODO decomposition and per-TODO agent execution
re-derived work the master template already specifies, and did so fail-silently, so
both are gone along with the three scripts behind them.

MINOR rather than MAJOR: every removal below was verified to have no caller or
reader before it was made, and `runtime_verification`'s two dropped exports had no
consumer outside their own tests. It is not the v2.0.0 situation, where every
installation was affected and none upgraded silently.

The through-line of the release is that **enforcement beats audit**. The audit that
scheduled this work missed a doc-count gap of 99 files, a flag promised in five
documents and implemented in none, and two documentation fixes that survived only
inside an orphaned package. Tests found all four.

### Added

- **Step 1 now verifies the orchestration prompt it emits.** `verify_orchestration_prompt()` existed, was exported and had four unit tests, and was called by nothing; it is now wired in at the point the prompt is stored, and its findings are recorded on `orchestrator_result["prompt_warnings"]` and logged. The gap it closes is narrow and specific: both degraded paths in the node already log (an `ERROR` from prompt-gen, and an empty response), so this is not for those. It is for a response that is **non-empty and therefore silent** but not a usable prompt — a truncated template, the wrong file, a stub — which until now was indistinguishable from a good one. Warnings are never fatal: `STEP1_CONTRACT` documents the short raw-task fallback as a legitimate degraded path, and it trips both checks by design, so failing here would convert a recoverable run into a dead one.

### Removed

- **`langgraph_engine/helper_nodes/` is deleted** (5 modules, 538 lines). All nine of its public node functions were also defined in `orchestrator.py`, which is the module the graph actually wires, and nothing imported the package -- it was an extraction that was started and never completed. Two documentation corrections existed **only** in the orphaned copy and were ported to `orchestrator.py` before the deletion rather than discarded with it: `save_workflow_memory`'s comment named `~/.claude/memory/sessions/` while its code writes to `memory/logs/sessions/`, and `optimize_context_after_level1` still said "Level 3" in three places, a level that stopped existing in the `06b0463` rename. The live module had the stale text in both cases.

- **Step 1 no longer decomposes or executes the prompt it emits** (fb7bbaa). Phase 2 ran `todo_decomposer` to split the orchestration prompt into a TODO list and `orchestrator_agent_caller` once per TODO, each a nested `claude -p` subprocess. Both re-derived work that belongs elsewhere: the master template's STEP 13 already produces the MULTI-AGENT PROMPT BUNDLE, and the node runs inside a hook subprocess, so it cannot execute in the session it is serving -- it can only hand that session something to run. `orchestrator_result` now records what was emitted (`mode`, `prompt_chars`, `template_source`, `library_version`) rather than what was executed. An empty dict would have satisfied the contracts equally well, but `flow_trace_converter` and `decision_explainer` both read the field to build reports, and handing them a hollow value to keep a postcondition green is how a trace starts lying about what happened.
- **The three Step 1 Phase 2 scripts are deleted** (c1d1d47): `todo_decomposer.py`, `todo_executor.py`, `orchestrator_agent_caller.py`, together with `tests/test_todo_decomposition.py` (27 tests, which imported them directly and covered nothing else). They had no caller after fb7bbaa. Dead code that still looks live is worse than absent code -- the next reader would have found three plausible scripts describing an execution model the pipeline no longer has.
- **Four FlowState fields dropped** (e59a271): `todo_list`, `todo_results`, `completed_todos`, `current_todo_index`. With the scripts gone they had neither a writer nor a reader anywhere in the engine. `completed_todos` additionally declared an `_merge_lists` parallel-write reducer for a value no node produces.
- **`ORCHESTRATOR_CONTRACT` and `verify_orchestrator_result()` retired** (94cbaf7), along with `_MIN_RESULT_LEN` and `_ERROR_PREFIXES`, which existed solely for the latter. The contract is also removed from `NODE_CONTRACT_REGISTRY`: a registry is a `node_name -> contract` lookup, so it was offering a contract under a key nothing can produce. `verify_orchestration_prompt()` is kept -- it has no production caller either, but unlike its sibling it encodes a true contract.

### Fixed

- **`FORCE_GRAPH_REBUILD` now exists in code, not only in documentation.** The variable was described in five files -- `CLAUDE.md`, `ADR-002`, the deployment guide, `RUNBOOK_STALE_GRAPH.md` and the troubleshooting guide -- and read by nothing, since `a43595b` (2026-03-28). RUNBOOK Option B tells an operator to `export FORCE_GRAPH_REBUILD=1` while recovering from a stale-graph incident, and that command did nothing. It is now honoured by `refresh_call_graph_if_stale()`, which rebuilds unconditionally when it is `1`. This matters for the exact case ADR-002 names as its own risk and the stale flag cannot cover: when `call_graph_stale` is never set because the node that sets it crashed, the guard cannot fire and Step 5 reviews an outdated snapshot in silence — with no in-state signal for an operator to correct, so the override must come from outside the state. Implementing it made the ADR, the deployment guide and the troubleshooting guide true as written; none needed editing.
- **`RUNBOOK_STALE_GRAPH.md` Option A described behaviour the flag never had.** It implied that `FORCE_GRAPH_REBUILD=0` disabled stale-based rebuilding and that unsetting it re-enabled it. Stale rebuilding is driven by the `call_graph_stale` state flag and no environment variable; the override only ever *adds* a rebuild. Corrected, and pinned by a test so the wording cannot drift back.
- **`CLAUDE.md` documented the wrong default for `ENABLE_CI`.** The table said `false`; `ci.yml` reads `vars.ENABLE_CI` and falls back to `true`, so CI runs unless explicitly disabled. The row now also records that it is a repository variable rather than a process environment variable, which is why it behaves unlike every other flag in that table.

- **A dormant runtime-contract bug that predated this work** (fb7bbaa, 6982930). The `step0 -> step8` transition guard declared `orchestrator_result` as a `str` of at least 50 characters; the node has always written a `dict`, and `node_contracts.py` described it correctly as a dict -- so the two disagreed with each other and one disagreed with reality. It never fired only because `ENABLE_RUNTIME_VERIFICATION` defaults to `0`, which means the first operator to enable verification would have hit a failure that had nothing to do with their change. `verify_orchestrator_result()` carried the same `str` premise and is removed above.
- **A guard test that was pinning the bug rather than the behaviour** (6982930). `test_guard_step1_to_step2_pass` fed the guard a 60-character string -- exactly what the wrong spec asked for -- so it would have stayed green no matter how wrong the spec became. A positive test alone cannot detect a wrong type, because it builds its input from the same mistaken premise. Paired with a negative case asserting that a `str` `orchestrator_result` is reported as a violation, verified capable of failing by reverting the spec and watching it go red.
- **Step 1 Phase 2 no longer claims success it did not have** (e0d9372). `call_execution_script` reports failure as a status dict rather than raising, so the `try/except` meant to catch a failing decomposer could not fire and its warning never logged. Every script-level failure fell through to an empty TODO list with no diagnostic, after which the result was written with a hardcoded `"success": True` -- a decomposer that never ran was indistinguishable from a task with nothing to do.

### Changed

- **Live documentation now describes the emit-only Step 1** (7ed4a0d and this batch): the pipeline flow and Key Components table in `CLAUDE.md`, the Mermaid diagram and directory tree in `README.md`, and the Step 1 node in `docs/architecture/PIPELINE_ARCHITECTURE.md`. `CLAUDE.md` also stopped advertising `STEP1_PROMPT_GEN_TIMEOUT` and `STEP1_TODO_DECOMPOSER_TIMEOUT`, which ADR-016 retired from the code. Point-in-time records under `docs/phase-*/`, `docs/reports/` and `docs/releases/` still name the deleted files and are deliberately left alone -- rewriting them would falsify the history rather than correct it.
- **The forked orchestration template is deleted** (0eceeae, 7ed4a0d). Step 1 resolves `ORCHESTRATION_TEMPLATE.md` from `claude-global-library` through the 3-tier resolver, with no fallback: a missing library aborts the step rather than degrading. `templates/orchestration_system_prompt.txt` was a 198-line fork missing nine of the master's steps, STEP 7's mandatory anti-hallucination layer among them.
- **NFR-2's ADR-016 site enumeration is split rather than trimmed** (c1d1d47). Three of the five named files were deleted, which would have failed `test_the_named_adr_016_sites_no_longer_carry_a_fixed_timeout` on `unreadable`. The names are kept: surviving files are still scanned for fixed timeouts, retired ones are asserted absent, so a retired file reappearing fails just as a surviving file regressing would.
- **The `sdlc_pipeline` call-graph canary floor moves 45 -> 44 -> 41** (59f2a41, c1d1d47), matching the templates purge and this deletion. Lowering a canary is normally how a regression gets buried; it is safe here only because completeness is proven independently by `test_canary_symmetric_difference_is_empty`, which compares the analysed set against a live enumeration of the tree.

## [2.0.0] - 2026-08-04

**The hooks are gone.** `PreToolUse`, `PostToolUse` and `UserPromptSubmit` are no longer
registered in the user-scope `settings.json`, and pipeline execution now requires an explicit
`--invoked-by=<command>` declaration naming one of six commands. A session in which no command
is invoked runs no engine code and enforces nothing. Every existing v1.x installation is
affected and none upgrades silently, which is what makes this MAJOR rather than MINOR.
`docs/guides/migration-v1.21.5-to-v2.0.0.md` is the runbook.

Reconstructed from the 67 commits in `873db04..00c31f8` (260 files, +76,680/-2,025). No
`[Unreleased]` section accumulated while the sprint ran, so this entry was rebuilt from commit
history rather than from in-flight notes; that gap is the reason the empty `[Unreleased]`
heading above now exists.

### BREAKING CHANGES

- **The three enforcement hooks are deleted from the live user-scope settings** (2e371f6). `PreToolUse`, `PostToolUse` and `UserPromptSubmit` are gone; `Stop` and `Notification` are retained and were proved byte-identical by comparing canonical-JSON digests of the entries rather than their mere presence. Verified at this release: the `hooks` object holds exactly `Stop` and `Notification`. The deletion was ordered behind a precondition -- the replacement push gate was registered and proved reachable by completing a real `tools/call` first -- because deleting `PreToolUse` while the MCP-side gate existed only in the repository and not on the machine would have left no push gate at all, reopening the bypass that `1bb4303` closed. `UserPromptSubmit` was removed by owner ruling; neither issue's written criteria called for it.
- **Pipeline execution is gated on an explicit declaration** (2e371f6, `scripts/pipeline_invocation.py`). `scripts/3-level-flow.py` refuses to run unless `--invoked-by=<command>` names one of `plan`, `implement`, `review`, `document`, `release` or `run-pipeline`. The declaration is a command-line argument and deliberately not an environment variable: the engine spawns `claude` CLI subprocesses and every one of them would inherit a variable, making an authorization nobody granted. There is no escape hatch, no filename exemption and no opt-out flag. An absent declaration exits 0 (nobody asked for a run); a declaration that was attempted with the wrong name exits 2 (a typo that would otherwise silently cost a whole run).
- **Enforcement is no longer automatic** (ADR-006, 7173bda). Nothing is enforced on a session where no command is invoked. This is the intended trade-off of the hook-free design, not a regression, and it is the change a v1.x user will notice first.
- **The plugin bundles zero hooks and zero MCP servers** (ADR-010, ADR-019; 902d1d0). Installing the plugin adds commands, agents and skills only. No MCP-backed capability exists until `register-mcp` is run, so an enabled-but-uninvoked plugin contributes no processes to a session.

### Added

- **Installable plugin** (902d1d0) -- `.claude-plugin/marketplace.json` catalog plus a `plugin/` tree carrying ten commands: the six pipeline entry points above, plus `about`, `doctor`, `register-mcp` and `unregister-mcp`.
- **`register-mcp` and `unregister-mcp`** (d4a06dc) -- opt-in MCP registration written by merge-against-fresh-read, with `unregister-mcp` refusing by default when `PreToolUse` is absent, since that combination leaves a machine with no local push gate at all.
- **ADR-020 three-layer push-gate control** (88bb5e9) -- prevention on the one path the plugin owns, detection on the manual-edit path that has no interception point, and a corrected refusal message that had been stating something false.
- **The push gate as an MCP tool, and six explicit entry points** (0900fff) -- the FR-23 replacement for the deleted `PreToolUse` gate.
- **`assert_push_gate_reachable` CI assertion** (f893fd2) -- the third and last R-1 precondition, in a workflow that declares no path filters so a docs-only commit cannot skip the sequencing gate it protects.
- **Eight verification gates**, all wired into CI: `verify_policy_audit_matrix`, `verify_policy_orphan_dispositions`, `verify_policy_capability_dispositions`, `verify_open_encoding`, `verify_home_paths`, `verify_no_fixed_timeouts`, `verify_plugin_conformance` and `verify_push_gate_reachable` (5e287ff, 918561c, b9b8128, 6aab1fc, 7d324bb, 7c98147, 7edba10, 115d827, f893fd2). The plugin-conformance workflow runs both a negative control (it plants a hooks artefact and fails the build if the gate accepts it) and a specificity control (it fails if the gate rejects content violating nothing).
- **NFR-11 install / invoke / uninstall lifecycle tests** (e9f7059) and a ledger-driven uninstall residue attribution (c0e1c0a), with the by-hand cleanup procedure in `docs/guides/uninstall-residue.md` (7c98147).
- **Knowledge-graph-driven agent and skill selection** (92053ff, 90e6125) -- selection with no hardcoded names, plus a degraded-outcome path and FR-23 explainability.
- **Model-fallback tier escalation** (32febbc) -- escalates on rate-limit errors only, never as a preference switch.
- **Per-component process-count measurement harness** for NFR-1 (28cd530).
- **The v2.0.0 document set** -- PRD v2 and product sequencing (7699e89), the Phase 1 HLD (bee6135), the Phase 2 delta HLD and consensus record (d5b575f), the review index (6141d93), the sprint plan and 37 issue drafts (7b29820), and `SRS.md` appended with FR-10..FR-38 and NFR-7..NFR-12 (6df37d9).

### Changed

- **The checkpoint durability contract is stated rather than assumed** (463451e), alongside a census of what the retained `Stop` hook actually does.
- **Fixed pipeline timeouts replaced** (115d827). The v1.20 step renumbering had silently voided the per-step timeout table: it was keyed on the pre-v1.20 numbering, the live wrapped steps intersected it at exactly one entry, and a test was pinning the stale table and passing.
- **Every home-directory occurrence classified, and the 33 code sites remediated** (7edba10), under a gate that now keeps them out.

### Removed

- **Generated UML and draw.io diagrams are no longer tracked** (ddd40ec) -- 13 `.drawio` files, per `rules/45` section 2, which requires both output directories to be gitignored.
- **Seven dead `Stop`-hook references retired** (115d827).

### Fixed

- **CallGraph bound builtin-named calls to same-named project methods** (43083ee), and both binding truncation caps were lifted with runtime proof (135b4f1).
- **The Level 0 auto-fix corrupted the source it was scanning** (557a025), and the preflight guard failed on its own test fixtures because it classified drive paths without regard to the enclosing node (7ee370a).
- **Version strings had drifted from `VERSION` again** (1919bdb).
- **Fifty rotted citations re-anchored** across the phase artifacts (0691ec1), plus a premise-staleness sweep of batches B-H (78f398f) -- a class of defect where a document's line references still resolve but no longer point at what they claim.

### Known issues carried into this release

- **`scripts/settings-config.json` still registers all three deleted hooks** (REVIEW-INDEX 46; re-verified at this release: its `hooks` object holds `PreToolUse`, `PostToolUse`, `UserPromptSubmit` and `Stop`). It is the template a machine's `settings.json` is bootstrapped from, so a fresh setup re-creates exactly what this release removed. No gate catches it. The migration guide names this explicitly.
- **The durable checkpointer does not exist at runtime** (REVIEW-INDEX 42; re-verified: `langgraph.checkpoint.sqlite` and `langgraph_checkpoint_sqlite` both raise `ModuleNotFoundError`, while `requirements.txt:31` declares `langgraph-checkpoint-sqlite>=1.0.0`). Requesting a durable checkpointer silently returns an in-memory one.
- **The retained `Stop` hook attempts a pull request on every response turn** (REVIEW-INDEX 40, escalated then partly de-escalated by REVIEW-INDEX 45). Two independent conditions currently stand between it and doing so. Restoring either missing import without first revisiting the trigger conditions would make it open real PRs unprompted, once per turn, on any feature branch.
- **The three ADR-009b policy deletions did not ship.** `docs/phase-2-validation/hld_v2.md` section 10 names them as "the irreversible part of v2.0.0" (1,864 lines). Measured across `873db04..00c31f8`, the only deletions in this release are the 13 generated diagram files above; `policies/` and `docs/policies/` are byte-unchanged. The migration this release actually ships therefore has no irreversible step of that kind.
## [1.21.5] - 2026-07-31

### Changed

- **`docs/` was 160 files in one flat directory, so nothing indicated what any document was.** Standards, pipeline policies, ADRs, runbooks, one-off audit reports, per-release design notes and the GitHub community files all sat side by side at `docs/*.md`. They are now segregated into nine folders -- `standards/` (52), `policies/` (46), `architecture/` (17), `reports/` (20), `guides/` (14), `releases/` (6), `contributing/` (5), plus the pre-existing `api/` and `phase-1-architecture/`. Classification used an objective signal wherever one existed rather than name-guessing: a file whose name also appears in `~/.claude/rules/` is a standard and one that appears in `~/.claude/policies/` is a policy, which covered 98 of the 160. Every move went through `git mv`, so history follows the files. `docs/README.md` is a new index naming what each folder holds and why.

### Fixed

- **`load_framework_standards()` and `load_language_standards()` would have stopped resolving any bundled standard.** Both build their path as `<repo>/docs/<filename>` at runtime, so the segregation above silently emptied the framework tier (flask, django, spring-boot) and the entire language tier (all six languages `detect_project_type()` recognises). Runtime-assembled paths are invisible to a grep for `docs/<file>.md`, which is how the first reference sweep missed them. Both now read `docs/standards/`, verified by loading all nine bundled documents.
- **`_bump_version_and_changelog()` wrote to `docs/CHANGELOG-SYSTEM.md`, a file that has never existed in this repo.** The function exists to enforce the version-release-policy rule that every code push updates VERSION and CHANGELOG; instead it took the `else` branch on every run and logged "No CHANGELOG file found - skipping changelog update", so the enforcement had never once fired. It now targets the root `CHANGELOG.md` that rules/11 designates as canonical, emits a proper `## [X.Y.Z] - DATE` / `### Changed` section instead of a bare bullet, and stages the file it actually writes.
- **Four intra-`docs/` cross-links were already broken before this change** and are repaired now that link paths were being touched anyway: `TESTING_GUIDE.md` and `TESTING_SUMMARY.md` both pointed at a `CODE_QUALITY_REPORT.md` that does not exist, `TESTING_SUMMARY.md` linked `docs/TESTING_GUIDE.md` from inside `docs/` (resolving to `docs/docs/`), and `noqa-audit-todo.md` linked `../CONTRIBUTING.md` at the root when that file lives under `docs/`.
- **Nine GitHub-relative links (`../../issues`, `../../discussions`, `../../issues/212`-`217`) broke further when their files moved one level deeper.** They now use absolute repository URLs, which no directory depth can invalidate.
- **`CLAUDE.md` documented a root `rules/` directory holding "46 coding standard definitions".** No such directory exists in this repository -- zero files tracked, nothing on disk. The rules live in `~/.claude/rules/`, and the repo's readable copies are what now sits in `docs/standards/`. The Directory Layout section describes the real `docs/` tree instead.
- `README.md`'s 15 documentation links and `scripts/setup/setup_wizard.py`'s two references were repointed to the new locations. A full audit of every relative link in all 165 tracked Markdown files now reports zero unresolved targets.

## [1.21.4] - 2026-07-30

### Fixed

- **`rules/44`, `rules/45` and `rules/46` all named a package that no longer exists** -- each claims to drive a specific module ("this rule replaces hardcoded logic in ..."), and all three pointed at `langgraph_engine/level3_execution/`, renamed to `sdlc_pipeline` in v1.20. `rules/46` also routed Step 13 through `level3_execution/routing.py`, now `routing/sdlc_pipeline_routes.py`. A rule naming a module nobody can find is indistinguishable from a rule nobody implements, which is exactly how the SRS divergence in #252 went unnoticed. Every method name the three rules cite was checked and is correct; only the package path had drifted. Corrected in both copies -- the repo's `docs/` and the global `~/.claude/rules/` -- which were byte-identical before and remain so. A test now scans every rule copy for `langgraph_engine/...` references and fails when one names a path that does not exist.

---

## [1.21.3] - 2026-07-30

### Fixed

- **`rules/11`, `rules/44` and the SRS implementation described three different documents** (#252) -- both rules mandate the same numbered structure (`## 1. Purpose` ... `## 6. Change Log`) and `rules/11` states its checks block at the pre-tool gate, but **zero of those eight sections existed** in `SRS.md`. The code emitted and consumed `## Functional Requirements` / `### FR-N` instead, and `documentation_manager` located its insertion point with `existing.find("## Non-Functional Requirements")` -- matching the generator, not the rule. Since the two rules agree with each other and only the code diverged, the rules win: `SRS.md` is restructured to the mandated layout, the generator template emits it so fresh projects comply from birth, and the manager finds either spelling so pre-numbering documents still work.
- **`_update_srs` wrote every entry as the literal `FR-NEW` and never touched the Change Log** -- `rules/44` section 4 requires a numbered `**FR-{n}:**` entry with Priority/Source/Added plus one Change Log row per update. Repeated runs previously produced a document full of indistinguishable `FR-NEW` blocks. It now computes the next unused number, inserts into section 3.1, and appends the row, creating the table if absent per section 5.
- **Three claims in `SRS.md` that the working tree contradicted** -- "Session management with TOON compression" (the `toons`/`toon_schema` modules were deleted in v1.15.2; every remaining mention in the code is a removal note), `**Key Module:** pipeline_builder.py` with a `PipelineBuilder().add_level_minus1()` sample (the file is gone and no such symbol exists; `orchestrator.create_flow_graph` is the single factory), and hook entry points listed under `scripts/` (they live in `hooks/`). The restructure preserved every other line: a diff of body content shows exactly these five lines removed and all 15 FR/NFR headings intact.

---

## [1.21.2] - 2026-07-30

### Fixed

- **`git commit && git push` bypassed the VERSION rule entirely** -- a hole in the gate added earlier today, spotted when one of my own pushes sailed through a branch that changed no VERSION. Self-committing commands are exempt from the gates because a PreToolUse hook can only see the state before the command runs, but applying that exemption to the version rule meant the most common push shape never had to satisfy it. The clean-tree rule still stands down (the command is about to make the tree clean); the version rule instead widens its view to the branch's commits *plus* the changes the pending commit will carry, so a staged VERSION bump satisfies it and a branch that bumps nothing is still refused.
- **The SRS was generated somewhere nothing reads it** -- `DocumentationGenerator` created the SRS at `docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md`, a path that exists nowhere in this repo, while `documentation_manager` reads the project-root `SRS.md` and both `rules/11` (permitted root documentation files) and `rules/44` (SRS lifecycle: "Create `SRS.md` at project root") place it at the root. Since the generator creates the file when absent, a fresh project got one SRS written into `docs/` that nothing ever read, while the root `SRS.md` the manager later appends FR entries and Change Log rows to was never generated at all -- two half-documents instead of one. The generator now targets root `SRS.md`, and a test asserts it stays in step with the first entry of the manager's `_SRS_ALTERNATES`.

---

## [1.21.1] - 2026-07-30

### Fixed

- **The push gates could not block a push, and fired on commands that merely mentioned one** (#249) -- `[BLOCKED L3.10]` and `[BLOCKED L3.11]` ran from the PostToolUse tracker, which fires *after* the tool completes: the push had already reached the remote by the time the gate printed that it was blocked. Four defects in total. (1) Wrong hook event, so nothing was ever prevented. (2) Detection was `"git push" in command`, so a grep for that string, an `echo`, or a commit message mentioning it all tripped the gate -- observed repeatedly on read-only greps during this work. (3) The VERSION question was answered from a session-wide list of every edited file, which spanned repositories and included scratchpad paths. (4) On a multi-commit branch the answer changed per push, so a follow-up commit re-reported a violation the branch already satisfied. Both rules now live in `hooks/pre_tool_enforcer/policies/push_gate.py` on PreToolUse, where a non-zero result actually stops the push. The command is tokenized and a git invocation is only recognized at the command position (`cd X && git push`, `git -C X push`, `VAR=1 git push`, `sudo git push` all handled; `--dry-run` / `--delete` exempt). VERSION is checked against the branch's merge base so one bump covers every push on the branch, and the clean-tree rule is scoped to the repository being pushed and ignores untracked files so coverage artifacts cannot block. Every check fails open, and the VERSION rule only applies to a repo that actually tracks a VERSION file -- only 4 of the 25 repos in this workspace do, so without that guard the gate would have blocked every push in the other 21 permanently, with nothing to bump to satisfy it. A command that commits before pushing is exempt from both rules: PreToolUse can only see the state before the command runs, so a chained `git commit && git push` looked dirty and version-less at gate time and produced a block the user could not act on -- committing first is exactly what they had already written. Four bugs of my own were caught, the last one by the gate blocking a real push of mine: a porcelain-prefix slice truncated the first reported path by a character, and `shlex.split(posix=True)` ate the backslashes in Windows paths so `git -C C:\path
epo push` resolved to nothing and silently allowed the push.
- **`scripts/tools/sync-version.py` never propagated anything, and any argument became the project version** (#248) -- three defects, all silent. `PROJECT_ROOT` was `Path(__file__).resolve().parent.parent`, which resolves to `scripts/` rather than the repo root, so `VERSION_FILE` pointed at a non-existent `scripts/VERSION` and every markdown target reported `[SKIP] not found` while the run still exited 0. `argv[1]` was written straight into VERSION with no validation, so `sync-version.py --help` set the version to the literal string `--help` and left a stray `scripts/VERSION` behind. Targets were rewritten with `Path.write_text`, which on Windows converts the committed LF files to CRLF and turns a two-line bump into a whole-file diff. Now: root resolved three parents up, real `argparse` with semver validation that rejects before touching any file, byte-preserving writes, a missing target fails the run instead of being skipped, and the stale `docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md` target replaced with the root `SRS.md` that actually exists.
- **`scripts/tools/release.py` had the identical `parent.parent` root bug**, so it read a non-existent `scripts/VERSION` (reporting the current version as `0.0.0`) and looked for `scripts/CHANGELOG.md`.
- **`locked_json_update` raced instead of skipping when its lock was unavailable** -- `FileLock` fails open after a 5-second timeout so a lock problem can never break a tool call, but the read-modify-write then proceeded unlocked, which is exactly what produced the original `flow-trace.corrupt-*` archives. Surfaced as a flaky assertion in the new concurrency test: it passed in isolation (180/180 updates, lock acquired every time) and failed only under full-suite load. The read-modify-write is now skipped and reported as failure when the lock cannot be taken; the durable record is the append-only `flow-trace.jsonl` stream, which a single `O_APPEND` write cannot interleave. `record_policy_execution` accordingly reports success on that append rather than on the best-effort aggregate. A full-file replace under `atomic_write_text` keeps the opposite behavior deliberately -- an unlocked replace can lose an update but can never corrupt the file.
- **Version drift the broken sync had been hiding** -- `langgraph_engine/__init__.py` still declared `__version__ = "1.19.1"` and `SRS.md` said `1.20.0`. Both now match `VERSION`; a test asserts every hand-written reference agrees.

### Removed

- **`scripts/tools/bump-version.sh`** -- dead foreign code. It invoked `bump-version.py` and `update-docs.py` (neither exists in this repo) and staged `src/app.py` and `templates/base.html` (leftovers from an unrelated Flask project), on top of carrying the same off-by-one `PROJECT_ROOT`. `release.py` is the working release path.

---

## [1.21.0] - 2026-07-30

### Fixed

- **Hooks were not session-aware and fought each other over shared files** -- Claude Code passes a `session_id` in every hook stdin payload and no hook read it. Seven independent resolvers (`project_session.py`, `policy_tracking_helper.py`, `pre_tool_enforcer/loaders.py`, `post_tool_tracker/loaders.py`, `stop_notifier/voice.py`, `src/mcp/base/persistence.py`, `scripts/helpers/session_resolver.py`) each guessed the session from `.current-session.json`, a pointer file only the `session_create` MCP tool ever wrote -- so it had been frozen since 2026-03-17 while hooks kept appending to that 4-month-old session folder. Two of those resolvers were dead code: `scripts/helpers/session_resolver.py` read a `session_id` key the pointer file never had, and every resolver rejected IDs lacking a `SESSION-` prefix, which is exactly the shape of Claude's own payload UUID.
- **New `hooks/session_context.py` owns session identity** -- resolution order is bound payload `session_id` -> `CLAUDE_SESSION_ID` env -> pointer file -> legacy progress file. Each hook calls `bind_session(payload)` immediately after parsing stdin, which publishes the identity process-wide (and to child processes) so no call signature had to change. All seven resolvers now delegate to it.
- **Two incompatible session ID generators produced two folders per run** -- `context_sync/session_loader.py` minted `session-<ts>-<hex8>` and overwrote the `SESSION-<ts>-<suffix>` ID that `3-level-flow.py` had already set. Hooks validate the `SESSION-` prefix, so the engine's ID was rejected by all of them. The node now inherits the caller's ID and normalizes it; generation is a last-resort fallback only.
- **Two session roots (split brain)** -- hooks hardcoded `{memory}/logs/sessions` while `context_sync/helpers.py` fell back to `~/.claude/logs/sessions` on a failed `src/` import, leaving 569 session directories in a tree nothing read. Both sides now resolve the root through `session_context.get_sessions_root()`.
- **`flow-trace.json` corruption from concurrent read-modify-write** -- `record_policy_execution()` read, mutated and rewrote the file with no lock, from pre-tool, post-tool and stop hooks firing concurrently; one session folder held 44 `flow-trace.corrupt-*` archives (three within the same minute). Writes now run under a cross-process `FileLock` with atomic `os.replace`, plus an append-only `flow-trace.jsonl` companion stream written with a single `O_APPEND` `os.write`.
- **`session-progress.json` was one global file shared by every session and project** -- observed carrying `modified_files_since_commit` entries from `claude-global-library` while the active session was `claude-workflow-engine`. Progress is now per-session at `sessions/{SESSION_ID}/progress.json`, stamped with its `session_id`; the global file remains read-only as a fallback for pre-existing sessions. `save_session_progress()` also no longer truncates the target with mode `"w"` before taking its lock.
- **Unresolved sessions fabricated a `sessions/unknown/` folder** -- `policy_tracking_helper.get_session_id()` defaulted to the literal string `"unknown"`, so every failed resolution appended into one directory that looked like a real session. Those records now route to `sessions/_unresolved/`.
- **Warm PreToolUse daemon leaked session state across requests** -- the long-lived daemon reused `loaders._flow_trace_cache` from whichever session first populated it. Each request now binds its own session and resets session-scoped caches.

- **CI went red on every branch when `mcp` 2.0.0 was released** -- unrelated to the session work, surfaced by it. `requirements.txt` carried an unbounded `mcp>=1.0.0`; mcp 2.0.0 renamed `FastMCP` to `MCPServer` and moved `mcp.server.fastmcp.*` to `mcp.server.mcpserver.*`, so `src/mcp/session_mcp_server.py`'s `from mcp.server.fastmcp import FastMCP` fails with `ModuleNotFoundError` and collection aborts. Confirmed as dependency drift rather than a code regression by re-running main's last green run (commit `66bd654`, green 2026-07-26) with a fresh install: it now fails identically. Bounded to `mcp>=1.0.0,<2.0.0`; the 2.x migration spans this repo plus the 13 `mcp-*` server repos and is tracked separately.

- **`mcp` 2.x support; the `<2.0.0` bound from earlier in this release is removed** -- mcp 2.0.0 renamed `FastMCP` to `MCPServer` and moved `mcp.server.fastmcp.*` to `mcp.server.mcpserver.*`, with the v1 path gone and no alias. All 22 server files across this repo and the `mcp-*` fleet now use a two-line version probe that prefers the v2 name and falls back to v1, so each repo runs under either major version and can be upgraded independently -- a hard cut would have broken every repo not migrated in the same breath, since they all share one installed `mcp` package. Nothing else needed changing: `MCPServer(name, instructions=...)`, `@mcp.tool()` and `mcp.run(transport="stdio")` are identical in both versions. Verified by loading all 22 servers (292 tools registered, counts unchanged) and resolving the probe under both mcp 1.26.0 and 2.0.0.

### Added

- **`scripts/tools/migrate_session_dirs.py`** -- consolidates historical session directories onto one root and one ID format. Move-only, never deletes; anything not cleanly normalizable goes to a timestamped `sessions/_archive/` folder. Dry run by default, `--apply` to execute. Applied: 1264 directories case-normalized, 148 renamed, 2032 files merged, orphan root drained, `unknown/` archived, 0 failures, 0 empty directories left behind.
- **`tests/test_session_context.py`** -- 34 tests covering normalization of all three ID forms, resolution precedence, per-session scoping, path-traversal rejection, IDE-mode roots, and concurrency regression tests that assert 180 threaded updates leave the aggregate parseable with no lost records and 200 concurrent JSONL appends produce exactly 200 valid lines.

---

## [1.20.3] - 2026-07-25

### Changed

- **`agent_persona.py` PreToolUse gate message clarified** -- the `[GENERIC-OK]` escape hatch already accepted any generic subagent spawn, but its message only described "genuinely generic one-off tasks". Documented that it also covers recurring content-authoring tasks where no persona exists to inject because the persona/skill itself is what the task produces (e.g. authoring a new `SKILL.md`/`agent.md` for a library domain that doesn't have that persona yet). No logic change.

---

## [1.20.2] - 2026-07-22

### Fixed

- **CI red on `main` for 5 consecutive runs** -- 9 tests (`test_faithfulness_gate.py`, `test_import_manager.py`, `test_kg_routing.py`, `test_library_resolver.py`) required the real `claude-global-library` sibling checkout, which exists on developer machines but is never checked out on the GitHub Actions runner. Moved all 9 to `tests/integration/test_library_resolver_real_sibling.py` with a `pytest.mark.skipif` guard keyed on sibling-directory presence, so they run fully in local dev and skip cleanly in CI instead of hard-failing.

---

## [1.20.1] - 2026-07-22

### Fixed

- **Non-ASCII characters in `library_adapter.py` docstrings** -- three section-symbol characters replaced with "Section" to satisfy the Windows/cp1252 ASCII-only file check.

---

## [1.20.0] - 2026-07-12

Major release: flat -> domain-subpackage migration, Step 0 TODO-decomposition pipeline,
audited-deficiency remediation, and a standards / logging hardening pass.

### Added

- **Domain subpackages** -- flat `langgraph_engine/*.py` modules reorganized into focused packages: `analysis/`, `context/`, `engine_logging/`, `github/`, `metrics/`, `quality/`, `security/`, `skills/`, `standards/` (backward-compat shims kept at the old paths).
- **Step 0 TODO-decomposition pipeline** -- the monolithic orchestrator call is replaced by `prompt_gen_expert_caller -> todo_decomposer -> todo_executor` (per-TODO agent execution).
- **SRS / UML / architecture lifecycle rules** added under `rules/`.

### Changed

- **Graph factory unified** -- `verify_node` runtime-verification wrapping moved into `orchestrator.create_flow_graph`; duplicate `pipeline_builder.py` removed; `ENABLE_RUNTIME_VERIFICATION` now live.
- **error_logger console output routed through the shared logger** (severity-based dispatch; `_print_error` -> `_log_error`).
- **~180 silent `except Exception: pass`** across 44 modules narrowed to specific exception types + `logger.debug/warning` (Rule 2: no silently-swallowed exceptions).

### Fixed

- **loguru interpolation bug** -- 124 `logger.<level>("...%s...", arg)` calls across 17 loguru-backed files silently dropped their positional args (loguru uses `str.format`, not %-interpolation); converted to brace-style `"...{}...", arg`.
- **Step 0 planning chain revived** -- node<->caller CLI-flag mismatch, wrong return-key read, and a hardcoded 30s timeout overriding the STEP0_* budgets; all repaired.
- **level1_sync hyphen->underscore rename completed** -- session pruning and preference / pattern / context features (previously silent no-ops) restored.
- **Red CI greened** -- test suites repointed from deleted hyphen modules to real subpackage locations; `llm_call` neutralized in the unit suite (no real `claude` subprocess) and `github`/`quality` added to the PEP 562 `_LAZY_SUBMODULES` self-heal so `unittest.mock.patch` dotted targets resolve on Python 3.10.
- **Post-migration review fixes** -- the `step_logger` shim now re-exports `_summarize_result` (previously `ImportError` on every step-log write, escaping the `OSError`-only handler); fixed an `exc` name-clobber in the SonarQube auto-fixer backup-restore path (`NameError` on double-failure); the `metrics` aggregator counts `"COMPLETED"` status toward `success_rate` again. The legacy `complexity_distribution` histogram (tied to the removed 1-10 `complexity` field) is intentionally dropped in favor of the 1-25 `combined_complexity_score`.

### Docs

- CLAUDE.md: corrected directory layout (`langgraph_engine/` is at repo root, not under `scripts/`), rewrote the Step 0 flow (todo-decomposition), and refreshed Quick Info counts. README version + test badges updated (1.20.0, 45 test files).

---

## [1.19.3] - 2026-04-19

### Fixed

- **Level -1 regex: single-char escape sequences still matched** -- `%d:\n`, `%s:\t` were matched because `%` is not a word char so negative lookbehind passed. Fixed by requiring 2+ chars after `:\` (first char `[A-Za-z0-9_]` + at least one more). Prevents `test_call_graph_analyzer.py` fixture corruption. (Issue #229, PR #230)
- **`OPTIONS:\n` and `KB SUGGESTIONS:\n` restored** -- These strings in `recovery.py` were corrupted to `/n` by the old auto-fix bug. Restored in PR #230. (Issue #225)
- **Full escape sequence corruption audit** -- 6 additional `/n` corruptions fixed across `github_code_review.py`, `steps8to12_github.py`, `steps8to12_jira.py`, `prompt-generator.py`, `test_call_graph_analyzer.py`. (Issue #226, PR #232)
- **ASCII encoding: 37 non-ASCII Python files fixed** -- Replaced em dashes, arrows, box-drawing chars, emoji, curly quotes with ASCII equivalents. Level -1 ASCII check now passes. (Issue #227, PR #231)

### Files Changed

| File | Change |
|------|--------|
| `langgraph_engine/level_minus1/nodes.py` | Detection regex: 2-char minimum path segment |
| `langgraph_engine/level_minus1/recovery.py` | Fix regex: 2-char min + restored `OPTIONS:\n` |
| `langgraph_engine/level3_execution/github_code_review.py` | Restored `\n` escape sequences |
| `langgraph_engine/level3_execution/steps8to12_github.py` | Restored `\n` escape sequences |
| `langgraph_engine/level3_execution/steps8to12_jira.py` | Restored `\n` escape sequences |
| `tests/test_call_graph_analyzer.py` | Restored `\n` in fixture source string |
| 37 Python files | Replaced non-ASCII chars with ASCII equivalents |

---

## [1.19.2] - 2026-04-19

### Fixed

- **Level -1 Windows path regex corrupts escape sequences** — `nodes.py` detection and `recovery.py` fix regex both used `([A-Za-z]):\\([\w\\. \-]+)` which matched any `<letter>:\<word>` sequence. This caused false positives on Python escape sequences: `"Either:\n"` became `"Either:/n"`, `r"\s+"` patterns became `r"/s+"`. Fixed by adding `(?<![A-Za-z0-9_])` negative lookbehind so only real Windows drive paths (`C:\Users\...`) are matched. (Issue #222, PR #223)
- **stop-notifier shim simplified** — replaced `importlib.util` spec-loading with `sys.path` insert + direct import, consistent with other hook shims. (Issue #220, PR #221)

### Files Changed

| File | Change |
|------|--------|
| `langgraph_engine/level_minus1/nodes.py` | Detection regex: added negative lookbehind, switched from `"\\" in content` to compiled regex |
| `langgraph_engine/level_minus1/recovery.py` | Fix regex: added `(?<![A-Za-z0-9_])` negative lookbehind |
| `hooks/stop-notifier.py` | Simplified from 27-line `importlib.util` loader to 15-line `sys.path` shim |

---

## [1.19.1] - 2026-04-15

### Fixed — CI Failures

- **Python 3.9 dependency conflict** — `mcp>=1.0.0` requires Python>=3.10; CI matrix updated from `["3.9","3.11"]` to `["3.10","3.11"]`; `pyproject.toml` `requires-python` updated from `>=3.9` to `>=3.10`; Python 3.9 classifier removed
- **Python 3.11 collection error** — `tests/test_session.py` was a misplaced Flask scratch script from the `claude-insight` project (not a pytest file, imported `flask` which is not installed); deleted
- **4 untracked test files** — `tests/e2e/conftest.py`, `tests/e2e/test_full_mode_runtime_verification.py`, `tests/e2e/test_hook_mode_runtime_verification.py`, `tests/integration/test_runtime_verification_integration.py` were documented in CHANGELOG v1.18.0 as added but never committed; now committed

### Changed

- **README roadmap** — removed redundant "Past Releases" summary table (full history already in CHANGELOG); renamed "Next" to "Upcoming"; updated Python badge and prerequisites from 3.9+ to 3.10+

### Files Changed

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Python matrix: `["3.9","3.11"]` → `["3.10","3.11"]` |
| `pyproject.toml` | `requires-python = ">=3.9"` → `">=3.10"`; removed 3.9 classifier |
| `tests/test_session.py` | Deleted (misplaced Flask script, not a pytest file) |
| `tests/e2e/conftest.py` | Added (was untracked since v1.18.0) |
| `tests/e2e/test_full_mode_runtime_verification.py` | Added (was untracked since v1.18.0) |
| `tests/e2e/test_hook_mode_runtime_verification.py` | Added (was untracked since v1.18.0) |
| `tests/integration/test_runtime_verification_integration.py` | Added (was untracked since v1.18.0) |
| `README.md` | Python badge + prerequisites updated to 3.10+; roadmap cleanup |

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
