"""
Level 1 Foundations - Comprehensive Test Suite
Covers all 8 acceptance criteria for Task #2.

AC Summary:
 1. TOONValidator validates structure and fields
 2. Complexity scores 1-10 correctly (40% files, 45% LOC, 15% deps)
 3. Timeouts prevent file hangs (30s per file, 120s total)
 4. TOON compression validated before use
 5. Memory limits enforced (1MB file, 10MB total)
 6. Context deduplication removes >20% duplicates
 7. Partial context works when individual files fail
 8. Cache invalidates after 24h or file changes
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Add project root and scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ============================================================================
# FIXTURE HELPERS
# ============================================================================


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal temp project directory with Python files."""
    # Create some Python files
    for i in range(5):
        (tmp_path / "module_{}.py".format(i)).write_text(
            "# Module {}\n".format(i) + "x = {}\n".format(i) * 50,
            encoding="utf-8",
        )
    # Create requirements.txt with 5 deps
    (tmp_path / "requirements.txt").write_text(
        "flask\nrequests\nsqlalchemy\npytest\nloguru\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def tmp_context_files(tmp_path):
    """Create SRS, README, CLAUDE.md in temp dir."""
    srs_text = "# SRS\nThis is the requirements document.\n" + "Common requirement line\n" * 10
    readme_text = "# README\nThis is the readme.\n" + "Common requirement line\n" * 10
    claude_text = "# CLAUDE.md\nThis is claude context.\nUnique content here.\n"

    (tmp_path / "SRS.md").write_text(srs_text, encoding="utf-8")
    (tmp_path / "README.md").write_text(readme_text, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(claude_text, encoding="utf-8")
    return tmp_path


# ============================================================================
# 1. TOONValidator - Validates structure and fields
# ============================================================================


# NOTE: TestTOONValidator removed in v1.15.2 (TOON/subgraphs purge).
# See GitHub issue #200 for the purge history.


class TestComplexityCalculator:
    """AC 2: Complexity scores 1-10 correctly calculated with weighted formula."""

    def test_score_in_range_1_to_10(self, tmp_project):
        """Any project must produce a score between 1 and 10."""
        from langgraph_engine.analysis.complexity_calculator import calculate_complexity

        score = calculate_complexity(str(tmp_project))
        assert isinstance(score, int)
        assert 1 <= score <= 10, "Score {} out of range".format(score)

    def test_tiny_project_low_score(self, tmp_path):
        """A project with very few files should get a low score."""
        from langgraph_engine.analysis.complexity_calculator import calculate_complexity

        # Create 2 tiny Python files
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
        score = calculate_complexity(str(tmp_path))
        assert score <= 5, "Tiny project score {} too high".format(score)

    def test_large_project_high_score(self, tmp_path):
        """A project with many files should get a higher score."""
        from langgraph_engine.analysis.complexity_calculator import calculate_complexity

        # Create 150 Python files each with 50 LOC
        for i in range(150):
            code = "\n".join("x_{} = {}".format(j, j) for j in range(50))
            (tmp_path / "mod_{}.py".format(i)).write_text(code, encoding="utf-8")
        # Add 40 deps
        deps = "\n".join("dep_{}".format(i) for i in range(40))
        (tmp_path / "requirements.txt").write_text(deps, encoding="utf-8")
        score = calculate_complexity(str(tmp_path))
        assert score >= 8, "Large project score {} too low".format(score)

    def test_weighted_formula_correct(self):
        """Verify weighted formula: 40% file_score + 45% loc_score + 15% dep_score."""
        from langgraph_engine.analysis.complexity_calculator import _dep_score, _file_score, _loc_score

        # Test some known values
        # < 5 files -> file_score = 2
        assert _file_score(3) == 2
        # 5-19 files -> file_score = 4
        assert _file_score(10) == 4
        # 20-99 files -> file_score = 6
        assert _file_score(50) == 6
        # >= 100 files -> file_score = 9
        assert _file_score(100) == 9

        # < 500 LOC -> loc_score = 2
        assert _loc_score(100) == 2
        # 500-1999 LOC -> loc_score = 4
        assert _loc_score(1000) == 4
        # 2000-4999 LOC -> loc_score = 6
        assert _loc_score(3000) == 6
        # >= 5000 LOC -> loc_score = 9
        assert _loc_score(5000) == 9

        # 0 deps -> dep_score = 1
        assert _dep_score(0) == 1
        # 1-9 deps -> dep_score = 4
        assert _dep_score(5) == 4
        # 10-29 deps -> dep_score = 6
        assert _dep_score(15) == 6
        # >= 30 deps -> dep_score = 9
        assert _dep_score(30) == 9

    def test_should_plan_rules(self):
        """Verify planning threshold rules by task type."""
        from langgraph_engine.analysis.complexity_calculator import should_plan

        # Refactoring always requires planning
        assert should_plan(1, "refactoring") is True
        assert should_plan(3, "refactoring") is True

        # Bug fix requires planning at complexity >= 4
        assert should_plan(3, "bug_fix") is False
        assert should_plan(4, "bug_fix") is True

        # General: planning at complexity >= 6
        assert should_plan(5, "general") is False
        assert should_plan(6, "general") is True

    def test_nonexistent_path_returns_default(self):
        """Non-existent project path should return a safe default."""
        from langgraph_engine.analysis.complexity_calculator import calculate_complexity

        score = calculate_complexity("/nonexistent/path/that/does/not/exist")
        assert 1 <= score <= 10

    def test_complexity_report_structure(self, tmp_project):
        """complexity_report() should return a structured dict with all metrics."""
        from langgraph_engine.analysis.complexity_calculator import complexity_report

        report = complexity_report(str(tmp_project))
        assert "complexity_score" in report
        assert "py_file_count" in report
        assert "lines_of_code" in report
        assert "dependency_count" in report
        assert "file_score" in report
        assert "loc_score" in report
        assert "dep_score" in report
        assert 1 <= report["complexity_score"] <= 10

    def test_requirements_txt_parsed(self, tmp_path):
        """Dependencies in requirements.txt should be counted."""
        from langgraph_engine.analysis.complexity_calculator import _count_dependencies

        # Create requirements.txt with 15 deps
        (tmp_path / "requirements.txt").write_text(
            "# comment\n" + "\n".join("dep_{}".format(i) for i in range(15)),
            encoding="utf-8",
        )
        count = _count_dependencies(tmp_path)
        assert count == 15

    def test_package_json_parsed(self, tmp_path):
        """Dependencies in package.json should be counted."""
        from langgraph_engine.analysis.complexity_calculator import _count_dependencies

        pkg_data = {
            "dependencies": {"react": "^18", "axios": "^1"},
            "devDependencies": {"jest": "^29"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg_data), encoding="utf-8")
        count = _count_dependencies(tmp_path)
        assert count == 3


# ============================================================================
# 3. Timeouts Prevent File Hangs
# ============================================================================


# NOTE: TestContextTimeout removed in v1.15.2 (TOON/subgraphs purge).
# See GitHub issue #200 for the purge history.

# NOTE: TestTOONCompression removed in v1.15.2 (TOON/subgraphs purge).
# See GitHub issue #200 for the purge history.

# NOTE: TestMemoryLimits removed in v1.15.2 (TOON/subgraphs purge).
# See GitHub issue #200 for the purge history.


class TestContextDeduplication:
    """AC 6: Context deduplication removes >20% duplicates across SRS/README/CLAUDE.md."""

    def test_high_duplication_applied(self):
        """Dedup applied when savings >= 20%."""
        from langgraph_engine.context.deduplicator import deduplicate_context

        dup_line = "This line appears in both documents\n"
        context = {
            "srs": dup_line * 30 + "SRS unique content\n",
            "readme": dup_line * 30 + "README unique content\n",
            "files_loaded": ["SRS", "README"],
        }
        result = deduplicate_context(context)
        assert result.get("_dedup_applied") is True
        assert result["_dedup_savings_ratio"] >= 0.20

    def test_low_duplication_skipped(self):
        """Dedup NOT applied when savings < 20%."""
        from langgraph_engine.context.deduplicator import deduplicate_context

        # Generate truly unique lines per file - no line in SRS appears in README
        srs_lines = (
            "\n".join("SRS requirement number {} with unique token alpha{}beta".format(i, i * 7) for i in range(50))
            + "\n"
        )
        readme_lines = (
            "\n".join(
                "README instruction section {} with unique token gamma{}delta".format(j, j * 11) for j in range(50)
            )
            + "\n"
        )

        context = {
            "srs": srs_lines,
            "readme": readme_lines,
            "files_loaded": ["SRS", "README"],
        }
        result = deduplicate_context(context)
        # Savings should be 0% since no lines are shared
        assert result.get("_dedup_applied") is False
        assert result.get("_dedup_savings_ratio", 1.0) < 0.20

    def test_fingerprint_dedup_uses_md5(self):
        """Fingerprint function should use MD5 for dedup hashing.

        _fingerprint is a private helper inside the real implementation at
        langgraph_engine.level1_sync.context_deduplicator. The compat shim
        at langgraph_engine.context_deduplicator only re-exports the public
        'deduplicate_context' function.
        """
        from langgraph_engine.level1_sync.context_deduplicator import _fingerprint

        fp1 = _fingerprint("hello world")
        fp2 = _fingerprint("hello world")
        fp3 = _fingerprint("different text")

        assert fp1 == fp2  # Same input -> same fingerprint
        assert fp1 != fp3  # Different input -> different fingerprint
        assert len(fp1) == 32  # MD5 produces 32 hex chars

    def test_priority_order_respected(self):
        """Primary doc (SRS) lines should not be removed, secondary docs deduplicated."""
        from langgraph_engine.context.deduplicator import deduplicate_context

        dup = "shared content line\n"
        context = {
            "srs": dup * 20 + "SRS unique\n",
            "readme": dup * 20 + "README unique\n",
            "files_loaded": ["SRS", "README"],
        }
        result = deduplicate_context(context)

        if result.get("_dedup_applied"):
            # SRS should retain its dup lines (it's primary)
            assert "shared content line" in result["srs"]
            # README should have dup lines removed
            readme_dup_count = result["readme"].count("shared content line")
            assert readme_dup_count < 20  # Should be reduced

    def test_single_file_not_deduped(self):
        """Dedup requires at least 2 files."""
        from langgraph_engine.context.deduplicator import deduplicate_context

        context = {
            "srs": "Only SRS content\n" * 50,
            "files_loaded": ["SRS"],
        }
        result = deduplicate_context(context)
        # Should return unchanged (not enough files to dedup)
        assert result["srs"] == context["srs"]

    def test_savings_estimate_function(self):
        """dedup_savings_estimate should return ratio and byte counts."""
        from langgraph_engine.context.deduplicator import dedup_savings_estimate

        dup = "duplicate line\n"
        context = {
            "srs": dup * 20 + "unique srs\n",
            "readme": dup * 20 + "unique readme\n",
        }
        ratio, original, new = dedup_savings_estimate(context)
        assert 0.0 <= ratio <= 1.0
        assert original > 0
        assert new <= original

    def test_dedup_metadata_always_present(self):
        """Dedup metadata fields should be in result even when not applied."""
        from langgraph_engine.context.deduplicator import deduplicate_context

        context = {
            "srs": "unique srs content\n",
            "readme": "unique readme content\n",
            "files_loaded": ["SRS", "README"],
        }
        result = deduplicate_context(context)
        assert "_dedup_applied" in result
        assert "_dedup_savings_ratio" in result
        assert "_dedup_original_bytes" in result
        assert "_dedup_new_bytes" in result


# ============================================================================
# 7. Partial Context Works When Individual Files Fail
# ============================================================================


# NOTE: TestPartialContextFallback removed in v1.15.2 (TOON/subgraphs purge).
# See GitHub issue #200 for the purge history.


class TestCacheInvalidation:
    """AC 8: Cache invalidates after 24h or file changes."""

    def test_cache_ttl_is_24_hours(self):
        """CACHE_MAX_AGE_HOURS must be exactly 24."""
        from langgraph_engine.context.cache import CACHE_MAX_AGE_HOURS

        assert CACHE_MAX_AGE_HOURS == 24

    def test_fresh_cache_is_valid(self, tmp_path):
        """A freshly saved cache should be valid."""
        from langgraph_engine.context.cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)

        context_data = {"srs": "test", "files_loaded": ["SRS"]}
        cache.save_cache(project, context_data)

        loaded = cache.load_cache(project)
        assert loaded is not None
        assert loaded.get("_cache_hit") is True

    def test_expired_cache_returns_none(self, tmp_path):
        """Cache older than 24h must be invalidated."""
        from langgraph_engine.context.cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)

        # Save a cache entry
        context_data = {"readme": "content", "files_loaded": ["README"]}
        cache.save_cache(project, context_data)

        # Manually backdating the saved_at timestamp
        from langgraph_engine.context.cache import ContextCache as CC

        key = CC._cache_key(project)
        cache_file = tmp_path / "cache" / (key + ".json")
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        entry["saved_at"] = old_time
        cache_file.write_text(json.dumps(entry), encoding="utf-8")

        # Should return None (expired)
        loaded = cache.load_cache(project)
        assert loaded is None

    def test_file_change_invalidates_cache(self, tmp_path):
        """Changing a tracked file must invalidate the cache."""
        from langgraph_engine.context.cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))

        # Create a README.md and save cache
        readme = tmp_path / "README.md"
        readme.write_text("original content", encoding="utf-8")
        context_data = {"readme": "original content", "files_loaded": ["README"]}
        cache.save_cache(str(tmp_path), context_data)

        # Verify cache is valid
        loaded = cache.load_cache(str(tmp_path))
        assert loaded is not None

        # Modify README.md
        time.sleep(0.01)  # Ensure mtime changes
        readme.write_text("modified content - new version", encoding="utf-8")

        # Cache must be invalidated now
        loaded_after = cache.load_cache(str(tmp_path))
        assert loaded_after is None

    def test_cache_key_is_md5_of_path(self):
        """Cache key must be derived from project path hash."""
        from langgraph_engine.context.cache import ContextCache

        project_path = "/some/test/project"
        key = ContextCache._cache_key(project_path)

        # Key must be a hex string of fixed length
        assert isinstance(key, str)
        assert len(key) == 64 or len(key) == 32  # SHA-256 (64) or MD5 (32) truncated
        assert all(c in "0123456789abcdef" for c in key)

    def test_invalidate_removes_cache_file(self, tmp_path):
        """invalidate() must remove the cache file."""
        from langgraph_engine.context.cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)

        context_data = {"claude_md": "content", "files_loaded": ["CLAUDE.md"]}
        cache.save_cache(project, context_data)

        # Verify it exists
        assert cache.load_cache(project) is not None

        # Invalidate
        result = cache.invalidate(project)
        assert result is True

        # Should be gone now
        assert cache.load_cache(project) is None

    def test_cache_info_returns_metadata(self, tmp_path):
        """cache_info() must return metadata about the cache entry."""
        from langgraph_engine.context.cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)

        # No cache yet
        info = cache.cache_info(project)
        assert info["exists"] is False

        # After saving
        cache.save_cache(project, {"files_loaded": []})
        info = cache.cache_info(project)
        assert info["exists"] is True
        assert "age_hours" in info
        assert "valid" in info
        assert info["age_hours"] < 1.0  # Just saved

    def test_cache_hit_returns_age_metadata(self, tmp_path):
        """Cache hit must include _cache_age_hours in returned context."""
        from langgraph_engine.context.cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)
        cache.save_cache(project, {"files_loaded": [], "readme": "content"})

        loaded = cache.load_cache(project)
        assert loaded is not None
        assert "_cache_age_hours" in loaded
        assert isinstance(loaded["_cache_age_hours"], float)

    def test_cache_stats_tracked(self, tmp_path):
        """Session hit/miss stats must be tracked."""
        from langgraph_engine.context.cache import ContextCache

        ContextCache.reset_session_stats()
        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)

        # Miss
        cache.load_cache(project)
        stats = ContextCache.get_session_stats()
        assert stats["misses"] >= 1

        # Hit
        cache.save_cache(project, {"files_loaded": []})
        cache.load_cache(project)
        stats = ContextCache.get_session_stats()
        assert stats["hits"] >= 1


# ============================================================================
# INTEGRATION: Full Level 1 Pipeline
# ============================================================================


# NOTE: TestLevel1Integration removed in v1.15.2 (TOON/subgraphs purge).
# See GitHub issue #200 for the purge history.
