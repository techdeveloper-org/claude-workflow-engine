"""Unit tests for langgraph_engine/library/resolver.py -- the ADR-1 local-path
bridge (3-tier Chain-of-Responsibility: local sibling -> opt-in GitHub -> hard-fail).

Covers:
- Local-sibling hit with zero network calls
- Local-sibling absent + fallback disabled -> LibrarySetupError with structured fields
- Local-sibling absent + fallback enabled -> falls through to the GitHub tier
- SKILL.md vs skill.md casing precedence
- Path-traversal rejection for crafted names
- Integration against the REAL sibling claude-global-library checkout
"""

import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langgraph_engine.library.resolver import (  # noqa: E402
    ChainedResourceResolver,
    GitHubAdapter,
    HardFailAdapter,
    LibrarySetupError,
    LocalSiblingAdapter,
    _reset_library_root_cache,
    _validate_kg_relpath,
    _validate_resource_name,
    build_default_resolver,
    locate_library_root,
)

_REAL_LIBRARY_ROOT = _PROJECT_ROOT.parent / "claude-global-library"


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every test starts with a clean locate_library_root() memoization cache."""
    _reset_library_root_cache()
    yield
    _reset_library_root_cache()


@pytest.fixture
def sibling_root(tmp_path):
    """A fake sibling library with one skill (both casings) and one agent."""
    root = tmp_path / "claude-global-library"
    (root / "skills" / "alpha-skill").mkdir(parents=True)
    (root / "skills" / "alpha-skill" / "SKILL.md").write_text("# alpha-skill (upper)", encoding="utf-8")
    (root / "skills" / "beta-skill").mkdir(parents=True)
    (root / "skills" / "beta-skill" / "skill.md").write_text("# beta-skill (lower)", encoding="utf-8")
    (root / "agents" / "gamma-agent").mkdir(parents=True)
    (root / "agents" / "gamma-agent" / "agent.md").write_text("# gamma-agent", encoding="utf-8")
    (root / "knowledge-graph").mkdir(parents=True)
    (root / "knowledge-graph" / "patterns.json").write_text("{}", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# LocalSiblingAdapter
# ---------------------------------------------------------------------------


class TestLocalSiblingAdapter:
    def test_fetch_skill_hit_zero_network(self, sibling_root):
        """A local hit never touches urllib -- assert no HTTP call is made."""
        adapter = LocalSiblingAdapter(sibling_root)
        with patch("urllib.request.urlopen") as mock_urlopen:
            resource = adapter.try_fetch_skill("alpha-skill")
        mock_urlopen.assert_not_called()
        assert resource is not None
        assert resource.source == "local"
        assert "alpha-skill" in resource.content

    def test_fetch_agent_hit(self, sibling_root):
        adapter = LocalSiblingAdapter(sibling_root)
        resource = adapter.try_fetch_agent("gamma-agent")
        assert resource is not None
        assert resource.source == "local"
        assert "gamma-agent" in resource.content

    def test_fetch_kg_file_hit(self, sibling_root):
        adapter = LocalSiblingAdapter(sibling_root)
        resource = adapter.try_fetch_kg_file("knowledge-graph/patterns.json")
        assert resource is not None
        assert resource.content == "{}"

    def test_fetch_skill_miss_returns_none(self, sibling_root):
        adapter = LocalSiblingAdapter(sibling_root)
        assert adapter.try_fetch_skill("does-not-exist") is None

    def test_skill_md_vs_SKILL_md_casing_precedence(self, tmp_path):
        """SKILL.md must be probed before skill.md (HLD Section 7.1 casing contract).

        NTFS/Windows filesystems are case-insensitive, so writing both
        "SKILL.md" and "skill.md" collapses to a single file on disk and
        cannot exercise precedence directly. Instead, spy on the probe order
        via ``_read_if_exists`` and assert the first path attempted ends in
        the uppercase filename.
        """
        root = tmp_path / "lib"
        skill_dir = root / "skills" / "dual-case"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")

        adapter = LocalSiblingAdapter(root)
        probed_paths = []
        original_read = adapter._read_if_exists

        def spy(path):
            probed_paths.append(path)
            return original_read(path)

        adapter._read_if_exists = spy
        resource = adapter.try_fetch_skill("dual-case")

        assert resource is not None
        assert probed_paths[0].name == "SKILL.md"

    def test_lowercase_skill_md_used_when_only_lowercase_exists(self, sibling_root):
        adapter = LocalSiblingAdapter(sibling_root)
        resource = adapter.try_fetch_skill("beta-skill")
        assert resource.content == "# beta-skill (lower)"

    def test_path_traversal_rejected_for_skill_name(self, sibling_root):
        adapter = LocalSiblingAdapter(sibling_root)
        with pytest.raises(ValueError):
            adapter.try_fetch_skill("../../etc/passwd")

    def test_path_traversal_rejected_for_kg_relpath(self, sibling_root):
        adapter = LocalSiblingAdapter(sibling_root)
        with pytest.raises(ValueError):
            adapter.try_fetch_kg_file("../../../etc/passwd")


# ---------------------------------------------------------------------------
# Name / path validation helpers
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_name_accepted(self):
        assert _validate_resource_name("python-backend-engineer", "skill_name") == "python-backend-engineer"

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError):
            _validate_resource_name("", "skill_name")

    def test_uppercase_name_rejected(self):
        with pytest.raises(ValueError):
            _validate_resource_name("Docker", "skill_name")

    def test_dotdot_in_name_rejected(self):
        with pytest.raises(ValueError):
            _validate_resource_name("..", "skill_name")

    def test_valid_kg_relpath_accepted(self):
        assert _validate_kg_relpath("knowledge-graph/_orchestration-decision-tree/patterns.json")

    def test_kg_relpath_with_dotdot_rejected(self):
        with pytest.raises(ValueError):
            _validate_kg_relpath("knowledge-graph/../../../etc/passwd")


# ---------------------------------------------------------------------------
# locate_library_root
# ---------------------------------------------------------------------------


class TestLocateLibraryRoot:
    def test_env_override_used_when_present(self, sibling_root, monkeypatch):
        monkeypatch.setenv("CLAUDE_GLOBAL_LIB_PATH", str(sibling_root))
        assert locate_library_root(Path("/nonexistent/engine/root")) == sibling_root

    def test_env_override_ignored_when_missing_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_GLOBAL_LIB_PATH", str(tmp_path / "does-not-exist"))
        engine_root = tmp_path / "engine"
        engine_root.mkdir()
        (tmp_path / "claude-global-library").mkdir()
        assert locate_library_root(engine_root) == tmp_path / "claude-global-library"

    def test_default_sibling_layout(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        engine_root = tmp_path / "claude-workflow-engine"
        engine_root.mkdir()
        (tmp_path / "claude-global-library").mkdir()
        assert locate_library_root(engine_root) == tmp_path / "claude-global-library"

    def test_none_when_neither_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        engine_root = tmp_path / "claude-workflow-engine"
        engine_root.mkdir()
        assert locate_library_root(engine_root) is None

    def test_real_sibling_repo_resolves(self, monkeypatch):
        """Integration check against the REAL sibling checkout on this machine."""
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        result = locate_library_root(_PROJECT_ROOT)
        assert result == _REAL_LIBRARY_ROOT
        assert (result / "skills" / "docker" / "SKILL.md").is_file()
        assert (result / "agents" / "python-backend-engineer" / "agent.md").is_file()


# ---------------------------------------------------------------------------
# GitHubAdapter
# ---------------------------------------------------------------------------


class TestGitHubAdapter:
    def test_success_on_first_attempt_no_sleep(self):
        sleeps = []
        adapter = GitHubAdapter("https://example.invalid/base", sleep_fn=sleeps.append)
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = b"content"
            resource = adapter.try_fetch_skill("some-skill")
        assert resource is not None
        assert resource.source == "github"
        assert sleeps == []  # first attempt has 0 delay -> no sleep call

    def test_404_skips_to_next_candidate_without_retry(self):
        sleeps = []
        adapter = GitHubAdapter("https://example.invalid/base", sleep_fn=sleeps.append)
        call_count = {"n": 0}

        def fake_urlopen(req, timeout=None):
            call_count["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resource = adapter.try_fetch_skill("missing-skill")

        assert resource is None
        # Both filename candidates (SKILL.md, skill.md) attempted once each (404 = no retry per candidate)
        assert call_count["n"] == 2

    def test_retries_on_transient_failure_then_succeeds(self):
        sleeps = []
        adapter = GitHubAdapter("https://example.invalid/base", sleep_fn=sleeps.append)
        attempts = {"n": 0}

        def fake_urlopen(req, timeout=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise urllib.error.URLError("connection reset")
            return _FakeResponse(b"eventual success")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resource = adapter.try_fetch_skill("flaky-skill")

        assert resource is not None
        assert resource.content == "eventual success"
        # sleeps recorded for the delay schedule before the 3rd (successful) attempt
        assert sleeps[:2] == [1, 2]


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


# ---------------------------------------------------------------------------
# HardFailAdapter / LibrarySetupError
# ---------------------------------------------------------------------------


class TestHardFailAdapter:
    def test_raises_with_structured_fields(self, tmp_path):
        expected = tmp_path / "claude-global-library"
        adapter = HardFailAdapter(expected, "CLAUDE_GLOBAL_LIB_PATH")
        with pytest.raises(LibrarySetupError) as excinfo:
            adapter.try_fetch_skill("anything")
        err = excinfo.value
        assert err.expected_local_path == expected
        assert err.override_env_var == "CLAUDE_GLOBAL_LIB_PATH"
        assert str(expected) in str(err)
        assert "CLAUDE_GLOBAL_LIB_PATH" in str(err)


# ---------------------------------------------------------------------------
# ChainedResourceResolver + build_default_resolver (end-to-end tier behavior)
# ---------------------------------------------------------------------------


class TestChainedResourceResolver:
    def test_local_hit_short_circuits_chain(self, sibling_root):
        local = LocalSiblingAdapter(sibling_root)
        hard_fail = HardFailAdapter(sibling_root)
        resolver = ChainedResourceResolver([local, hard_fail])
        resource = resolver.fetch_skill("alpha-skill")
        assert resource.source == "local"

    def test_local_miss_falls_through_to_hard_fail(self, sibling_root):
        local = LocalSiblingAdapter(sibling_root)
        hard_fail = HardFailAdapter(sibling_root)
        resolver = ChainedResourceResolver([local, hard_fail])
        with pytest.raises(LibrarySetupError):
            resolver.fetch_skill("does-not-exist")

    def test_local_miss_falls_through_to_github_when_enabled(self, sibling_root):
        local = LocalSiblingAdapter(sibling_root)
        github = GitHubAdapter("https://example.invalid/base")
        hard_fail = HardFailAdapter(sibling_root)
        resolver = ChainedResourceResolver([local, github, hard_fail])

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = b"from github"
            resource = resolver.fetch_skill("not-local-but-remote")

        assert resource.source == "github"
        assert resource.content == "from github"

    def test_no_tiers_raises_valueerror(self):
        with pytest.raises(ValueError):
            ChainedResourceResolver([])


class TestBuildDefaultResolver:
    def test_fallback_disabled_by_default_raises_setup_error_when_local_absent(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
        engine_root = tmp_path / "claude-workflow-engine"
        engine_root.mkdir()
        # No sibling directory created -> local tier absent, GitHub tier absent (default off)
        resolver = build_default_resolver(engine_root=engine_root)
        with pytest.raises(LibrarySetupError):
            resolver.fetch_skill("anything")

    def test_fallback_enabled_adds_github_tier(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.setenv("CLAUDE_ALLOW_GITHUB_FALLBACK", "1")
        engine_root = tmp_path / "claude-workflow-engine"
        engine_root.mkdir()
        resolver = build_default_resolver(engine_root=engine_root)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = b"github content"
            resource = resolver.fetch_skill("some-skill")

        assert resource.source == "github"

    def test_real_sibling_resolves_locally_with_zero_network(self, monkeypatch):
        """End-to-end against the REAL sibling repo: docker skill resolves locally."""
        monkeypatch.delenv("CLAUDE_GLOBAL_LIB_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_ALLOW_GITHUB_FALLBACK", raising=False)
        resolver = build_default_resolver(engine_root=_PROJECT_ROOT)

        with patch("urllib.request.urlopen") as mock_urlopen:
            resource = resolver.fetch_skill("docker")

        mock_urlopen.assert_not_called()
        assert resource.source == "local"
        assert "docker" in resource.content.lower()
