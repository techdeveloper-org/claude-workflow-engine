"""
FlowState TypedDict - Single source of truth for 3-level flow execution state.

This TypedDict defines all state fields passed through the LangGraph StateGraph.
Each node reads from and writes to relevant state fields, enabling:
- Type-safe state access across all nodes
- Clear field documentation and ownership
- Backward-compatible flow-trace.json output format
"""

from typing import TypedDict, Optional, List, Dict, Any, Annotated
from datetime import datetime


def _keep_first_value(current_value, update_value):
    """Reducer for immutable fields - always keep the first value.

    Used for session_id and other fields that should never change.
    This prevents LangGraph from complaining about multiple updates.
    """
    return current_value if current_value is not None else update_value


def _merge_lists(current_value, update_value):
    """Reducer for list fields that receive concurrent updates from parallel nodes.

    Merges lists instead of raising INVALID_CONCURRENT_GRAPH_UPDATE.
    Used for: pipeline, errors, warnings - fields written by multiple parallel nodes.
    """
    if current_value is None:
        return update_value if update_value is not None else []
    if update_value is None:
        return current_value
    if isinstance(current_value, list) and isinstance(update_value, list):
        return current_value + update_value
    return update_value


def _merge_dicts(current_value, update_value):
    """Reducer for dict fields that may receive concurrent updates.

    Merges dicts (update overwrites existing keys) instead of raising error.
    Used for: step3_phase_file_map and similar dict fields from parallel nodes.
    """
    if current_value is None:
        return update_value if update_value is not None else {}
    if update_value is None:
        return current_value
    if isinstance(current_value, dict) and isinstance(update_value, dict):
        merged = dict(current_value)
        merged.update(update_value)
        return merged
    return update_value


