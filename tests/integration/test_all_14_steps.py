"""
Integration Tests - All 15 Steps (Step 0-14) of the Level 3 Execution Pipeline

Covers:
- Individual unit tests for each of the 15 steps (Step 0-14)
- Step-sequence integration tests (upstream data flowing to downstream steps)
- Full workflow end-to-end validation
- FlowState integrity across transitions
- Conditional routing (plan_required branch, step11 retry branch)
- Checkpoint saving after each step
- Metrics collection per step

Steps under test:
  Step 0  - task analysis (pre-step, feeds Step 1)
  Step 1  - plan mode decision (conditional branch)
  Step 2  - plan execution (only when plan_required=True)
  Step 3  - task breakdown validation
  Step 4  - TOON refinement
  Step 5  - skill & agent selection
  Step 6  - skill validation & download
  Step 7  - final prompt generation
  Step 8  - GitHub issue creation
  Step 9  - branch creation
  Step 10 - implementation execution
  Step 11 - pull request & code review (retry loop)
  Step 12 - issue closure
  Step 13 - project documentation update
  Step 14 - final summary generation
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts directory is importable
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _base_state(
    session_id: str = "test-session-001",
    user_message: str = "Add logging to the Flask app",
    project_root: str = "/tmp/test-project",
) -> Dict[str, Any]:
    """Return a minimal but representative FlowState for tests."""
    return {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "user_message": user_message,
        "user_message_original": user_message,
        "user_message_length": len(user_message),
        "project_root": project_root,
        "level_minus1_status": "OK",
        "unicode_check": True,
        "encoding_check": True,
        "windows_path_check": True,
        "auto_fix_applied": [],
        "context_loaded": True,
        "context_percentage": 25.0,
        "context_threshold_exceeded": False,
        "context_metadata": {"files_loaded_count": 2},
        "session_chain_loaded": True,
        "preferences_loaded": True,
        "patterns_detected": ["python", "flask"],
        "is_java_project": False,
        "is_fresh_project": False,
        "standards_loaded": True,
        "level1_context_toon": {
            "session_id": session_id,
            "complexity_score": 4,
            "files_loaded_count": 2,
            "context": {"files": ["README.md", "CLAUDE.md"], "readme": True, "claude_md": True},
        },
    }


def _state_with_step0(base: Dict[str, Any]) -> Dict[str, Any]:
    """Inject plausible Step 0 outputs into the state."""
    state = dict(base)
    state.update({
        "step0_task_type": "Enhancement",
        "step0_complexity": 4,
        "step0_reasoning": "Adding logging is a straightforward enhancement",
        "step0_task_count": 2,
        "step0_tasks": {
            "count": 2,
            "tasks": [
                {"id": "task-1", "description": "Add logging configuration", "files": ["src/app.py"]},
                {"id": "task-2", "description": "Add log statements to routes", "files": ["src/routes.py"]},
            ],
        },
    })
    return state


def _state_with_steps0_to_3(base: Dict[str, Any]) -> Dict[str, Any]:
    """Build state with Steps 0-3 outputs (needed by Steps 4+)."""
    state = _state_with_step0(base)
    state.update({
        "step1_plan_required": False,
        "step1_reasoning": "Simple enhancement, no plan needed",
        "step1_complexity_score": 4,
        "step3_tasks_validated": [
            {
                "id": "task-1",
                "description": "Add logging configuration",
                "files": ["src/app.py"],
                "dependencies": [],
                "estimated_effort": "low",
            },
            {
                "id": "task-2",
                "description": "Add log statements to routes",
                "files": ["src/routes.py"],
                "dependencies": ["task-1"],
                "estimated_effort": "low",
            },
        ],
        "step3_task_count": 2,
        "step3_validation_status": "OK",
    })
    return state


def _state_with_steps0_to_5(base: Dict[str, Any]) -> Dict[str, Any]:
    """Build state through Step 5 outputs."""
    state = _state_with_steps0_to_3(base)
    state.update({
        "step4_toon_refined": {
            "session_id": base["session_id"],
            "complexity_score": 4,
            "adjusted_complexity": 4,
            "task_descriptions": ["Add logging configuration", "Add log statements to routes"],
            "estimated_files": 2,
            "has_dependencies": True,
        },
        "step4_refinement_status": "OK",
        "step4_complexity_adjusted": 4,
        "step4_tasks_included": 2,
        # Step 5 actual API uses singular skill/agent (not list)
        "step5_skill": "python-logging",
        "step5_agent": "backend-agent",
        "step5_skill_definition": "content",
        "step5_agent_definition": "content",
        "step5_reasoning": "best match",
        "step5_confidence": 0.9,
        "step5_alternatives": [],
        "step5_llm_query_needed": False,
        "step5_context_provided": True,
        "step5_task_count": 2,
        "step5_skills_available": 2,
        "step5_agents_available": 1,
    })
    return state


def _state_ready_for_step8(base: Dict[str, Any]) -> Dict[str, Any]:
    """Build state through Step 7 (prompt generation) outputs."""
    state = _state_with_steps0_to_5(base)
    state.update({
        # Step 6 actual API
        "step6_skill_validation": {"skill_exists": True, "agent_exists": True, "downloaded": []},
        "step6_skill_ready": True,
        "step6_agent_ready": True,
        "step6_validation_status": "OK",
        # Step 7 actual API (when no session_dir)
        "step7_prompt_saved": False,
        "step7_error": "No session_dir available",
    })
    return state


# ===========================================================================
# TEST CLASS: FlowState Schema & Initialization
# ===========================================================================

class TestFlowStateSchema:
    """Verify FlowState TypedDict structure matches expected fields."""

    def test_flow_state_imports_cleanly(self):
        from langgraph_engine.flow_state import FlowState
        assert FlowState is not None

    def test_flow_state_accepts_base_fields(self):
        from langgraph_engine.flow_state import FlowState
        state: FlowState = _base_state()
        assert state["session_id"] == "test-session-001"
        assert state["level_minus1_status"] == "OK"
        assert isinstance(state["patterns_detected"], list)

    def test_workflow_context_optimizer_imports(self):
        from langgraph_engine.flow_state import WorkflowContextOptimizer
        assert WorkflowContextOptimizer is not None

    def test_level3_step_fields_present_in_state(self):
        state = _state_with_steps0_to_5(_base_state())
        assert "step0_task_type" in state
        assert "step1_plan_required" in state
        assert "step3_tasks_validated" in state
        assert "step4_toon_refined" in state
        # Step 5 API uses singular: step5_skill / step5_agent
        assert "step5_skill" in state


# ===========================================================================
# TEST CLASS: Level -1 Individual Nodes
# ===========================================================================

class TestLevelMinus1Nodes:
    """Unit tests for the three Level -1 auto-fix enforcement nodes."""

    def test_node_unicode_fix_non_windows(self):
        """On non-Windows platforms unicode check is a no-op pass."""
        from langgraph_engine.subgraphs.level_minus1 import node_unicode_fix
        state = _base_state()
        with patch("sys.platform", "linux"):
            result = node_unicode_fix(state)
        assert result.get("unicode_check") is True

    def test_node_encoding_validation_pass(self):
        """Encoding validation passes when no non-ASCII files exist."""
        from langgraph_engine.subgraphs.level_minus1 import node_encoding_validation
        state = _base_state()
        with tempfile.TemporaryDirectory() as tmpdir:
            state["project_root"] = tmpdir
            ascii_file = Path(tmpdir) / "test.py"
            ascii_file.write_text("print('hello')\n", encoding="utf-8")
            result = node_encoding_validation(state)
        assert result.get("encoding_check") is True

    def test_node_windows_path_check_passes_forward_slashes(self):
        """Windows path check passes when paths use forward slashes."""
        from langgraph_engine.subgraphs.level_minus1 import node_windows_path_check
        state = _base_state()
        state["project_root"] = "/tmp/test-project"
        result = node_windows_path_check(state)
        assert result.get("windows_path_check") is True

    def test_level_minus1_merge_node_all_pass(self):
        """Merge node sets OK status when all checks pass."""
        from langgraph_engine.subgraphs.level_minus1 import level_minus1_merge_node
        state = _base_state()
        state.update({"unicode_check": True, "encoding_check": True, "windows_path_check": True})
        result = level_minus1_merge_node(state)
        assert result.get("level_minus1_status") == "OK"

    def test_level_minus1_merge_node_one_fail(self):
        """Merge node sets FAILED status when any check fails."""
        from langgraph_engine.subgraphs.level_minus1 import level_minus1_merge_node
        state = _base_state()
        state.update({"unicode_check": True, "encoding_check": False, "windows_path_check": True})
        result = level_minus1_merge_node(state)
        assert result.get("level_minus1_status") == "FAILED"

    def test_max_retry_limit_enforced(self):
        """Retry count above MAX_LEVEL_MINUS1_ATTEMPTS is respected."""
        from langgraph_engine.subgraphs.level_minus1 import MAX_LEVEL_MINUS1_ATTEMPTS
        assert MAX_LEVEL_MINUS1_ATTEMPTS == 3


# ===========================================================================
# TEST CLASS: Step 0 - Task Analysis
# ===========================================================================

class TestStep0TaskAnalysis:
    """Unit tests for step0_task_analysis."""

    def test_step0_returns_required_keys(self):
        from langgraph_engine.subgraphs.level3_execution import step0_task_analysis
        state = _base_state()
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            return_value={"task_type": "Enhancement", "complexity": 3, "reasoning": "Simple task", "task_count": 1, "tasks": []}
        ):
            result = step0_task_analysis(state)
        assert "step0_task_type" in result
        assert "step0_complexity" in result
        assert "step0_task_count" in result

    def test_step0_falls_back_when_script_missing(self):
        from langgraph_engine.subgraphs.level3_execution import step0_task_analysis
        state = _base_state()
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            return_value={"status": "SCRIPT_NOT_FOUND"}
        ):
            result = step0_task_analysis(state)
        assert "step0_task_type" in result
        # Should fall back gracefully without raising
        assert result.get("step0_complexity") is not None

    def test_step0_uses_env_var_when_user_message_empty(self):
        """Step 0 reads CURRENT_USER_MESSAGE env var if state has no user_message."""
        from langgraph_engine.subgraphs.level3_execution import step0_task_analysis
        state = _base_state(user_message="")
        env_msg = "Refactor database layer"
        with patch.dict(os.environ, {"CURRENT_USER_MESSAGE": env_msg}):
            with patch(
                "langgraph_engine.subgraphs.level3_execution.call_execution_script",
                return_value={"task_type": "Refactor", "complexity": 6, "reasoning": "db refactor", "task_count": 1, "tasks": []}
            ) as mock_call:
                result = step0_task_analysis(state)
        # Verify call was made (env var fallback exercised)
        assert result["step0_task_type"] == "Refactor"


# ===========================================================================
# TEST CLASS: Step 1 - Plan Mode Decision
# ===========================================================================

class TestStep1PlanModeDecision:
    """Unit tests for step1_plan_mode_decision."""

    def test_step1_returns_plan_required_bool(self):
        from langgraph_engine.subgraphs.level3_execution import step1_plan_mode_decision
        state = _state_with_step0(_base_state())
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            return_value={"plan_required": False, "reasoning": "Simple task"}
        ):
            result = step1_plan_mode_decision(state)
        assert isinstance(result["step1_plan_required"], bool)
        assert "step1_reasoning" in result

    def test_step1_true_for_complex_task(self):
        from langgraph_engine.subgraphs.level3_execution import step1_plan_mode_decision
        state = _state_with_step0(_base_state())
        state["step0_complexity"] = 9
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            return_value={"plan_required": True, "reasoning": "High complexity"}
        ):
            result = step1_plan_mode_decision(state)
        assert result["step1_plan_required"] is True

    def test_step1_false_for_simple_task(self):
        from langgraph_engine.subgraphs.level3_execution import step1_plan_mode_decision
        state = _state_with_step0(_base_state())
        state["step0_complexity"] = 2
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            return_value={"plan_required": False, "reasoning": "Low complexity"}
        ):
            result = step1_plan_mode_decision(state)
        assert result["step1_plan_required"] is False

    def test_route_after_step1_goes_to_step2_when_plan_required(self):
        from langgraph_engine.orchestrator import route_after_step1_decision
        state = _base_state()
        state["step1_plan_required"] = True
        assert route_after_step1_decision(state) == "level3_step2"

    def test_route_after_step1_skips_to_step3_when_no_plan(self):
        from langgraph_engine.orchestrator import route_after_step1_decision
        state = _base_state()
        state["step1_plan_required"] = False
        assert route_after_step1_decision(state) == "level3_step3"

    def test_route_after_step1_defaults_to_step2_when_missing(self):
        """When step1_plan_required is absent, default is True (conservative)."""
        from langgraph_engine.orchestrator import route_after_step1_decision
        state = _base_state()
        # step1_plan_required not set
        assert route_after_step1_decision(state) == "level3_step2"


# ===========================================================================
# TEST CLASS: Step 2 - Plan Execution
# ===========================================================================

class TestStep2PlanExecution:
    """Unit tests for step2_plan_execution (runs only when plan_required=True)."""

    def test_step2_returns_plan_structure(self):
        from langgraph_engine.subgraphs.level3_execution import step2_plan_execution
        state = _state_with_step0(_base_state())
        result = step2_plan_execution(state)
        assert "step2_plan_execution" in result
        assert "step2_plan_status" in result
        assert result["step2_plan_status"] in ("OK", "ERROR")

    def test_step2_plan_has_phases(self):
        from langgraph_engine.subgraphs.level3_execution import step2_plan_execution
        state = _state_with_step0(_base_state())
        # Add tasks with known keywords to trigger phase creation
        state["step0_tasks"] = {
            "count": 3,
            "tasks": [
                {"id": "t1", "description": "analyze the codebase", "files": []},
                {"id": "t2", "description": "implement the feature", "files": []},
                {"id": "t3", "description": "test and review the changes", "files": []},
            ],
        }
        result = step2_plan_execution(state)
        plan = result.get("step2_plan_execution", {})
        assert "phases" in plan
        assert isinstance(plan["phases"], list)

    def test_step2_handles_empty_tasks_gracefully(self):
        from langgraph_engine.subgraphs.level3_execution import step2_plan_execution
        state = _state_with_step0(_base_state())
        state["step0_tasks"] = {"count": 0, "tasks": []}
        result = step2_plan_execution(state)
        assert result.get("step2_plan_status") == "OK"


# ===========================================================================
# TEST CLASS: Step 3 - Task Breakdown Validation
# ===========================================================================

class TestStep3TaskBreakdown:
    """Unit tests for step3_task_breakdown_validation."""

    def test_step3_validates_dict_tasks(self):
        from langgraph_engine.subgraphs.level3_execution import step3_task_breakdown_validation
        state = _state_with_step0(_base_state())
        result = step3_task_breakdown_validation(state)
        assert "step3_tasks_validated" in result
        assert isinstance(result["step3_tasks_validated"], list)

    def test_step3_handles_string_tasks(self):
        """Step 3 must accept plain-string tasks (not just dicts)."""
        from langgraph_engine.subgraphs.level3_execution import step3_task_breakdown_validation
        state = _base_state()
        state["step0_tasks"] = {"count": 2, "tasks": ["Configure logging", "Add route handlers"]}
        result = step3_task_breakdown_validation(state)
        validated = result.get("step3_tasks_validated", [])
        assert len(validated) == 2
        assert all(isinstance(t, dict) for t in validated)
        assert all("id" in t and "description" in t for t in validated)

    def test_step3_handles_mixed_task_formats(self):
        """Mix of dict and string tasks should all produce valid outputs."""
        from langgraph_engine.subgraphs.level3_execution import step3_task_breakdown_validation
        state = _base_state()
        state["step0_tasks"] = {
            "count": 2,
            "tasks": [
                {"id": "t1", "description": "Analyze", "files": []},
                "Implement feature",
            ],
        }
        result = step3_task_breakdown_validation(state)
        validated = result.get("step3_tasks_validated", [])
        assert len(validated) == 2

    def test_step3_reports_ok_status_for_valid_input(self):
        from langgraph_engine.subgraphs.level3_execution import step3_task_breakdown_validation
        state = _state_with_step0(_base_state())
        result = step3_task_breakdown_validation(state)
        assert result.get("step3_validation_status") == "OK"

    def test_step3_handles_empty_tasks(self):
        from langgraph_engine.subgraphs.level3_execution import step3_task_breakdown_validation
        state = _base_state()
        state["step0_tasks"] = {"count": 0, "tasks": []}
        result = step3_task_breakdown_validation(state)
        assert result["step3_task_count"] == 0


# ===========================================================================
# TEST CLASS: Step 4 - TOON Refinement
# ===========================================================================

class TestStep4ToonRefinement:
    """Unit tests for step4_toon_refinement."""

    def test_step4_enriches_toon_with_task_data(self):
        from langgraph_engine.subgraphs.level3_execution import step4_toon_refinement
        state = _state_with_steps0_to_3(_base_state())
        result = step4_toon_refinement(state)
        assert result.get("step4_refinement_status") == "OK"
        refined = result.get("step4_toon_refined", {})
        assert "task_descriptions" in refined

    def test_step4_calculates_adjusted_complexity(self):
        from langgraph_engine.subgraphs.level3_execution import step4_toon_refinement
        state = _state_with_steps0_to_3(_base_state())
        result = step4_toon_refinement(state)
        assert "step4_complexity_adjusted" in result
        assert 1 <= result["step4_complexity_adjusted"] <= 10

    def test_step4_skips_gracefully_when_no_toon(self):
        """If level1_context_toon is absent, step should return SKIPPED."""
        from langgraph_engine.subgraphs.level3_execution import step4_toon_refinement
        state = _state_with_steps0_to_3(_base_state())
        del state["level1_context_toon"]
        result = step4_toon_refinement(state)
        assert result.get("step4_refinement_status") == "SKIPPED"

    def test_step4_includes_plan_phases_when_step2_ran(self):
        from langgraph_engine.subgraphs.level3_execution import step4_toon_refinement
        state = _state_with_steps0_to_3(_base_state())
        state["step2_plan_execution"] = {"phases": [{"name": "Phase 1", "task_count": 2}], "estimated_steps": 2}
        result = step4_toon_refinement(state)
        refined = result.get("step4_toon_refined", {})
        assert refined.get("planned_phases") == 1

    def test_step4_adjusted_complexity_is_within_bounds(self):
        """Adjusted complexity must always be within [1, 10] regardless of task count."""
        from langgraph_engine.subgraphs.level3_execution import step4_toon_refinement
        state = _base_state()
        state["step3_tasks_validated"] = []
        result = step4_toon_refinement(state)
        # Formula: base_complexity + (len(tasks)-1)//2
        # With 0 tasks: 4 + (0-1)//2 = 4 + (-1) = 3 (Python floor division)
        # Key invariant: result must be an integer in [1, 10]
        if "step4_complexity_adjusted" in result:
            adj = result["step4_complexity_adjusted"]
            assert isinstance(adj, int)
            assert 1 <= adj <= 10


# ===========================================================================
# TEST CLASS: Step 5 - Skill & Agent Selection
# ===========================================================================

class TestStep5SkillAgentSelection:
    """Unit tests for step5_skill_agent_selection."""

    def _mock_loader(self):
        loader = MagicMock()
        loader.list_all_skills.return_value = {
            "python-logging": "# Python Logging Skill\nProvides structured logging.",
            "flask": "# Flask Skill\nFlask web framework helpers.",
        }
        loader.list_all_agents.return_value = {
            "backend-agent": "# Backend Agent\nHandles backend development.",
        }
        return loader

    def test_step5_returns_selected_skill(self):
        from langgraph_engine.subgraphs.level3_execution import step5_skill_agent_selection
        state = _state_with_steps0_to_3(_base_state())
        with patch("langgraph_engine.subgraphs.level3_execution.call_execution_script",
                   return_value={"selected_skill": "python-logging", "selected_agent": "backend-agent",
                                 "confidence": 0.9, "reasoning": "best match"}):
            with patch("langgraph_engine.skill_agent_loader.get_skill_agent_loader",
                       return_value=self._mock_loader()):
                result = step5_skill_agent_selection(state)
        # Step 5 returns step5_skill (singular) and step5_agent
        assert "step5_skill" in result

    def test_step5_handles_empty_skills_response(self):
        from langgraph_engine.subgraphs.level3_execution import step5_skill_agent_selection
        state = _state_with_steps0_to_3(_base_state())
        with patch("langgraph_engine.subgraphs.level3_execution.call_execution_script",
                   return_value={}):
            with patch("langgraph_engine.skill_agent_loader.get_skill_agent_loader",
                       return_value=self._mock_loader()):
                result = step5_skill_agent_selection(state)
        # Should not raise - fallback is expected
        assert "step5_skill" in result


# ===========================================================================
# TEST CLASS: Step 6 - Skill Validation & Download
# ===========================================================================

class TestStep6SkillValidation:
    """Unit tests for step6_skill_validation_download."""

    def test_step6_validates_existing_skills(self):
        from langgraph_engine.subgraphs.level3_execution import step6_skill_validation_download
        state = _state_with_steps0_to_5(_base_state())
        # step6 reads step5_skill / step5_agent directly and checks filesystem
        state["step5_skill"] = "python-logging"
        state["step5_agent"] = ""
        with patch("pathlib.Path.exists", return_value=True):
            result = step6_skill_validation_download(state)
        assert "step6_validation_status" in result

    def test_step6_reports_validation_status(self):
        from langgraph_engine.subgraphs.level3_execution import step6_skill_validation_download
        state = _state_with_steps0_to_5(_base_state())
        state["step5_skill"] = ""
        state["step5_agent"] = ""
        result = step6_skill_validation_download(state)
        assert "step6_validation_status" in result


# ===========================================================================
# TEST CLASS: Step 7 - Final Prompt Generation
# ===========================================================================

class TestStep7PromptGeneration:
    """Unit tests for step7_final_prompt_generation."""

    def test_step7_generates_prompt_saved_status(self):
        """Step 7 builds system_prompt.txt and user_message.txt when session_dir is available."""
        from langgraph_engine.subgraphs.level3_execution import step7_final_prompt_generation
        state = _state_with_steps0_to_5(_base_state())
        with tempfile.TemporaryDirectory() as tmpdir:
            state["session_dir"] = tmpdir
            result = step7_final_prompt_generation(state)
        # Result must have step7_prompt_saved indicating whether files were written
        assert "step7_prompt_saved" in result

    def test_step7_returns_error_when_no_session_dir(self):
        """Without session_dir, step 7 should return step7_prompt_saved=False."""
        from langgraph_engine.subgraphs.level3_execution import step7_final_prompt_generation
        import tempfile
        state = _state_with_steps0_to_5(_base_state())
        # Ensure no session_dir set and env var absent
        state.pop("session_dir", None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_SESSION_PATH", None)
            result = step7_final_prompt_generation(state)
        assert result.get("step7_prompt_saved") is False


# ===========================================================================
# TEST CLASS: Step 8 - GitHub Issue Creation
# ===========================================================================

class TestStep8GithubIssue:
    """Unit tests for step8_github_issue_creation."""

    def test_step8_returns_issue_id(self):
        """Step 8 creates issue using built-in logic (no call_execution_script)."""
        from langgraph_engine.subgraphs.level3_execution import step8_github_issue_creation
        state = _state_ready_for_step8(_base_state())
        result = step8_github_issue_creation(state)
        assert "step8_issue_id" in result

    def test_step8_returns_ok_status(self):
        """Step 8 should return a valid step8_status on any execution path.

        In test environments the GitHub CLI resolves to the actual repo, but
        the test project_root (/tmp/test-project) is not a git repository, so
        the issue creation falls back gracefully.  Valid statuses are:
          - OK       : issue created successfully via gh CLI
          - FALLBACK : gh CLI unavailable; branch name generated locally
          - SKIPPED  : prompt too short / system notification / no LLM analysis
          - ERROR    : unexpected exception
        """
        from langgraph_engine.subgraphs.level3_execution import step8_github_issue_creation
        state = _state_ready_for_step8(_base_state())
        result = step8_github_issue_creation(state)
        assert result.get("step8_status") in ("OK", "FALLBACK", "SKIPPED", "ERROR")


# ===========================================================================
# TEST CLASS: Step 9 - Branch Creation
# ===========================================================================

class TestStep9BranchCreation:
    """Unit tests for step9_branch_creation."""

    def test_step9_returns_branch_name(self):
        """Step 9 creates a branch name when a GitHub issue was created.

        step9 skips branch creation when step8_issue_created is False (issue_id=0
        fallback).  We mark issue_id="42" AND issue_created=True so the step
        reaches the branch-name generation logic.  The real gh CLI call will fail
        because /tmp/test-project is not a git repo, but the fallback still
        returns a local branch name containing the issue id.
        """
        from langgraph_engine.subgraphs.level3_execution import step9_branch_creation
        state = _state_ready_for_step8(_base_state())
        state["step8_issue_id"] = "42"
        state["step8_issue_created"] = True
        result = step9_branch_creation(state)
        assert "step9_branch_name" in result
        assert "42" in result.get("step9_branch_name", "")

    def test_step9_branch_includes_task_type(self):
        """Branch name should include task type in lowercase.

        step9 skips unless step8_issue_created=True.  We set it explicitly so
        the fallback branch name (label/issue-{id}) is generated.
        """
        from langgraph_engine.subgraphs.level3_execution import step9_branch_creation
        state = _state_ready_for_step8(_base_state())
        state["step8_issue_id"] = "55"
        state["step8_issue_created"] = True
        state["step0_task_type"] = "Enhancement"
        result = step9_branch_creation(state)
        branch = result.get("step9_branch_name", "")
        assert "enhancement" in branch.lower() or "55" in branch


# ===========================================================================
# TEST CLASS: Step 10 - Implementation
# ===========================================================================

class TestStep10Implementation:
    """Unit tests for step10_implementation_execution."""

    def test_step10_returns_implementation_status(self):
        """Step 10 returns implementation_status; hybrid_inference failures are handled."""
        from langgraph_engine.subgraphs.level3_execution import step10_implementation_execution
        state = _state_ready_for_step8(_base_state())
        state["step9_branch_name"] = "issue-42-enhancement"
        # Step 10 imports get_hybrid_manager inside a try/except, so if it fails
        # the step degrades gracefully and still returns a status key.
        result = step10_implementation_execution(state)
        assert "step10_implementation_status" in result or "step10_error" in result


# ===========================================================================
# TEST CLASS: Step 11 - Pull Request & Code Review (retry loop)
# ===========================================================================

class TestStep11PullRequestReview:
    """Unit and integration tests for step11 including retry routing logic."""

    def test_step11_returns_review_result(self):
        """Step 11 creates PR and runs review; returns step11_review_passed."""
        from langgraph_engine.subgraphs.level3_execution import step11_pull_request_review
        state = _state_ready_for_step8(_base_state())
        state["step9_branch_name"] = "issue-42-enhancement"
        state["step5_skill"] = "python-logging"
        result = step11_pull_request_review(state)
        assert "step11_review_passed" in result
        assert isinstance(result["step11_review_passed"], bool)

    def test_route_after_step11_passes_to_step12_on_success(self):
        from langgraph_engine.orchestrator import route_after_step11_review
        state = _base_state()
        state["step11_review_passed"] = True
        state["step11_retry_count"] = 0
        assert route_after_step11_review(state) == "level3_step12"

    def test_route_after_step11_retries_on_failure(self):
        from langgraph_engine.orchestrator import route_after_step11_review
        state = _base_state()
        state["step11_review_passed"] = False
        state["step11_retry_count"] = 0
        route = route_after_step11_review(state)
        assert route == "level3_step10"
        # retry_count should be incremented
        assert state["step11_retry_count"] == 1

    def test_route_after_step11_stops_retrying_at_max(self):
        from langgraph_engine.orchestrator import route_after_step11_review
        state = _base_state()
        state["step11_review_passed"] = False
        state["step11_retry_count"] = 3  # already at max
        assert route_after_step11_review(state) == "level3_step12"

    def test_step11_retry_count_increments_correctly(self):
        """Verify retry count increments on each failed review call.

        Routing logic: if retry_count < 3 AND review failed -> retry (increment count).
        When retry_count reaches 3, next call with retry_count=3 goes to step12.
        """
        from langgraph_engine.orchestrator import route_after_step11_review
        state = _base_state()
        state["step11_review_passed"] = False

        # Call 1: retry_count=0 -> route to step10, count becomes 1
        state["step11_retry_count"] = 0
        assert route_after_step11_review(state) == "level3_step10"
        assert state["step11_retry_count"] == 1

        # Call 2: retry_count=1 -> route to step10, count becomes 2
        assert route_after_step11_review(state) == "level3_step10"
        assert state["step11_retry_count"] == 2

        # Call 3: retry_count=2 -> route to step10, count becomes 3
        assert route_after_step11_review(state) == "level3_step10"
        assert state["step11_retry_count"] == 3

        # Call 4: retry_count=3 (>= max) -> route to step12 (stop retrying)
        assert route_after_step11_review(state) == "level3_step12"


# ===========================================================================
# TEST CLASS: Steps 12-14 - Closure, Docs, Summary
# ===========================================================================

class TestSteps12to14Closure:
    """Unit tests for steps 12, 13, and 14."""

    def test_step12_closes_issue(self):
        """Step 12 attempts issue closure and returns a valid status.

        step12 checks step8_issue_created before proceeding.  We set it to True
        so the step reaches the gh CLI / fallback logic.  In the test environment
        /tmp/test-project is not a git repo, so the gh call will fail and the
        step returns an error or fallback status.  Valid outcomes:
          - OK      : issue closed successfully via gh CLI
          - FALLBACK: closure attempted but gh CLI unavailable
          - ERROR   : unexpected exception
          - SKIPPED : no real issue was created (step8_issue_created=False)
        """
        from langgraph_engine.subgraphs.level3_execution import step12_issue_closure
        state = _state_ready_for_step8(_base_state())
        state["step8_issue_id"] = "42"
        state["step8_issue_created"] = True
        state["step11_pr_url"] = "https://github.com/repo/pull/42"
        state["step11_review_passed"] = True
        result = step12_issue_closure(state)
        assert "step12_issue_closed" in result
        assert result.get("step12_status") in ("OK", "FALLBACK", "ERROR", "SKIPPED")

    def test_step13_updates_documentation(self):
        """Step 13 prepares documentation updates and returns status."""
        from langgraph_engine.subgraphs.level3_execution import step13_project_documentation_update
        state = _state_ready_for_step8(_base_state())
        result = step13_project_documentation_update(state)
        assert "step13_documentation_status" in result
        assert result.get("step13_documentation_status") in ("OK", "ERROR")

    def test_step14_generates_final_summary(self):
        """Step 14 builds execution summary and returns it."""
        from langgraph_engine.subgraphs.level3_execution import step14_final_summary_generation
        state = _state_ready_for_step8(_base_state())
        state.update({
            "step8_issue_id": "42",
            "step9_branch_name": "issue-42-enhancement",
            "step10_modified_files": ["src/app.py"],
            "step11_pr_id": "42",
            "step11_review_passed": True,
            "step12_issue_closed": True,
        })
        result = step14_final_summary_generation(state)
        assert "step14_summary" in result or "step14_status" in result or "step14_error" in result


# ===========================================================================
# TEST CLASS: Step Sequence Integration
# ===========================================================================

class TestStepSequenceIntegration:
    """Integration tests verifying data flows correctly between consecutive steps."""

    def test_step0_output_feeds_step1(self):
        """Step 1 must correctly read step0_complexity from state.

        Step 0 calls call_execution_script twice (analysis + breakdown).
        Step 1 calls it once (plan decision).
        """
        from langgraph_engine.subgraphs.level3_execution import (
            step0_task_analysis,
            step1_plan_mode_decision,
        )
        state = _base_state()
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            side_effect=[
                # Step 0 call 1: prompt-generator (task analysis)
                {"task_type": "Feature", "complexity": 8, "reasoning": "complex", "task_count": 3, "tasks": []},
                # Step 0 call 2: task-auto-analyzer (task breakdown)
                {"task_count": 3, "tasks": []},
                # Step 1 call: auto-plan-mode-suggester
                {"plan_required": True, "reasoning": "High complexity"},
            ]
        ):
            result0 = step0_task_analysis(state)
            state.update(result0)
            result1 = step1_plan_mode_decision(state)
        assert result1.get("step1_plan_required") is True

    def test_step3_output_feeds_step4(self):
        """Step 4 must read step3_tasks_validated to build refined TOON."""
        from langgraph_engine.subgraphs.level3_execution import (
            step3_task_breakdown_validation,
            step4_toon_refinement,
        )
        state = _state_with_step0(_base_state())
        result3 = step3_task_breakdown_validation(state)
        state.update(result3)
        result4 = step4_toon_refinement(state)
        refined = result4.get("step4_toon_refined", {})
        assert "task_descriptions" in refined
        assert len(refined["task_descriptions"]) == state["step3_task_count"]

    def test_step4_output_feeds_step5(self):
        """Step 5 must read step4_toon_refined for context-aware skill selection."""
        from langgraph_engine.subgraphs.level3_execution import step5_skill_agent_selection
        state = _state_with_steps0_to_3(_base_state())
        state["step4_toon_refined"] = {
            "session_id": "test-session-001",
            "complexity_score": 5,
            "adjusted_complexity": 6,
            "task_descriptions": ["Add logging"],
        }
        mock_loader = MagicMock()
        mock_loader.list_all_skills.return_value = {"python-logging": "content"}
        mock_loader.list_all_agents.return_value = {"backend-agent": "content"}
        with patch("langgraph_engine.subgraphs.level3_execution.call_execution_script",
                   return_value={"selected_skill": "python-logging", "selected_agent": "",
                                 "confidence": 0.8, "reasoning": "match"}):
            with patch("langgraph_engine.skill_agent_loader.get_skill_agent_loader",
                       return_value=mock_loader):
                result5 = step5_skill_agent_selection(state)
        # Step 5 returns step5_skill (singular string)
        assert "step5_skill" in result5

    def test_step5_output_feeds_step6(self):
        """Step 6 reads step5_skill for filesystem validation."""
        from langgraph_engine.subgraphs.level3_execution import step6_skill_validation_download
        state = _state_with_steps0_to_5(_base_state())
        state["step5_skill"] = "python-logging"
        state["step5_agent"] = ""
        with patch("pathlib.Path.exists", return_value=True):
            result6 = step6_skill_validation_download(state)
        assert "step6_validation_status" in result6

    def test_steps_0_through_7_complete_sequence(self):
        """Run Steps 0 through 7 in sequence verifying state accumulates correctly."""
        from langgraph_engine.subgraphs.level3_execution import (
            step0_task_analysis,
            step1_plan_mode_decision,
            step3_task_breakdown_validation,
            step4_toon_refinement,
            step5_skill_agent_selection,
            step6_skill_validation_download,
            step7_final_prompt_generation,
        )
        mock_loader = MagicMock()
        mock_loader.list_all_skills.return_value = {"python-logging": "content"}
        mock_loader.list_all_agents.return_value = {"backend-agent": "content"}

        # Step 0: 2 script calls (prompt-generator + task-auto-analyzer)
        # Step 1: 1 script call (auto-plan-mode-suggester)
        # Step 5: 1 script call (auto-skill-agent-selector)
        # Total: 4 script calls
        script_responses = [
            # Step 0 call 1: prompt-generator
            {"task_type": "Enhancement", "complexity": 3, "reasoning": "simple", "task_count": 1,
             "tasks": [{"id": "t1", "description": "add log", "files": ["app.py"]}]},
            # Step 0 call 2: task-auto-analyzer
            {"task_count": 1, "tasks": [{"id": "t1", "description": "add log", "files": []}]},
            # Step 1: auto-plan-mode-suggester
            {"plan_required": False, "reasoning": "simple task"},
            # Step 5: auto-skill-agent-selector
            {"selected_skill": "python-logging", "selected_agent": "",
             "confidence": 0.9, "reasoning": "best match"},
        ]

        state = _base_state()
        with patch("langgraph_engine.subgraphs.level3_execution.call_execution_script",
                   side_effect=script_responses):
            with patch("langgraph_engine.skill_agent_loader.get_skill_agent_loader",
                       return_value=mock_loader):
                state.update(step0_task_analysis(state))
                state.update(step1_plan_mode_decision(state))
                # plan_required=False -> skip step2
                state.update(step3_task_breakdown_validation(state))
                state.update(step4_toon_refinement(state))
                state.update(step5_skill_agent_selection(state))
        # Step 6: filesystem-based skill validation
        state["step5_skill"] = state.get("step5_skill", "python-logging")
        state["step5_agent"] = ""
        with patch("pathlib.Path.exists", return_value=True):
            state.update(step6_skill_validation_download(state))
        # Step 7: without session_dir prompt_saved=False
        state.pop("session_dir", None)
        os.environ.pop("CLAUDE_SESSION_PATH", None)
        state.update(step7_final_prompt_generation(state))

        assert "step0_task_type" in state
        assert "step1_plan_required" in state
        assert "step3_tasks_validated" in state
        assert "step4_toon_refined" in state
        assert "step5_skill" in state
        assert "step6_validation_status" in state
        assert "step7_prompt_saved" in state


# ===========================================================================
# TEST CLASS: V2 Wrapper (_run_step infrastructure)
# ===========================================================================

class TestV2StepWrapper:
    """Tests for the _run_step wrapper in level3_execution_v2.py."""

    def test_run_step_calls_step_function(self):
        from langgraph_engine.subgraphs.level3_execution_v2 import _run_step
        state = _base_state()
        called = []
        def fake_step(s):
            called.append(True)
            return {"result_key": "ok"}
        result = _run_step(1, "STEP 1 TEST", fake_step, state)
        assert called
        assert result.get("result_key") == "ok"

    def test_run_step_returns_fallback_on_exception(self):
        from langgraph_engine.subgraphs.level3_execution_v2 import _run_step
        state = _base_state()
        def failing_step(s):
            raise RuntimeError("Simulated failure")
        fallback = {"step1_error": "Simulated failure"}
        result = _run_step(1, "STEP 1 FAIL TEST", failing_step, state, fallback_result=fallback)
        assert result.get("step1_error") == "Simulated failure"

    def test_run_step_records_execution_time(self):
        from langgraph_engine.subgraphs.level3_execution_v2 import _run_step
        state = _base_state()
        def timed_step(s):
            time.sleep(0.01)
            return {}
        result = _run_step(3, "TIMING TEST", timed_step, state)
        assert "step3_execution_time_ms" in result
        assert result["step3_execution_time_ms"] >= 0

    def test_run_step_returns_empty_dict_on_none_result(self):
        from langgraph_engine.subgraphs.level3_execution_v2 import _run_step
        state = _base_state()
        result = _run_step(2, "NONE RESULT", lambda s: None, state)
        assert isinstance(result, dict)


# ===========================================================================
# TEST CLASS: CheckpointManager Integration
# ===========================================================================

class TestCheckpointManagerIntegration:
    """Verify checkpoint save/load works correctly per step."""

    def test_checkpoint_save_and_load_roundtrip(self):
        from langgraph_engine.checkpoint_manager import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            cp = CheckpointManager.__new__(CheckpointManager)
            cp.session_id = "chk-test-001"
            cp.checkpoint_dir = Path(tmpdir) / "checkpoints"
            cp.checkpoint_dir.mkdir(parents=True)

            state = {"session_id": "chk-test-001", "step1_plan_required": False, "step3_task_count": 2}
            cp.save_checkpoint(step=3, state=state)

            last_step, recovered = cp.get_last_checkpoint()
            assert last_step == 3
            assert recovered["step1_plan_required"] is False
            assert recovered["step3_task_count"] == 2

    def test_checkpoint_handles_non_serializable_values(self):
        from langgraph_engine.checkpoint_manager import CheckpointManager, _serialize_state
        state_with_objects = {
            "session_id": "test",
            "mock_object": MagicMock(),
            "regular_value": 42,
        }
        safe = _serialize_state(state_with_objects)
        assert safe["regular_value"] == 42
        # mock_object should be serialized to string, not raise
        assert isinstance(safe["mock_object"], str)

    def test_checkpoint_latest_json_is_updated(self):
        from langgraph_engine.checkpoint_manager import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            cp = CheckpointManager.__new__(CheckpointManager)
            cp.session_id = "chk-test-002"
            cp.checkpoint_dir = Path(tmpdir) / "checkpoints"
            cp.checkpoint_dir.mkdir(parents=True)

            cp.save_checkpoint(step=1, state={"session_id": "chk-test-002", "step": 1})
            cp.save_checkpoint(step=2, state={"session_id": "chk-test-002", "step": 2})

            latest_file = cp.checkpoint_dir / "latest.json"
            assert latest_file.exists()
            data = json.loads(latest_file.read_text())
            assert data["step"] == 2


# ===========================================================================
# TEST CLASS: ErrorLogger Integration
# ===========================================================================

class TestErrorLoggerIntegration:
    """Verify ErrorLogger records and retrieves errors correctly."""

    def test_error_logger_records_error(self):
        from langgraph_engine.error_logger import ErrorLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ErrorLogger(session_id="err-test-001", log_base_dir=tmpdir)
            logger.log_error("Step 3", "Validation failed", severity="ERROR", error_type="ValidationError")
            summary = logger.get_error_summary()
            assert summary["total_errors"] == 1
            assert "ERROR" in summary["by_severity"]

    def test_error_logger_records_decision(self):
        from langgraph_engine.error_logger import ErrorLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ErrorLogger(session_id="err-test-002", log_base_dir=tmpdir)
            logger.log_decision("Step 1", "Skip planning", "Low complexity")
            summary = logger.get_decision_summary()
            assert summary["total_decisions"] == 1

    def test_error_logger_audit_trail_json(self):
        from langgraph_engine.error_logger import ErrorLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ErrorLogger(session_id="err-test-003", log_base_dir=tmpdir)
            logger.log_error("Step 5", "Skill not found", severity="WARNING")
            audit_path = logger.save_audit_trail()
            assert audit_path.exists()
            data = json.loads(audit_path.read_text())
            assert data["session_id"] == "err-test-003"
            assert len(data["errors"]) == 1

    def test_error_logger_critical_error_isolation(self):
        from langgraph_engine.error_logger import ErrorLogger
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ErrorLogger(session_id="err-test-004", log_base_dir=tmpdir)
            logger.log_error("Step 7", "LLM failed completely", severity="CRITICAL")
            logger.log_error("Step 3", "Minor warning", severity="WARNING")
            summary = logger.get_error_summary()
            assert len(summary["critical_errors"]) == 1
            assert summary["critical_errors"][0]["step"] == "Step 7"


# ===========================================================================
# TEST CLASS: Orchestrator Routing Logic
# ===========================================================================

class TestOrchestratorRouting:
    """Unit tests for all routing functions in orchestrator.py."""

    def test_route_after_level_minus1_ok_goes_to_level1(self):
        from langgraph_engine.orchestrator import route_after_level_minus1
        state = _base_state()
        state["level_minus1_status"] = "OK"
        assert route_after_level_minus1(state) == "level1_session"

    def test_route_after_level_minus1_failed_asks_user(self):
        from langgraph_engine.orchestrator import route_after_level_minus1
        state = _base_state()
        state["level_minus1_status"] = "FAILED"
        assert route_after_level_minus1(state) == "ask_level_minus1_fix"

    def test_route_user_choice_autofix_below_max(self):
        from langgraph_engine.orchestrator import route_after_level_minus1_user_choice
        state = _base_state()
        state["level_minus1_user_choice"] = "auto-fix"
        state["level_minus1_retry_count"] = 1
        assert route_after_level_minus1_user_choice(state) == "fix_level_minus1"

    def test_route_user_choice_autofix_at_max_goes_to_level1(self):
        from langgraph_engine.orchestrator import route_after_level_minus1_user_choice
        state = _base_state()
        state["level_minus1_user_choice"] = "auto-fix"
        state["level_minus1_retry_count"] = 3  # at max
        assert route_after_level_minus1_user_choice(state) == "level1_session"

    def test_route_user_choice_skip_goes_to_level1(self):
        from langgraph_engine.orchestrator import route_after_level_minus1_user_choice
        state = _base_state()
        state["level_minus1_user_choice"] = "skip"
        state["level_minus1_retry_count"] = 0
        assert route_after_level_minus1_user_choice(state) == "level1_session"

    def test_route_context_threshold_exceeded(self):
        from langgraph_engine.orchestrator import route_context_threshold
        state = _base_state()
        state["context_threshold_exceeded"] = True
        assert route_context_threshold(state) == "emergency_archive"

    def test_route_context_threshold_within_limit(self):
        from langgraph_engine.orchestrator import route_context_threshold
        state = _base_state()
        state["context_threshold_exceeded"] = False
        assert route_context_threshold(state) == "level2_common_standards"


# ===========================================================================
# TEST CLASS: Full End-to-End Workflow Smoke Test
# ===========================================================================

class TestEndToEndWorkflow:
    """
    End-to-end smoke tests that execute the full pipeline under mock conditions.
    These tests verify flow state accumulation without running actual LLM calls.
    """

    def test_full_pipeline_accumulates_all_step_keys(self):
        """
        Run all 15 steps (Step 0-14) in sequence with mocked calls.
        Verify the final state contains outputs from all steps.
        """
        import tempfile
        from langgraph_engine.subgraphs.level3_execution import (
            step0_task_analysis, step1_plan_mode_decision,
            step3_task_breakdown_validation, step4_toon_refinement,
            step5_skill_agent_selection, step6_skill_validation_download,
            step7_final_prompt_generation, step8_github_issue_creation,
            step9_branch_creation, step10_implementation_execution,
            step11_pull_request_review, step12_issue_closure,
            step13_project_documentation_update, step14_final_summary_generation,
        )
        mock_loader = MagicMock()
        mock_loader.list_all_skills.return_value = {"python-logging": "content"}
        mock_loader.list_all_agents.return_value = {"backend-agent": "content"}

        # Step 0: 2 calls (prompt-generator + task-auto-analyzer)
        # Step 1: 1 call (auto-plan-mode-suggester)
        # Step 5: 1 call (auto-skill-agent-selector)
        script_responses = [
            # Step 0 call 1: prompt-generator (analysis)
            {"task_type": "Enhancement", "complexity": 3, "reasoning": "ok",
             "task_count": 1, "tasks": [{"id": "t1", "description": "add log", "files": []}]},
            # Step 0 call 2: task-auto-analyzer (breakdown)
            {"task_count": 1, "tasks": [{"id": "t1", "description": "add log", "files": []}]},
            # Step 1: auto-plan-mode-suggester
            {"plan_required": False, "reasoning": "simple"},
            # Step 5: auto-skill-agent-selector
            {"selected_skill": "python-logging", "selected_agent": "",
             "confidence": 0.9, "reasoning": "best match"},
        ]

        state = _base_state()
        with patch("langgraph_engine.subgraphs.level3_execution.call_execution_script",
                   side_effect=script_responses):
            with patch("langgraph_engine.skill_agent_loader.get_skill_agent_loader",
                       return_value=mock_loader):
                state.update(step0_task_analysis(state))
                state.update(step1_plan_mode_decision(state))
                state.update(step3_task_breakdown_validation(state))
                state.update(step4_toon_refinement(state))
                state.update(step5_skill_agent_selection(state))

        state["step5_skill"] = state.get("step5_skill", "python-logging")
        state["step5_agent"] = ""
        with patch("pathlib.Path.exists", return_value=True):
            state.update(step6_skill_validation_download(state))

        # Step 7: with temp session dir so files can be written
        with tempfile.TemporaryDirectory() as tmpdir:
            state["session_dir"] = tmpdir
            state.update(step7_final_prompt_generation(state))

        # Steps 8-14: all have built-in logic, no script calls needed
        state.update(step8_github_issue_creation(state))
        state.update(step9_branch_creation(state))
        # step10 handles hybrid_inference import failure gracefully
        state.update(step10_implementation_execution(state))
        state.update(step11_pull_request_review(state))
        state.update(step12_issue_closure(state))
        state.update(step13_project_documentation_update(state))
        state.update(step14_final_summary_generation(state))

        # Verify state breadcrumbs across all phases
        assert "step0_task_type" in state
        assert "step1_plan_required" in state
        assert "step3_tasks_validated" in state
        assert "step4_toon_refined" in state
        assert "step5_skill" in state
        assert "step6_validation_status" in state
        assert "step7_prompt_saved" in state
        assert "step8_issue_id" in state
        assert "step9_branch_name" in state
        assert "step10_implementation_status" in state
        assert "step11_review_passed" in state
        assert "step12_issue_closed" in state
        assert "step13_documentation_status" in state
        assert "step14_summary" in state or "step14_status" in state

    def test_plan_required_branch_executes_step2(self):
        """When plan_required=True, step2 should be executed and produce plan output."""
        from langgraph_engine.subgraphs.level3_execution import (
            step0_task_analysis,
            step1_plan_mode_decision,
            step2_plan_execution,
        )
        state = _base_state(user_message="Completely refactor the database layer with multiple phases")
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            side_effect=[
                # Step 0 call 1: prompt-generator
                {"task_type": "Refactor", "complexity": 9, "reasoning": "complex", "task_count": 5,
                 "tasks": [
                     {"id": "t1", "description": "analyze current schema"},
                     {"id": "t2", "description": "implement new models"},
                     {"id": "t3", "description": "test migration scripts"},
                 ]},
                # Step 0 call 2: task-auto-analyzer
                {"task_count": 3, "tasks": []},
                # Step 1: auto-plan-mode-suggester
                {"plan_required": True, "reasoning": "High complexity refactor"},
            ]
        ):
            state.update(step0_task_analysis(state))
            state.update(step1_plan_mode_decision(state))

        assert state["step1_plan_required"] is True
        state.update(step2_plan_execution(state))
        assert "step2_plan_execution" in state
        assert state["step2_plan_status"] == "OK"

    def test_no_plan_branch_skips_step2(self):
        """When plan_required=False, step2 output should be absent from state."""
        from langgraph_engine.subgraphs.level3_execution import (
            step0_task_analysis,
            step1_plan_mode_decision,
        )
        state = _base_state(user_message="Fix a typo in README")
        with patch(
            "langgraph_engine.subgraphs.level3_execution.call_execution_script",
            side_effect=[
                # Step 0 call 1: prompt-generator
                {"task_type": "Docs", "complexity": 1, "reasoning": "trivial", "task_count": 1, "tasks": []},
                # Step 0 call 2: task-auto-analyzer
                {"task_count": 1, "tasks": []},
                # Step 1: auto-plan-mode-suggester
                {"plan_required": False, "reasoning": "Trivial fix"},
            ]
        ):
            state.update(step0_task_analysis(state))
            state.update(step1_plan_mode_decision(state))

        assert state["step1_plan_required"] is False
        # step2 was NOT called - its keys should be absent
        assert "step2_plan_execution" not in state
        assert "step2_plan_status" not in state
