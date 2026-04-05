"""StepKeys - Constants for flow state dictionary keys.

Centralizes all step state key strings so typos become import errors
instead of silent bugs. String VALUES are preserved for backward
compatibility with flow-trace.json and existing state serialization.

Usage:
    state.get(StepKeys.TASK_TYPE, "task")
    state[StepKeys.REVIEW_PASSED] = True
"""


class StepKeys:
    """Constants for flow state dictionary keys."""

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
    LEVEL_MINUS1_FIXES_APPLIED = "level_minus1_fixes_applied"
    LEVEL_MINUS1_FIX_ERRORS = "level_minus1_fix_errors"
    LEVEL_MINUS1_READY_TO_RETRY = "level_minus1_ready_to_retry"
    LEVEL_MINUS1_MAX_ATTEMPTS_REACHED = "level_minus1_max_attempts_reached"
    LEVEL_MINUS1_FATAL_FAILURE = "level_minus1_fatal_failure"
    LEVEL_MINUS1_FAILED_CHECKS = "level_minus1_failed_checks"
    ENCODING_NONASCII_FILES = "encoding_nonascii_files"
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
    # v1.15.2: TOON_SAVED removed (TOON compression removed in v1.15.0)
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
    ORCHESTRATION_PROMPT = "orchestration_prompt"
    ORCHESTRATOR_RESULT = "orchestrator_result"

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
    # FIGMA INTEGRATION
    # ------------------------------------------------------------------
    FIGMA_ENABLED = "figma_enabled"
    FIGMA_FILE_KEY = "figma_file_key"
    FIGMA_DESIGN_TOKENS = "figma_design_tokens"
    FIGMA_PROMPT_SNIPPET = "figma_prompt_snippet"
    FIGMA_ERROR = "figma_error"

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
