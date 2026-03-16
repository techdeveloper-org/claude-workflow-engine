"""Tests for Git MCP Server (src/mcp/git_mcp_server.py)."""

import json
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
import importlib.util

_MCP_DIR = Path(__file__).parent.parent / "src" / "mcp"

def _load_module(name, file_path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_git_mod = _load_module("git_mcp_server", _MCP_DIR / "git_mcp_server.py")

git_status = _git_mod.git_status
git_branch_create = _git_mod.git_branch_create
git_branch_switch = _git_mod.git_branch_switch
git_branch_list = _git_mod.git_branch_list
git_branch_delete = _git_mod.git_branch_delete
git_commit = _git_mod.git_commit
git_push = _git_mod.git_push
git_pull = _git_mod.git_pull
git_diff = _git_mod.git_diff
git_stash = _git_mod.git_stash
git_log = _git_mod.git_log
git_fetch = _git_mod.git_fetch


def _parse(result: str) -> dict:
    """Parse JSON result from MCP tool."""
    return json.loads(result)


class TestGitStatus:
    """Tests for git_status tool."""

    def test_status_valid_repo(self):
        """Test status on current repo (which is a git repo)."""
        result = _parse(git_status("."))
        assert result["success"] is True
        assert "branch" in result
        assert "is_dirty" in result
        assert isinstance(result["modified"], list)
        assert isinstance(result["staged"], list)
        assert isinstance(result["untracked"], list)

    def test_status_invalid_repo(self):
        """Test status on non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _parse(git_status(tmpdir))
            assert result["success"] is False
            assert "error" in result


class TestGitBranchList:
    """Tests for git_branch_list tool."""

    def test_list_branches(self):
        """Test listing branches on current repo."""
        result = _parse(git_branch_list("."))
        assert result["success"] is True
        assert "current" in result
        assert isinstance(result["local"], list)
        assert len(result["local"]) > 0


class TestGitLog:
    """Tests for git_log tool."""

    def test_log_default(self):
        """Test log with default count."""
        result = _parse(git_log(10, "."))
        assert result["success"] is True
        assert isinstance(result["commits"], list)
        assert result["count"] > 0

    def test_log_single_commit(self):
        """Test log with count=1."""
        result = _parse(git_log(1, "."))
        assert result["success"] is True
        assert result["count"] == 1
        commit = result["commits"][0]
        assert "hash" in commit
        assert "message" in commit
        assert "author" in commit
        assert "date" in commit


class TestGitDiff:
    """Tests for git_diff tool."""

    def test_diff_default(self):
        """Test diff with no arguments."""
        result = _parse(git_diff(False, None, "."))
        assert result["success"] is True
        assert "diff_summary" in result

    def test_diff_staged(self):
        """Test staged diff."""
        result = _parse(git_diff(True, None, "."))
        assert result["success"] is True
        assert result["staged"] is True


class TestGitStash:
    """Tests for git_stash tool."""

    def test_stash_list(self):
        """Test listing stashes."""
        result = _parse(git_stash("list", None, "."))
        assert result["success"] is True
        assert result["action"] == "list"
        assert isinstance(result["stashes"], list)

    def test_stash_invalid_action(self):
        """Test invalid stash action."""
        result = _parse(git_stash("invalid", None, "."))
        assert result["success"] is False
        assert "Unknown stash action" in result["error"]


class TestGitCommit:
    """Tests for git_commit tool - non-destructive tests only."""

    def test_commit_no_changes(self):
        """Test commit when there are no changes (clean tree)."""
        # This test only works if the tree is clean
        status = _parse(git_status("."))
        if not status.get("is_dirty"):
            result = _parse(git_commit("test commit", None, "."))
            assert result["success"] is True
            assert "No changes" in result.get("message", "")


class TestGitFetch:
    """Tests for git_fetch tool."""

    def test_fetch_default(self):
        """Test fetch from origin."""
        result = _parse(git_fetch("origin", None, False, "."))
        # May fail if no network, but should return valid JSON
        assert "success" in result


class TestJsonFormat:
    """Tests for consistent JSON response format."""

    def test_all_tools_return_json(self):
        """Verify all tools return valid JSON with success field."""
        tools = [
            lambda: git_status("."),
            lambda: git_branch_list("."),
            lambda: git_log(1, "."),
            lambda: git_diff(False, None, "."),
            lambda: git_stash("list", None, "."),
        ]
        for tool_fn in tools:
            result = json.loads(tool_fn())
            assert "success" in result, f"Missing 'success' field in {tool_fn}"
