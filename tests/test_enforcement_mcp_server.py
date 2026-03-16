"""Tests for Policy Enforcement MCP Server (src/mcp/enforcement_mcp_server.py)."""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

import sys
import importlib.util

_MCP_DIR = Path(__file__).parent.parent / "src" / "mcp"

def _load_module(name, file_path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_enf_mod = _load_module("enforcement_mcp_server", _MCP_DIR / "enforcement_mcp_server.py")

check_enforcement_status = _enf_mod.check_enforcement_status
enforce_policy_step = _enf_mod.enforce_policy_step
log_tool_usage = _enf_mod.log_tool_usage
verify_compliance = _enf_mod.verify_compliance
list_policies = _enf_mod.list_policies


def _parse(result: str) -> dict:
    """Parse JSON result from MCP tool."""
    return json.loads(result)


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create temporary state directory and patch paths."""
    state_file = tmp_path / ".blocking-enforcer-state.json"
    log_dir = tmp_path / ".tool-logs"
    log_dir.mkdir()

    with patch.object(_enf_mod, "ENFORCER_STATE_FILE", state_file), \
         patch.object(_enf_mod, "MEMORY_PATH", tmp_path):
        yield tmp_path, state_file


class TestCheckEnforcementStatus:
    """Tests for check_enforcement_status tool."""

    def test_status_no_state_file(self, temp_state_dir):
        """Test status when no state file exists."""
        result = _parse(check_enforcement_status())
        assert result["success"] is True
        assert result["state"] == {}
        assert "timestamp" in result

    def test_status_with_state(self, temp_state_dir):
        """Test status with existing state."""
        _, state_file = temp_state_dir
        state = {"session_started": True, "context_checked": True}
        state_file.write_text(json.dumps(state), encoding="utf-8")

        result = _parse(check_enforcement_status())
        assert result["success"] is True
        assert result["state"]["session_started"] is True


class TestEnforcePolicyStep:
    """Tests for enforce_policy_step tool."""

    def test_enforce_valid_step(self, temp_state_dir):
        """Test enforcing a valid step."""
        result = _parse(enforce_policy_step(0, "Prompt Generation"))
        assert result["success"] is True
        assert result["step"] == 0
        assert result["name"] == "Prompt Generation"
        assert "ENFORCED" in result.get("message", "") or "enforced" in result.get("message", "")

    def test_enforce_saves_state(self, temp_state_dir):
        """Test that enforcing updates state file."""
        _, state_file = temp_state_dir
        enforce_policy_step(5, "Skills Check")

        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert "step_5" in state
        assert state["step_5"]["name"] == "Skills Check"

    def test_enforce_unmapped_step(self, temp_state_dir):
        """Test enforcing a step without policy mapping."""
        result = _parse(enforce_policy_step(99, "Unknown Step"))
        assert result["success"] is True  # Still succeeds, just no policy file
        assert result["policy_file"] is None


class TestLogToolUsage:
    """Tests for log_tool_usage tool."""

    def test_log_basic(self, temp_state_dir):
        """Test basic tool logging."""
        result = _parse(log_tool_usage("Read", "Read file test.py"))
        assert result["success"] is True
        assert result["tool"] == "Read"
        assert result["logged"] is True

    def test_log_with_params(self, temp_state_dir):
        """Test logging with parameters."""
        params = json.dumps({"file": "test.py", "offset": 0})
        result = _parse(log_tool_usage("Edit", "Edit file", params, "SUCCESS"))
        assert result["success"] is True
        assert result["tool"] == "Edit"

    def test_log_creates_file(self, temp_state_dir):
        """Test that logging creates a JSONL file."""
        tmp_path, _ = temp_state_dir
        log_tool_usage("Bash", "Run tests")

        log_dir = tmp_path / ".tool-logs"
        log_files = list(log_dir.glob("tools-*.jsonl"))
        assert len(log_files) >= 1


class TestVerifyCompliance:
    """Tests for verify_compliance tool."""

    def test_compliance_empty_state(self, temp_state_dir):
        """Test compliance with no steps completed."""
        result = _parse(verify_compliance())
        assert result["compliant"] is False
        assert result["completed_steps"] == 0
        assert result["total_steps"] == 8
        assert len(result["missing_steps"]) == 8

    def test_compliance_partial(self, temp_state_dir):
        """Test compliance with some steps completed."""
        _, state_file = temp_state_dir
        state = {
            "session_started": True,
            "context_checked": True,
            "standards_loaded": True
        }
        state_file.write_text(json.dumps(state), encoding="utf-8")

        result = _parse(verify_compliance())
        assert result["compliant"] is False
        assert result["completed_steps"] == 3
        assert result["total_steps"] == 8

    def test_compliance_full(self, temp_state_dir):
        """Test full compliance."""
        _, state_file = temp_state_dir
        state = {
            "session_started": True,
            "context_checked": True,
            "standards_loaded": True,
            "prompt_generated": True,
            "tasks_created": True,
            "plan_mode_decided": True,
            "model_selected": True,
            "skills_agents_checked": True
        }
        state_file.write_text(json.dumps(state), encoding="utf-8")

        result = _parse(verify_compliance())
        assert result["compliant"] is True
        assert result["completed_steps"] == 8
        assert result["missing_steps"] == []


class TestListPolicies:
    """Tests for list_policies tool."""

    def test_list_all_policies(self):
        """Test listing all policies from project directory."""
        result = _parse(list_policies("all"))
        # Should find policies if running from project root
        assert "success" in result
        if result["success"]:
            assert isinstance(result["policies"], list)
            assert result["count"] > 0

    def test_list_filtered_policies(self):
        """Test listing policies filtered by level."""
        result = _parse(list_policies("03-execution"))
        assert "success" in result
        if result["success"]:
            for policy in result["policies"]:
                assert "03-execution" in policy["level"]


class TestJsonFormat:
    """Tests for consistent JSON response format."""

    def test_all_tools_return_valid_json(self, temp_state_dir):
        """Verify all tools return valid JSON."""
        tools = [
            check_enforcement_status,
            lambda: enforce_policy_step(0, "Test"),
            lambda: log_tool_usage("Test", "test op"),
            verify_compliance,
            lambda: list_policies("all"),
        ]
        for tool_fn in tools:
            result = json.loads(tool_fn())
            assert isinstance(result, dict)