class FlowState(TypedDict, total=False):
    """Complete state for 3-level architecture execution.

    All fields are optional (total=False) to allow incremental state building.
    Each level and node populates relevant fields.
    """

    # ===========================================================================
    # SESSION IDENTIFICATION (all immutable - use reducer)
    # ===========================================================================
    session_id: Annotated[str, _keep_first_value]  # Immutable - never changes after init
    timestamp: Annotated[str, _keep_first_value]   # Immutable - set at session start
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
    level_minus1_status: str           # OK / BLOCKED / SKIPPED
    level_minus1_errors: List[str]     # Any auto-fix errors encountered

    # Auto-fix checks
    unicode_check: bool                # Windows Unicode fix applied
    unicode_check_error: Optional[str] # Error message if failed

    encoding_check: bool               # File encoding validation passed
    encoding_check_error: Optional[str]

    windows_path_check: bool           # Windows path validation passed
    windows_path_check_error: Optional[str]

    auto_fix_applied: List[str]        # List of auto-fixes that were applied

    # Failure Prevention KB
    failure_kb_loaded: Optional[bool]              # True if KB was parsed successfully
    failure_kb_suggestions: Optional[List[Dict]]   # KB matches for current failures

    # ===========================================================================
    # LEVEL 1: SYNC SYSTEM (4 PARALLEL TASKS)
    # ===========================================================================
    # All 4 tasks run in parallel, then merge

    # Context Management
    context_loaded: bool               # Successfully loaded context
    context_percentage: float          # Context usage (0-100)
    context_threshold_exceeded: bool   # True if context > 85% (emergency routing)
    context_error: Optional[str]
    context_metadata: Dict[str, Any]   # Additional context metadata

    # Context loader detail fields (Subtasks 3, 5, 6, 7, 8)
    context_skipped_files: Optional[List[str]]   # Files skipped due to size/timeout
    context_load_warnings: Optional[List[str]]   # Warnings from loader
    context_total_bytes: Optional[int]           # Total bytes loaded into memory
    context_cache_hit: Optional[bool]            # True if cache was used
    context_cache_age_hours: Optional[float]     # Age of cache entry used
    context_cache_key: Optional[str]             # Cache key (MD5 of project path)

    # Toon compression integrity
    toon_integrity_ok: Optional[bool]            # True if compression integrity verified

    # Session Management
    session_chain_loaded: bool         # Session chain initialized
    session_history: List[Dict]        # Previous session data
    session_state_data: Dict[str, Any]  # Current session state
    session_error: Optional[str]
    session_parent_id: Optional[str]           # Parent session ID (for chaining)
    session_tags: Optional[List[str]]          # Auto-tags from user message keywords
    session_pruning_errors: Optional[List[str]]  # Errors from session pruning

    # User Preferences
    preferences_loaded: bool           # User preferences initialized
    preferences_data: Dict[str, Any]   # Loaded preferences
    preferences_error: Optional[str]

    # Pattern Detection
    patterns_detected: List[str]       # Cross-project patterns found
    pattern_metadata: Dict[str, Any]   # Pattern analysis data
    patterns_error: Optional[str]

    # Level 1 merge result
    level1_status: str                 # OK / PARTIAL / FAILED
    level1_context_toon: Optional[Dict]  # TOON-formatted context from Level 1 (for Level 3)

    # Level 1 TOON schema validation result
    toon_schema_valid: Optional[bool]       # True if TOON passed validate_toon()
    toon_schema_errors: Optional[List[str]] # Validation error messages (empty list = valid)
    toon_version: Optional[str]             # TOON schema version used ("1.0.0")

    # Level 1 complexity (also stored inside TOON but kept in state for quick access)
    complexity_score: Optional[int]         # 1-10 score from complexity_calculator
    complexity_calculated: Optional[bool]   # Whether calculation succeeded
    complexity_error: Optional[str]         # Error if calculation failed

    # Level 1 graph-based complexity (NetworkX + Lizard)
    graph_complexity_score: Optional[int]       # 1-25 graph-based score
    graph_metrics: Optional[Dict]               # density, centrality, coupling, etc.
    cyclomatic_complexity_avg: Optional[float]  # average cyclomatic complexity
    combined_complexity_score: Optional[int]    # final combined 1-25 score

    # Level 1 caching
    context_cache_hit: Optional[bool]       # True if cache was valid and used
    context_cache_age_hours: Optional[float]  # How old the cached context is
    context_cache_key: Optional[str]        # Cache key (SHA-256 of project path)

    # Level 1 optimization metrics (Task #6)
    context_load_time_ms: Optional[int]        # Wall-clock ms for context load
    context_hit_rate_pct: Optional[float]      # Session cache hit rate percentage (0-100)
    context_streamed_files: Optional[List[str]]  # Files loaded via streaming (large files)

    # ===========================================================================
    # LEVEL 2: STANDARDS SYSTEM
    # ===========================================================================
    standards_loaded: bool             # Common standards loaded
    standards_count: int               # Number of standards loaded
    standards_error: Optional[str]

    # Java-specific standards (only if is_java_project=True)
    java_standards_loaded: bool        # Java/Spring standards loaded
    spring_boot_patterns: Dict         # Spring Boot-specific patterns
    java_standards_error: Optional[str]

    # Tool Optimization Standards (loaded at Level 2, enforced by PreToolUse hook)
    tool_optimization_rules: Optional[Dict]   # {read_max_lines, grep_max_matches, etc.}
    tool_optimization_loaded: Optional[bool]  # True after Level 2 loads rules

    # ===========================================================================
    # LEVEL 2: MCP REGISTRY & PLUGIN DISCOVERY (NEW)
    # ===========================================================================
    mcp_servers_available: Optional[List[Dict]]   # All discovered MCP plugins with metadata
    mcp_filesystem_enabled: Optional[bool]        # True if Filesystem MCP available
    mcp_plugins_path: Optional[str]               # Path to plugins directory (usually ~/.claude/mcp/plugins/)
    mcp_cache_dir: Optional[str]                  # Cache directory (usually ~/.claude/mcp/cache/)
    mcp_discovered_count: Optional[int]           # Number of MCPs successfully discovered
    mcp_initialization_status: Optional[str]      # OK / PARTIAL / ERROR / SKIPPED
    mcp_error: Optional[str]                      # Error message if initialization failed
    mcp_auto_routing_enabled: Optional[bool]      # Enable AUTO-ROUTE in hook (true if filesystem available)

    # Standards selector result (level2_select_standards_node output)
    standards_selection: Optional[Dict]       # {project_type, framework, total_loaded, conflicts_detected, merged_rules}
    standards_merged_rules: Optional[Dict]    # Conflict-resolved merged rules from all standards sources
    detected_framework: Optional[str]         # Framework detected by standard_selector (flask/django/spring-boot/react/etc.)
    standards_selection_error: Optional[str]  # Error from standards selector (non-fatal)

    # Standards integration hook outputs (set at each pipeline step)
    standards_applied_step1: Optional[bool]   # Standards applied at Step 1 (plan mode decision)
    standards_applied_step2: Optional[bool]   # Standards applied at Step 2 (plan execution)
    standards_applied_step5: Optional[bool]   # Standards applied at Step 5 (skill selection)
    standards_applied_step10: Optional[bool]  # Standards applied at Step 10 (code review)
    standards_applied_step13: Optional[bool]  # Standards applied at Step 13 (documentation)

    # Step-specific standards context injected by integration hooks
    step1_standards_context: Optional[Dict]         # Standards metadata for plan complexity scorer
    step2_standards_constraints: Optional[Dict]     # Naming/layer constraints for planner
    step5_standards_validation: Optional[Dict]      # Skill/standards compatibility check result
    step10_standards_checklist: Optional[Dict]      # Code review compliance checklist
    step13_standards_doc_requirements: Optional[Dict]  # Documentation update requirements

    # Level 2: Standards enforcement (linting, non-blocking)
    standards_enforcement_ran: Optional[bool]      # True if linter ran successfully
    standards_violations: Optional[List[Dict]]     # List of {file, line, code, message, severity}
    standards_violations_count: Optional[int]      # Total violations found (max 20 returned)
    standards_linter_used: Optional[str]           # Linter used: ruff / flake8 / none

    level2_status: str                 # OK / PARTIAL / FAILED

    # ===========================================================================
    # LEVEL 3: EXECUTION SYSTEM (15 STEPS)
    # ===========================================================================

    # Step 0.0: Pre-flight - Project Context
    step0_0_project_context: Optional[Dict]        # README, CHANGELOG, VERSION, etc.
    step0_0_files_read: Optional[List[str]]        # Files successfully read
    step0_0_error: Optional[str]
    step0_0_execution_time_ms: Optional[float]

    # Step 0.1: Pre-flight - Initial CallGraph Snapshot
    step0_1_initial_callgraph: Optional[Dict]      # Baseline call graph for Step 11 diff
    step0_1_callgraph_available: Optional[bool]    # True if snapshot succeeded
    step0_1_error: Optional[str]
    step0_1_execution_time_ms: Optional[float]

    # User Preferences Context (extracted from Level 1 preferences_data)
    user_preferences_context: Optional[Dict]       # Pre-computed model/skill/complexity hints

    # Step 0: Prompt Generation
    step0_prompt: Dict                 # Prompt context and metadata
    step0_task_type: str               # Detected task type
    step0_error: Optional[str]

    # Step 1: Task Breakdown
    step1_tasks: Dict                  # Broken down tasks
    step1_task_count: int              # Number of tasks identified
    step1_error: Optional[str]

    # Step 2: Plan Mode Decision
    step2_plan_mode: bool              # Whether to suggest EnterPlanMode
    step2_reasoning: str               # Why plan mode was chosen
    step2_error: Optional[str]

    # Step 3: Context Read Enforcement
    step3_context_read: bool           # Context read check passed
    step3_enforcement_applies: bool    # Whether enforcement applies to this project
    step3_error: Optional[str]

    # Step 4: Model Selection
    step4_model: str                   # Selected model: fast_classification/complex_reasoning
    step4_reasoning: str               # Why this model was chosen
    step4_error: Optional[str]

    # Step 5: Skill & Agent Selection (with Phase 2 DeepSeek reasoning)
    step5_skill: str                   # Selected skill name (if any)
    step5_agent: str                   # Selected agent name (if any)
    step5_reasoning: str               # Why this skill/agent was chosen
    step5_error: Optional[str]
    step5_llm_query_needed: bool       # True if LLM needed to decide
    # Phase 2: DeepSeek Enhanced Selection
    step5_deepseek_mcp_reasoning: Optional[Dict]  # DeepSeek MCP analysis result
    step5_deepseek_skill_eval: Optional[Dict]    # DeepSeek skill/agent evaluation
    step5_deepseek_used: Optional[bool]          # True if DeepSeek was called
    step5_mcp_selected: Optional[List[str]]      # MCPs selected based on reasoning
    step5_mcp_reasoning: Optional[str]           # Why these MCPs were selected

    # Step 6: Tool Optimization
    step6_tool_hints: List[str]        # Optimization hints for tools
    step6_read_optimization: Dict      # Read tool optimization (offset, limit)
    step6_grep_optimization: Dict      # Grep tool optimization (head_limit)
    step6_error: Optional[str]

    # Step 7: Auto-Recommendations
    step7_recommendations: List[str]   # Automatic recommendations to user
    step7_error: Optional[str]

    # Step 8: Progress Tracking
    step8_progress: Dict               # Task progress metadata
    step8_incomplete_work: List[str]   # Any incomplete work detected
    step8_error: Optional[str]

    # Step 9: Git Commit Preparation
    step9_commit_ready: bool           # Commit can be auto-created
    step9_commit_message: str          # Prepared commit message
    step9_version_bump: str            # Version to bump to
    step9_error: Optional[str]

    # Step 10: Session Save
    step10_session: Dict               # Session save preparation
    step10_archive_needed: bool        # Session should be archived
    step10_error: Optional[str]

    # Step 11 (implicit): Failure Prevention
    failure_prevention: Dict           # Failure KB checks
    failure_prevention_warnings: List[str]  # Warnings from failure KB

    # ===========================================================================
    # WORKFLOW MEMORY & CONTEXT OPTIMIZATION
    # ===========================================================================
    # Temp memory store - keeps full outputs during workflow without bloating LLM context
    # Each step stores its full output here, but only passes optimized data to next step

    workflow_memory: Dict[str, Any]    # Full outputs: {'step0': {...}, 'step1': {...}}
    workflow_context_optimized: Dict[str, Any]  # Optimized context for LLM (compressed)
    workflow_context_tokens: int       # Estimated token count for current context
    workflow_memory_size_kb: float     # Size of workflow memory in KB

    # For each step: what data was compressed and by how much
    step_optimization_stats: Dict[str, Dict]  # {'step1': {'original_tokens': 500, 'optimized_tokens': 80}}

    # Session memory file path for persistence
    workflow_memory_file: str          # ~/.claude/memory/sessions/{session_id}/workflow-memory.json

    # ===========================================================================
    # PIPELINE & OUTPUT
    # ===========================================================================
    # For flow-trace.json (backward compatibility)
    # Annotated with _merge_lists to handle parallel node updates (Level 2 parallel writes)
    pipeline: Annotated[List[Dict], _merge_lists]

    # Final execution status
    final_status: str                  # OK / PARTIAL / FAILED / BLOCKED

    # Errors and warnings (Annotated: multiple nodes can append errors concurrently)
    errors: Annotated[List[str], _merge_lists]
    warnings: Annotated[List[str], _merge_lists]

    # Execution metadata
    execution_time_ms: int             # Total execution time in milliseconds
    level_durations: Dict[str, int]    # Duration per level in milliseconds

    # ===========================================================================
    # SYNTHESIS OUTPUT (3-PHASE PROMPT SYNTHESIS)
    # ===========================================================================
    synthesized_prompt: str            # Comprehensive prompt created from 3-level flow data
    synthesis_metadata: Dict[str, Any] # Metadata about synthesis (context_level, data_used, etc.)

    # ===========================================================================
    # v2 LEVEL 3 PIPELINE FIELDS (14-STEP WORKFLOW.MD COMPLIANT)
    # ===========================================================================
    # Bridge fields
    session_dir: Optional[str]         # v2 uses session_dir (str path)
    user_requirement: Optional[str]    # Alias for user_message in v2 context

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
    step2_code_context: Optional[str]        # Code analysis from exploration tools
    step2_selected_model: Optional[str]      # Which model was used (fast_classification/complex_reasoning)
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
    step0_task_type: str               # Detected task type
    step0_complexity: int              # Complexity score (1-10)
    step0_reasoning: str               # Reasoning for task analysis
    step0_tasks: Dict                  # Broken down tasks
    step0_task_count: int              # Number of tasks identified
    step0_docs_found: Optional[Dict[str, Any]]  # Which project docs exist (SDLC read phase)
    step0_target_files: Optional[List[str]]    # Target files identified from task analysis
    step0_error: Optional[str]

    # Step 1: Plan Mode Decision (PHASE 2A - Renamed from step2_plan_mode)
    step1_plan_required: bool          # Whether plan mode is needed
    step1_reasoning: str               # Reasoning for plan decision
    step1_complexity_score: int        # Complexity score from Step 1
    step1_execution_time_ms: Optional[float]
    step1_error: Optional[str]

    # Step 2: Plan Execution (PHASE 2A - Renamed from step2b_plan_exec)
    step2_plan_execution: Optional[Dict]       # Detailed execution plan
    step2_plan_status: Optional[str]           # Plan generation status
    step2_phases: Optional[List[Dict]]         # Plan phases
    step2_total_estimated_steps: Optional[int] # Total estimated steps
    step2_execution_time_ms: Optional[float]
    step2_error: Optional[str]

    # Step 2: CallGraph impact analysis (pre-change)
    step2_impact_analysis: Optional[Dict]          # CallGraph impact before change
    step2_graph_risk_level: Optional[str]          # "low", "medium", "high"
    step2_affected_methods: Optional[List[str]]    # Methods that could break
    step2_plan_validated: Optional[bool]           # Whether plan passed CallGraph validation
    step2_plan_validation_issues: Optional[List[str]]  # Validation issues found (empty = passed)

    # Step 3: Task Breakdown Validation (PHASE 2A - Renamed from step3_breakdown)
    step3_tasks_validated: Optional[List[Dict]]      # Validated task list
    step3_task_count: Optional[int]                   # Number of validated tasks
    step3_validation_status: Optional[str]            # Validation status
    step3_validation_errors: Optional[List[str]]      # Any validation errors
    step3_execution_time_ms: Optional[float]
    step3_error: Optional[str]

    # Step 3: CallGraph phase-file mapping
    step3_phase_file_map: Annotated[Optional[Dict], _merge_dicts]  # {task_id: [files]} from graph analysis
    step3_graph_snapshot: Optional[Dict]            # Cached graph snapshot for Step 4 reuse

    # Step 4: TOON Refinement (PHASE 2A - Kept as is)
    step4_toon_refined: Optional[Dict]         # Refined TOON object
    step4_refinement_status: Optional[str]     # Refinement status
    step4_complexity_adjusted: Optional[int]   # Adjusted complexity
    step4_execution_time_ms: Optional[float]
    step4_error: Optional[str]

    # Step 4: Phase-scoped CallGraph context
    step4_phase_contexts: Optional[Dict]           # {task_id: phase_scoped_context} per phase
    step4_phase_scope_files: Optional[List[str]]   # All files in scope across phases
    step4_old_context_cleared: Optional[bool]      # Whether broad context was replaced with phase context

    # Step 5: Skill & Agent Selection (PHASE 2A - Renamed from step6_skill)
    step5_skill: str                           # Selected skill name
    step5_agent: str                           # Selected agent name
    step5_skill_definition: Optional[str]      # Full skill definition
    step5_agent_definition: Optional[str]      # Full agent definition
    step5_reasoning: str                       # Reasoning for selection
    step5_confidence: float                    # Confidence score
    step5_alternatives: List[Dict]             # Alternative selections
    step5_llm_query_needed: bool               # Whether LLM was needed
    step5_conflicts_detected: Optional[int]    # Number of skill/agent conflicts found
    step5_conflicts_removed: Optional[List[str]]  # Names removed due to conflicts
    step5_execution_time_ms: Optional[float]
    step5_error: Optional[str]

    # Step 6: Skill Validation & Download (PHASE 2A - Renamed from step6b_validation)
    step6_skill_validation: Optional[Dict]     # Validation results
    step6_skill_ready: bool                    # Skill is ready to use
    step6_agent_ready: bool                    # Agent is ready to use
    step6_validation_status: Optional[str]     # Validation status
    step6_execution_time_ms: Optional[float]
    step6_error: Optional[str]

    # Step 7: Final Prompt Generation (PHASE 2A - Renamed from step12_prompt)
    step7_prompt_saved: bool                   # Prompt successfully saved
    step7_prompt_file: Optional[str]           # Path to saved prompt
    step7_prompt_size: Optional[int]           # Size of prompt in bytes
    step7_execution_time_ms: Optional[float]
    step7_error: Optional[str]

    # Step 8: GitHub Issue Creation (NEW - PHASE 2B)
    step8_issue_id: str                        # GitHub issue ID
    step8_issue_url: str                       # GitHub issue URL
    step8_issue_created: bool                  # Issue successfully created
    step8_title: Optional[str]                 # Issue title
    step8_label: Optional[str]                 # Issue label (bug/feature/enhancement/etc)
    step8_status: Optional[str]                # Creation status (OK/ERROR/FALLBACK)
    step8_execution_time_ms: Optional[float]
    step8_error: Optional[str]

    # Step 9: Branch Creation (NEW - PHASE 2B)
    step9_branch_name: str                     # Created branch name (may differ if conflict resolved)
    step9_original_branch: Optional[str]       # Originally requested branch name
    step9_branch_created: bool                 # Branch successfully created
    step9_conflict_detected: Optional[bool]    # True if branch name collision was found & auto-resolved
    step9_status: Optional[str]                # Creation status (OK/ERROR)
    step9_execution_time_ms: Optional[float]
    step9_error: Optional[str]

    # Step 10: Implementation Execution (NEW - PHASE 2B)
    step10_tasks_executed: int                 # Number of tasks executed
    step10_modified_files: List[str]           # List of modified files
    step10_implementation_status: str          # Implementation status (OK/ERROR)
    step10_changes_summary: Optional[Dict]     # Summary of changes
    step10_execution_time_ms: Optional[float]
    step10_error: Optional[str]

    # Step 10: CallGraph implementation context
    step10_call_context: Optional[Dict]            # Implementation context from CallGraph
    step10_pre_change_graph: Optional[Dict]        # Serialized CallGraph snapshot (before changes)
    step10_suggested_test_scope: Optional[List[str]]  # Test files to run

    # Step 11: Pull Request & Code Review (NEW - PHASE 2B)
    step11_pr_id: str                          # GitHub PR ID
    step11_pr_url: str                         # GitHub PR URL
    step11_review_passed: bool                 # Code review passed
    step11_review_issues: List[str]            # Issues found in review
    step11_merged: Optional[bool]             # PR was merged
    step11_retry_count: int                    # Number of retry attempts
    step11_criteria_result: Optional[Dict]     # Full ReviewCriteria evaluation result
    step11_criteria_score: Optional[float]     # ReviewCriteria score (0.0-1.0)
    step11_status: Optional[str]               # PR status (OK/ERROR)
    step11_execution_time_ms: Optional[float]
    step11_error: Optional[str]

    # Step 11: CallGraph review analysis
    step11_impact_review: Optional[Dict]           # Post-change impact comparison
    step11_breaking_changes: Optional[List[Dict]]  # Methods with signature changes + callers
    step11_risk_assessment: Optional[str]          # "safe", "caution", "risky"

    # Step 12: Issue Closure (NEW - PHASE 2B)
    step12_issue_closed: bool                  # Issue successfully closed
    step12_closing_comment: Optional[str]      # Closing comment text
    step12_status: Optional[str]               # Closure status (OK/ERROR)
    step12_execution_time_ms: Optional[float]
    step12_error: Optional[str]

    # -- Jira Integration (optional, ENABLE_JIRA=1) -----------------------
    jira_enabled: bool                         # Jira integration active
    jira_project_key: Optional[str]            # Jira project key (PROJ)
    jira_issue_key: Optional[str]              # Created Jira issue key (PROJ-123)
    jira_issue_url: Optional[str]              # Jira issue URL
    jira_issue_created: bool                   # Jira issue successfully created
    jira_pr_linked: bool                       # PR linked to Jira via remote link
    jira_transitioned: bool                    # Jira issue transitioned
    jira_issue_closed: bool                    # Jira issue closed/Done
    jira_error: Optional[str]                  # Last Jira error (non-blocking)

    # Step 13: Project Documentation (PHASE 2A - Renamed from existing)
    step13_updates_prepared: bool              # Documentation updates prepared
    step13_update_count: int                   # Number of updates
    step13_documentation_status: Optional[str] # Update status (OK/ERROR)
    step13_updated_files: Optional[List[str]]  # Files that were updated
    step13_docs_created: Optional[List[str]]   # Files created (fresh project SDLC)
    step13_execution_time_ms: Optional[float]
    step13_error: Optional[str]

    # Step 14: Final Summary (PHASE 2A - Renamed from existing)
    step14_summary: Optional[Dict]             # Execution summary
    step14_status: Optional[str]               # Summary generation status
    step14_voice_sent: Optional[bool]          # Voice notification sent
    step14_execution_time_ms: Optional[float]
    step14_error: Optional[str]

    # Level 3 Overall Status (PHASE 2A)
    level3_status: Optional[str]               # Overall Level 3 execution status
    level3_total_execution_time_ms: Optional[float]

    # ===========================================================================
    # USER INTERACTION SYSTEM (FUTURE EXPANSION)
    # ===========================================================================
    user_interactions: Optional[List[Dict]]        # FUTURE: Log of all user Q&A during pipeline
    pending_interactions: Optional[List[Dict]]     # FUTURE: Unanswered questions for user

    # ===========================================================================
    # DEPENDENCY RESOLUTION (FUTURE EXPANSION)
    # ===========================================================================
    dependency_resolution: Optional[Dict]          # FUTURE: {internal, external, unknown deps}
    unresolved_internal_deps: Optional[List[Dict]] # FUTURE: Deps needing user input for location
    dependency_graph_enhanced: Optional[bool]      # FUTURE: Whether graph was enhanced with resolved deps


