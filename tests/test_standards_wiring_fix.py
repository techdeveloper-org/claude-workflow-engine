"""Unit tests for the FR-4 standards-system wiring fix.

The FR-4 standards system (select_standards() + LibrarySkillStandardsAdapter)
was fully implemented but never executed at runtime: select_standards() had
zero callers, so state["standards_selection"]/state["standards_merged_rules"]
were never populated, and the LIVE step10/step13 hooks in
langgraph_engine/standards/integration.py always fell back to their hardcoded
defaults.

Covers:
- step0_task_analysis_node PRE-INJECTION D: populates
  state["standards_selection"]/state["standards_merged_rules"] from a real
  project structure; fail-open on select_standards() exception (mirrors the
  existing CallGraph/KG-routing pre-injection pattern).
- apply_standards_at_step(10, state) / apply_standards_at_step(13, state):
  now produces a checklist/doc-requirements list that actually reflects
  library-sourced standards content when standards_selection is populated --
  proving the Step 0 -> Step 10/13 wiring is closed, not just that Step 0
  computes a value nobody reads.
- End-to-end: step0_task_analysis_node's own output, merged into state and
  fed into apply_standards_at_step(10, ...), produces a checklist item
  sourced from the injected standards_selection.
- LibrarySkillLanguageAdapter (P1, new language-tier adapter): real mapped
  language resolves real sibling content, unmapped language returns [],
  sibling-missing returns [] without raising.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langgraph_engine.library.resolver import _reset_library_root_cache  # noqa: E402
from langgraph_engine.standards.integration import apply_standards_at_step  # noqa: E402
from langgraph_engine.standards.library_adapter import (  # noqa: E402
    _LANGUAGE_SKILL_MAP,
    PRIORITY_LIBRARY_LANGUAGE_SKILL,
    LibrarySkillLanguageAdapter,
)

_REAL_LIBRARY_ROOT = _PROJECT_ROOT.parent / "claude-global-library"
_HAS_REAL_LIBRARY = _REAL_LIBRARY_ROOT.is_dir()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every test starts with a clean locate_library_root() memoization cache."""
    _reset_library_root_cache()
    yield
    _reset_library_root_cache()


def _mock_call_execution_script(captured_calls):
    def _side_effect(script_name, args=None, model_tier=None, timeout=None):
        captured_calls.append((script_name, args))
        if script_name == "prompt_gen_expert_caller":
            return {"status": "SUCCESS", "llm_response": "orchestration prompt body", "prompt": "raw"}
        if script_name == "todo_decomposer":
            return {"status": "SUCCESS", "todo_list": []}
        return {"status": "SUCCESS"}

    return _side_effect


# ===========================================================================
# step0_task_analysis_node PRE-INJECTION D -- populate + fail-open
# ===========================================================================


