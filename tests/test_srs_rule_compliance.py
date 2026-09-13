"""Tests that the SRS implementation follows rules/11 and rules/44 (issue #252).

Both rules mandate the same numbered structure, and rules/11 states its checks
"block commit at pre-tool gate". The implementation used to emit and consume a
different shape entirely -- `## Functional Requirements` / `### FR-N` -- so zero of
the eight required sections existed in the document, and `documentation_manager`
located its insertion point by the heading the generator produced rather than the
one the rule specifies.

Windows-safe: ASCII only, no Unicode characters.
"""

import importlib.util as ilu
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "langgraph_engine" / "sdlc_pipeline" / "documentation_generator.py"
MANAGER = REPO_ROOT / "langgraph_engine" / "sdlc_pipeline" / "documentation_manager.py"
RULES_DIR = Path.home() / ".claude" / "rules"

REQUIRED_SECTIONS = [
    "## 1. Purpose",
    "## 2. Scope",
    "## 3. Requirements",
    "### 3.1 Functional Requirements",
    "### 3.2 Non-Functional Requirements",
    "## 4. Acceptance Criteria",
    "## 5. Out of Scope",
    "## 6. Change Log",
]


def _load(path, name):
    """Load a module by file path.

    Args:
        path: Module file.
        name: Name to register it under.

    Returns:
        module: The loaded module.
    """
    spec = ilu.spec_from_file_location(name, str(path))
    module = ilu.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _headings(text):
    """Return the document's heading lines, stripped.

    Args:
        text: Markdown text.

    Returns:
        list[str]: Heading lines.
    """
    return [line.strip() for line in text.splitlines() if line.strip().startswith("#")]


class TestRepositorySrs:
    """This repo's own SRS.md must satisfy the rules it ships."""

    def test_all_required_sections_present(self):
        headings = _headings((REPO_ROOT / "SRS.md").read_text(encoding="utf-8"))
        missing = [s for s in REQUIRED_SECTIONS if s not in headings]
        assert missing == [], "missing sections: {}".format(missing)

    def test_rule_11_section_7_check_passes(self):
        """rules/11 section 7 greps for four numbered headings and all must match."""
        text = (REPO_ROOT / "SRS.md").read_text(encoding="utf-8")
        pattern = re.compile(r"(?m)^## (1\. Purpose|2\. Scope|3\. Requirements|4\. Acceptance Criteria)")
        assert len(pattern.findall(text)) == 4

    def test_existing_requirements_were_not_lost_in_the_restructure(self):
        text = (REPO_ROOT / "SRS.md").read_text(encoding="utf-8")
        for number in range(1, 10):
            assert "FR-{}".format(number) in text, "FR-{} disappeared".format(number)


class TestGeneratedSrs:
    """A freshly generated project must comply from birth."""

    @pytest.fixture
    def generated(self, tmp_path):
        """Generate documentation for a throwaway project.

        Yields:
            Path: The generated project root.
        """
        generator = _load(GENERATOR, "dg_under_test")
        project = tmp_path / "proj"
        project.mkdir()
        (project / "app.py").write_text("x = 1\n", encoding="utf-8")
        (project / "VERSION").write_text("0.1.0\n", encoding="utf-8")
        generator.DocumentationGenerator(project_root=str(project)).update_all_documentation()
        yield project

    def test_srs_is_created_at_the_project_root(self, generated):
        assert (generated / "SRS.md").is_file()

    def test_no_srs_is_created_under_docs(self, generated):
        assert not (generated / "docs" / "SYSTEM_REQUIREMENTS_SPECIFICATION.md").exists()

    def test_generated_srs_has_every_required_section(self, generated):
        headings = _headings((generated / "SRS.md").read_text(encoding="utf-8"))
        missing = [s for s in REQUIRED_SECTIONS if s not in headings]
        assert missing == [], "missing sections: {}".format(missing)