# ==============================================================================
# STEP KEYS - Constants for flow state keys (eliminates stringly-typed access)
# ==============================================================================


class StepKeys:
    """Constants for flow state dictionary keys.

    Centralizes all step state key strings so typos become import errors
    instead of silent bugs. String VALUES are preserved for backward
    compatibility with flow-trace.json and existing state serialization.

    Usage:
        state.get(StepKeys.TASK_TYPE, "task")
        state[StepKeys.REVIEW_PASSED] = True
    """

    # ------------------------------------------------------------------
    # SESSION / PROJECT IDENTIFICATION
    # ------------------------------------------------------------------
    SESSION_ID = "session_id"
    TIMESTAMP = "timestamp"
    PROJECT_ROOT = "project_root"
    IS_JAVA_PROJECT = "is_java_project"
    IS_FRESH_PROJECT = "is_fresh_project"
    SESSION_DIR = "session_dir"
    SESSION_PATH = "session_path"

    # ------------------------------------------------------------------
    # USER MESSAGE
    # ------------------------------------------------------------------
    USER_MESSAGE = "user_message"
    USER_MESSAGE_ORIGINAL = "user_message_original"

    # ------------------------------------------------------------------
    # LEVEL -1: AUTO-FIX
    # ------------------------------------------------------------------
    LEVEL_MINUS1_STATUS = "level_minus1_status"
    LEVEL_MINUS1_USER_CHOICE = "level_minus1_user_choice"
    LEVEL_MINUS1_RETRY_COUNT = "level_minus1_retry_count"
    UNICODE_CHECK = "unicode_check"
    ENCODING_CHECK = "encoding_check"
    WINDOWS_PATH_CHECK = "windows_path_check"
    FAILURE_KB_LOADED = "failure_kb_loaded"
    FAILURE_KB_SUGGESTIONS = "failure_kb_suggestions"

    # ------------------------------------------------------------------
    # LEVEL 1: SYNC SYSTEM
    # ------------------------------------------------------------------
    CONTEXT_LOADED = "context_loaded"
    CONTEXT_PERCENTAGE = "context_percentage"
    CONTEXT_THRESHOLD_EXCEEDED = "context_threshold_exceeded"
    CONTEXT_CACHE_HIT = "context_cache_hit"
    FILES_LOADED_COUNT = "files_loaded_count"
    SESSION_CHAIN_LOADED = "session_chain_loaded"
    SESSION_PARENT_ID = "session_parent_id"
    SESSION_TAGS = "session_tags"
    SESSION_PRUNING_ERRORS = "session_pruning_errors"
    PATTERNS_DETECTED = "patterns_detected"
    PREFERENCES_DATA = "preferences_data"
    TOON_SAVED = "toon_saved"
    COMPLEXITY_SCORE = "complexity_score"
    GRAPH_COMPLEXITY_SCORE = "graph_complexity_score"
    COMBINED_COMPLEXITY_SCORE = "combined_complexity_score"
    LEVEL1_STATUS = "level1_status"

    # ------------------------------------------------------------------
    # LEVEL 2: STANDARDS
    # ------------------------------------------------------------------
    STANDARDS_LOADED = "standards_loaded"
    STANDARDS_COUNT = "standards_count"
    JAVA_STANDARDS_LOADED = "java_standards_loaded"
    SPRING_BOOT_PATTERNS = "spring_boot_patterns"
    TOOL_OPTIMIZATION_RULES = "tool_optimization_rules"
    TOOL_OPTIMIZATION_LOADED = "tool_optimization_loaded"
    DETECTED_FRAMEWORK = "detected_framework"
    MCP_DISCOVERED_COUNT = "mcp_discovered_count"
    LEVEL2_STATUS = "level2_status"

    # ------------------------------------------------------------------
    # STEP 0.0: PRE-FLIGHT - PROJECT CONTEXT
    # ------------------------------------------------------------------
    STEP0_0_PROJECT_CONTEXT = "step0_0_project_context"
    STEP0_0_FILES_READ = "step0_0_files_read"
    STEP0_0_ERROR = "step0_0_error"
    STEP0_0_EXECUTION_TIME_MS = "step0_0_execution_time_ms"

    # ------------------------------------------------------------------
    # STEP 0.1: PRE-FLIGHT - INITIAL CALLGRAPH
    # ------------------------------------------------------------------
    STEP0_1_INITIAL_CALLGRAPH = "step0_1_initial_callgraph"
    STEP0_1_CALLGRAPH_AVAILABLE = "step0_1_callgraph_available"
    STEP0_1_ERROR = "step0_1_error"
    STEP0_1_EXECUTION_TIME_MS = "step0_1_execution_time_ms"

    # ------------------------------------------------------------------
    # USER PREFERENCES CONTEXT
    # ------------------------------------------------------------------
    USER_PREFERENCES_CONTEXT = "user_preferences_context"

    # ------------------------------------------------------------------
    # STEP 0: TASK ANALYSIS
    # ------------------------------------------------------------------
    TASK_TYPE = "step0_task_type"
    COMPLEXITY = "step0_complexity"
    REASONING = "step0_reasoning"
    TASKS = "step0_tasks"
    TASK_COUNT = "step0_task_count"
    STEP0_DOCS_FOUND = "step0_docs_found"
    STEP0_TARGET_FILES = "step0_target_files"
    STEP0_ERROR = "step0_error"

    # ------------------------------------------------------------------
    # STEP 1: PLAN MODE DECISION
    # ------------------------------------------------------------------
    PLAN_REQUIRED = "step1_plan_required"
    STEP1_REASONING = "step1_reasoning"
    STEP1_ERROR = "step1_error"

    # ------------------------------------------------------------------
    # STEP 2: PLAN EXECUTION
    # ------------------------------------------------------------------
    PLAN_EXECUTION = "step2_plan_execution"
    PLAN_STATUS = "step2_plan_status"
    STEP2_ERROR = "step2_error"
    STEP2_IMPACT_ANALYSIS = "step2_impact_analysis"
    STEP2_GRAPH_RISK_LEVEL = "step2_graph_risk_level"
    STEP2_AFFECTED_METHODS = "step2_affected_methods"

    # ------------------------------------------------------------------
    # STEP 3: TASK BREAKDOWN VALIDATION
    # ------------------------------------------------------------------
    TASKS_VALIDATED = "step3_tasks_validated"
    STEP3_TASK_COUNT = "step3_task_count"
    STEP3_VALIDATION_STATUS = "step3_validation_status"
    STEP3_ERROR = "step3_error"
    STEP3_PHASE_FILE_MAP = "step3_phase_file_map"
    STEP3_GRAPH_SNAPSHOT = "step3_graph_snapshot"

    # ------------------------------------------------------------------
    # STEP 4: TOON REFINEMENT
    # ------------------------------------------------------------------
    SELECTED_MODEL = "step4_model"
    STEP4_REFINEMENT_STATUS = "step4_refinement_status"
    STEP4_COMPLEXITY_ADJUSTED = "step4_complexity_adjusted"
    STEP4_ERROR = "step4_error"
    STEP4_PHASE_CONTEXTS = "step4_phase_contexts"
    STEP4_PHASE_SCOPE_FILES = "step4_phase_scope_files"
    STEP4_OLD_CONTEXT_CLEARED = "step4_old_context_cleared"

    # ------------------------------------------------------------------
    # STEP 5: SKILL & AGENT SELECTION
    # ------------------------------------------------------------------
    SKILL = "step5_skill"
    AGENT = "step5_agent"
    SKILLS = "step5_skills"
    AGENTS = "step5_agents"
    SKILL_DEFINITION = "step5_skill_definition"
    AGENT_DEFINITION = "step5_agent_definition"
    STEP5_REASONING = "step5_reasoning"
    STEP5_ERROR = "step5_error"

    # ------------------------------------------------------------------
    # STEP 6: SKILL VALIDATION
    # ------------------------------------------------------------------
    STEP6_VALIDATION_STATUS = "step6_validation_status"
    SKILL_READY = "step6_skill_ready"
    AGENT_READY = "step6_agent_ready"
    STEP6_ERROR = "step6_error"

    # ------------------------------------------------------------------
    # STEP 7: FINAL PROMPT GENERATION
    # ------------------------------------------------------------------
    PROMPT_SAVED = "step7_prompt_saved"
    PROMPT_FILE = "step7_prompt_file"
    PROMPT_SIZE = "step7_prompt_size"
    STEP7_ERROR = "step7_error"

    # ------------------------------------------------------------------
    # STEP 8: GITHUB ISSUE CREATION
    # ------------------------------------------------------------------
    ISSUE_STATUS = "step8_status"
    ISSUE_URL = "step8_issue_url"
    STEP8_ERROR = "step8_error"

    # ------------------------------------------------------------------
    # STEP 9: BRANCH CREATION
    # ------------------------------------------------------------------
    BRANCH_NAME = "step9_branch_name"
    BRANCH_STATUS = "step9_status"
    STEP9_ERROR = "step9_error"

    # ------------------------------------------------------------------
    # STEP 10: IMPLEMENTATION EXECUTION
    # ------------------------------------------------------------------
    IMPLEMENTATION_STATUS = "step10_implementation_status"
    STEP10_ERROR = "step10_error"
    STEP10_CALL_CONTEXT = "step10_call_context"
    STEP10_PRE_CHANGE_GRAPH = "step10_pre_change_graph"
    STEP10_SUGGESTED_TEST_SCOPE = "step10_suggested_test_scope"

    # ------------------------------------------------------------------
    # STEP 11: PR & CODE REVIEW
    # ------------------------------------------------------------------
    REVIEW_PASSED = "step11_review_passed"
    RETRY_COUNT = "step11_retry_count"
    PR_URL = "step11_pr_url"
    STEP11_STATUS = "step11_status"
    STEP11_ERROR = "step11_error"
    STEP11_IMPACT_REVIEW = "step11_impact_review"
    STEP11_BREAKING_CHANGES = "step11_breaking_changes"
    STEP11_RISK_ASSESSMENT = "step11_risk_assessment"

    # ------------------------------------------------------------------
    # STEP 12: ISSUE CLOSURE
    # ------------------------------------------------------------------
    ISSUE_CLOSED = "step12_issue_closed"
    STEP12_STATUS = "step12_status"
    STEP12_ERROR = "step12_error"

    # ------------------------------------------------------------------
    # JIRA INTEGRATION
    # ------------------------------------------------------------------
    JIRA_ENABLED = "jira_enabled"
    JIRA_ISSUE_KEY = "jira_issue_key"
    JIRA_ISSUE_URL = "jira_issue_url"
    JIRA_ISSUE_CREATED = "jira_issue_created"
    JIRA_PR_LINKED = "jira_pr_linked"
    JIRA_ISSUE_CLOSED = "jira_issue_closed"
    JIRA_ERROR = "jira_error"

    # ------------------------------------------------------------------
    # STEP 13: DOCUMENTATION
    # ------------------------------------------------------------------
    DOCUMENTATION_STATUS = "step13_documentation_status"
    UPDATE_COUNT = "step13_update_count"
    STEP13_DOCS_CREATED = "step13_docs_created"
    STEP13_ERROR = "step13_error"

    # ------------------------------------------------------------------
    # STEP 14: FINAL SUMMARY
    # ------------------------------------------------------------------
    SUMMARY_SAVED = "step14_summary_saved"
    STEP14_STATUS = "step14_status"
    VOICE_SENT = "step14_voice_sent"
    STEP14_ERROR = "step14_error"

    # ------------------------------------------------------------------
    # WORKFLOW MEMORY & OPTIMIZATION
    # ------------------------------------------------------------------
    WORKFLOW_MEMORY = "workflow_memory"
    WORKFLOW_MEMORY_SIZE_KB = "workflow_memory_size_kb"
    STEP_OPTIMIZATION_STATS = "step_optimization_stats"

    # ------------------------------------------------------------------
    # PIPELINE & OUTPUT
    # ------------------------------------------------------------------
    PIPELINE = "pipeline"
    ERRORS = "errors"
    WARNINGS = "warnings"
    FINAL_STATUS = "final_status"

    # ------------------------------------------------------------------
    # USER INTERACTION SYSTEM
    # ------------------------------------------------------------------
    USER_INTERACTIONS = "user_interactions"
    PENDING_INTERACTIONS = "pending_interactions"

    # ------------------------------------------------------------------
    # DEPENDENCY RESOLUTION
    # ------------------------------------------------------------------
    DEPENDENCY_RESOLUTION = "dependency_resolution"
    UNRESOLVED_INTERNAL_DEPS = "unresolved_internal_deps"
    DEPENDENCY_GRAPH_ENHANCED = "dependency_graph_enhanced"


