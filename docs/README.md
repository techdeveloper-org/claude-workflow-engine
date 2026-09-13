# Documentation Index

Every document in this repository lives under `docs/`, grouped by what it is.
The repository root carries only the five files `rules/11-documentation-files.md`
permits: `README.md`, `CLAUDE.md`, `SRS.md`, `CHANGELOG.md` and `VERSION`.

| Folder | Contains | Files |
|---|---|---|
| [`api/`](api/) | API specifications | 1 |
| [`architecture/`](architecture/) | Architecture and design | 19 |
| [`contributing/`](contributing/) | Contribution and community files | 5 |
| [`guides/`](guides/) | How-to guides and runbooks | 21 |
| [`phase-0-requirements/`](phase-0-requirements/) | Requirements and sequencing | 7 |
| [`phase-0-reverse-engineering/`](phase-0-reverse-engineering/) | Reverse-engineering artefacts | 25 |
| [`phase-1-architecture/`](phase-1-architecture/) | Phase 1 architecture artefacts | 10 |
| [`phase-2-validation/`](phase-2-validation/) | Cross-validation and the v2 HLD | 13 |
| [`phase-5-srs/`](phase-5-srs/) | SRS update report | 1 |
| [`phase-5-uml/`](phase-5-uml/) | CallGraph and diagram probes | 4 |
| [`phase-6-sprint/`](phase-6-sprint/) | Sprint plan and issue drafts | 4 |
| [`phase-7-routing/`](phase-7-routing/) | Issue-to-agent routing | 4 |
| [`phase-8-alignment/`](phase-8-alignment/) | Pre-implementation alignment | 4 |
| [`policies/`](policies/) | Pipeline policies | 44 |
| [`releases/`](releases/) | Per-release design notes | 7 |
| [`reports/`](reports/) | Investigations and audits | 26 |

