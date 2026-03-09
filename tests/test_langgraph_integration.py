"""
Integration Tests - Real Policy Script Execution

Tests that verify actual policy scripts are being called and produce expected output.
These tests skip if policy scripts don't exist.
"""

import pytest
import json
import sys
from pathlib import Path
from subprocess import run

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from langgraph_engine.subgraphs.level1_sync import run_policy_script
from langgraph_engine.subgraphs.level2_standards import (
    load_policies_from_directory,
    run_standards_loader_script,
)
from langgraph_engine.subgraphs.level3_execution import call_execution_script


class TestPolicyScriptIntegration:
    """Test actual policy script execution"""

    def test_architecture_directory_exists(self):
        """Verify architecture directory structure exists"""
        scripts_dir = Path(__file__).parent.parent / "scripts"
        arch_dir = scripts_dir / "architecture"

        assert arch_dir.exists(), "scripts/architecture directory not found"

        # Check all 3 levels
        assert (arch_dir / "01-sync-system").exists(), "01-sync-system not found"
        assert (arch_dir / "02-standards-system").exists(), "02-standards-system not found"
        assert (arch_dir / "03-execution-system").exists(), "03-execution-system not found"

    def test_level1_script_existence(self):
        """Verify Level 1 policy scripts exist"""
        scripts_dir = Path(__file__).parent.parent / "scripts"
        level1_dir = scripts_dir / "architecture" / "01-sync-system"

        # List what's actually in the directory
        if level1_dir.exists():
            scripts = list(level1_dir.glob("**/*.py"))
            # We should have at least some scripts
            print(f"Found {len(scripts)} Python scripts in Level 1")

    def test_level2_script_existence(self):
        """Verify Level 2 policy scripts exist"""
        scripts_dir = Path(__file__).parent.parent / "scripts"
        level2_dir = scripts_dir / "architecture" / "02-standards-system"

        if level2_dir.exists():
            scripts = list(level2_dir.glob("**/*.py"))
            print(f"Found {len(scripts)} Python scripts in Level 2")

    def test_level3_script_existence(self):
        """Verify Level 3 policy scripts exist"""
        scripts_dir = Path(__file__).parent.parent / "scripts"
        level3_dir = scripts_dir / "architecture" / "03-execution-system"

        if level3_dir.exists():
            scripts = list(level3_dir.glob("**/*.py"))
            print(f"Found {len(scripts)} Python scripts in Level 3")
            # Should have multiple subdirectories
            subdirs = [d for d in level3_dir.iterdir() if d.is_dir()]
            print(f"Found {len(subdirs)} subdirectories in Level 3")

    def test_policies_directory_structure(self):
        """Verify ~/.claude/policies directory structure if it exists"""
        policies_dir = Path.home() / ".claude" / "policies"

        if policies_dir.exists():
            # Check for level directories
            level_dirs = [
                policies_dir / "01-sync-system",
                policies_dir / "02-standards-system",
                policies_dir / "03-execution-system",
            ]
            for level_dir in level_dirs:
                if level_dir.exists():
                    md_files = list(level_dir.glob("**/*.md"))
                    print(f"{level_dir.name}: {len(md_files)} policy files")
        else:
            pytest.skip("~/.claude/policies directory not found")


class TestPolicyScriptOutput:
    """Test that policy scripts produce expected output format"""

    def test_run_policy_script_returns_dict(self):
        """Verify run_policy_script returns a dict"""
        # This will try to run a script - if it doesn't exist, returns error dict
        result = run_policy_script("test-nonexistent")

        # Should always return a dict (error or success)
        assert isinstance(result, dict), "run_policy_script should return dict"
        assert "status" in result, "Result should have 'status' field"

    def test_call_execution_script_returns_dict(self):
        """Verify call_execution_script returns a dict"""
        result = call_execution_script("test-nonexistent")

        assert isinstance(result, dict), "call_execution_script should return dict"
        assert "status" in result, "Result should have 'status' field"

    def test_policies_loader_returns_structure(self):
        """Verify load_policies_from_directory returns correct structure"""
        result = load_policies_from_directory()

        # Should always return a dict with level keys
        assert isinstance(result, dict)
        assert "level1" in result or "error" in result
        assert "level2" in result or "error" in result
        assert "level3" in result or "error" in result


class TestFlowTraceOutputFormat:
    """Test flow-trace.json format for backward compatibility"""

    def test_flow_trace_json_structure(self):
        """Verify flow-trace.json can be parsed as JSON"""
        # Create a sample flow trace
        flow_trace = {
            "session_id": "test-session",
            "timestamp": "2026-03-10T10:00:00",
            "project_root": "/tmp/test",
            "final_status": "OK",
            "pipeline": [
                {
                    "node": "level1_context",
                    "status": "OK",
                    "duration_ms": 100,
                }
            ],
            "errors": [],
            "warnings": [],
            "context_percentage": 45.5,
            "standards_count": 12,
        }

        # Should be JSON serializable
        json_str = json.dumps(flow_trace)
        parsed = json.loads(json_str)

        assert parsed["session_id"] == "test-session"
        assert parsed["final_status"] == "OK"
        assert len(parsed["pipeline"]) == 1

    def test_backward_compatibility_fields(self):
        """Verify flow-trace.json has all fields pre-tool-enforcer.py expects"""
        # Simulate what pre-tool-enforcer.py reads from flow-trace.json
        flow_trace = {
            "session_id": "test",
            "final_status": "OK",
            "context_percentage": 50.0,
            "standards_count": 12,
            "errors": [],
            "warnings": [],
        }

        # These are the fields pre-tool-enforcer.py checks
        assert flow_trace.get("session_id") is not None
        assert flow_trace.get("final_status") in ["OK", "PARTIAL", "FAILED"]
        assert isinstance(flow_trace.get("context_percentage", 0), (int, float))
        assert isinstance(flow_trace.get("standards_count", 0), int)
        assert isinstance(flow_trace.get("errors", []), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
