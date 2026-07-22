"""Unit tests for quality_gate._evaluate_tests_exist_gate's file-name matching.

Covers the hyphen/underscore normalization fix: a hyphenated source file
stem (e.g. "sync-library.py") must match its real underscore-named test
file (e.g. "test_sync_library.py"), since Python test modules cannot
contain hyphens. Before the fix, every hyphenated source file with a real,
passing test was reported as missing one.
"""

from pathlib import Path

from langgraph_engine.level3_execution.quality_gate import _evaluate_tests_exist_gate

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


def test_hyphenated_source_file_matches_underscore_test_file():
    """scripts/tools/sync-library.py must match the real tests/test_sync_library.py."""
    gate = _evaluate_tests_exist_gate(
        _PROJECT_ROOT,
        {},
        {"require_tests_for_modified": True},
        ["scripts/tools/sync-library.py"],
    )
    assert gate["passed"] is True
    assert "scripts/tools/sync-library.py" in gate["modified_with_tests"]
    assert gate["modified_without_tests"] == []


def test_underscore_source_file_still_matches_underscore_test_file():
    """Regression guard: plain underscore stems (the common case) must keep working."""
    gate = _evaluate_tests_exist_gate(
        _PROJECT_ROOT,
        {},
        {"require_tests_for_modified": True},
        ["langgraph_engine/level3_execution/faithfulness_gate.py"],
    )
    assert gate["passed"] is True
    assert "langgraph_engine/level3_execution/faithfulness_gate.py" in gate["modified_with_tests"]


def test_genuinely_untested_file_still_reported_missing():
    """A source file with no real test file anywhere must still be flagged."""
    gate = _evaluate_tests_exist_gate(
        _PROJECT_ROOT,
        {},
        {"require_tests_for_modified": True},
        ["langgraph_engine/level3_execution/nonexistent_module_xyz123.py"],
    )
    assert gate["passed"] is False
    assert "langgraph_engine/level3_execution/nonexistent_module_xyz123.py" in gate["modified_without_tests"]


def test_require_tests_false_downgrades_to_warning_only():
    """When require_tests_for_modified=False, a missing test warns but does not block."""
    gate = _evaluate_tests_exist_gate(
        _PROJECT_ROOT,
        {},
        {"require_tests_for_modified": False},
        ["langgraph_engine/level3_execution/nonexistent_module_xyz123.py"],
    )
    assert gate["passed"] is True
    assert "langgraph_engine/level3_execution/nonexistent_module_xyz123.py" in gate["modified_without_tests"]