# ==============================================================================
# WORKFLOW CONTEXT OPTIMIZER - Smart context compression for LLM efficiency
# ==============================================================================

class ToonObject:
    """TOON Format - Tokenized Object-Oriented Notation.

    Compact, semantic-preserving data format for workflow context.
    - Stores data in compressed "essential" form
    - Maintains reference to full data in workflow_memory
    - Includes schema for smart reconstruction
    - Preserves deep semantic meaning in minimal space

    Example:
    {
        "_toon": True,
        "_schema": "task_list",
        "_version": "1.0",
        "essential": {"count": 5, "critical": ["auth", "db"]},
        "metadata": {"original_size_kb": 45, "compressed_size_kb": 2},
        "_memory_key": "step1_output"
    }
    """

    @staticmethod
    def create(schema: str, essential_data: Dict, full_data: Dict = None, memory_key: str = "") -> Dict:
        """Create a TOON object.

        Args:
            schema: Type of data (e.g., "task_list", "context_status")
            essential_data: Minimal representation of data
            full_data: Full data (for size calculation)
            memory_key: Reference to where full data is stored

        Returns:
            TOON-formatted dict
        """
        full_size = len(str(full_data).encode()) / 1024 if full_data else 0
        essential_size = len(str(essential_data).encode()) / 1024

        return {
            "_toon": True,
            "_schema": schema,
            "_version": "1.0",
            "essential": essential_data,
            "metadata": {
                "original_size_kb": round(full_size, 2),
                "compressed_size_kb": round(essential_size, 2),
                "compression_ratio": round(full_size / (essential_size or 1), 1)
            },
            "_memory_key": memory_key,  # Reference to full data in workflow_memory
        }

    @staticmethod
    def is_toon(obj: Any) -> bool:
        """Check if object is TOON format."""
        return isinstance(obj, dict) and obj.get("_toon") is True

    @staticmethod
    def extract(toon_obj: Dict) -> Dict:
        """Extract essential data from TOON object."""
        if ToonObject.is_toon(toon_obj):
            return toon_obj.get("essential", {})
        return toon_obj

    @staticmethod
    def get_schema(toon_obj: Dict) -> str:
        """Get schema of TOON object."""
        if ToonObject.is_toon(toon_obj):
            return toon_obj.get("_schema", "unknown")
        return "unknown"

    @staticmethod
    def get_memory_reference(toon_obj: Dict) -> str:
        """Get reference to full data in workflow_memory."""
        if ToonObject.is_toon(toon_obj):
            return toon_obj.get("_memory_key", "")
        return ""


