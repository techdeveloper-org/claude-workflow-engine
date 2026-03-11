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
    project_root: Annotated[str, _keep_first_value]  # Immutable - project being analyzed
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
    pipeline: List[Dict]              # List of policy execution steps

    # Final execution status
    final_status: str                  # OK / PARTIAL / FAILED / BLOCKED

    # Errors and warnings
    errors: List[str]                  # Accumulated errors from all levels
    warnings: List[str]                # Accumulated warnings

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

    # Step 8: GitHub Issue
    step8_issue_number: Optional[int]
    step8_issue_url: Optional[str]
    step8_label: Optional[str]
    step8_execution_time_ms: Optional[float]
    step8_error: Optional[str]

    # Step 9: Branch Creation
    step9_branch_name: Optional[str]
    step9_execution_time_ms: Optional[float]
    step9_error: Optional[str]

    # Step 10: Implementation Placeholder
    step10_status: Optional[str]
    step10_message: Optional[str]
    step10_execution_time_ms: Optional[float]
    step10_error: Optional[str]

    # Step 11: PR & Review
    step11_pr_number: Optional[int]
    step11_pr_url: Optional[str]
    step11_merged: Optional[bool]
    step11_execution_time_ms: Optional[float]
    step11_error: Optional[str]

    # Step 12: Issue Closure
    step12_closed: Optional[bool]
    step12_execution_time_ms: Optional[float]
    step12_error: Optional[str]

    # Step 13: Documentation Update
    step13_updated_files: Optional[List[str]]
    step13_execution_time_ms: Optional[float]
    step13_error: Optional[str]

    # Step 14: Final Summary
    step14_summary: Optional[str]
    step14_voice_sent: Optional[bool]
    step14_execution_time_ms: Optional[float]
    step14_error: Optional[str]

    # Level 3 Overall
    level3_status: Optional[str]
    level3_total_execution_time_ms: Optional[float]


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
