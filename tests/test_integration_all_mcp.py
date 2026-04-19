"""Integration tests for all 10 MCP servers.

Tests cross-server scenarios, import health, and tool function signatures.
Does NOT require running MCP servers - imports functions directly.

Windows-safe: ASCII only (cp1252 compatible).

HISTORICAL NOTE (issue #202):
  This test file predates the MCP server extraction. All 13 MCP servers
  have since been moved to separate repos under techdeveloper-org:
    mcp-git-ops, mcp-github-api, mcp-enforcement, mcp-token-optimizer,
    mcp-pre-tool-gate, mcp-post-tool-tracker, mcp-standards-loader,
    mcp-uml-diagram, mcp-drawio-diagram, mcp-jira-api, mcp-jenkins-ci,
    mcp-figma
  Only session-mgr retains an in-engine copy at src/mcp/session_mcp_server.py
  (the other 12 server.py files are gone). These integration tests should
  be moved INTO each corresponding MCP server repo as the test owner.

  This module-level skip stops the entire file from running in the
  claude-workflow-engine test suite. Re-enable for session-mgr tests by
  moving them to a dedicated tests/test_session_mcp_integration.py file.
"""

import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

_MCP_DIR = Path(__file__).parent.parent / "src" / "mcp"

# Module-level skip -- 12 of 13 MCP server files no longer live in-engine.
# See issue #202 and CLAUDE.md for the repo extraction history.
pytestmark = pytest.mark.skip(
    reason="MCP servers moved to separate repos under techdeveloper-org; "
    "integration tests should follow -- see issue #202"
)


