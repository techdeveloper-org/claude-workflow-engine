"""Unit tests for langgraph_engine/standards/library_adapter.py -- the ADR-4
LibrarySkillStandardsAdapter (C12) and the selector.py priority-ordering fix
it depends on (int() truncation of priority=1.5 would silently collide with
PRIORITY_LANGUAGE=1).

Covers:
- A real mapped framework resolves and returns content from the real sibling
  skill file, with the Mathematical Foundations section stripped.
- An unmapped framework returns [] with zero resolver calls.
- Sibling-missing (locate_library_root -> None) returns [] without raising.
- selector.py's resolve_conflicts() priority order survives the 1.5 tier:
  framework(2) beats library_skill(1.5) beats language(1).
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langgraph_engine.library.resolver import _reset_library_root_cache  # noqa: E402
from langgraph_engine.standards.library_adapter import (  # noqa: E402
    _FRAMEWORK_SKILL_MAP,
    PRIORITY_LIBRARY_SKILL,
    LibrarySkillStandardsAdapter,
    _extract_standards_content,
)
from langgraph_engine.standards.selector import PRIORITY_FRAMEWORK, PRIORITY_LANGUAGE, resolve_conflicts  # noqa: E402

_REAL_LIBRARY_ROOT = _PROJECT_ROOT.parent / "claude-global-library"
_HAS_REAL_LIBRARY = _REAL_LIBRARY_ROOT.is_dir()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every test starts with a clean locate_library_root() memoization cache."""
    _reset_library_root_cache()
    yield
    _reset_library_root_cache()


# ---------------------------------------------------------------------------
# _extract_standards_content
# ---------------------------------------------------------------------------


class TestExtractStandardsContent:
    def test_strips_mathematical_foundations_section(self):
        raw = (
            "---\nname: foo\n---\n\n"
            "# Foo Skill\n\n"
            "## Mathematical Foundations\n"
            "some derivation content\nmore math\n\n"
            "## Foo Fundamentals\n"
            "applied guidance stays\n"
        )
        result = _extract_standards_content(raw)
        assert "Mathematical Foundations" not in result
        assert "some derivation content" not in result
        assert "## Foo Fundamentals" in result
        assert "applied guidance stays" in result

    def test_no_math_heading_returns_unchanged(self):
        raw = "---\nname: foo\n---\n\n## Foo Fundamentals\nno math section here\n"
        assert _extract_standards_content(raw) == raw


# ---------------------------------------------------------------------------
# LibrarySkillStandardsAdapter.load()
# ---------------------------------------------------------------------------


class TestLibrarySkillStandardsAdapterUnmapped:
    def test_unmapped_framework_returns_empty_with_zero_resolver_calls(self):
        adapter = LibrarySkillStandardsAdapter()
        with patch("langgraph_engine.standards.library_adapter.build_default_resolver") as mock_build:
            result = adapter.load("python", "definitely-not-a-mapped-framework")
        assert result == []
        mock_build.assert_not_called()

    def test_unknown_project_type_returns_empty(self):
        adapter = LibrarySkillStandardsAdapter()
        with patch("langgraph_engine.standards.library_adapter.build_default_resolver") as mock_build:
            result = adapter.load("unknown", "unknown")
        assert result == []
        mock_build.assert_not_called()


class TestLibrarySkillStandardsAdapterSiblingMissing:
    def test_sibling_missing_returns_empty_without_raising(self):
        adapter = LibrarySkillStandardsAdapter()
        with patch("langgraph_engine.library.resolver.locate_library_root", return_value=None):
            result = adapter.load("python", "fastapi")
        assert result == []


@pytest.mark.skipif(not _HAS_REAL_LIBRARY, reason="sibling claude-global-library checkout not present")
class TestLibrarySkillStandardsAdapterRealSibling:
    def test_mapped_framework_resolves_real_skill_content(self):
        adapter = LibrarySkillStandardsAdapter()
        result = adapter.load("python", "fastapi")

        assert len(result) == 1
        entry = result[0]
        assert entry["id"] == "library_skill_fastapi"
        assert entry["source"] == "library_skill_standards"
        assert entry["priority"] == PRIORITY_LIBRARY_SKILL
        assert "fastapi-core" in entry["file"] or "SKILL.md" in entry["file"]
        assert "Mathematical Foundations" not in entry["content"]
        assert "FastAPI" in entry["content"]

    def test_all_map_entries_resolve_without_raising(self):
        adapter = LibrarySkillStandardsAdapter()
        for (project_type, framework), skill_name in _FRAMEWORK_SKILL_MAP.items():
            result = adapter.load(project_type, framework)
            assert len(result) == 1, f"expected a hit for ({project_type}, {framework}) -> {skill_name}"
            assert result[0]["content"], f"empty content for {skill_name}"


# ---------------------------------------------------------------------------
# selector.py priority-ordering fix (int() -> float() truncation bug)
# ---------------------------------------------------------------------------


class TestPriorityOrderingSurvivesFractionalTier:
    def test_framework_beats_library_skill_beats_language(self):
        """The exact case int(1.5)==1 truncation would break: library_skill(1.5)
        must beat language(1) but still lose to framework(2).
        """
        standards = [
            {"id": "language_python", "priority": PRIORITY_LANGUAGE, "rules": {"quotes": "single"}},
            {"id": "library_skill_fastapi", "priority": PRIORITY_LIBRARY_SKILL, "rules": {"quotes": "double"}},
            {"id": "framework_fastapi", "priority": PRIORITY_FRAMEWORK, "rules": {"quotes": "backtick"}},
        ]
        merged = resolve_conflicts(standards)
        assert merged["quotes"] == "backtick"

    def test_library_skill_beats_language_alone(self):
        standards = [
            {"id": "language_python", "priority": PRIORITY_LANGUAGE, "rules": {"quotes": "single"}},
            {"id": "library_skill_fastapi", "priority": PRIORITY_LIBRARY_SKILL, "rules": {"quotes": "double"}},
        ]
        merged = resolve_conflicts(standards)
        assert merged["quotes"] == "double"
