"""FlowState TypedDict - Single source of truth for 3-level flow execution state.

This TypedDict defines all state fields passed through the LangGraph StateGraph.
Each node reads from and writes to relevant state fields, enabling:
- Type-safe state access across all nodes
- Clear field documentation and ownership
- Backward-compatible flow-trace.json output format

Organized into logical sections:
  - Session Identification
  - User Input
  - Level -1: Auto-Fix
  - Level 1: Sync System
  - Level 2: Standards System
  - Level 3: Execution (Steps 0-14)
  - Integrations (Jira, Figma)
  - Workflow Memory & Context Optimization
  - Pipeline & Output

CHANGE LOG (v1.15.0):
  Removed TOON fields: toon_integrity_ok, level1_context_toon, toon_schema_valid,
    toon_schema_errors, toon_version (TOON compression node removed from pipeline).

CHANGE LOG (v1.15.2):
  Removed step4_toon_refined field (TOON removed in v1.15.0, stale field purged).
"""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from .reducers import _keep_first_value, _merge_dicts, _merge_lists


class FlowState(TypedDict, total=False):
    """Complete state for 3-level architecture execution.

    All fields are optional (total=False) to allow incremental state building.
    Each level and node populates relevant fields.
    """

    # ===========================================================================
    # SESSION IDENTIFICATION (all immutable - use reducer)
    # ===========================================================================
    session_id: Annotated[str, _keep_first_value]  # Immutable - never changes after init
    timestamp: Annotated[str, _keep_first_value]  # Immutable - set at session start
    project_root: str  # MUTABLE: Changed from Annotated[str, _keep_first_value] because reducer was clearing it
    is_java_project: Annotated[bool, _keep_first_value]  # Immutable - detected once
    is_fresh_project: Annotated[bool, _keep_first_value]  # Immutable - detected once

    # ===========================================================================
    # USER INPUT (immutable - captured at entry, NEVER MODIFIED)
    # ===========================================================================
    user_message: Annotated[str, _keep_first_value]  # User's ORIGINAL prompt - NEVER modify, NEVER regenerate
    user_message_original: Annotated[str, _keep_first_value]  # Backup of original - for safety
    user_message_length: Annotated[int, _keep_first_value]  # Length of message for context tracking

    # CRITICAL: All analysis/processing COPIES user_message for analysis only
    # Original stays pristine and gets sent to Claude AS-IS without any modification

    # ===========================================================================
    # LEVEL -1: AUTO-FIX ENFORCEMENT
    # ===========================================================================
    level_minus1_status: str  # OK / BLOCKED / SKIPPED
    level_minus1_errors: List[str]  # Any auto-fix errors encountered

    # Auto-fix checks
    unicode_check: bool  # Windows Unicode fix applied
    unicode_check_error: Optional[str]  # Error message if failed

    encoding_check: bool  # File encoding validation passed
    encoding_check_error: Optional[str]

    windows_path_check: bool  # Windows path validation passed
    windows_path_check_error: Optional[str]

    auto_fix_applied: List[str]  # List of auto-fixes that were applied

    # Failure Prevention KB
    failure_kb_loaded: Optional[bool]  # True if KB was parsed successfully
    failure_kb_suggestions: Optional[List[Dict]]  # KB matches for current failures

    # Recovery state (written by ask/fix nodes, read by routing)
    level_minus1_retry_count: int  # attempt counter (incremented by ask node)
    level_minus1_user_choice: str  # "auto-fix" | "skip" | "force_continue"
    level_minus1_fixes_applied: List[str]  # applied fixes (from fix node)
    level_minus1_fix_errors: List[str]  # errors during fix attempts
    level_minus1_ready_to_retry: bool  # True after fix node completes
    level_minus1_max_attempts_reached: bool  # True when 3 attempts exceeded
    level_minus1_fatal_failure: bool  # True on unrecoverable failure
    level_minus1_failed_checks: List[str]  # messages for failed checks

    # Encoding scan results
    encoding_nonascii_files: List[str]  # files with non-ASCII content

    # ===========================================================================
    # LEVEL 1: SYNC SYSTEM (3 PARALLEL TASKS: session + complexity + context)
    # ===========================================================================
    # All tasks run in parallel (complexity + context), then merge

    # Context Management
    context_loaded: bool  # Successfully loaded context
    context_percentage: float  # Context usage (0-100)
    context_threshold_exceeded: bool  # True if context > 85% (emergency routing)
    context_error: Optional[str]
    context_metadata: Dict[str, Any]  # Additional context metadata

    # Raw context dict (set by context_loader, cleared by cleanup node)
    context_data: Optional[Dict]  # {srs, readme, claude_md, files_loaded} -- freed after merge

    # Context loader detail fields (Subtasks 3, 5, 6, 7, 8)
    context_skipped_files: Optional[List[str]]  # Files skipped due to size/timeout
    context_load_warnings: Optional[List[str]]  # Warnings from loader
    context_total_bytes: Optional[int]  # Total bytes loaded into memory
    context_cache_hit: Optional[bool]  # True if cache was used
    context_cache_age_hours: Optional[float]  # Age of cache entry used
    context_cache_key: Optional[str]  # Cache key (MD5 of project path)

    # Session Management
    session_chain_loaded: bool  # Session chain initialized
    session_history: List[Dict]  # Previous session data
    session_state_data: Dict[str, Any]  # Current session state
    session_error: Optional[str]
    session_parent_id: Optional[str]  # Parent session ID (for chaining)
    session_tags: Optional[List[str]]  # Auto-tags from user message keywords
    session_pruning_errors: Optional[List[str]]  # Errors from session pruning

    # User Preferences
    preferences_loaded: bool  # User preferences initialized
    preferences_data: Dict[str, Any]  # Loaded preferences
    preferences_error: Optional[str]

    # Pattern Detection
    patterns_detected: List[str]  # Cross-project patterns found
    pattern_metadata: Dict[str, Any]  # Pattern analysis data
    patterns_error: Optional[str]

    # Level 1 merge result
    level1_status: str  # OK / PARTIAL / FAILED
    clear_memory: Optional[List]  # Signal list of field names to clear (written by merge node)

    # Level 1 complexity (kept in state for quick access by downstream nodes)
    complexity_score: Optional[int]  # 1-10 score from complexity_calculator
    complexity_calculated: Optional[bool]  # Whether calculation succeeded
    complexity_error: Optional[str]  # Error if calculation failed

    # Level 1 graph-based complexity (NetworkX + Lizard)
    graph_complexity_score: Optional[int]  # 1-25 graph-based score
    graph_metrics: Optional[Dict]  # density, centrality, coupling, etc.
    cyclomatic_complexity_avg: Optional[float]  # average cyclomatic complexity
    combined_complexity_score: Optional[
        int
    ]  # final combined 1-25 score (NOT 1-10 -- see CLAUDE.md Key Components table)

    # Level 1 caching
    context_cache_hit: Optional[bool]  # True if cache was valid and used
    context_cache_age_hours: Optional[float]  # How old the cached context is
    context_cache_key: Optional[str]  # Cache key (SHA-256 of project path)

    # Level 1 optimization metrics (Task #6)
    context_load_time_ms: Optional[int]  # Wall-clock ms for context load
    context_hit_rate_pct: Optional[float]  # Session cache hit rate percentage (0-100)
    context_streamed_files: Optional[List[str]]  # Files loaded via streaming (large files)

    # ===========================================================================
    # LEVEL 2: STANDARDS SYSTEM
    # ===========================================================================
    standards_loaded: bool  # Common standards loaded
    standards_count: int  # Number of standards loaded
    standards_error: Optional[str]

    # Java-specific standards (only if is_java_project=True)
    java_standards_loaded: bool  # Java/Spring standards loaded
    spring_boot_patterns: Dict  # Spring Boot-specific patterns
    java_standards_error: Optional[str]

    # Tool Optimization Standards (loaded at Level 2, enforced by PreToolUse hook)
    tool_optimization_rules: Optional[Dict]  # {read_max_lines, grep_max_matches, etc.}
    tool_optimization_loaded: Optional[bool]  # True after Level 2 loads rules

    # ===========================================================================
    # LEVEL 2: MCP REGISTRY & PLUGIN DISCOVERY
    # ===========================================================================
    mcp_servers_available: Optional[List[Dict]]  # All discovered MCP plugins with metadata
    mcp_filesystem_enabled: Optional[bool]  # True if Filesystem MCP available
    mcp_plugins_path: Optional[str]  # Path to plugins directory (usually ~/.claude/mcp/plugins/)
    mcp_cache_dir: Optional[str]  # Cache directory (usually ~/.claude/mcp/cache/)
    mcp_discovered_count: Optional[int]  # Number of MCPs successfully discovered
    mcp_initialization_status: Optional[str]  # OK / PARTIAL / ERROR / SKIPPED
    mcp_error: Optional[str]  # Error message if initialization failed
    mcp_auto_routing_enabled: Optional[bool]  # Enable AUTO-ROUTE in hook (true if filesystem available)

    # Standards selector result (populated by standard_selector.py at runtime)
    standards_selection: Optional[Dict]  # {project_type, framework, total_loaded, conflicts_detected, merged_rules}
    standards_merged_rules: Optional[Dict]  # Conflict-resolved merged rules from all standards sources
    detected_framework: Optional[str]  # Framework detected by standard_selector (flask/django/spring-boot/react/etc.)
    standards_selection_error: Optional[str]  # Error from standards selector (non-fatal)

    # Standards integration hook outputs (set at each pipeline step)
    standards_applied_step1: Optional[bool]  # Standards applied at Step 1 (plan mode decision)
    standards_applied_step2: Optional[bool]  # Standards applied at Step 2 (plan execution)
    standards_applied_step5: Optional[bool]  # Standards applied at Step 5 (skill selection)
    standards_applied_step10: Optional[bool]  # Standards applied at Step 10 (code review)
    standards_applied_step13: Optional[bool]  # Standards applied at Step 13 (documentation)

    # Step-specific standards context injected by integration hooks
    step1_standards_context: Optional[Dict]  # Standards metadata for plan complexity scorer
    step2_standards_constraints: Optional[Dict]  # Naming/layer constraints for planner
    step5_standards_validation: Optional[Dict]  # Skill/standards compatibility check result
    step10_standards_checklist: Optional[Dict]  # Code review compliance checklist
    step13_standards_doc_requirements: Optional[Dict]  # Documentation update requirements

    # Level 2: Standards enforcement (linting, non-blocking)
    standards_enforcement_ran: Optional[bool]  # True if linter ran successfully
    standards_violations: Optional[List[Dict]]  # List of {file, line, code, message, severity}
    standards_violations_count: Optional[int]  # Total violations found (max 20 returned)
    standards_linter_used: Optional[str]  # Linter used: ruff / flake8 / none

    level2_status: str  # OK / PARTIAL / FAILED

    # ===========================================================================
    # LEVEL 3: EXECUTION SYSTEM (15 STEPS)
    # ===========================================================================

    # Orchestration Pre-Analysis Gate (runs before Step 0.0)
    pre_analysis_result: Optional[Dict]  # Raw result from get_orchestration_context()
    call_graph_metrics: Optional[Dict]  # hot_nodes, leaf_nodes, dependency_order, boost
    skip_architecture: Optional[bool]  # True -> bypass Step 2 (plan execution) [template fast-path]
    skip_consensus: Optional[bool]  # True -> bypass consensus validation [template fast-path]
    pre_analysis_execution_time_ms: Optional[float]
    # Orchestration Template fast-path (--orchestration-template CLI flag)
    orchestration_template: Optional[Dict]  # Pre-filled template from prompt-generation-expert
    template_fast_path: Optional[bool]  # True -> skip Steps 0-5, jump to Step 6
    step0_complexity_boosted: Optional[bool]  # True if boost was applied by call graph
    step0_complexity_boost_source: Optional[str]  # Source of boost: "call_graph"

    # Step 0.0: Pre-flight - Project Context
    step0_0_project_context: Optional[Dict]  # README, CHANGELOG, VERSION, etc.
    step0_0_files_read: Optional[List[str]]  # Files successfully read
    step0_0_error: Optional[str]
    step0_0_execution_time_ms: Optional[float]

    # Step 0.1: Pre-flight - Initial CallGraph Snapshot
    step0_1_initial_callgraph: Optional[Dict]  # Baseline call graph for Step 11 diff
    step0_1_callgraph_available: Optional[bool]  # True if snapshot succeeded
    step0_1_error: Optional[str]
    step0_1_execution_time_ms: Optional[float]

    # User Preferences Context (extracted from Level 1 preferences_data)
    user_preferences_context: Optional[Dict]  # Pre-computed model/skill/complexity hints

    # Step 0: Prompt Generation
    step0_prompt: Dict  # Prompt context and metadata
    step0_task_type: str  # Detected task type
    step0_error: Optional[str]

    # Step 1: Task Breakdown
    step1_tasks: Dict  # Broken down tasks
    step1_task_count: int  # Number of tasks identified
    step1_error: Optional[str]

    # Step 2: Plan Mode Decision
    step2_plan_mode: bool  # Whether to suggest EnterPlanMode
    step2_reasoning: str  # Why plan mode was chosen
    step2_error: Optional[str]

    # Step 3: Context Read Enforcement
    step3_context_read: bool  # Context read check passed
    step3_enforcement_applies: bool  # Whether enforcement applies to this project
    step3_error: Optional[str]

    # Step 4: Model Selection
    step4_model: str  # Selected model: fast_classification/complex_reasoning
    step4_reasoning: str  # Why this model was chosen
    step4_error: Optional[str]

    # Step 5: Skill & Agent Selection (removed in v1.13 -- fields kept for state compat)
    step5_skill: str  # Selected skill name (if any)
    step5_agent: str  # Selected agent name (if any)
    step5_reasoning: str  # Why this skill/agent was chosen
    step5_error: Optional[str]
    step5_llm_query_needed: bool  # True if LLM needed to decide

    # Step 6: Tool Optimization
    step6_tool_hints: List[str]  # Optimization hints for tools
    step6_read_optimization: Dict  # Read tool optimization (offset, limit)
    step6_grep_optimization: Dict  # Grep tool optimization (head_limit)
    step6_error: Optional[str]

    # Step 7: Auto-Recommendations
    step7_recommendations: List[str]  # Automatic recommendations to user
    step7_error: Optional[str]

    # Step 8: Progress Tracking
    step8_progress: Dict  # Task progress metadata
    step8_incomplete_work: List[str]  # Any incomplete work detected
    step8_error: Optional[str]

    # Step 9: Git Commit Preparation
    step9_commit_ready: bool  # Commit can be auto-created
    step9_commit_message: str  # Prepared commit message
    step9_version_bump: str  # Version to bump to
    step9_error: Optional[str]

    # Step 10: Session Save
    step10_session: Dict  # Session save preparation
    step10_archive_needed: bool  # Session should be archived
    step10_error: Optional[str]

    # Step 11 (implicit): Failure Prevention
    failure_prevention: Dict  # Failure KB checks
    failure_prevention_warnings: List[str]  # Warnings from failure KB

    # ===========================================================================
    # v2 LEVEL 3 PIPELINE FIELDS (14-STEP WORKFLOW.MD COMPLIANT)
    # ===========================================================================
    # Bridge fields
    session_dir: Optional[str]  # v2 uses session_dir (str path)
    user_requirement: Optional[str]  # Alias for user_message in v2 context

    # Step 1: Plan Mode Decision
    step1_decision: Optional[Dict[str, Any]]
    step1_plan_required: Optional[bool]
    step1_execution_time_ms: Optional[float]
    step1_error: Optional[str]

    # Step 2: Plan Execution
    step2_plan: Optional[str]
    step2_files_affected: Optional[List[str]]
    step2_phases: Optional[List[Dict]]
    step2_risks: Optional[Dict]
    step2_code_context: Optional[str]  # Code analysis from exploration tools
    step2_selected_model: Optional[str]  # Which model was used (fast_classification/complex_reasoning)
    step2_execution_time_ms: Optional[float]
    step2_error: Optional[str]

    # Step 3: Task Breakdown
    step3_tasks: Optional[List[Dict]]
    step3_task_count: Optional[int]
    step3_execution_time_ms: Optional[float]
    step3_error: Optional[str]

    # Step 4: TOON Refinement
    step4_blueprint: Optional[Dict]
    step4_execution_time_ms: Optional[float]
    step4_error: Optional[str]

    # Step 5: Skill Selection
    step5_available_skills: Optional[List[str]]
    step5_available_agents: Optional[List[str]]
    step5_available_skills_full: Optional[List[Dict]]
    step5_available_agents_full: Optional[List[Dict]]
    step5_skill_mappings: Optional[Dict]
    step5_skills: Optional[List[str]]
    step5_agents: Optional[List[str]]
    step5_execution_time_ms: Optional[float]
    step5_error: Optional[str]

    # Step 6: Skill Validation & Download
    step6_available_on_system: Optional[List[str]]
    step6_final_skills: Optional[List[Dict]]
    step6_final_agents: Optional[List[Dict]]
    step6_downloaded: Optional[List[str]]
    step6_execution_time_ms: Optional[float]
    step6_error: Optional[str]

    # Step 7: Final Prompt Generation
    step7_execution_prompt: Optional[str]
    step7_execution_time_ms: Optional[float]
    step7_error: Optional[str]

    # Step 0: Task Analysis (PHASE 2A - New)
    step0_task_type: str  # Detected task type
    step0_complexity: int  # Complexity score (1-10)
    step0_reasoning: str  # Reasoning for task analysis
    step0_tasks: Dict  # Broken down tasks
    step0_task_count: int  # Number of tasks identified
    step0_docs_found: Optional[Dict[str, Any]]  # Which project docs exist (SDLC read phase)
    step0_target_files: Optional[List[str]]  # Target files identified from task analysis
    step0_error: Optional[str]
    orchestration_prompt: Optional[str]  # Prompt generated by prompt-gen-expert for orchestrator
    orchestrator_result: Optional[Dict[str, Any]]  # Full result dict from orchestrator-agent-caller

    # Step 1: Plan Mode Decision (PHASE 2A - Renamed from step2_plan_mode)
    step1_plan_required: bool  # Whether plan mode is needed
    step1_reasoning: str  # Reasoning for plan decision
    step1_complexity_score: int  # Complexity score from Step 1
    step1_execution_time_ms: Optional[float]
    step1_error: Optional[str]

    # Step 2: Plan Execution (PHASE 2A - Renamed from step2b_plan_exec)
    step2_plan_execution: Optional[Dict]  # Detailed execution plan
    step2_plan_status: Optional[str]  # Plan generation status
    step2_phases: Optional[List[Dict]]  # Plan phases
    step2_total_estimated_steps: Optional[int]  # Total estimated steps
    step2_execution_time_ms: Optional[float]
    step2_error: Optional[str]

    # Step 2: CallGraph impact analysis (pre-change)
    step2_impact_analysis: Optional[Dict]  # CallGraph impact before change
    step2_graph_risk_level: Optional[str]  # "low", "medium", "high"
    step2_affected_methods: Optional[List[str]]  # Methods that could break
    step2_plan_validated: Optional[bool]  # Whether plan passed CallGraph validation
    step2_plan_validation_issues: Optional[List[str]]  # Validation issues found (empty = passed)

    # Step 3: Task Breakdown Validation (PHASE 2A - Renamed from step3_breakdown)
    step3_tasks_validated: Optional[List[Dict]]  # Validated task list
    step3_task_count: Optional[int]  # Number of validated tasks
    step3_validation_status: Optional[str]  # Validation status
    step3_validation_errors: Optional[List[str]]  # Any validation errors
    step3_execution_time_ms: Optional[float]
    step3_error: Optional[str]

    # Step 3: CallGraph phase-file mapping
    step3_phase_file_map: Annotated[Optional[Dict], _merge_dicts]  # {task_id: [files]} from graph analysis
    step3_graph_snapshot: Optional[Dict]  # Cached graph snapshot for Step 4 reuse

    # Step 4: TOON Refinement (PHASE 2A)
    # v1.15.2: step4_toon_refined removed (TOON removed in v1.15.0)
    step4_refinement_status: Optional[str]  # Refinement status
    step4_complexity_adjusted: Optional[int]  # Adjusted complexity
    step4_execution_time_ms: Optional[float]
    step4_error: Optional[str]

    # Step 4: Phase-scoped CallGraph context
    step4_phase_contexts: Optional[Dict]  # {task_id: phase_scoped_context} per phase
    step4_phase_scope_files: Optional[List[str]]  # All files in scope across phases
    step4_old_context_cleared: Optional[bool]  # Whether broad context was replaced with phase context

    # Step 5: Skill & Agent Selection (PHASE 2A - Renamed from step6_skill)
    step5_skill: str  # Selected skill name
    step5_agent: str  # Selected agent name
    step5_skill_definition: Optional[str]  # Full skill definition
    step5_agent_definition: Optional[str]  # Full agent definition
    step5_reasoning: str  # Reasoning for selection
    step5_confidence: float  # Confidence score
    step5_alternatives: List[Dict]  # Alternative selections
    step5_llm_query_needed: bool  # Whether LLM was needed
    step5_conflicts_detected: Optional[int]  # Number of skill/agent conflicts found
    step5_conflicts_removed: Optional[List[str]]  # Names removed due to conflicts
    step5_execution_time_ms: Optional[float]
    step5_error: Optional[str]

    # Step 6: Skill Validation & Download (PHASE 2A - Renamed from step6b_validation)
    step6_skill_validation: Optional[Dict]  # Validation results
    step6_skill_ready: bool  # Skill is ready to use
    step6_agent_ready: bool  # Agent is ready to use
    step6_validation_status: Optional[str]  # Validation status
    step6_execution_time_ms: Optional[float]
    step6_error: Optional[str]

    # Step 7: Final Prompt Generation (PHASE 2A - Renamed from step12_prompt)
    step7_prompt_saved: bool  # Prompt successfully saved
    step7_prompt_file: Optional[str]  # Path to saved prompt
    step7_prompt_size: Optional[int]  # Size of prompt in bytes
    step7_execution_time_ms: Optional[float]
    step7_error: Optional[str]

    # Step 8: GitHub Issue Creation (NEW - PHASE 2B)
    step8_issue_id: str  # GitHub issue ID
    step8_issue_url: str  # GitHub issue URL
    step8_issue_created: bool  # Issue successfully created
    step8_title: Optional[str]  # Issue title
    step8_label: Optional[str]  # Issue label (bug/feature/enhancement/etc)
    step8_status: Optional[str]  # Creation status (OK/ERROR/FALLBACK)
    step8_execution_time_ms: Optional[float]
    step8_error: Optional[str]

    # Step 9: Branch Creation (NEW - PHASE 2B)
    step9_branch_name: str  # Created branch name (may differ if conflict resolved)
    step9_original_branch: Optional[str]  # Originally requested branch name
    step9_branch_created: bool  # Branch successfully created
    step9_conflict_detected: Optional[bool]  # True if branch name collision was found & auto-resolved
    step9_status: Optional[str]  # Creation status (OK/ERROR)
    step9_execution_time_ms: Optional[float]
    step9_error: Optional[str]

    # Step 10: Implementation Execution (NEW - PHASE 2B)
    step10_tasks_executed: int  # Number of tasks executed
    step10_modified_files: List[str]  # List of modified files
    step10_implementation_status: str  # Implementation status (OK/ERROR)
    step10_changes_summary: Optional[Dict]  # Summary of changes
    step10_execution_time_ms: Optional[float]
    step10_error: Optional[str]

    # Step 10: CallGraph implementation context
    step10_call_context: Optional[Dict]  # Implementation context from CallGraph
    step10_pre_change_graph: Optional[Dict]  # Serialized CallGraph snapshot (before changes)
    step10_suggested_test_scope: Optional[List[str]]  # Test files to run
    call_graph_stale: Optional[
        bool
    ]  # True after Step 10 writes files; cached snapshots from pre-implementation are stale

    # Step 11: Pull Request & Code Review (NEW - PHASE 2B)
    step11_pr_id: str  # GitHub PR ID
    step11_pr_url: str  # GitHub PR URL
    step11_review_passed: bool  # Code review passed
    step11_review_issues: List[str]  # Issues found in review
    step11_merged: Optional[bool]  # PR was merged
    step11_retry_count: int  # Number of retry attempts
    step11_criteria_result: Optional[Dict]  # Full ReviewCriteria evaluation result
    step11_criteria_score: Optional[float]  # ReviewCriteria score (0.0-1.0)
    step11_status: Optional[str]  # PR status (OK/ERROR)
    step11_execution_time_ms: Optional[float]
    step11_error: Optional[str]

    # Step 11: CallGraph review analysis
    step11_impact_review: Optional[Dict]  # Post-change impact comparison
    step11_breaking_changes: Optional[List[Dict]]  # Methods with signature changes + callers
    step11_risk_assessment: Optional[str]  # "safe", "caution", "risky"

    # Step 12: Issue Closure (NEW - PHASE 2B)
    step12_issue_closed: bool  # Issue successfully closed
    step12_closing_comment: Optional[str]  # Closing comment text
    step12_status: Optional[str]  # Closure status (OK/ERROR)
    step12_execution_time_ms: Optional[float]
    step12_error: Optional[str]

    # ===========================================================================
    # INTEGRATION FIELDS: JIRA (optional, ENABLE_JIRA=1)
    # ===========================================================================
    jira_enabled: bool  # Jira integration active
    jira_project_key: Optional[str]  # Jira project key (PROJ)
    jira_issue_key: Optional[str]  # Created Jira issue key (PROJ-123)
    jira_issue_url: Optional[str]  # Jira issue URL
    jira_issue_created: bool  # Jira issue successfully created
    jira_pr_linked: bool  # PR linked to Jira via remote link
    jira_transitioned: bool  # Jira issue transitioned
    jira_issue_closed: bool  # Jira issue closed/Done
    jira_error: Optional[str]  # Last Jira error (non-blocking)

    # ===========================================================================
    # INTEGRATION FIELDS: FIGMA (optional, ENABLE_FIGMA=1)
    # ===========================================================================
    figma_enabled: bool  # Figma integration active
    figma_file_key: Optional[str]  # Figma file key extracted from URL
    figma_design_tokens: Optional[Dict]  # Extracted design tokens (colors, typography, etc.)
    figma_components: Optional[List]  # Extracted component list
    figma_prompt_snippet: Optional[str]  # Design token summary injected into prompt
    figma_error: Optional[str]  # Last Figma error (non-blocking)

    # Step 13: Project Documentation (PHASE 2A - Renamed from existing)
    step13_updates_prepared: bool  # Documentation updates prepared
    step13_update_count: int  # Number of updates
    step13_documentation_status: Optional[str]  # Update status (OK/ERROR)
    step13_updated_files: Optional[List[str]]  # Files that were updated
    step13_docs_created: Optional[List[str]]  # Files created (fresh project SDLC)
    step13_execution_time_ms: Optional[float]
    step13_error: Optional[str]

    # Step 14: Final Summary (PHASE 2A - Renamed from existing)
    step14_summary: Optional[Dict]  # Execution summary
    step14_status: Optional[str]  # Summary generation status
    step14_voice_sent: Optional[bool]  # Voice notification sent
    step14_execution_time_ms: Optional[float]
    step14_error: Optional[str]

    # Level 3 Overall Status (PHASE 2A)
    level3_status: Optional[str]  # Overall Level 3 execution status
    level3_total_execution_time_ms: Optional[float]

    # ===========================================================================
    # USER INTERACTION SYSTEM (FUTURE EXPANSION)
    # ===========================================================================
    user_interactions: Optional[List[Dict]]  # FUTURE: Log of all user Q&A during pipeline
    pending_interactions: Optional[List[Dict]]  # FUTURE: Unanswered questions for user

    # ===========================================================================
    # DEPENDENCY RESOLUTION (FUTURE EXPANSION)
    # ===========================================================================
    dependency_resolution: Optional[Dict]  # FUTURE: {internal, external, unknown deps}
    unresolved_internal_deps: Optional[List[Dict]]  # FUTURE: Deps needing user input for location
    dependency_graph_enhanced: Optional[bool]  # FUTURE: Whether graph was enhanced with resolved deps

    # ===========================================================================
    # WORKFLOW MEMORY & CONTEXT OPTIMIZATION
    # ===========================================================================
    # Temp memory store - keeps full outputs during workflow without bloating LLM context
    # Each step stores its full output here, but only passes optimized data to next step

    workflow_memory: Dict[str, Any]  # Full outputs: {'step0': {...}, 'step1': {...}}
    workflow_context_optimized: Dict[str, Any]  # Optimized context for LLM (compressed)
    workflow_context_tokens: int  # Estimated token count for current context
    workflow_memory_size_kb: float  # Size of workflow memory in KB

    # For each step: what data was compressed and by how much
    step_optimization_stats: Dict[str, Dict]  # {'step1': {'original_tokens': 500, 'optimized_tokens': 80}}

    # Session memory file path for persistence
    workflow_memory_file: str  # ~/.claude/memory/sessions/{session_id}/workflow-memory.json

    # ===========================================================================
    # PIPELINE & OUTPUT
    # ===========================================================================
    # For flow-trace.json (backward compatibility)
    # Annotated with _merge_lists to handle parallel node updates (Level 2 parallel writes)
    pipeline: Annotated[List[Dict], _merge_lists]

    # Final execution status
    final_status: str  # OK / PARTIAL / FAILED / BLOCKED

    # Errors and warnings (Annotated: multiple nodes can append errors concurrently)
    errors: Annotated[List[str], _merge_lists]
    warnings: Annotated[List[str], _merge_lists]

    # Execution metadata
    execution_time_ms: int  # Total execution time in milliseconds
    level_durations: Dict[str, int]  # Duration per level in milliseconds

    # ===========================================================================
    # SYNTHESIS OUTPUT (3-PHASE PROMPT SYNTHESIS)
    # ===========================================================================
    synthesized_prompt: str  # Comprehensive prompt created from 3-level flow data
    synthesis_metadata: Dict[str, Any]  # Metadata about synthesis (context_level, data_used, etc.)
