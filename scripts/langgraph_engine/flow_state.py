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


class FlowState(TypedDict, total=False):
    """Complete state for 3-level architecture execution.

    All fields are optional (total=False) to allow incremental state building.
    Each level and node populates relevant fields.
    """

    # ===========================================================================
    # SESSION IDENTIFICATION
    # ===========================================================================
    session_id: str                    # Unique session identifier
    timestamp: str                     # ISO format timestamp when session started
    project_root: str                  # Project directory being analyzed
    is_java_project: bool              # True if project contains Java (pom.xml, build.gradle)
    is_fresh_project: bool             # True if no README/CLAUDE.md found (new project)

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

    # Session Management
    session_chain_loaded: bool         # Session chain initialized
    session_history: List[Dict]        # Previous session data
    session_state_data: Dict[str, Any]  # Current session state
    session_error: Optional[str]

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

    level2_status: str                 # OK / PARTIAL / FAILED

    # ===========================================================================
    # LEVEL 3: EXECUTION SYSTEM (12 STEPS)
    # ===========================================================================

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
    step4_model: str                   # Selected model: haiku/sonnet/opus
    step4_reasoning: str               # Why this model was chosen
    step4_error: Optional[str]

    # Step 5: Skill & Agent Selection
    step5_skill: str                   # Selected skill name (if any)
    step5_agent: str                   # Selected agent name (if any)
    step5_reasoning: str               # Why this skill/agent was chosen
    step5_error: Optional[str]
    step5_llm_query_needed: bool       # True if LLM needed to decide

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
    # PIPELINE & OUTPUT
    # ===========================================================================
    # For flow-trace.json (backward compatibility)
    pipeline: List[Dict]              # List of policy execution steps

    # Final execution status
    final_status: str                  # OK / PARTIAL / FAILED / BLOCKED

    # Errors and warnings
    errors: List[str]                  # Accumulated errors from all levels
    warnings: List[str]                # Accumulated warnings

    # Execution metadata
    execution_time_ms: int             # Total execution time in milliseconds
    level_durations: Dict[str, int]    # Duration per level in milliseconds