Coding and testing standards (numbered rules 01-46 plus per-language standards) are not kept in this repository. They live only in `~/.claude/rules/`, which is what Claude Code and `standards/selector.py` load (#320).

---

## `policies/` -- Pipeline policies

One document per policy the SDLC pipeline enforces. `~/.claude/policies/` is the directory
`get_policies_dir()` actually reads; it is **not** a mirror of this one -- the two are different
sets and nothing keeps them in step. See `docs/reports/policy-implementation-audit-v2.md`
section 4.

<details><summary>44 file(s)</summary>

- [EXECUTION-SYSTEM-FIXES-SUMMARY.md](policies/EXECUTION-SYSTEM-FIXES-SUMMARY.md)
- [INTELLIGENT-PROMPT-GENERATION-UPGRADE.md](policies/INTELLIGENT-PROMPT-GENERATION-UPGRADE.md)
- [anti-hallucination-enforcement.md](policies/anti-hallucination-enforcement.md)
- [architecture-script-mapping-policy.md](policies/architecture-script-mapping-policy.md)
- [automatic-task-breakdown-policy.md](policies/automatic-task-breakdown-policy.md)
- [callgraph-analysis-policy.md](policies/callgraph-analysis-policy.md)
- [code-graph-analysis-policy.md](policies/code-graph-analysis-policy.md)
- [coding-standards-enforcement-policy.md](policies/coding-standards-enforcement-policy.md)
- [common-failures-prevention.md](policies/common-failures-prevention.md)
- [common-standards-policy.md](policies/common-standards-policy.md)
- [context-management-policy.md](policies/context-management-policy.md)
- [context-reading-policy.md](policies/context-reading-policy.md)
- [cross-project-patterns-policy.md](policies/cross-project-patterns-policy.md)
- [documentation-update-policy.md](policies/documentation-update-policy.md)
- [encoding-validation-policy.md](policies/encoding-validation-policy.md)
- [error-recovery-policy.md](policies/error-recovery-policy.md)
- [file-management-policy.md](policies/file-management-policy.md)
- [final-summary-policy.md](policies/final-summary-policy.md)
- [git-auto-commit-policy.md](policies/git-auto-commit-policy.md)
- [github-issues-integration-policy.md](policies/github-issues-integration-policy.md)
- [hook-system-policy.md](policies/hook-system-policy.md)
- [implementation-execution-policy.md](policies/implementation-execution-policy.md)
- [intelligent-decision-engine-policy.md](policies/intelligent-decision-engine-policy.md)
- [intelligent-model-selection-policy.md](policies/intelligent-model-selection-policy.md)
- [issue-closure-policy.md](policies/issue-closure-policy.md)
- [mcp-plugin-discovery-policy.md](policies/mcp-plugin-discovery-policy.md)
- [metrics-monitoring-policy.md](policies/metrics-monitoring-policy.md)
- [parallel-execution-policy.md](policies/parallel-execution-policy.md)
- [pr-code-review-policy.md](policies/pr-code-review-policy.md)
- [proactive-consultation-policy.md](policies/proactive-consultation-policy.md)
- [prompt-generation-policy.md](policies/prompt-generation-policy.md)
- [quality-gate-policy.md](policies/quality-gate-policy.md)
- [recovery-policy.md](policies/recovery-policy.md)
- [session-management-policy.md](policies/session-management-policy.md)
- [task-phase-enforcement-policy.md](policies/task-phase-enforcement-policy.md)
- [task-progress-tracking-policy.md](policies/task-progress-tracking-policy.md)
- [test-case-policy.md](policies/test-case-policy.md)
- [test-generation-policy.md](policies/test-generation-policy.md)
- [tool-optimization-policy.md](policies/tool-optimization-policy.md)
- [tool-usage-optimization-policy.md](policies/tool-usage-optimization-policy.md)
- [unicode-fix-policy.md](policies/unicode-fix-policy.md)
- [user-preferences-policy.md](policies/user-preferences-policy.md)
- [version-release-policy.md](policies/version-release-policy.md)
- [windows-path-policy.md](policies/windows-path-policy.md)

</details>

## `architecture/` -- Architecture and design

ADRs, pipeline architecture, level design, flow diagrams and the orchestration prompt.

<details><summary>18 file(s)</summary>

- [ADR-002-call-graph-intelligence.md](architecture/ADR-002-call-graph-intelligence.md)
- [ADR-003-runtime-verification-decorator.md](architecture/ADR-003-runtime-verification-decorator.md)
- [ADR-004-opt-in-default.md](architecture/ADR-004-opt-in-default.md)
- [ADR-005-no-llm-in-verifier.md](architecture/ADR-005-no-llm-in-verifier.md)
- [ADR-006-hook-free-execution.md](architecture/ADR-006-hook-free-execution.md)
- [ARCHITECTURE_QUICK_SUMMARY.md](architecture/ARCHITECTURE_QUICK_SUMMARY.md)
- [ARCHITECTURE_REVIEW.md](architecture/ARCHITECTURE_REVIEW.md)
- [HYBRID-EVENT-DRIVEN-ARCHITECTURE.md](architecture/HYBRID-EVENT-DRIVEN-ARCHITECTURE.md)
- [LANGGRAPH-ENGINE.md](architecture/LANGGRAPH-ENGINE.md)
- [LEVEL3-DESIGN.md](architecture/LEVEL3-DESIGN.md)
- [PERMANENT-SOLUTION-ARCHITECTURE.md](architecture/PERMANENT-SOLUTION-ARCHITECTURE.md)
- [PIPELINE_ARCHITECTURE.md](architecture/PIPELINE_ARCHITECTURE.md)
- [POLICIES-AND-SCRIPTS-FLOW.md](architecture/POLICIES-AND-SCRIPTS-FLOW.md)
- [POLICY-CHAIN-FLOWCHART.md](architecture/POLICY-CHAIN-FLOWCHART.md)
- [call-graph-diagram.md](architecture/call-graph-diagram.md)
- [impact_map-l3-collapse-draft.md](architecture/impact_map-l3-collapse-draft.md)
- [orchestration-prompt-v2.1-generic-rules.md](architecture/orchestration-prompt-v2.1-generic-rules.md)
- [orchestration_prompt.md](architecture/orchestration_prompt.md)

</details>

## `guides/` -- How-to guides and runbooks

Getting started, deployment, testing, troubleshooting and operational runbooks.

<details><summary>21 file(s)</summary>

- [00_START_HERE.md](guides/00_START_HERE.md)
- [DEPLOYMENT_GUIDE.md](guides/DEPLOYMENT_GUIDE.md)
- [DOCUMENTATION_TEMPLATES.md](guides/DOCUMENTATION_TEMPLATES.md)
- [LEVEL3-IMPLEMENTATION-GUIDE.md](guides/LEVEL3-IMPLEMENTATION-GUIDE.md)
- [MCP-TOOLS.md](guides/MCP-TOOLS.md)
- [PARALLEL_EXECUTION_STRATEGY.md](guides/PARALLEL_EXECUTION_STRATEGY.md)
- [RUNBOOK_STALE_GRAPH.md](guides/RUNBOOK_STALE_GRAPH.md)
- [STEP-BY-STEP-PROMPTS.md](guides/STEP-BY-STEP-PROMPTS.md)
- [SYNTHESIS-INTEGRATION-GUIDE.md](guides/SYNTHESIS-INTEGRATION-GUIDE.md)
- [TESTING_GUIDE.md](guides/TESTING_GUIDE.md)
- [TROUBLESHOOTING_GUIDE.md](guides/TROUBLESHOOTING_GUIDE.md)
- [WORKFLOW.md](guides/WORKFLOW.md)
- [adr-020-path-c-verification.md](guides/adr-020-path-c-verification.md)
- [computer-use-preflight-checklist.md](guides/computer-use-preflight-checklist.md)
- [fr17-entry-point-invocation-verification.md](guides/fr17-entry-point-invocation-verification.md)
- [fr31-uninstall-residue-verification.md](guides/fr31-uninstall-residue-verification.md)
- [fr8-hook-retention-verification.md](guides/fr8-hook-retention-verification.md)
- [migration-v1.21.5-to-v2.0.0.md](guides/migration-v1.21.5-to-v2.0.0.md)
- [nfr11-lifecycle-verification.md](guides/nfr11-lifecycle-verification.md)
- [parallel-execution-quick-guide.md](guides/parallel-execution-quick-guide.md)
- [uninstall-residue.md](guides/uninstall-residue.md)

</details>

## `reports/` -- Investigations and audits

One-off analyses, audit results, migration notes and summaries. Point-in-time records, not living documents.

<details><summary>25 file(s)</summary>

- [AUTO-FIX-ENFORCEMENT-SUMMARY.md](reports/AUTO-FIX-ENFORCEMENT-SUMMARY.md)
- [AUTO-SYNC-POLICIES.md](reports/AUTO-SYNC-POLICIES.md)
- [CONTEXT_READ_ENFORCEMENT.md](reports/CONTEXT_READ_ENFORCEMENT.md)
- [DEPENDENCY-RESEARCH-STEP.md](reports/DEPENDENCY-RESEARCH-STEP.md)
- [HOOKS-SETUP-2026-03-10.md](reports/HOOKS-SETUP-2026-03-10.md)
- [IMPLEMENTATION-NOTES.md](reports/IMPLEMENTATION-NOTES.md)
- [PLAN-DETECTION-SUMMARY.md](reports/PLAN-DETECTION-SUMMARY.md)
- [SESSION-BLOAT-ANALYSIS.md](reports/SESSION-BLOAT-ANALYSIS.md)
- [SMART-ADAPTIVE-SUMMARY.md](reports/SMART-ADAPTIVE-SUMMARY.md)
- [STEP7_DOCUMENTATION_IMPLEMENTATION.md](reports/STEP7_DOCUMENTATION_IMPLEMENTATION.md)
- [TESTING_SUMMARY.md](reports/TESTING_SUMMARY.md)
- [anthropic-feedback-letter.md](reports/anthropic-feedback-letter.md)
- [capability-disposition-ledger.md](reports/capability-disposition-ledger.md)
- [fr8a-stop-hook-spawn-instrumentation.md](reports/fr8a-stop-hook-spawn-instrumentation.md)
- [home_path_classification.md](reports/home_path_classification.md)
- [home_path_classification_baseline.md](reports/home_path_classification_baseline.md)
- [naming_audit_report.md](reports/naming_audit_report.md)
- [noqa-audit-todo.md](reports/noqa-audit-todo.md)
- [policy-implementation-audit-v2.md](reports/policy-implementation-audit-v2.md)
- [qa_stream1_verification_report.md](reports/qa_stream1_verification_report.md)
- [refactoring-plan.md](reports/refactoring-plan.md)
- [review-checkpoint-consistency-fix.md](reports/review-checkpoint-consistency-fix.md)
- [session-id-tracking.md](reports/session-id-tracking.md)
- [session-isolation-fix.md](reports/session-isolation-fix.md)
- [session-management-comparison.md](reports/session-management-comparison.md)

</details>

## `releases/` -- Per-release design notes

Design briefs, blueprints and review notes tied to a specific version.

<details><summary>7 file(s)</summary>

- [v1.14.0-design-brief.md](releases/v1.14.0-design-brief.md)
- [v1.14.0-design-output.md](releases/v1.14.0-design-output.md)
- [v1.18.0-blueprint.md](releases/v1.18.0-blueprint.md)
- [v1.18.0-consensus-review.md](releases/v1.18.0-consensus-review.md)
- [v1.18.0-runtime-verification.md](releases/v1.18.0-runtime-verification.md)
- [v1.18.0-squad-lead-instruction.md](releases/v1.18.0-squad-lead-instruction.md)
- [v2.0.0-plugin-transformation-requirements.md](releases/v2.0.0-plugin-transformation-requirements.md)

</details>

## `contributing/` -- Contribution and community files

Issue and PR templates, contributing guide, code of conduct. They live here rather than the repo root because rules/11 permits only five documentation files at the root.

<details><summary>5 file(s)</summary>

- [CODE_OF_CONDUCT.md](contributing/CODE_OF_CONDUCT.md)
- [CONTRIBUTING.md](contributing/CONTRIBUTING.md)
- [bug_report.md](contributing/bug_report.md)
- [feature_request.md](contributing/feature_request.md)
- [pull_request_template.md](contributing/pull_request_template.md)

</details>

## `api/` -- API specifications

OpenAPI and related interface specs.

<details><summary>1 file(s)</summary>

- [OPENAPI_SPEC.yaml](api/OPENAPI_SPEC.yaml)

</details>

## `phase-1-architecture/` -- Phase 1 architecture artefacts

High-level design and feasibility output from the original phase-1 work.

<details><summary>10 file(s)</summary>

- [consensus_summary_phase1.md](phase-1-architecture/consensus_summary_phase1.md)
- [consensus_verdict_phase1.json](phase-1-architecture/consensus_verdict_phase1.json)
- [faithfulness_scorecard_phase1.json](phase-1-architecture/faithfulness_scorecard_phase1.json)
- [faithfulness_summary_phase1.md](phase-1-architecture/faithfulness_summary_phase1.md)
- [feasibility_analysis.json](phase-1-architecture/feasibility_analysis.json)
- [hallucination_report_phase1.json](phase-1-architecture/hallucination_report_phase1.json)
- [hallucination_summary_phase1.md](phase-1-architecture/hallucination_summary_phase1.md)
- [hld-v1.20.0-superseded.md](phase-1-architecture/hld-v1.20.0-superseded.md)
- [hld.md](phase-1-architecture/hld.md)
- [plugin_schema_spike.md](phase-1-architecture/plugin_schema_spike.md)

</details>

## `phase-0-requirements/` -- Requirements and sequencing

PRD v2, the product sequencing plan, the Phase 1 architect brief and the faithfulness and hallucination scorecards taken over them.

<details><summary>7 file(s)</summary>

- [faithfulness_scorecard_phase0.json](phase-0-requirements/faithfulness_scorecard_phase0.json)
- [faithfulness_summary_phase0.md](phase-0-requirements/faithfulness_summary_phase0.md)
- [hallucination_report_phase0.json](phase-0-requirements/hallucination_report_phase0.json)
- [hallucination_summary_phase0.md](phase-0-requirements/hallucination_summary_phase0.md)
- [phase1_architect_brief.md](phase-0-requirements/phase1_architect_brief.md)
- [prd-v2.md](phase-0-requirements/prd-v2.md)
- [product-sequencing-v2.md](phase-0-requirements/product-sequencing-v2.md)

</details>

## `phase-0-reverse-engineering/` -- Reverse-engineering artefacts

What the v1 system actually did, measured rather than described: the audit surface, path violations, capability loss and the policy inventory.

<details><summary>25 file(s)</summary>

- [api_surface.json](phase-0-reverse-engineering/api_surface.json)
- [as-built-prd.md](phase-0-reverse-engineering/as-built-prd.md)
- [as_built_executive_summary.md](phase-0-reverse-engineering/as_built_executive_summary.md)
- [ast_call_graph_summary.md](phase-0-reverse-engineering/ast_call_graph_summary.md)
- [audit_surface.json](phase-0-reverse-engineering/audit_surface.json)
- [builder_divergence.md](phase-0-reverse-engineering/builder_divergence.md)
- [capability_loss.md](phase-0-reverse-engineering/capability_loss.md)
- [claude_md_drift.md](phase-0-reverse-engineering/claude_md_drift.md)
- [complexity_report.json](phase-0-reverse-engineering/complexity_report.json)
- [contradictions.md](phase-0-reverse-engineering/contradictions.md)
- [dead_code_report.json](phase-0-reverse-engineering/dead_code_report.json)
- [dead_code_report.json.malformed.bak](phase-0-reverse-engineering/dead_code_report.json.malformed.bak)
- [dead_code_summary.md](phase-0-reverse-engineering/dead_code_summary.md)
- [impact_analysis_graph.json](phase-0-reverse-engineering/impact_analysis_graph.json)
- [impact_analysis_summary.md](phase-0-reverse-engineering/impact_analysis_summary.md)
- [lhs.json](phase-0-reverse-engineering/lhs.json)
- [path_violations.md](phase-0-reverse-engineering/path_violations.md)
- [policy_corpus_inventory.json](phase-0-reverse-engineering/policy_corpus_inventory.json)
- [policy_corpus_summary.md](phase-0-reverse-engineering/policy_corpus_summary.md)
- [policy_enforcement_raw.json](phase-0-reverse-engineering/policy_enforcement_raw.json)
- [policy_enforcement_summary.md](phase-0-reverse-engineering/policy_enforcement_summary.md)
- [rts_selection.json](phase-0-reverse-engineering/rts_selection.json)
- [stop_hook_overhead.md](phase-0-reverse-engineering/stop_hook_overhead.md)
- [structural_inventory.json](phase-0-reverse-engineering/structural_inventory.json)
- [structural_inventory_summary.md](phase-0-reverse-engineering/structural_inventory_summary.md)

</details>

## `phase-2-validation/` -- Cross-validation and the v2 HLD

The v2.0.0 high-level design, its ADRs, the advisory items and the consensus record from cross-validating the earlier phases.

<details><summary>13 file(s)</summary>

- [advisory_items.json](phase-2-validation/advisory_items.json)
- [ba_review.json](phase-2-validation/ba_review.json)
- [consensus_summary_phase2.md](phase-2-validation/consensus_summary_phase2.md)
- [consensus_verdict_phase2.json](phase-2-validation/consensus_verdict_phase2.json)
- [faithfulness_scorecard_phase2.json](phase-2-validation/faithfulness_scorecard_phase2.json)
- [faithfulness_summary_phase2.md](phase-2-validation/faithfulness_summary_phase2.md)
- [hallucination_report_phase2.json](phase-2-validation/hallucination_report_phase2.json)
- [hallucination_report_sequencing.json](phase-2-validation/hallucination_report_sequencing.json)
- [hallucination_summary_phase2.md](phase-2-validation/hallucination_summary_phase2.md)
- [hallucination_summary_sequencing.md](phase-2-validation/hallucination_summary_sequencing.md)
- [hld_v2.md](phase-2-validation/hld_v2.md)
- [pm_review.json](phase-2-validation/pm_review.json)
- [sa_defence.json](phase-2-validation/sa_defence.json)

</details>

## `phase-5-srs/` -- SRS update report

The record of what the Phase 5 pass appended to SRS.md and why.

<details><summary>1 file(s)</summary>

- [srs_update_report.md](phase-5-srs/srs_update_report.md)

</details>

## `phase-5-uml/` -- CallGraph and diagram probes

The CallGraph coverage probe and the diagram generation reports it fed.

<details><summary>4 file(s)</summary>

- [callgraph_coverage_probe.md](phase-5-uml/callgraph_coverage_probe.md)
- [discovery_manifest.json](phase-5-uml/discovery_manifest.json)
- [drawio_generation_report.md](phase-5-uml/drawio_generation_report.md)
- [mermaid_generation_report.md](phase-5-uml/mermaid_generation_report.md)

</details>

## `phase-6-sprint/` -- Sprint plan and issue drafts

The 37 issue drafts, their sequencing risks and the key-to-issue-number map.

<details><summary>4 file(s)</summary>

- [github_issues.json](phase-6-sprint/github_issues.json)
- [issue_key_map.json](phase-6-sprint/issue_key_map.json)
- [sequencing_risks.md](phase-6-sprint/sequencing_risks.md)
- [sprint_plan.md](phase-6-sprint/sprint_plan.md)

</details>

## `phase-7-routing/` -- Issue-to-agent routing

Which library agent and skills each issue was routed to, the capability gaps that routing exposed, and the specification for the agents written to close them.

<details><summary>4 file(s)</summary>

- [capability_gaps.md](phase-7-routing/capability_gaps.md)
- [library_gap_spec.md](phase-7-routing/library_gap_spec.md)
- [routing_map.json](phase-7-routing/routing_map.json)
- [routing_table.md](phase-7-routing/routing_table.md)

</details>

## `phase-8-alignment/` -- Pre-implementation alignment

Premise scans run over the sprint's own artefacts before implementation, and the readiness report drawn from them.

<details><summary>4 file(s)</summary>

- [blockers.json](phase-8-alignment/blockers.json)
- [premise_scan_bh.json](phase-8-alignment/premise_scan_bh.json)
- [premise_scan_bh.md](phase-8-alignment/premise_scan_bh.md)
- [readiness_report.md](phase-8-alignment/readiness_report.md)

</details>
