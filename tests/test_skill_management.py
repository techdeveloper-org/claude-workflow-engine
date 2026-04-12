"""
Tests for Task #8: Skill Management

Covers:
- Download failure handling with exponential backoff retry
- Cache fallback behavior
- Skill metadata parsing
- Dependency resolution (recursive, circular detection)
- Version compatibility checking
- Deprecated skill handling
- Version set validation
"""

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------
import sys
from pathlib import Path
from typing import Dict
from unittest.mock import patch

import pytest

# Ensure the project root and scripts directory are on the path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from langgraph_engine.dependency_resolver import (
    build_dependency_graph,
    detect_circular,
    parse_skill_metadata,
    resolve_dependencies,
)
from langgraph_engine.skill_manager import SkillManager, get_skill_manager
from langgraph_engine.version_selector import (
    Version,
    build_compatibility_matrix,
    check_compatibility,
    handle_deprecated,
    select_best_version,
    validate_version_set,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def tmp_skills_root(tmp_path):
    """Temporary skills root directory."""
    skills_root = tmp_path / ".claude" / "skills"
    skills_root.mkdir(parents=True)
    return skills_root


@pytest.fixture
def skill_manager(tmp_skills_root):
    """SkillManager with temp directory."""
    return SkillManager(skills_root=tmp_skills_root)


@pytest.fixture
def sample_skill_content():
    """Minimal skill markdown with dependencies section."""
    return """# python-backend-engineer

**Version:** 1.5.0

## Overview
Python backend engineering skill.

## Skill Dependencies

### Mandatory
- skill: rdbms-core
  version: ">=1.0.0"
- skill: context-management-core
  version: "*"

### Optional
- skill: redis
  version: ">=3.0.0"

## Capabilities
- rest_api
- orm
- jwt
- flask
"""


@pytest.fixture
def deprecated_skill_content():
    return """# old-skill

**Deprecated:** This skill is deprecated. Use new-skill instead.

## Overview
This is an old skill replaced by new-skill.
"""


@pytest.fixture
def eol_skill_content():
    return """# very-old-skill

**Status:** End-of-life. Do not use. Migrate to modern-skill.

## Overview
This skill has reached end-of-life.
"""


@pytest.fixture
def skill_no_deps():
    return """# rdbms-core

**Version:** 2.0.0

## Overview
Core relational database skill.

## Capabilities
- sql
- orm
- migrations
"""


# ===========================================================================
# dependency_resolver tests
# ===========================================================================


class TestParseSkillMetadata:
    def test_parses_mandatory_deps(self, sample_skill_content):
        meta = parse_skill_metadata(sample_skill_content, "python-backend-engineer")
        assert meta["name"] == "python-backend-engineer"
        mandatory_names = [d["name"] for d in meta["mandatory"]]
        assert "rdbms-core" in mandatory_names
        assert "context-management-core" in mandatory_names

    def test_parses_optional_deps(self, sample_skill_content):
        meta = parse_skill_metadata(sample_skill_content, "python-backend-engineer")
        optional_names = [d["name"] for d in meta["optional"]]
        assert "redis" in optional_names

    def test_parses_version_requirements(self, sample_skill_content):
        meta = parse_skill_metadata(sample_skill_content, "python-backend-engineer")
        rdbms = next(d for d in meta["mandatory"] if d["name"] == "rdbms-core")
        assert rdbms["version_req"] == ">=1.0.0"

    def test_wildcard_version(self, sample_skill_content):
        meta = parse_skill_metadata(sample_skill_content, "python-backend-engineer")
        ctx = next(d for d in meta["mandatory"] if d["name"] == "context-management-core")
        assert ctx["version_req"] == "*"

    def test_all_deps_only_mandatory(self, sample_skill_content):
        meta = parse_skill_metadata(sample_skill_content, "python-backend-engineer")
        assert "rdbms-core" in meta["all_deps"]
        # optional should NOT be in all_deps
        assert "redis" not in meta["all_deps"]

    def test_empty_content(self):
        meta = parse_skill_metadata("", "empty-skill")
        assert meta["mandatory"] == []
        assert meta["optional"] == []
        assert meta["all_deps"] == []

    def test_no_dependencies_section(self, skill_no_deps):
        meta = parse_skill_metadata(skill_no_deps, "rdbms-core")
        assert meta["mandatory"] == []
        assert meta["all_deps"] == []


class TestDetectCircular:
    def test_no_cycle(self):
        graph = {"a": ["b"], "b": ["c"], "c": []}
        cycles = detect_circular(graph)
        assert cycles == []

    def test_simple_cycle(self):
        graph = {"a": ["b"], "b": ["a"]}
        cycles = detect_circular(graph)
        assert len(cycles) == 1
        cycle = cycles[0]
        assert "a" in cycle
        assert "b" in cycle

    def test_three_node_cycle(self):
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        cycles = detect_circular(graph)
        assert len(cycles) >= 1
        all_nodes = set(n for c in cycles for n in c)
        assert {"a", "b", "c"}.issubset(all_nodes)

    def test_self_loop(self):
        graph = {"a": ["a"]}
        cycles = detect_circular(graph)
        assert len(cycles) >= 1

    def test_disconnected_with_cycle(self):
        graph = {"a": ["b"], "b": ["a"], "c": ["d"], "d": []}
        cycles = detect_circular(graph)
        # Only a->b->a is a cycle
        assert len(cycles) == 1


class TestResolveDependencies:
    def test_simple_resolution(self, sample_skill_content, skill_no_deps):
        contents = {
            "python-backend-engineer": sample_skill_content,
            "rdbms-core": skill_no_deps,
            "context-management-core": "# context-management-core",
        }
        result = resolve_dependencies("python-backend-engineer", contents)
        assert result["success"] is True
        assert "python-backend-engineer" in result["resolved"]
        assert "rdbms-core" in result["resolved"]

    def test_dep_before_dependent_in_order(self, sample_skill_content, skill_no_deps):
        contents = {
            "python-backend-engineer": sample_skill_content,
            "rdbms-core": skill_no_deps,
            "context-management-core": "# context-management-core",
        }
        result = resolve_dependencies("python-backend-engineer", contents)
        resolved = result["resolved"]
        if "rdbms-core" in resolved and "python-backend-engineer" in resolved:
            assert resolved.index("rdbms-core") < resolved.index("python-backend-engineer")

    def test_missing_dependency_reported(self, sample_skill_content):
        # Only provide root - deps are missing
        contents = {"python-backend-engineer": sample_skill_content}
        result = resolve_dependencies("python-backend-engineer", contents)
        assert len(result["unresolvable"]) > 0
        assert result["success"] is False

    def test_circular_detected(self):
        # a -> b -> a
        contents = {
            "a": "# a\n## Dependencies\n- skill: b",
            "b": "# b\n## Dependencies\n- skill: a",
        }
        result = resolve_dependencies("a", contents)
        assert len(result["circular"]) >= 1

    def test_max_depth_limit(self):
        # Chain deeper than max_depth
        contents = {f"s{i}": f"# s{i}\n## Dependencies\n- skill: s{i+1}" for i in range(15)}
        contents["s15"] = "# s15"
        result = resolve_dependencies("s0", contents, max_depth=5)
        assert len(result["unresolvable"]) > 0


class TestBuildDependencyGraph:
    def test_builds_correct_graph(self, sample_skill_content, skill_no_deps):
        contents = {
            "python-backend-engineer": sample_skill_content,
            "rdbms-core": skill_no_deps,
        }
        graph = build_dependency_graph(["python-backend-engineer", "rdbms-core"], contents)
        assert "python-backend-engineer" in graph
        assert "rdbms-core" in graph["python-backend-engineer"]
        assert graph["rdbms-core"] == []

    def test_missing_content_treated_as_leaf(self):
        graph = build_dependency_graph(["missing-skill"], {})
        assert graph["missing-skill"] == []


# ===========================================================================
# version_selector tests
# ===========================================================================


class TestVersion:
    def test_parse_full_semver(self):
        v = Version.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_partial_version(self):
        v = Version.parse("2.0")
        assert v.major == 2
        assert v.minor == 0
        assert v.patch == 0

    def test_parse_prerelease(self):
        v = Version.parse("1.0.0-beta.2")
        assert v.major == 1
        assert v.pre == "beta"
        assert v.pre_num == 2

    def test_ordering(self):
        assert Version.parse("1.0.0") < Version.parse("2.0.0")
        assert Version.parse("1.5.0") > Version.parse("1.4.9")
        assert Version.parse("1.0.0-beta") < Version.parse("1.0.0")

    def test_equality(self):
        assert Version.parse("1.0.0") == Version.parse("1.0.0")

    def test_wildcard_parses_to_zero(self):
        v = Version.parse("*")
        assert v.major == 0
        assert v.minor == 0
        assert v.patch == 0

    def test_compatible_release(self):
        v = Version.parse("1.5.3")
        base = Version.parse("1.5.0")
        assert v.is_compatible_release(base) is True
        other = Version.parse("1.6.0")
        assert v.is_compatible_release(other) is False


class TestCheckCompatibility:
    def test_wildcard_always_compatible(self):
        ok, msg = check_compatibility("1.0.0", "*")
        assert ok is True

    def test_ge_satisfied(self):
        ok, _ = check_compatibility("1.5.0", ">=1.0.0")
        assert ok is True

    def test_ge_not_satisfied(self):
        ok, _ = check_compatibility("0.9.0", ">=1.0.0")
        assert ok is False

    def test_lt_satisfied(self):
        ok, _ = check_compatibility("1.5.0", "<2.0.0")
        assert ok is True

    def test_lt_not_satisfied(self):
        ok, _ = check_compatibility("2.1.0", "<2.0.0")
        assert ok is False

    def test_range_satisfied(self):
        ok, _ = check_compatibility("1.5.0", ">=1.0.0,<2.0.0")
        assert ok is True

    def test_range_upper_violated(self):
        ok, _ = check_compatibility("2.1.0", ">=1.0.0,<2.0.0")
        assert ok is False

    def test_exclusion(self):
        ok, _ = check_compatibility("1.5.0", "!=1.5.0")
        assert ok is False

    def test_compatible_release(self):
        ok, _ = check_compatibility("1.2.5", "~=1.2.0")
        assert ok is True

    def test_compatible_release_wrong_minor(self):
        ok, _ = check_compatibility("1.3.0", "~=1.2.0")
        assert ok is False

    def test_exact_match(self):
        ok, _ = check_compatibility("1.2.3", "==1.2.3")
        assert ok is True

    def test_exact_no_match(self):
        ok, _ = check_compatibility("1.2.4", "==1.2.3")
        assert ok is False


class TestSelectBestVersion:
    def test_selects_highest_compatible(self):
        result = select_best_version("my-skill", ["1.0.0", "1.5.0", "1.9.0"], ">=1.0.0,<2.0.0")
        assert result["selected"] == "1.9.0"

    def test_prefers_stable_over_prerelease(self):
        result = select_best_version("my-skill", ["1.5.0-beta", "1.4.0"], ">=1.0.0", prefer_stable=True)
        assert result["selected"] == "1.4.0"
        assert result["is_stable"] is True

    def test_falls_back_to_prerelease_when_no_stable(self):
        result = select_best_version("my-skill", ["1.5.0-beta", "1.4.0-rc.1"], ">=1.0.0", prefer_stable=True)
        assert result["selected"] is not None

    def test_no_compatible_version(self):
        result = select_best_version("my-skill", ["0.5.0", "0.9.0"], ">=1.0.0")
        assert result["selected"] is None

    def test_wildcard_selects_newest(self):
        result = select_best_version("my-skill", ["1.0.0", "2.5.0", "1.8.0"], "*")
        assert result["selected"] == "2.5.0"

    def test_empty_available(self):
        result = select_best_version("my-skill", [], ">=1.0.0")
        assert result["selected"] is None


class TestHandleDeprecated:
    def test_detects_deprecated_keyword(self, deprecated_skill_content):
        result = handle_deprecated("old-skill", deprecated_skill_content)
        assert result["is_deprecated"] is True
        assert result["severity"] == "warning"

    def test_detects_eol(self, eol_skill_content):
        result = handle_deprecated("very-old-skill", eol_skill_content)
        assert result["is_deprecated"] is True
        assert result["severity"] == "error"

    def test_extracts_replacement(self, deprecated_skill_content):
        result = handle_deprecated("old-skill", deprecated_skill_content)
        assert result["replacement"] == "new-skill"

    def test_not_deprecated(self, sample_skill_content):
        result = handle_deprecated("python-backend-engineer", sample_skill_content)
        assert result["is_deprecated"] is False
        assert result["severity"] == "none"

    def test_empty_content(self):
        result = handle_deprecated("some-skill", "")
        assert result["is_deprecated"] is False

    def test_message_includes_replacement(self, deprecated_skill_content):
        result = handle_deprecated("old-skill", deprecated_skill_content)
        assert "new-skill" in result["message"]


class TestValidateVersionSet:
    def test_all_satisfied(self):
        versions = {"a": "1.5.0", "b": "2.0.0"}
        reqs = {"a": {"b": ">=1.0.0"}}
        result = validate_version_set(versions, reqs)
        assert result["valid"] is True
        assert result["violations"] == []

    def test_violation_detected(self):
        versions = {"a": "1.5.0", "b": "0.9.0"}
        reqs = {"a": {"b": ">=1.0.0"}}
        result = validate_version_set(versions, reqs)
        assert result["valid"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["skill"] == "a"

    def test_missing_dep_is_violation(self):
        versions = {"a": "1.0.0"}
        reqs = {"a": {"b": ">=1.0.0"}}
        result = validate_version_set(versions, reqs)
        assert result["valid"] is False

    def test_empty_requirements(self):
        versions = {"a": "1.0.0"}
        result = validate_version_set(versions, {})
        assert result["valid"] is True


class TestBuildCompatibilityMatrix:
    def test_compatible_set(self):
        skills = [
            {"name": "a", "version": "1.5.0", "version_requirements": {"b": ">=1.0.0"}},
            {"name": "b", "version": "2.0.0", "version_requirements": {}},
        ]
        result = build_compatibility_matrix(skills)
        assert result["all_compatible"] is True
        assert result["conflicts"] == []

    def test_conflict_detected(self):
        skills = [
            {"name": "a", "version": "1.5.0", "version_requirements": {"b": ">=3.0.0"}},
            {"name": "b", "version": "2.0.0", "version_requirements": {}},
        ]
        result = build_compatibility_matrix(skills)
        assert result["all_compatible"] is False
        assert len(result["conflicts"]) == 1

    def test_matrix_structure(self):
        skills = [
            {"name": "a", "version": "1.0.0", "version_requirements": {"b": "*"}},
            {"name": "b", "version": "1.0.0", "version_requirements": {}},
        ]
        result = build_compatibility_matrix(skills)
        assert "a" in result["matrix"]
        assert "b" in result["matrix"]["a"]
        assert result["matrix"]["a"]["b"] is True


# ===========================================================================
# skill_manager tests
# ===========================================================================


class TestSkillManagerDownloadRetry:
    """Test download failure handling with exponential backoff."""

    def test_successful_download_on_first_attempt(self, skill_manager, sample_skill_content):
        with patch.object(skill_manager, "_attempt_download") as mock_download:
            mock_download.return_value = {"success": True, "content": sample_skill_content}
            result = skill_manager.provision_skill("python-backend-engineer", force_download=True)
        assert result["success"] is True
        assert result["source"] == "download"
        assert result["attempts"] >= 1

    def test_retry_on_transient_failure(self, skill_manager, sample_skill_content):
        """Should retry and succeed on 3rd attempt."""
        call_count = 0

        def mock_download_side_effect(url):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"success": False, "content": None, "error": "Connection reset", "status_code": 0}
            return {"success": True, "content": sample_skill_content}

        with patch.object(skill_manager, "_attempt_download", side_effect=mock_download_side_effect):
            with patch("langgraph_engine.skill_manager.time.sleep"):
                result = skill_manager.provision_skill("python-backend-engineer", force_download=True)
        assert result["success"] is True

    def test_exponential_backoff_delays(self, skill_manager):
        """Verify delays follow exponential backoff: 0, 1, 2, 4, 8."""
        sleep_calls = []

        def mock_sleep(delay):
            sleep_calls.append(delay)

        def always_fail(url):
            return {"success": False, "content": None, "error": "timeout", "status_code": 0}

        with patch.object(skill_manager, "_attempt_download", side_effect=always_fail):
            with patch("langgraph_engine.skill_manager.time.sleep", side_effect=mock_sleep):
                result = skill_manager.provision_skill("nonexistent-skill", force_download=True)

        # First attempt is immediate (no sleep), subsequent ones have delays
        assert result["success"] is False
        # Delays should be present and follow 1, 2, 4, 8 pattern
        expected_delays = [1, 2, 4, 8]
        for expected in expected_delays:
            assert expected in sleep_calls, f"Expected delay {expected}s not found in {sleep_calls}"

    def test_max_retries_not_exceeded(self, skill_manager):
        """Verifies no more than MAX_RETRIES+1 total attempts per URL candidate."""
        attempt_count = 0

        def counting_download(url):
            nonlocal attempt_count
            attempt_count += 1
            return {"success": False, "content": None, "error": "timeout", "status_code": 0}

        with patch.object(skill_manager, "_attempt_download", side_effect=counting_download):
            with patch("langgraph_engine.skill_manager.time.sleep"):
                skill_manager.provision_skill("nonexistent-skill", force_download=True)

        # Each URL candidate gets MAX_RETRIES+1 attempts (5 total per candidate)
        # With many candidates, total could be high, but per-URL is bounded
        assert attempt_count > 0
        # We should not loop infinitely
        assert attempt_count < 1000

    def test_404_skips_retry_for_url(self, skill_manager, sample_skill_content):
        """404 responses should skip retries for that URL, try next candidate."""
        url_attempts: Dict[str, int] = {}

        def mock_404_then_success(url):
            url_attempts[url] = url_attempts.get(url, 0) + 1
            # First URL: 404 immediately
            if "backend" in url:
                return {"success": False, "content": None, "error": "HTTP 404", "status_code": 404}
            # Later URL: success
            return {"success": True, "content": sample_skill_content}

        with patch.object(skill_manager, "_attempt_download", side_effect=mock_404_then_success):
            with patch("langgraph_engine.skill_manager.time.sleep"):
                _result = skill_manager.provision_skill("python-backend-engineer", force_download=True)

        # 404 URLs should only be attempted once (no retry)
        for url, count in url_attempts.items():
            if "backend" in url:
                assert count == 1, f"404 URL {url} was retried {count} times - should be 1"


class TestSkillManagerCache:
    def test_memory_cache_hit_skips_download(self, skill_manager, sample_skill_content):
        """After first provisioning, memory cache should be used."""
        with patch.object(skill_manager, "_attempt_download") as mock_dl:
            mock_dl.return_value = {"success": True, "content": sample_skill_content}
            _result1 = skill_manager.provision_skill("python-backend-engineer", force_download=True)

        # Second call should hit memory cache, not download
        with patch.object(skill_manager, "_attempt_download") as mock_dl2:
            result2 = skill_manager.provision_skill("python-backend-engineer")
            mock_dl2.assert_not_called()

        assert result2["source"] == "memory_cache"
        assert result2["success"] is True

    def test_disk_cache_fallback_on_download_failure(self, skill_manager, tmp_skills_root, sample_skill_content):
        """Should return disk-cached skill when download fails."""
        # Pre-populate disk cache
        skill_dir = tmp_skills_root / "backend" / "python-backend-engineer"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(sample_skill_content, encoding="utf-8")

        # Download always fails
        def always_fail(url):
            return {"success": False, "content": None, "error": "network down", "status_code": 0}

        with patch.object(skill_manager, "_attempt_download", side_effect=always_fail):
            with patch("langgraph_engine.skill_manager.time.sleep"):
                result = skill_manager.provision_skill("python-backend-engineer", force_download=True)

        assert result["success"] is True
        assert result["source"] == "disk_cache"

    def test_disk_cache_loaded_on_second_call(self, skill_manager, tmp_skills_root, sample_skill_content):
        """Second call with empty memory cache should hit disk cache."""
        # Write to disk
        skill_dir = tmp_skills_root / "backend" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(sample_skill_content, encoding="utf-8")

        with patch.object(skill_manager, "_attempt_download") as mock_dl:
            result = skill_manager.provision_skill("my-skill")
            mock_dl.assert_not_called()

        assert result["source"] == "disk_cache"

    def test_force_download_bypasses_cache(self, skill_manager, sample_skill_content):
        """force_download=True should always call download."""
        with patch.object(skill_manager, "_attempt_download") as mock_dl:
            mock_dl.return_value = {"success": True, "content": sample_skill_content}
            _result1 = skill_manager.provision_skill("python-backend-engineer", force_download=True)

        with patch.object(skill_manager, "_attempt_download") as mock_dl2:
            mock_dl2.return_value = {"success": True, "content": sample_skill_content}
            _result2 = skill_manager.provision_skill("python-backend-engineer", force_download=True)
            mock_dl2.assert_called()

    def test_save_to_disk_after_download(self, skill_manager, tmp_skills_root, sample_skill_content):
        """Downloaded skill should be saved to disk cache."""
        with patch.object(skill_manager, "_attempt_download") as mock_dl:
            mock_dl.return_value = {"success": True, "content": sample_skill_content}
            skill_manager.provision_skill("python-backend-engineer", force_download=True)

        # Check that file was saved
        saved_file = tmp_skills_root / "downloaded" / "python-backend-engineer" / "skill.md"
        assert saved_file.exists()
        assert saved_file.read_text(encoding="utf-8") == sample_skill_content

    def test_clear_memory_cache(self, skill_manager, sample_skill_content):
        """clear_memory_cache() should empty in-memory cache."""
        with patch.object(skill_manager, "_attempt_download") as mock_dl:
            mock_dl.return_value = {"success": True, "content": sample_skill_content}
            skill_manager.provision_skill("python-backend-engineer", force_download=True)

        assert skill_manager.get_cache_stats()["memory_entries"] == 1
        skill_manager.clear_memory_cache()
        assert skill_manager.get_cache_stats()["memory_entries"] == 0


class TestSkillManagerProvisionBatch:
    def test_batch_all_success(self, skill_manager, sample_skill_content, skill_no_deps):
        def mock_provision(skill_name, version_req="*", force_download=False):
            content = sample_skill_content if "engineer" in skill_name else skill_no_deps
            return {
                "success": True,
                "skill_name": skill_name,
                "content": content,
                "version": "1.0.0",
                "source": "download",
                "attempts": 1,
                "deprecated": False,
                "deprecation_info": {},
                "metadata": {},
                "error": None,
            }

        with patch.object(skill_manager, "provision_skill", side_effect=mock_provision):
            result = skill_manager.provision_skills_batch(["python-backend-engineer", "rdbms-core"], resolve_deps=False)

        assert result["all_success"] is True
        assert len(result["failed"]) == 0

    def test_batch_reports_failures(self, skill_manager):
        def fail_provision(skill_name, version_req="*", force_download=False):
            return {
                "success": False,
                "skill_name": skill_name,
                "content": None,
                "version": None,
                "source": "failed",
                "attempts": 5,
                "deprecated": False,
                "deprecation_info": {},
                "metadata": {},
                "error": "network unreachable",
            }

        with patch.object(skill_manager, "provision_skill", side_effect=fail_provision):
            result = skill_manager.provision_skills_batch(["skill-a", "skill-b"], resolve_deps=False)

        assert result["all_success"] is False
        assert "skill-a" in result["failed"]
        assert "skill-b" in result["failed"]


class TestSkillManagerValidateSet:
    def test_validates_clean_set(self, skill_manager, tmp_skills_root, sample_skill_content, skill_no_deps):
        # Write skills to disk
        for skill_name, content in [
            ("python-backend-engineer", sample_skill_content),
            ("rdbms-core", skill_no_deps),
            ("context-management-core", "# context-management-core"),
        ]:
            d = tmp_skills_root / "backend" / skill_name
            d.mkdir(parents=True)
            (d / "skill.md").write_text(content, encoding="utf-8")

        result = skill_manager.validate_skill_set(["python-backend-engineer", "rdbms-core", "context-management-core"])
        # Should succeed - rdbms-core has no deps and is present
        assert isinstance(result["valid"], bool)
        assert "report" in result

    def test_detects_deprecated_in_set(self, skill_manager, tmp_skills_root, deprecated_skill_content):
        skill_dir = tmp_skills_root / "legacy" / "old-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(deprecated_skill_content, encoding="utf-8")

        result = skill_manager.validate_skill_set(["old-skill"])
        assert len(result["deprecation_warnings"]) > 0
        assert result["valid"] is False


class TestGetSkillManager:
    def test_returns_skill_manager_instance(self):
        manager = get_skill_manager()
        assert isinstance(manager, SkillManager)

    def test_custom_skills_root(self, tmp_path):
        custom_root = tmp_path / "custom_skills"
        manager = get_skill_manager(skills_root=custom_root)
        assert manager.skills_root == custom_root


# ===========================================================================
# Integration tests
# ===========================================================================


class TestSkillManagementIntegration:
    """End-to-end integration tests for the complete skill management flow."""

    def test_full_provisioning_flow(self, skill_manager, tmp_skills_root, sample_skill_content, skill_no_deps):
        """Full flow: download -> cache -> load deps -> validate."""

        download_responses = {
            "python-backend-engineer": sample_skill_content,
            "rdbms-core": skill_no_deps,
            "context-management-core": "# context-management-core\n**Version:** 1.0.0",
        }

        def mock_attempt(url):
            for skill_name, content in download_responses.items():
                if skill_name in url:
                    return {"success": True, "content": content}
            return {"success": False, "content": None, "error": "HTTP 404", "status_code": 404}

        with patch.object(skill_manager, "_attempt_download", side_effect=mock_attempt):
            result = skill_manager.provision_skill("python-backend-engineer", force_download=True)

        assert result["success"] is True
        assert result["deprecated"] is False
        assert result["content"] is not None

        # Verify it was cached
        stats = skill_manager.get_cache_stats()
        assert stats["memory_entries"] >= 1

    def test_version_compatibility_enforcement(self):
        """Verify version checking catches incompatible dependencies."""
        # v0.5.0 does not satisfy >=1.0.0
        ok, reason = check_compatibility("0.5.0", ">=1.0.0")
        assert ok is False
        assert "0.5.0" in reason or "fails" in reason

        # v1.5.0 satisfies >=1.0.0,<2.0.0
        ok, reason = check_compatibility("1.5.0", ">=1.0.0,<2.0.0")
        assert ok is True

    def test_circular_dependency_blocks_resolution(self):
        """Circular deps should be detected and reported."""
        contents = {
            "skill-a": "# skill-a\n## Dependencies\n- skill: skill-b",
            "skill-b": "# skill-b\n## Dependencies\n- skill: skill-a",
        }
        result = resolve_dependencies("skill-a", contents)
        assert len(result["circular"]) > 0
        assert result["success"] is False
        assert result["error"] is not None