class WorkflowContextOptimizer:
    """Optimizes context passing between workflow steps.

    Keeps full outputs in workflow_memory, but sends TOON-formatted data to LLM.
    Uses smart filtering and compression to minimize tokens while maintaining info flow.
    """

    # Rough token estimates: ~4 chars = 1 token
    TOKEN_RATIO = 4

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for text."""
        if isinstance(text, str):
            return len(text) // WorkflowContextOptimizer.TOKEN_RATIO
        return 0

    @staticmethod
    def extract_essential_fields(data: Dict, essential_keys: List[str]) -> Dict:
        """Extract only essential fields from a dict for next step.

        Args:
            data: Full output from current step
            essential_keys: Keys that next step actually needs

        Returns:
            Optimized dict with only essential data
        """
        if not data:
            return {}

        optimized = {}
        for key in essential_keys:
            if key in data:
                optimized[key] = data[key]
        return optimized

    @staticmethod
    def compress_task_list(tasks: List[Dict]) -> Dict:
        """Compress task list for Step 1→2 transition using TOON format.

        Full: [{"id": 1, "name": "x", "description": "...", "dependencies": []}]
        TOON: {"_toon": true, "essential": {"count": N, "critical": [...]}}
        """
        if not tasks:
            essential = {"count": 0, "summary": "No tasks"}
            return ToonObject.create("task_list", essential, memory_key="step1_tasks")

        essential = {
            "count": len(tasks),
            "summary": f"{len(tasks)} tasks identified",
            "critical_tasks": [t.get("name", "Unknown") for t in tasks[:3]],
            "task_types": list(set(t.get("type", "unknown") for t in tasks))
        }

        return ToonObject.create("task_list", essential, tasks, memory_key="step1_tasks")

    @staticmethod
    def compress_context_status(context_data: Dict) -> Dict:
        """Compress context status for Level 1→2 transition using TOON format.

        Full: {"metadata": {...}, "loaded_files": [...], ...}
        TOON: {"_toon": true, "essential": {"status": "OK", "pct": 85, ...}}
        """
        essential = {
            "status": "OK" if context_data.get("context_loaded") else "PENDING",
            "usage_pct": context_data.get("context_percentage", 0),
            "threshold_exceeded": context_data.get("context_threshold_exceeded", False)
        }

        return ToonObject.create("context_status", essential, context_data, memory_key="level1_context")

    @staticmethod
    def build_optimized_context(state: "FlowState") -> Dict:
        """Build optimized context dict for LLM consumption.

        Rules:
        - Level -1: Keep minimal (status only)
        - Level 1→2: Summary only, not full data
        - Level 2→3: Critical info only
        - Level 3 steps: Only next-step-specific data

        Returns:
            Optimized dict with only LLM-necessary info
        """
        optimized = {}

        # Level -1 outcome (minimal)
        optimized["level_minus1"] = {
            "status": state.get("level_minus1_status", "UNKNOWN"),
            "auto_fixes_applied": len(state.get("auto_fix_applied", []))
        }

        # Level 1 outcome (summary only)
        if state.get("level1_status"):
            optimized["level1"] = {
                "status": state.get("level1_status"),
                "context": WorkflowContextOptimizer.compress_context_status(
                    {
                        "context_loaded": state.get("context_loaded"),
                        "context_percentage": state.get("context_percentage"),
                        "context_threshold_exceeded": state.get("context_threshold_exceeded")
                    }
                )
            }

        # Level 2 outcome (summary only)
        if state.get("level2_status"):
            optimized["level2"] = {
                "status": state.get("level2_status"),
                "standards_active": state.get("standards_count", 0),
                "is_java": state.get("is_java_project", False)
            }

        # Level 3 step context (only what's needed for next step)
        current_step = WorkflowContextOptimizer._find_current_level3_step(state)
        if current_step:
            optimized["current_step"] = {
                "name": current_step.get("name"),
                "step_number": current_step.get("order")
            }

        return optimized

    @staticmethod
    def _find_current_level3_step(state: "FlowState") -> Optional[Dict]:
        """Find the last completed Level 3 step."""
        pipeline = state.get("pipeline", [])
        level3_steps = [s for s in pipeline if s.get("level") == 3]
        return level3_steps[-1] if level3_steps else None

    @staticmethod
    def store_step_output(state: "FlowState", step_name: str, output: Dict) -> "FlowState":
        """Store full step output in workflow_memory."""
        if not state.get("workflow_memory"):
            state["workflow_memory"] = {}

        state["workflow_memory"][step_name] = output

        # Update memory size estimate
        import json
        try:
            size_kb = len(json.dumps(state["workflow_memory"]).encode()) / 1024
            state["workflow_memory_size_kb"] = size_kb
        except:
            pass

        return state

    @staticmethod
    def get_memory_item(state: "FlowState", step_name: str) -> Optional[Dict]:
        """Retrieve full output from workflow memory."""
        memory = state.get("workflow_memory", {})
        return memory.get(step_name)