def _load_module(name, file_path):
    """Load a module from file path without polluting sys.modules."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse(result):
    """Parse JSON result from MCP tool."""
    return json.loads(result)


# =============================================================================
# IMPORT HEALTH: All 10 servers must import without errors
# =============================================================================


class TestImportHealth:
    """Verify all MCP server modules import cleanly."""

    def test_git_ops_imports(self):
        mod = _load_module("git_mcp", _MCP_DIR / "git_mcp_server.py")
        assert hasattr(mod, "git_status")
        assert hasattr(mod, "git_post_merge_cleanup")
        assert hasattr(mod, "git_get_origin_url")

    def test_github_api_imports(self):
        mod = _load_module("github_mcp", _MCP_DIR / "github_mcp_server.py")
        assert hasattr(mod, "github_create_issue")
        assert hasattr(mod, "github_auto_commit_and_pr")
        assert hasattr(mod, "github_validate_build")
        assert hasattr(mod, "github_full_merge_cycle")

    def test_session_mgr_imports(self):
        mod = _load_module("session_mcp", _MCP_DIR / "session_mcp_server.py")
        assert hasattr(mod, "session_save")
        assert hasattr(mod, "session_create")
        assert hasattr(mod, "session_link")
        assert hasattr(mod, "session_tag")
        assert hasattr(mod, "session_get_context")
        assert hasattr(mod, "session_accumulate")
        assert hasattr(mod, "session_finalize")
        assert hasattr(mod, "session_add_work_item")

    def test_enforcement_imports(self):
        mod = _load_module("enforcement_mcp", _MCP_DIR / "enforcement_mcp_server.py")
        assert hasattr(mod, "check_enforcement_status")
        assert hasattr(mod, "record_policy_execution")
        assert hasattr(mod, "get_flow_trace_summary")
        assert hasattr(mod, "check_module_health")

    def test_token_optimizer_imports(self):
        mod = _load_module("token_opt_mcp", _MCP_DIR / "token_optimization_mcp_server.py")
        assert hasattr(mod, "optimize_tool_call")
        assert hasattr(mod, "ast_navigate_code")
        assert hasattr(mod, "smart_read_analyze")
        assert hasattr(mod, "deduplicate_context")
        assert hasattr(mod, "context_budget_status")

    def test_pre_tool_gate_imports(self):
        mod = _load_module("pre_tool_gate", _MCP_DIR / "pre_tool_gate_mcp_server.py")
        assert hasattr(mod, "validate_tool_call")
        assert hasattr(mod, "check_task_breakdown")
        assert hasattr(mod, "check_skill_selected")
        assert hasattr(mod, "get_enforcer_state")
        assert hasattr(mod, "reset_enforcer_flags")

    def test_post_tool_tracker_imports(self):
        mod = _load_module("post_tool_tracker", _MCP_DIR / "post_tool_tracker_mcp_server.py")
        assert hasattr(mod, "track_tool_usage")
        assert hasattr(mod, "get_progress_status")
        assert hasattr(mod, "get_tool_stats")
        assert hasattr(mod, "check_commit_readiness")

    def test_standards_loader_imports(self):
        mod = _load_module("standards_mcp", _MCP_DIR / "standards_loader_mcp_server.py")
        assert hasattr(mod, "detect_project_type")
        assert hasattr(mod, "detect_framework")
        assert hasattr(mod, "load_standards")
        assert hasattr(mod, "list_available_standards")


# =============================================================================
# TOOL COUNT VERIFICATION: Each server has expected number of tools
# =============================================================================


class TestToolCounts:
    """Verify each server exposes the expected number of tools."""

    def test_git_ops_tool_count(self):
        mod = _load_module("git_mcp", _MCP_DIR / "git_mcp_server.py")
        tools = [attr for attr in dir(mod) if attr.startswith("git_")]
        assert len(tools) >= 14, f"Expected 14+ git tools, got {len(tools)}: {tools}"

    def test_session_mgr_tool_count(self):
        mod = _load_module("session_mcp", _MCP_DIR / "session_mcp_server.py")
        tools = [attr for attr in dir(mod) if attr.startswith("session_")]
        assert len(tools) >= 13, f"Expected 13+ session tools, got {len(tools)}: {tools}"

    def test_enforcement_tool_count(self):
        mod = _load_module("enforcement_mcp", _MCP_DIR / "enforcement_mcp_server.py")
        public_tools = [
            "check_enforcement_status",
            "enforce_policy_step",
            "log_tool_usage",
            "verify_compliance",
            "list_policies",
            "record_policy_execution",
            "get_session_id",
            "get_flow_trace_summary",
            "check_module_health",
        ]
        for tool in public_tools:
            assert hasattr(mod, tool), f"Missing tool: {tool}"


# =============================================================================
# CROSS-SERVER INTEGRATION: Scenarios that span multiple servers
# =============================================================================


class TestCrossServerIntegration:
    """Test scenarios that require multiple MCP servers working together."""

    def test_token_optimizer_read_optimization(self):
        """Token optimizer should add offset/limit for large files."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")
        # Create a large temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("\n".join([f"line_{i} = {i}" for i in range(1000)]))
            tmp_path = f.name

        try:
            result = _parse(mod.optimize_tool_call("Read", json.dumps({"file_path": tmp_path})))
            assert result["success"] is True
            assert result["was_optimized"] is True
            assert result["optimized_params"].get("limit") is not None
            assert result["token_savings_estimate"] > 0
        finally:
            os.unlink(tmp_path)

    def test_token_optimizer_grep_head_limit(self):
        """Token optimizer should enforce head_limit on Grep."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")
        result = _parse(mod.optimize_tool_call("Grep", json.dumps({"pattern": "class.*Service"})))
        assert result["success"] is True
        assert result["optimized_params"]["head_limit"] == 100
        assert result["optimized_params"]["output_mode"] == "files_with_matches"

    def test_standards_detect_current_project(self):
        """Standards loader should detect this project as Python."""
        mod = _load_module("standards_mcp", _MCP_DIR / "standards_loader_mcp_server.py")
        project_root = str(Path(__file__).parent.parent)
        result = _parse(mod.detect_project_type(project_root))
        assert result["success"] is True
        assert result["project_type"] == "python"

    def test_pre_tool_gate_allows_read(self):
        """Pre-tool gate should always allow Read tool."""
        mod = _load_module("pre_tool_gate", _MCP_DIR / "pre_tool_gate_mcp_server.py")
        result = _parse(mod.validate_tool_call("Read", "{}"))
        assert result["allowed"] is True

    def test_pre_tool_gate_allows_grep(self):
        """Pre-tool gate should always allow Grep tool."""
        mod = _load_module("pre_tool_gate", _MCP_DIR / "pre_tool_gate_mcp_server.py")
        result = _parse(mod.validate_tool_call("Grep", "{}"))
        assert result["allowed"] is True

    def test_pre_tool_gate_dynamic_skill_hint(self):
        """Dynamic skill hint should map extensions correctly."""
        mod = _load_module("pre_tool_gate", _MCP_DIR / "pre_tool_gate_mcp_server.py")

        test_cases = [
            ("test.java", "java-spring-boot-microservices"),
            ("test.py", "python-core"),
            ("test.ts", "typescript-core"),
            ("test.tsx", "react-core"),
            ("test.kt", "kotlin-core"),
            ("test.swift", "swiftui-core"),
            ("test.sql", "rdbms-core"),
        ]
        for filename, expected_skill in test_cases:
            result = _parse(mod.get_dynamic_skill_hint(filename))
            assert result["success"] is True
            assert (
                result["suggested_skill"] == expected_skill
            ), f"Expected {expected_skill} for {filename}, got {result['suggested_skill']}"

    def test_enforcement_verify_compliance_structure(self):
        """Enforcement compliance check should return proper structure."""
        mod = _load_module("enforcement_mcp", _MCP_DIR / "enforcement_mcp_server.py")
        result = _parse(mod.verify_compliance())
        assert "compliant" in result
        assert "completed_steps" in result
        assert "total_steps" in result
        assert "missing_steps" in result

    def test_session_hooks_bridge_importable(self):
        """Session hooks bridge should be importable."""
        mod = _load_module("session_hooks", _MCP_DIR / "session_hooks.py")
        assert hasattr(mod, "accumulate_request")
        assert hasattr(mod, "finalize_session")
        assert hasattr(mod, "create_session")
        assert hasattr(mod, "link_sessions")
        assert hasattr(mod, "tag_session")


# =============================================================================
# AST CODE NAVIGATION: Token optimizer's unique feature
# =============================================================================


class TestASTNavigation:
    """Test AST code navigation across languages."""

    def test_python_ast_navigation(self):
        """AST navigate should extract Python class/function structure."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                "import os\n"
                "import json\n\n"
                "class MyService:\n"
                "    def handle(self, request):\n"
                "        pass\n\n"
                "    def validate(self, data):\n"
                "        pass\n\n"
                "def helper_func():\n"
                "    pass\n"
            )
            tmp_path = f.name

        try:
            result = _parse(mod.ast_navigate_code(tmp_path, show_methods=True))
            assert result["success"] is True
            assert result["language"] == "python"
            assert len(result["classes"]) == 1
            assert result["classes"][0]["name"] == "MyService"
            assert "handle" in result["classes"][0]["methods"]
            assert "validate" in result["classes"][0]["methods"]
            assert any(f["name"] == "helper_func" for f in result["functions"])
            assert result["tokens_saved_estimate"] > 0
        finally:
            os.unlink(tmp_path)

    def test_java_ast_navigation(self):
        """AST navigate should extract Java class structure via regex."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(
                "package com.example.service;\n\n"
                "import java.util.List;\n"
                "import java.util.Map;\n\n"
                "public class ProductService {\n"
                "    public List<Product> getAll() { return null; }\n"
                "    private void validate(Product p) {}\n"
                "}\n"
            )
            tmp_path = f.name

        try:
            result = _parse(mod.ast_navigate_code(tmp_path, show_methods=True))
            assert result["success"] is True
            assert result["language"] == "java"
            assert result["package"] == "com.example.service"
            assert "ProductService" in result["classes"]
            assert len(result["methods"]) >= 1  # Regex may not catch generic return types
        finally:
            os.unlink(tmp_path)

    def test_typescript_ast_navigation(self):
        """AST navigate should extract TypeScript structure via regex."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(
                "import { Injectable } from '@angular/core';\n"
                "import { HttpClient } from '@angular/common/http';\n\n"
                "export class ApiService {\n"
                "    getData(): Observable<any> { return null; }\n"
                "}\n\n"
                "export interface DataModel {\n"
                "    id: number;\n"
                "}\n\n"
                "export function helper(): void {}\n"
                "export const API_URL = 'http://localhost';\n"
            )
            tmp_path = f.name

        try:
            result = _parse(mod.ast_navigate_code(tmp_path, show_methods=False))
            assert result["success"] is True
            assert result["language"] == "typescript"
            assert "ApiService" in result["classes"]
            assert "DataModel" in result["interfaces"]
            assert "helper" in result["functions"]
            assert "API_URL" in result["constants"]
        finally:
            os.unlink(tmp_path)

    def test_unsupported_extension(self):
        """AST navigate should return error for unsupported types."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".rb", delete=False) as f:
            f.write("class Foo; end")
            tmp_path = f.name

        try:
            result = _parse(mod.ast_navigate_code(tmp_path))
            assert result["success"] is False
            assert "Unsupported" in result.get("error", "")
        finally:
            os.unlink(tmp_path)


# =============================================================================
# DEDUPLICATION TESTS
# =============================================================================


class TestContextDeduplication:
    """Test context deduplication logic."""

    def test_dedup_removes_duplicates(self):
        """Dedup should remove duplicate lines across docs when savings > 20%."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        contexts = {
            "srs": "# Project Overview\nThis is a Python project.\nIt uses Flask.\n" * 5,
            "readme": "# Project Overview\nThis is a Python project.\nIt uses Flask.\nExtra readme info.\n" * 5,
            "claude_md": "# Project Overview\nThis is a Python project.\nUnique claude info.\n",
        }
        result = _parse(mod.deduplicate_context(json.dumps(contexts)))
        assert result["success"] is True
        # With heavy duplication, savings should exceed 20%
        if result["dedup_applied"]:
            assert result["savings_ratio"] >= 0.20

    def test_dedup_skips_low_savings(self):
        """Dedup should skip when savings < 20%."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        contexts = {
            "srs": "Unique SRS content line 1.\nUnique SRS content line 2.\n",
            "readme": "Totally different readme.\nNo overlap with SRS.\n",
        }
        result = _parse(mod.deduplicate_context(json.dumps(contexts)))
        assert result["success"] is True
        assert result["dedup_applied"] is False

    def test_dedup_estimate(self):
        """Dedup estimate should return savings without modifying."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        contexts = {
            "srs": "Line A\nLine B\nLine C\n",
            "readme": "Line A\nLine B\nLine D\n",
        }
        result = _parse(mod.dedup_estimate(json.dumps(contexts)))
        assert result["success"] is True
        assert "savings_ratio" in result
        assert "original_bytes" in result


# =============================================================================
# SMART READ STRATEGY TESTS
# =============================================================================


class TestSmartRead:
    """Test smart file reading strategy recommendations."""

    def test_small_file_strategy(self):
        """Small files (<100 lines) should recommend full read."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("\n".join([f"x = {i}" for i in range(50)]))
            tmp_path = f.name

        try:
            result = _parse(mod.smart_read_analyze(tmp_path))
            assert result["success"] is True
            assert result["strategy"]["type"] == "small"
        finally:
            os.unlink(tmp_path)

    def test_large_file_strategy(self):
        """Large files (500-2000 lines) should recommend chunked read."""
        mod = _load_module("token_opt", _MCP_DIR / "token_optimization_mcp_server.py")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("\n".join([f"line_{i} = {i}" for i in range(800)]))
            tmp_path = f.name

        try:
            result = _parse(mod.smart_read_analyze(tmp_path))
            assert result["success"] is True
            assert result["strategy"]["type"] == "large"
            assert "offset" in result["strategy"].get("params", {})
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