class TestManagerAppend:
    """rules/44 section 4: append-only, numbered FR, plus a Change Log row."""

    @pytest.fixture
    def project(self, tmp_path):
        """Copy this repo's SRS into a throwaway project.

        Yields:
            tuple: (manager instance, path to the copied SRS).
        """
        manager_module = _load(MANAGER, "dm_under_test")
        root = tmp_path / "proj"
        root.mkdir()
        shutil.copy(REPO_ROOT / "SRS.md", root / "SRS.md")
        (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        yield manager_module.Level3DocumentationManager(project_root=str(root)), root / "SRS.md"

    def test_entry_is_numbered_rather_than_the_literal_fr_new(self, project):
        manager, srs = project
        manager._update_srs(srs, {"user_message": "do a thing"}, "2026-07-30")
        text = srs.read_text(encoding="utf-8")
        assert "FR-NEW" not in text
        assert "**FR-10:**" in text, "expected the next number after the existing FR-1..FR-9"

    def test_entry_lands_inside_functional_requirements(self, project):
        manager, srs = project
        manager._update_srs(srs, {"user_message": "do a thing"}, "2026-07-30")
        text = srs.read_text(encoding="utf-8")
        assert text.find("**FR-10:**") < text.find("### 3.2 Non-Functional Requirements")
        assert text.find("### 3.1 Functional Requirements") < text.find("**FR-10:**")

    def test_a_change_log_row_is_appended(self, project):
        manager, srs = project
        before = srs.read_text(encoding="utf-8").count("| 2026-")
        manager._update_srs(srs, {"user_message": "do a thing", "task_title": "a task"}, "2026-07-30")
        after = srs.read_text(encoding="utf-8").count("| 2026-")
        assert after == before + 1

    def test_numbers_keep_incrementing_across_runs(self, project):
        manager, srs = project
        manager._update_srs(srs, {"user_message": "first"}, "2026-07-30")
        manager._update_srs(srs, {"user_message": "second"}, "2026-07-30")
        text = srs.read_text(encoding="utf-8")
        assert "**FR-10:**" in text and "**FR-11:**" in text

    def test_required_sections_survive_an_append(self, project):
        manager, srs = project
        manager._update_srs(srs, {"user_message": "do a thing"}, "2026-07-30")
        headings = _headings(srs.read_text(encoding="utf-8"))
        missing = [s for s in REQUIRED_SECTIONS if s not in headings]
        assert missing == []

    def test_a_pre_numbering_document_is_still_located(self, tmp_path):
        """Documents written before the numbering was adopted must still work."""
        manager_module = _load(MANAGER, "dm_legacy_test")
        root = tmp_path / "legacy"
        root.mkdir()
        legacy = root / "SRS.md"
        legacy.write_text(
            "# SRS\n\n## Functional Requirements\n\n### FR-1: Thing\n\n"
            "## Non-Functional Requirements\n\n### NFR-1: Speed\n",
            encoding="utf-8",
        )
        manager = manager_module.Level3DocumentationManager(project_root=str(root))
        manager._update_srs(legacy, {"user_message": "legacy append"}, "2026-07-30")
        text = legacy.read_text(encoding="utf-8")
        assert "**FR-2:**" in text
        assert text.find("**FR-2:**") < text.find("## Non-Functional Requirements")


@pytest.mark.skipif(not RULES_DIR.is_dir(), reason="rules not installed at ~/.claude/rules")
class TestRuleFilePaths:
    """Every engine path a rule names must exist.

    rules/44, /45 and /46 each claim to drive a specific module, and all three
    pointed at `langgraph_engine/level3_execution/`, a package renamed to
    `sdlc_pipeline` in v1.20. A rule that names a module nobody can find is
    indistinguishable from a rule nobody implements.

    The rules live only in ~/.claude/rules/ (issue #320 removed the repo's
    docs/standards/ copy), so the class skips where they are not installed.
    """

    RULE_COPIES = sorted(RULES_DIR.glob("4[0-6]-*.md"))

    def test_rule_copies_are_present(self):
        assert self.RULE_COPIES, "no rule files found under ~/.claude/rules"

    def test_no_rule_names_a_missing_engine_path(self):
        pattern = re.compile(r"`(langgraph_engine/[A-Za-z0-9_./-]+\.py)`")
        missing = []
        for rule in self.RULE_COPIES:
            for ref in set(pattern.findall(rule.read_text(encoding="utf-8"))):
                if not (REPO_ROOT / ref).exists():
                    missing.append("{}: {}".format(rule.name, ref))
        assert missing == [], "rules naming paths that do not exist: {}".format(missing)

    def test_the_renamed_package_is_gone_from_the_rules(self):
        for rule in self.RULE_COPIES:
            text = rule.read_text(encoding="utf-8")
            assert "level3_execution" not in text, "{} still names the pre-v1.20 package".format(rule.name)

    def test_the_rename_actually_happened(self):
        assert not (REPO_ROOT / "langgraph_engine" / "level3_execution").exists()
        assert (REPO_ROOT / "langgraph_engine" / "sdlc_pipeline").exists()
