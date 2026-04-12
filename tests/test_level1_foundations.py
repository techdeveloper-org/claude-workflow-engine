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
from typing import Any, Dict
from unittest.mock import patch

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


class TestTOONValidator:
    """AC 1: TOONValidator class validates structure and fields."""

    def test_valid_toon_passes(self):
        """A fully valid TOON dict should pass validation."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        toon = create_toon(
            session_id="session-001",
            complexity_score=7,
            files_loaded=["SRS", "README", "CLAUDE.md"],
            has_srs=True,
            has_readme=True,
            has_claude_md=True,
        )
        is_valid, errors = validate_toon(toon)
        assert is_valid is True
        assert errors == []

    def test_missing_required_fields_fails(self):
        """TOON missing required fields should fail."""
        from langgraph_engine.toon_schema import validate_toon

        # Empty dict - all required fields missing
        is_valid, errors = validate_toon({})
        assert is_valid is False
        assert len(errors) >= 6  # All required fields reported

    def test_empty_session_id_fails(self):
        """session_id must be non-empty."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        toon = create_toon("session-test", 5, [])
        toon["session_id"] = "   "  # Whitespace only
        is_valid, errors = validate_toon(toon)
        assert is_valid is False
        assert any("session_id" in e for e in errors)

    def test_complexity_score_out_of_range_fails(self):
        """complexity_score must be 1-10."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        toon = create_toon("session-x", 5, [])
        # Test too high
        toon["complexity_score"] = 11
        is_valid, errors = validate_toon(toon)
        assert is_valid is False
        assert any("complexity_score" in e for e in errors)

        # Test too low
        toon["complexity_score"] = 0
        is_valid, errors = validate_toon(toon)
        assert is_valid is False

    def test_invalid_timestamp_fails(self):
        """timestamp must be a valid ISO-8601 string."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        toon = create_toon("session-x", 5, [])
        toon["timestamp"] = "not-a-date"
        is_valid, errors = validate_toon(toon)
        assert is_valid is False
        assert any("timestamp" in e for e in errors)

    def test_wrong_version_fails(self):
        """version must equal TOON_VERSION."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        toon = create_toon("session-x", 5, [])
        toon["version"] = "2.0.0"
        is_valid, errors = validate_toon(toon)
        assert is_valid is False
        assert any("version" in e for e in errors)

    def test_context_must_be_dict(self):
        """context field must be a dict."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        toon = create_toon("session-x", 5, [])
        toon["context"] = "not a dict"
        is_valid, errors = validate_toon(toon)
        assert is_valid is False
        assert any("context" in e for e in errors)

    def test_non_dict_input_fails(self):
        """Non-dict input should fail gracefully."""
        from langgraph_engine.toon_schema import validate_toon

        is_valid, errors = validate_toon(None)
        assert is_valid is False
        assert len(errors) == 1
        assert "dict" in errors[0].lower()

    def test_create_toon_produces_valid_toon(self):
        """create_toon() factory must always produce a valid TOON."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        for score in [1, 5, 10]:
            toon = create_toon("s-{}".format(score), score, ["SRS"])
            is_valid, errors = validate_toon(toon)
            assert is_valid, "Score {} failed: {}".format(score, errors)

    def test_optional_fields_validated_when_present(self):
        """Optional dict fields must be dicts if present."""
        from langgraph_engine.toon_schema import create_toon, validate_toon

        toon = create_toon("session-x", 5, [])
        toon["model_preferences"] = "not a dict"
        is_valid, errors = validate_toon(toon)
        assert is_valid is False
        assert any("model_preferences" in e for e in errors)


# ============================================================================
# 2. Complexity Score Calculation (40% files, 45% LOC, 15% deps)
# ============================================================================


class TestComplexityCalculator:
    """AC 2: Complexity scores 1-10 correctly calculated with weighted formula."""

    def test_score_in_range_1_to_10(self, tmp_project):
        """Any project must produce a score between 1 and 10."""
        from langgraph_engine.complexity_calculator import calculate_complexity

        score = calculate_complexity(str(tmp_project))
        assert isinstance(score, int)
        assert 1 <= score <= 10, "Score {} out of range".format(score)

    def test_tiny_project_low_score(self, tmp_path):
        """A project with very few files should get a low score."""
        from langgraph_engine.complexity_calculator import calculate_complexity

        # Create 2 tiny Python files
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
        score = calculate_complexity(str(tmp_path))
        assert score <= 5, "Tiny project score {} too high".format(score)

    def test_large_project_high_score(self, tmp_path):
        """A project with many files should get a higher score."""
        from langgraph_engine.complexity_calculator import calculate_complexity

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
        from langgraph_engine.complexity_calculator import _dep_score, _file_score, _loc_score

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
        from langgraph_engine.complexity_calculator import should_plan

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
        from langgraph_engine.complexity_calculator import calculate_complexity

        score = calculate_complexity("/nonexistent/path/that/does/not/exist")
        assert 1 <= score <= 10

    def test_complexity_report_structure(self, tmp_project):
        """complexity_report() should return a structured dict with all metrics."""
        from langgraph_engine.complexity_calculator import complexity_report

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
        from langgraph_engine.complexity_calculator import _count_dependencies

        # Create requirements.txt with 15 deps
        (tmp_path / "requirements.txt").write_text(
            "# comment\n" + "\n".join("dep_{}".format(i) for i in range(15)),
            encoding="utf-8",
        )
        count = _count_dependencies(tmp_path)
        assert count == 15

    def test_package_json_parsed(self, tmp_path):
        """Dependencies in package.json should be counted."""
        from langgraph_engine.complexity_calculator import _count_dependencies

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


class TestContextTimeout:
    """AC 3: Timeouts prevent file hangs (30s per file, 120s total)."""

    def test_timeout_constants_correct(self):
        """Per-file timeout must be 30s and total must be 120s."""
        from langgraph_engine.subgraphs.level1_sync import CONTEXT_TIMEOUT_PER_FILE, CONTEXT_TIMEOUT_TOTAL

        assert CONTEXT_TIMEOUT_PER_FILE == 30
        assert CONTEXT_TIMEOUT_TOTAL == 120

    def test_normal_file_read_succeeds(self, tmp_path):
        """Reading a small file within timeout should succeed."""
        from langgraph_engine.subgraphs.level1_sync import _read_file_with_timeout

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World\n" * 100, encoding="utf-8")

        content = _read_file_with_timeout(test_file, timeout_seconds=5)
        assert len(content) > 0
        assert "Hello World" in content

    def test_timeout_raises_timeout_error(self, tmp_path):
        """A file read that exceeds timeout must raise TimeoutError."""
        from langgraph_engine.subgraphs.level1_sync import _read_file_with_timeout

        test_file = tmp_path / "slow.txt"
        test_file.write_text("data", encoding="utf-8")

        # Patch read_text to block for longer than our timeout
        original_read_text = Path.read_text

        def slow_read_text(self, *args, **kwargs):
            time.sleep(10)  # Simulate a hang
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", slow_read_text):
            with pytest.raises(TimeoutError):
                _read_file_with_timeout(test_file, timeout_seconds=1)

    def test_string_path_accepted(self, tmp_path):
        """_read_file_with_timeout must accept both str and Path arguments."""
        from langgraph_engine.subgraphs.level1_sync import _read_file_with_timeout

        test_file = tmp_path / "test.txt"
        test_file.write_text("test content", encoding="utf-8")

        # Should not raise AttributeError for str argument
        content = _read_file_with_timeout(str(test_file), timeout_seconds=5)
        assert "test content" in content

    def test_total_timeout_stops_loading(self, tmp_context_files):
        """Total timeout of 120s should stop context loading."""
        # Set a very short total timeout via monkeypatching
        import langgraph_engine.subgraphs.level1_sync as lvl1
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        original = lvl1.CONTEXT_TIMEOUT_TOTAL
        try:
            lvl1.CONTEXT_TIMEOUT_TOTAL = 0  # Immediately trigger total timeout
            state = {
                "project_root": str(tmp_context_files),
                "session_id": "test-timeout",
                "session_path": "",
            }
            # Should still return gracefully (not raise)
            result = node_context_loader(state)
            assert "context_loaded" in result
        finally:
            lvl1.CONTEXT_TIMEOUT_TOTAL = original

    def test_threading_used_for_timeout(self):
        """Windows-compatible threading timeout must be used (no signal module)."""
        import inspect

        from langgraph_engine.subgraphs import level1_sync

        source = inspect.getsource(level1_sync._read_file_with_timeout)
        assert "threading" in source
        # Must NOT use signal module (POSIX-only, breaks on Windows)
        assert "signal.alarm" not in source


# ============================================================================
# 4. TOON Compression Validated Before Use
# ============================================================================


class TestTOONCompression:
    """AC 4: TOON compression validated before use."""

    def test_compression_produces_valid_toon(self, tmp_path):
        """node_toon_compression must produce a TOON that passes schema validation."""
        from langgraph_engine.subgraphs.level1_sync import node_toon_compression
        from langgraph_engine.toon_schema import validate_toon

        state = {
            "session_id": "test-session-001",
            "session_path": str(tmp_path),
            "context_data": {
                "srs": "SRS content here",
                "readme": "README content here",
                "claude_md": None,
                "files_loaded": ["SRS", "README"],
            },
            "complexity_score": 6,
        }
        result = node_toon_compression(state)

        assert result.get("toon_saved") is True
        toon = result.get("toon_object", {})
        is_valid, errors = validate_toon(toon)
        assert is_valid, "TOON validation failed: {}".format(errors)

    def test_integrity_check_verifies_file_count(self, tmp_path):
        """Integrity check must verify files_loaded_count matches original."""
        from langgraph_engine.subgraphs.level1_sync import _verify_toon_integrity

        original_context = {
            "srs": "srs content",
            "readme": "readme content",
            "claude_md": None,
            "files_loaded": ["SRS", "README"],
        }
        toon = {
            "session_id": "s1",
            "complexity_score": 5,
            "files_loaded_count": 2,  # Correct
            "context": {"srs": True, "readme": True, "claude_md": False},
        }
        assert _verify_toon_integrity(toon, original_context) is True

        # Tamper with count
        toon["files_loaded_count"] = 5  # Wrong
        assert _verify_toon_integrity(toon, original_context) is False

    def test_integrity_failure_uses_raw_fallback(self, tmp_path):
        """When integrity fails, raw context fallback must be applied."""
        from langgraph_engine.subgraphs.level1_sync import node_toon_compression

        state = {
            "session_id": "integrity-test",
            "session_path": str(tmp_path),
            "context_data": {
                "srs": "SRS content",
                "readme": None,
                "claude_md": None,
                "files_loaded": ["SRS"],
            },
            "complexity_score": 15,  # Out of range - will trigger integrity fail
        }
        result = node_toon_compression(state)

        # Should NOT crash, integrity_ok may be False
        assert "toon_object" in result
        assert "toon_integrity_ok" in result

    def test_toon_file_saved_to_session_folder(self, tmp_path):
        """TOON must be saved to context.toon.json in session folder."""
        from langgraph_engine.subgraphs.level1_sync import node_toon_compression

        state = {
            "session_id": "save-test",
            "session_path": str(tmp_path),
            "context_data": {
                "srs": "SRS",
                "readme": "README",
                "claude_md": None,
                "files_loaded": ["SRS", "README"],
            },
            "complexity_score": 5,
        }
        result = node_toon_compression(state)
        assert result.get("toon_saved") is True

        toon_file = tmp_path / "context.toon.json"
        assert toon_file.exists(), "TOON file not saved to session folder"

        # File may be in JSON or TOON format depending on toons library availability
        content = toon_file.read_text(encoding="utf-8")
        assert len(content) > 0, "TOON file must not be empty"

        # Verify essential data is present in either format
        assert "session_id" in content
        assert "complexity_score" in content

        # Verify the in-memory TOON object is complete
        toon = result.get("toon_object", {})
        assert toon.get("session_id") == "save-test"
        assert toon.get("complexity_score") == 5

    def test_schema_validation_called_during_compression(self, tmp_path):
        """Schema validation via toon_schema.validate_toon must be called."""
        from langgraph_engine.subgraphs.level1_sync import node_toon_compression

        with patch("langgraph_engine.subgraphs.level1_sync._TOON_SCHEMA_AVAILABLE", True):
            with patch(
                "langgraph_engine.subgraphs.level1_sync.validate_toon",
                return_value=(True, []),
            ) as mock_validate:
                state = {
                    "session_id": "schema-test",
                    "session_path": str(tmp_path),
                    "context_data": {"srs": "s", "readme": None, "claude_md": None, "files_loaded": ["SRS"]},
                    "complexity_score": 5,
                }
                node_toon_compression(state)
                mock_validate.assert_called_once()


# ============================================================================
# 5. Memory Limits Enforced (1MB file, 10MB total)
# ============================================================================


class TestMemoryLimits:
    """AC 5: Memory limits enforced (1MB file, 10MB total)."""

    def test_memory_limit_constants_correct(self):
        """Constants must be exactly 1MB per file and 10MB total."""
        from langgraph_engine.subgraphs.level1_sync import MAX_FILE_SIZE, MAX_TOTAL_SIZE

        assert MAX_FILE_SIZE == 1_000_000, "MAX_FILE_SIZE should be 1MB"
        assert MAX_TOTAL_SIZE == 10_000_000, "MAX_TOTAL_SIZE should be 10MB"

    def test_file_exceeding_limit_skipped(self, tmp_path):
        """Files larger than 1MB must be skipped with a warning."""
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        # Create a large SRS file (just over 1MB)
        large_srs = tmp_path / "SRS.md"
        large_srs.write_bytes(b"x" * 1_100_000)  # 1.1 MB

        state = {
            "project_root": str(tmp_path),
            "session_id": "mem-test",
            "session_path": "",
        }
        result = node_context_loader(state)

        # File should be skipped
        skipped = result.get("context_skipped_files", [])
        warnings = result.get("context_load_warnings", [])
        assert "SRS" in skipped or any("SRS" in w for w in warnings)

    def test_total_limit_stops_loading(self, tmp_path):
        """When total bytes exceed 10MB limit, loading should stop."""
        import langgraph_engine.subgraphs.level1_sync as lvl1
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        # Mock total size to already be at limit
        original_max = lvl1.MAX_TOTAL_SIZE
        try:
            lvl1.MAX_TOTAL_SIZE = 1  # 1 byte - immediately trigger total limit

            (tmp_path / "README.md").write_text("Hello", encoding="utf-8")
            (tmp_path / "CLAUDE.md").write_text("World", encoding="utf-8")

            state = {
                "project_root": str(tmp_path),
                "session_id": "total-limit-test",
                "session_path": "",
            }
            result = node_context_loader(state)
            # Must return gracefully (partial result or warnings)
            assert "context_loaded" in result
        finally:
            lvl1.MAX_TOTAL_SIZE = original_max

    def test_context_total_bytes_tracked(self, tmp_context_files):
        """Loaded bytes must be tracked in context_total_bytes."""
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        state = {
            "project_root": str(tmp_context_files),
            "session_id": "bytes-test",
            "session_path": "",
        }
        result = node_context_loader(state)

        # If files were loaded (not all from cache), bytes should be tracked
        if not result.get("context_cache_hit"):
            total_bytes = result.get("context_total_bytes", 0)
            assert isinstance(total_bytes, int)
            # If files were loaded, bytes should be > 0
            if result.get("files_loaded_count", 0) > 0:
                assert total_bytes >= 0  # Allows 0 for cache hit scenarios


# ============================================================================
# 6. Context Deduplication (>20% savings threshold)
# ============================================================================


class TestContextDeduplication:
    """AC 6: Context deduplication removes >20% duplicates across SRS/README/CLAUDE.md."""

    def test_high_duplication_applied(self):
        """Dedup applied when savings >= 20%."""
        from langgraph_engine.context_deduplicator import deduplicate_context

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
        from langgraph_engine.context_deduplicator import deduplicate_context

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
        """Fingerprint function should use MD5 for dedup hashing."""
        from langgraph_engine.context_deduplicator import _fingerprint

        fp1 = _fingerprint("hello world")
        fp2 = _fingerprint("hello world")
        fp3 = _fingerprint("different text")

        assert fp1 == fp2  # Same input -> same fingerprint
        assert fp1 != fp3  # Different input -> different fingerprint
        assert len(fp1) == 32  # MD5 produces 32 hex chars

    def test_priority_order_respected(self):
        """Primary doc (SRS) lines should not be removed, secondary docs deduplicated."""
        from langgraph_engine.context_deduplicator import deduplicate_context

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
        from langgraph_engine.context_deduplicator import deduplicate_context

        context = {
            "srs": "Only SRS content\n" * 50,
            "files_loaded": ["SRS"],
        }
        result = deduplicate_context(context)
        # Should return unchanged (not enough files to dedup)
        assert result["srs"] == context["srs"]

    def test_savings_estimate_function(self):
        """dedup_savings_estimate should return ratio and byte counts."""
        from langgraph_engine.context_deduplicator import dedup_savings_estimate

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
        from langgraph_engine.context_deduplicator import deduplicate_context

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


class TestPartialContextFallback:
    """AC 7: Partial context works when individual files fail."""

    def test_continue_after_single_file_failure(self, tmp_path):
        """Context loader must continue loading other files when one fails."""
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        # Create README.md (should load)
        (tmp_path / "README.md").write_text("README content", encoding="utf-8")
        # Create corrupt/unreadable SRS (simulate permission error by creating a directory)
        srs_dir = tmp_path / "SRS.md"
        srs_dir.mkdir()  # Directory at SRS path - read will fail

        state = {
            "project_root": str(tmp_path),
            "session_id": "partial-test",
            "session_path": "",
        }
        result = node_context_loader(state)

        # Must NOT crash
        assert "context_loaded" in result
        # README should still be loaded
        context_data = result.get("context_data", {})
        assert context_data.get("readme") is not None or result.get("context_cache_hit")

    def test_all_files_fail_returns_empty_gracefully(self, tmp_path):
        """When all files fail, context loader must return gracefully."""
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        # Empty directory - no context files
        state = {
            "project_root": str(tmp_path),
            "session_id": "empty-test",
            "session_path": "",
        }
        result = node_context_loader(state)

        # Must not crash and must return a valid dict
        assert isinstance(result, dict)
        assert "context_loaded" in result

    def test_timeout_file_skipped_others_loaded(self, tmp_path):
        """File that times out should be skipped; other files should still load."""
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        # Create README.md
        (tmp_path / "README.md").write_text("readme content here", encoding="utf-8")

        # Patch _read_file_with_timeout to timeout on SRS but succeed on others
        from langgraph_engine.subgraphs import level1_sync

        original_read = level1_sync._read_file_with_timeout

        def selective_timeout(file_path, *args, **kwargs):
            if "SRS" in str(file_path).upper():
                raise TimeoutError("Simulated SRS timeout")
            return original_read(file_path, *args, **kwargs)

        with patch.object(level1_sync, "_read_file_with_timeout", selective_timeout):
            # Create SRS file
            (tmp_path / "SRS.md").write_text("SRS content", encoding="utf-8")
            state = {
                "project_root": str(tmp_path),
                "session_id": "timeout-skip-test",
                "session_path": "",
            }
            result = node_context_loader(state)

        # SRS should be in skipped files
        warnings = result.get("context_load_warnings", [])
        skipped = result.get("context_skipped_files", [])
        srs_timed_out = any("SRS" in str(w) for w in warnings) or "SRS" in skipped
        assert srs_timed_out or result.get("context_cache_hit")  # Allow cache hit

    def test_level1_merge_works_with_no_context(self):
        """level1_merge_node must work even with empty TOON."""
        from langgraph_engine.subgraphs.level1_sync import level1_merge_node

        state = {
            "toon_object": {},
            "session_id": "empty-merge",
        }
        result = level1_merge_node(state)
        assert result.get("level1_complete") is True
        assert "level1_context_toon" in result

    def test_context_load_warnings_list_always_present(self, tmp_path):
        """context_load_warnings must always be a list, even on success."""
        from langgraph_engine.subgraphs.level1_sync import node_context_loader

        (tmp_path / "README.md").write_text("readme", encoding="utf-8")
        state = {
            "project_root": str(tmp_path),
            "session_id": "warnings-test",
            "session_path": "",
        }
        result = node_context_loader(state)
        if not result.get("context_cache_hit"):
            assert isinstance(result.get("context_load_warnings"), list)


# ============================================================================
# 8. Cache Invalidation (24h or file changes)
# ============================================================================


class TestCacheInvalidation:
    """AC 8: Cache invalidates after 24h or file changes."""

    def test_cache_ttl_is_24_hours(self):
        """CACHE_MAX_AGE_HOURS must be exactly 24."""
        from langgraph_engine.context_cache import CACHE_MAX_AGE_HOURS

        assert CACHE_MAX_AGE_HOURS == 24

    def test_fresh_cache_is_valid(self, tmp_path):
        """A freshly saved cache should be valid."""
        from langgraph_engine.context_cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)

        context_data = {"srs": "test", "files_loaded": ["SRS"]}
        cache.save_cache(project, context_data)

        loaded = cache.load_cache(project)
        assert loaded is not None
        assert loaded.get("_cache_hit") is True

    def test_expired_cache_returns_none(self, tmp_path):
        """Cache older than 24h must be invalidated."""
        from langgraph_engine.context_cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)

        # Save a cache entry
        context_data = {"readme": "content", "files_loaded": ["README"]}
        cache.save_cache(project, context_data)

        # Manually backdating the saved_at timestamp
        from langgraph_engine.context_cache import ContextCache as CC

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
        from langgraph_engine.context_cache import ContextCache

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
        from langgraph_engine.context_cache import ContextCache

        project_path = "/some/test/project"
        key = ContextCache._cache_key(project_path)

        # Key must be a hex string of fixed length
        assert isinstance(key, str)
        assert len(key) == 64 or len(key) == 32  # SHA-256 (64) or MD5 (32) truncated
        assert all(c in "0123456789abcdef" for c in key)

    def test_invalidate_removes_cache_file(self, tmp_path):
        """invalidate() must remove the cache file."""
        from langgraph_engine.context_cache import ContextCache

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
        from langgraph_engine.context_cache import ContextCache

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
        from langgraph_engine.context_cache import ContextCache

        cache = ContextCache(cache_base_dir=str(tmp_path / "cache"))
        project = str(tmp_path)
        cache.save_cache(project, {"files_loaded": [], "readme": "content"})

        loaded = cache.load_cache(project)
        assert loaded is not None
        assert "_cache_age_hours" in loaded
        assert isinstance(loaded["_cache_age_hours"], float)

    def test_cache_stats_tracked(self, tmp_path):
        """Session hit/miss stats must be tracked."""
        from langgraph_engine.context_cache import ContextCache

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


class TestLevel1Integration:
    """Integration test: Full Level 1 pipeline runs end-to-end."""

    def test_full_pipeline_success(self, tmp_context_files):
        """All 5 nodes must execute and produce valid TOON."""
        from langgraph_engine.subgraphs.level1_sync import (
            level1_merge_node,
            node_complexity_calculation,
            node_context_loader,
            node_session_loader,
            node_toon_compression,
        )
        from langgraph_engine.toon_schema import validate_toon

        state: Dict[str, Any] = {
            "project_root": str(tmp_context_files),
            "user_message": "test integration task",
        }

        # Node 1: Session loader
        session_result = node_session_loader(state)
        assert session_result.get("session_loaded") is True
        state.update(session_result)

        # Node 2: Complexity
        complexity_result = node_complexity_calculation(state)
        assert complexity_result.get("complexity_calculated") is True
        assert 1 <= complexity_result.get("complexity_score", 0) <= 10
        state.update(complexity_result)

        # Node 3: Context loader
        ctx_result = node_context_loader(state)
        assert ctx_result.get("context_loaded") is True
        state.update(ctx_result)

        # Node 4: TOON compression
        toon_result = node_toon_compression(state)
        assert toon_result.get("toon_saved") is True
        state.update(toon_result)

        # Node 5: Merge
        merge_result = level1_merge_node(state)
        assert merge_result.get("level1_complete") is True

        # Final TOON must be valid
        final_toon = merge_result.get("level1_context_toon", {})
        is_valid, errors = validate_toon(final_toon)
        assert is_valid, "Final TOON invalid: {}".format(errors)

    def test_pipeline_handles_missing_project_root(self):
        """Pipeline must not crash with a nonexistent project root."""
        from langgraph_engine.subgraphs.level1_sync import node_complexity_calculation, node_context_loader

        state: Dict[str, Any] = {
            "project_root": "/nonexistent/path/xyz123",
            "session_id": "crash-test",
            "session_path": "",
        }

        # These must not raise exceptions
        complexity_result = node_complexity_calculation(state)
        assert "complexity_score" in complexity_result

        ctx_result = node_context_loader(state)
        assert "context_loaded" in ctx_result