class TestStep0StandardsSelectionPreInjection:
    def test_populates_standards_selection_and_merged_rules(self):
        from langgraph_engine.level3_execution.nodes.step_wrappers_0to4 import step0_task_analysis_node

        captured_calls = []
        state = {
            "user_message": "Add a new endpoint",
            "project_root": str(_PROJECT_ROOT),
        }

        with patch(
            "langgraph_engine.level3_execution.helpers.call_execution_script",
            side_effect=_mock_call_execution_script(captured_calls),
        ):
            result = step0_task_analysis_node(state)

        assert "standards_selection" in result
        assert "standards_merged_rules" in result
        selection = result["standards_selection"]
        assert selection.get("project_type") == "python"
        assert isinstance(selection.get("standards_list"), list)
        assert result["standards_merged_rules"] == selection.get("merged_rules", {})
        # standards_count is a fallback -- absent from input state, so Step 0 sets it.
        assert result.get("standards_count") == selection.get("total_loaded", 0)

    def test_standards_count_not_clobbered_when_already_set(self):
        from langgraph_engine.level3_execution.nodes.step_wrappers_0to4 import step0_task_analysis_node

        captured_calls = []
        state = {
            "user_message": "Add a new endpoint",
            "project_root": str(_PROJECT_ROOT),
            "standards_count": 42,
        }

        with patch(
            "langgraph_engine.level3_execution.helpers.call_execution_script",
            side_effect=_mock_call_execution_script(captured_calls),
        ):
            result = step0_task_analysis_node(state)

        assert "standards_count" not in result

    def test_select_standards_exception_is_fail_open(self):
        """An exception raised inside select_standards() must not propagate out
        of step0_task_analysis_node -- PRE-INJECTION D mirrors the existing
        CallGraph/KG-routing pre-injection fail-open try/except pattern.
        """
        from langgraph_engine.level3_execution.nodes.step_wrappers_0to4 import step0_task_analysis_node

        captured_calls = []
        state = {"user_message": "anything", "project_root": str(_PROJECT_ROOT)}

        with (
            patch(
                "langgraph_engine.level3_execution.helpers.call_execution_script",
                side_effect=_mock_call_execution_script(captured_calls),
            ),
            patch(
                "langgraph_engine.standards.selector.select_standards",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = step0_task_analysis_node(state)

        assert result["standards_selection"] == {}
        assert result["standards_merged_rules"] == {}
        prompt_gen_calls = [c for c in captured_calls if c[0] == "prompt_gen_expert_caller"]
        assert len(prompt_gen_calls) == 1

    def test_select_standards_called_at_most_once(self):
        """No hot-loop re-invocation within a single Step 0 call."""
        from langgraph_engine.level3_execution.nodes.step_wrappers_0to4 import step0_task_analysis_node

        captured_calls = []
        state = {"user_message": "anything", "project_root": str(_PROJECT_ROOT)}

        with (
            patch(
                "langgraph_engine.level3_execution.helpers.call_execution_script",
                side_effect=_mock_call_execution_script(captured_calls),
            ),
            patch(
                "langgraph_engine.standards.selector.select_standards",
                return_value={
                    "project_type": "python",
                    "framework": "unknown",
                    "standards_list": [],
                    "merged_rules": {},
                    "total_loaded": 0,
                },
            ) as mock_select,
        ):
            step0_task_analysis_node(state)

        assert mock_select.call_count == 1


# ===========================================================================
# apply_standards_at_step(10/13, ...) -- prove the wiring loop is closed
# ===========================================================================


class TestStandardsHookReflectsSelection:
    _FAKE_SELECTION = {
        "project_type": "python",
        "framework": "fastapi",
        "standards_list": [
            {
                "id": "library_skill_fastapi",
                "source": "library_skill_standards",
                "file": "/fake/skills/fastapi-core/SKILL.md",
                "content": "FastAPI dependency-injection guidance goes here.",
                "priority": 1.5,
            }
        ],
        "merged_rules": {},
        "conflicts": [],
        "total_loaded": 1,
    }

    def test_step10_checklist_gains_library_item_when_selection_present(self):
        without = apply_standards_at_step(10, {"session_id": "wiring-test-step10-a"})
        with_selection = apply_standards_at_step(
            10,
            {
                "session_id": "wiring-test-step10-b",
                "standards_selection": self._FAKE_SELECTION,
                "standards_merged_rules": {},
            },
        )

        checklist_without = without["step10_standards_checklist"]["checklist"]
        checklist_with = with_selection["step10_standards_checklist"]["checklist"]

        ids_without = {c["check"] for c in checklist_without}
        ids_with = {c["check"] for c in checklist_with}

        assert "standards_source_library_skill_fastapi" not in ids_without
        assert "standards_source_library_skill_fastapi" in ids_with
        assert len(checklist_with) > len(checklist_without)

        lib_item = next(c for c in checklist_with if c["check"] == "standards_source_library_skill_fastapi")
        assert "library_skill_standards" in lib_item["description"]
        assert "library_skill_fastapi" in lib_item["description"]

    def test_step13_doc_requirements_gain_library_item_when_selection_present(self):
        without = apply_standards_at_step(13, {"session_id": "wiring-test-step13-a"})
        with_selection = apply_standards_at_step(
            13,
            {
                "session_id": "wiring-test-step13-b",
                "standards_selection": self._FAKE_SELECTION,
                "standards_merged_rules": {},
            },
        )

        reqs_without = without["step13_standards_doc_requirements"]["required_updates"]
        reqs_with = with_selection["step13_standards_doc_requirements"]["required_updates"]

        files_without = {r["file"] for r in reqs_without}
        files_with = {r["file"] for r in reqs_with}

        assert "/fake/skills/fastapi-core/SKILL.md" not in files_without
        assert "/fake/skills/fastapi-core/SKILL.md" in files_with
        assert len(reqs_with) > len(reqs_without)

    def test_doc_requirements_scoped_to_library_sources_only(self):
        """_build_selected_standards_doc_requirements is scoped to
        library_skill_standards/library_language_standards only -- a
        custom_standards entry should show up in the Step 10 checklist
        (all sources) but NOT get its own Step 13 doc-requirement row.
        """
        selection = {
            "project_type": "python",
            "framework": "unknown",
            "standards_list": [
                {
                    "id": "custom_naming",
                    "source": "custom_standards",
                    "file": "/fake/.claude/standards/naming.md",
                    "content": "naming rules",
                    "priority": 4,
                }
            ],
            "merged_rules": {},
            "conflicts": [],
            "total_loaded": 1,
        }

        step10_result = apply_standards_at_step(
            10, {"session_id": "wiring-test-custom-10", "standards_selection": selection}
        )
        step13_result = apply_standards_at_step(
            13, {"session_id": "wiring-test-custom-13", "standards_selection": selection}
        )

        checklist_ids = {c["check"] for c in step10_result["step10_standards_checklist"]["checklist"]}
        doc_files = {r["file"] for r in step13_result["step13_standards_doc_requirements"]["required_updates"]}

        assert "standards_source_custom_naming" in checklist_ids
        assert "/fake/.claude/standards/naming.md" not in doc_files


class TestStandardsWiringEndToEnd:
    def test_step0_output_flows_into_step10_checklist(self):
        """The full loop: step0_task_analysis_node's own returned
        standards_selection, merged into state exactly as the LangGraph
        orchestrator does (state.update(result)), must change apply_standards_
        at_step(10, ...)'s checklist output. This is the wiring-closed proof.
        """
        from langgraph_engine.level3_execution.nodes.step_wrappers_0to4 import step0_task_analysis_node

        captured_calls = []
        state = {
            "user_message": "Add a new endpoint",
            "project_root": str(_PROJECT_ROOT),
            "session_id": "wiring-test-e2e",
        }

        fake_selection = {
            "project_type": "python",
            "framework": "fastapi",
            "standards_list": [
                {
                    "id": "library_skill_fastapi",
                    "source": "library_skill_standards",
                    "file": "/fake/skills/fastapi-core/SKILL.md",
                    "content": "content",
                    "priority": 1.5,
                }
            ],
            "merged_rules": {},
            "conflicts": [],
            "total_loaded": 1,
        }

        with (
            patch(
                "langgraph_engine.level3_execution.helpers.call_execution_script",
                side_effect=_mock_call_execution_script(captured_calls),
            ),
            patch(
                "langgraph_engine.standards.selector.select_standards",
                return_value=fake_selection,
            ),
        ):
            step0_result = step0_task_analysis_node(state)

        # This is exactly what the LangGraph orchestrator does with a node's
        # return value: merge it into the running FlowState.
        state.update(step0_result)

        step10_result = apply_standards_at_step(10, state)
        checklist_ids = {c["check"] for c in step10_result["step10_standards_checklist"]["checklist"]}

        assert "standards_source_library_skill_fastapi" in checklist_ids


# ===========================================================================
# LibrarySkillLanguageAdapter.load() -- P1 new language-tier adapter
# ===========================================================================


class TestLibrarySkillLanguageAdapterUnmapped:
    def test_unmapped_language_returns_empty_with_zero_resolver_calls(self):
        adapter = LibrarySkillLanguageAdapter()
        with patch("langgraph_engine.standards.library_adapter.build_default_resolver") as mock_build:
            result = adapter.load("csharp")
        assert result == []
        mock_build.assert_not_called()

    def test_unknown_project_type_returns_empty(self):
        adapter = LibrarySkillLanguageAdapter()
        with patch("langgraph_engine.standards.library_adapter.build_default_resolver") as mock_build:
            result = adapter.load("unknown")
        assert result == []
        mock_build.assert_not_called()


class TestLibrarySkillLanguageAdapterSiblingMissing:
    def test_sibling_missing_returns_empty_without_raising(self):
        adapter = LibrarySkillLanguageAdapter()
        with patch("langgraph_engine.library.resolver.locate_library_root", return_value=None):
            result = adapter.load("python")
        assert result == []


@pytest.mark.skipif(not _HAS_REAL_LIBRARY, reason="sibling claude-global-library checkout not present")
class TestLibrarySkillLanguageAdapterRealSibling:
    def test_mapped_language_resolves_real_skill_content(self):
        adapter = LibrarySkillLanguageAdapter()
        result = adapter.load("python")

        assert len(result) == 1
        entry = result[0]
        assert entry["id"] == "library_language_python"
        assert entry["source"] == "library_language_standards"
        assert entry["priority"] == PRIORITY_LIBRARY_LANGUAGE_SKILL
        assert "python-core" in entry["file"] or "SKILL.md" in entry["file"]
        assert "Mathematical Foundations" not in entry["content"]

    def test_all_map_entries_resolve_without_raising(self):
        adapter = LibrarySkillLanguageAdapter()
        for project_type, skill_name in _LANGUAGE_SKILL_MAP.items():
            result = adapter.load(project_type)
            assert len(result) == 1, f"expected a hit for {project_type} -> {skill_name}"
            assert result[0]["content"], f"empty content for {skill_name}"
