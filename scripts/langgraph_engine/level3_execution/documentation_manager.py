"""
Level 3 Documentation Manager - Circular SDLC Documentation Cycle

Handles the READ docs (Step 0) -> WRITE/UPDATE docs (Step 13) cycle.
- Step 0: Detect which project docs exist, summarize for task analysis
- Step 13: Create docs for fresh projects, update docs for existing ones

Delegates to DocumentationGenerator for full doc creation on fresh projects.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Documentation files tracked by the SDLC cycle
_DOC_FILES = ["SRS.md", "README.md", "CLAUDE.md", "CHANGELOG.md"]

# Also check alternate SRS naming
_SRS_ALTERNATES = [
    "SRS.md",
    "System_Requirement_Analysis.md",
    "docs/SRS.md",
    "docs/System_Requirement_Analysis.md",
    "SYSTEM_REQUIREMENTS_SPECIFICATION.md",
    "docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md",
]


class Level3DocumentationManager:
    """Manages documentation lifecycle across pipeline steps.

    Step 0 (read): detect_project_docs(), summarize_existing_docs()
    Step 13 (write): create_all_docs(), update_existing_docs()
    """

    def __init__(self, project_root: str = ".", session_dir: str = ""):
        self.project_root = Path(project_root)
        self.session_dir = session_dir

    # ==================================================================
    # STEP 0: READ PHASE
    # ==================================================================

    def detect_project_docs(self) -> Dict[str, Any]:
        """Check which documentation files exist in the project.

        Returns dict with existence flags and is_fresh_project indicator.
        is_fresh_project = True ONLY if none of the 3 core docs exist.
        """
        try:
            srs_exists = self._find_srs() is not None
            readme_exists = (self.project_root / "README.md").is_file()
            claude_md_exists = (self.project_root / "CLAUDE.md").is_file()
            changelog_exists = (self.project_root / "CHANGELOG.md").is_file()

            is_fresh = not (srs_exists or readme_exists or claude_md_exists)

            result = {
                "srs_exists": srs_exists,
                "readme_exists": readme_exists,
                "claude_md_exists": claude_md_exists,
                "changelog_exists": changelog_exists,
                "is_fresh_project": is_fresh,
                "docs_found": [],
            }

            # Build list of found docs
            if srs_exists:
                result["docs_found"].append("SRS.md")
            if readme_exists:
                result["docs_found"].append("README.md")
            if claude_md_exists:
                result["docs_found"].append("CLAUDE.md")
            if changelog_exists:
                result["docs_found"].append("CHANGELOG.md")

            logger.info("Doc detection: fresh=%s, found=%s", is_fresh, result["docs_found"])
            return result

        except Exception as e:
            logger.warning("Doc detection failed: %s", e)
            return {
                "srs_exists": False,
                "readme_exists": False,
                "claude_md_exists": False,
                "changelog_exists": False,
                "is_fresh_project": False,
                "error": str(e),
            }

    def summarize_existing_docs(self, context_data: Dict) -> Dict[str, str]:
        """Summarize existing docs from Level 1 context_data.

        Takes the context_data dict (which contains srs, readme, claude_md
        content loaded by Level 1) and returns first 500 chars of each
        for injection into Step 0 task analysis context.
        """
        summaries = {}
        max_chars = 500

        # Level 1 stores these in context_data under various keys
        key_mappings = {
            "srs": ["srs_content", "srs", "system_requirements"],
            "readme": ["readme_content", "readme"],
            "claude_md": ["claude_md_content", "claude_md", "project_instructions"],
        }

        for doc_name, possible_keys in key_mappings.items():
            content = ""
            for key in possible_keys:
                val = context_data.get(key, "")
                if val and isinstance(val, str) and len(val) > 10:
                    content = val
                    break
            if content:
                summaries[doc_name] = content[:max_chars]

        return summaries

    # ==================================================================
    # STEP 13: WRITE PHASE
    # ==================================================================

    def create_all_docs(self, state: Dict) -> Dict[str, Any]:
        """Create all documentation for a FRESH project.

        Delegates to DocumentationGenerator for full doc creation.
        Returns dict with created file list and status.
        """
        try:
            from .documentation_generator import DocumentationGenerator

            generator = DocumentationGenerator(
                project_root=str(self.project_root),
                session_dir=self.session_dir,
            )

            modified_files = state.get("step10_modified_files", [])
            result = generator.update_all_documentation(files_modified=modified_files)

            created = result.get("updated_files", [])

            # Generate UML diagrams for fresh projects
            try:
                from ..uml_generators import UMLDiagramGenerator

                uml_gen = UMLDiagramGenerator(str(self.project_root))
                uml_result = uml_gen.generate_all()
                for name, syntax in uml_result.items():
                    uml_gen.save_diagram(name, syntax)
                created.extend(["uml/%s.md" % n for n in uml_result])
                logger.info("UML: generated %d diagrams", len(uml_result))

                # Also generate draw.io versions for all diagrams
                cg = uml_gen._get_call_graph()
                drawio_data = {
                    "classes": (uml_gen._classes_from_call_graph(cg) or uml_gen.analyzer.extract_all_classes()),
                    "call_chains": uml_gen._call_chains_from_call_graph(cg) or [],
                }
                drawio_files = self._generate_drawio_diagrams(drawio_data)
                created.extend(drawio_files)
            except Exception as e:
                logger.debug("UML generation skipped: %s", e)

            logger.info("Fresh project: created %d docs: %s", len(created), created)

            return {
                "step13_docs_created": created,
                "step13_updated_files": created,
                "step13_documentation_status": "CREATED",
            }

        except Exception as e:
            logger.error("Failed to create docs for fresh project: %s", e)
            return {
                "step13_docs_created": [],
                "step13_updated_files": [],
                "step13_documentation_status": "ERROR",
                "step13_error": str(e),
            }

    def update_existing_docs(self, state: Dict) -> Dict[str, Any]:
        """Update documentation for an EXISTING project.

        Smart per-file updates:
        - CLAUDE.md: Execution insight (enhanced)
        - SRS.md: New feature/change entry (if task_type=feature)
        - README.md: Light touch (only if major structural change)
        - CHANGELOG.md: Version entry with changes
        Uses step13_standards_doc_requirements from state if available.
        """
        updated_files = []
        task_type = state.get("step0_task_type", "General Task")
        complexity = state.get("step0_complexity", 5)
        skill = state.get("step5_skill", "")
        agent = state.get("step5_agent", "")
        session_id = state.get("session_id", "unknown")
        modified_files = state.get("step10_modified_files", [])
        doc_requirements = state.get("step13_standards_doc_requirements", {})

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        try:
            # --- CLAUDE.md: Always update with execution insight ---
            claude_md_path = self.project_root / "CLAUDE.md"
            if claude_md_path.is_file():
                self._update_claude_md(
                    claude_md_path, session_id, task_type, complexity, skill, agent, modified_files, date_str
                )
                updated_files.append("CLAUDE.md")

            # --- CHANGELOG.md: Always add entry ---
            changelog_path = self.project_root / "CHANGELOG.md"
            self._update_changelog(changelog_path, task_type, modified_files, date_str, state)
            updated_files.append("CHANGELOG.md")

            # --- SRS.md: Only update for feature tasks ---
            if task_type.lower() in ("feature", "new feature", "enhancement"):
                srs_path = self._find_srs()
                if srs_path and srs_path.is_file():
                    self._update_srs(srs_path, state, date_str)
                    updated_files.append(srs_path.name)

            # --- README.md: Only for major changes (complexity >= 7) ---
            readme_path = self.project_root / "README.md"
            if readme_path.is_file() and complexity >= 7:
                self._update_readme(readme_path, state, date_str)
                updated_files.append("README.md")

            # --- UML diagrams: Refresh structural + call flow diagrams ---
            try:
                from ..uml_generators import UMLDiagramGenerator

                uml_gen = UMLDiagramGenerator(str(self.project_root))

                # Build CallGraph once for all diagrams
                cg = uml_gen._get_call_graph()
                cg_classes = uml_gen._classes_from_call_graph(cg)
                classes = cg_classes if cg_classes else uml_gen.analyzer.extract_all_classes()
                dep_graph = uml_gen._dep_graph_from_call_graph(cg)
                cg_chains = uml_gen._call_chains_from_call_graph(cg)

                for diagram_type, method_args in [
                    ("class-diagram", lambda: uml_gen.generate_class_diagram(classes)),
                    ("package-diagram", lambda: uml_gen.generate_package_diagram(dep_graph)),
                    ("component-diagram", lambda: uml_gen.generate_component_diagram(dep_graph)),
                    ("sequence-diagram", lambda: uml_gen.generate_sequence_diagram(cg_chains)),
                    ("call-graph-diagram", lambda: uml_gen.generate_call_graph_diagram(cg)),
                ]:
                    syntax = method_args()
                    uml_gen.save_diagram(diagram_type, syntax)
                    updated_files.append("uml/%s.md" % diagram_type)
                logger.info("UML: refreshed 5 diagrams (3 structural + sequence + call graph)")

                # Also refresh draw.io versions using same analysis data
                drawio_data = {
                    "classes": classes,
                    "call_chains": cg_chains if isinstance(cg_chains, list) else [],
                }
                drawio_files = self._generate_drawio_diagrams(drawio_data)
                updated_files.extend(drawio_files)
            except Exception as e:
                logger.debug("UML refresh skipped: %s", e)

            # --- Apply doc_requirements if standards system provided them ---
            if doc_requirements:
                extra = self._apply_doc_requirements(doc_requirements, state)
                updated_files.extend(extra)

            logger.info("Existing project: updated %d docs: %s", len(updated_files), updated_files)

            return {
                "step13_updated_files": updated_files,
                "step13_documentation_status": "UPDATED",
            }

        except Exception as e:
            logger.error("Failed to update docs: %s", e)
            return {
                "step13_updated_files": updated_files,
                "step13_documentation_status": "ERROR",
                "step13_error": str(e),
            }

    # ==================================================================
    # PRIVATE HELPERS
    # ==================================================================

    def _generate_drawio_diagrams(self, analysis_data, diagram_types=None):
        # type: (dict, list) -> list
        """Generate draw.io (.drawio) files for all SDLC diagram types.

        Called automatically from create_all_docs() and update_existing_docs()
        after Mermaid diagrams are generated. Saves files to drawio/.

        Args:
            analysis_data: Dict with keys: classes, call_chains, states, etc.
            diagram_types: List of types to generate. None = all 12 supported types.

        Returns:
            List of relative file paths created (e.g. "drawio/class-diagram.drawio").
        """
        try:
            try:
                from .diagrams.drawio_converter import DrawioConverter
            except ImportError:
                from langgraph_engine.diagrams.drawio_converter import DrawioConverter
        except ImportError:
            logger.debug("DrawioConverter not available, skipping draw.io generation")
            return []

        import os as _os

        _env = _os.environ.get("DRAWIO_OUTPUT_DIR", "").strip()
        output_dir = Path(_env) if (_env and Path(_env).is_absolute()) else self.project_root / (_env or "drawio")
        output_dir.mkdir(parents=True, exist_ok=True)
        _rel = _os.path.relpath(str(output_dir), str(self.project_root))

        types = diagram_types or DrawioConverter.SUPPORTED_TYPES
        converter = DrawioConverter()
        generated = []

        for dtype in types:
            try:
                xml = converter.convert(dtype, analysis_data)
                out_path = output_dir / ("%s-diagram.drawio" % dtype)
                out_path.write_text(xml, encoding="utf-8")
                generated.append("%s/%s-diagram.drawio" % (_rel, dtype))
                logger.debug("draw.io: saved %s", out_path.name)
            except Exception as e:
                logger.debug("draw.io: %s failed: %s", dtype, e)

        if generated:
            logger.info("draw.io: generated %d diagrams in %s/", len(generated), _rel)
        return generated

    def _find_srs(self) -> Optional[Path]:
        """Find SRS file checking alternate names and locations."""
        for name in _SRS_ALTERNATES:
            path = self.project_root / name
            if path.is_file():
                return path
        return None

    def _update_claude_md(
        self,
        path: Path,
        session_id: str,
        task_type: str,
        complexity: int,
        skill: str,
        agent: str,
        modified_files: List[str],
        date_str: str,
    ):
        """Append enhanced execution insight to CLAUDE.md."""
        try:
            existing = path.read_text(encoding="utf-8", errors="replace")

            marker = "<!-- execution-insight-%s -->" % session_id
            if marker in existing:
                return  # Already has this session's insight

            # Remove previous "Latest Execution Insight" section to keep only latest
            lines = existing.split("\n")
            cleaned = []
            skip = False
            for line in lines:
                if line.strip().startswith("## Latest Execution Insight"):
                    skip = True
                    continue
                if skip and line.startswith("## "):
                    skip = False
                if skip and line.startswith("<!-- execution-insight-"):
                    continue
                if not skip:
                    cleaned.append(line)

            # Build new insight
            insight_lines = [
                "",
                marker,
                "## Latest Execution Insight",
                "",
                "- **Task**: %s (complexity %d/10)" % (task_type, complexity),
            ]
            if skill:
                insight_lines.append("- **Skill**: %s" % skill)
            if agent:
                insight_lines.append("- **Agent**: %s" % agent)
            if modified_files:
                insight_lines.append("- **Files Modified**: %d" % len(modified_files))
            insight_lines.append("- **Date**: %s" % date_str)
            insight_lines.append("")

            new_content = "\n".join(cleaned).rstrip() + "\n" + "\n".join(insight_lines)
            path.write_text(new_content, encoding="utf-8")

        except Exception as e:
            logger.warning("Could not update CLAUDE.md: %s", e)

    def _update_changelog(self, path: Path, task_type: str, modified_files: List[str], date_str: str, state: Dict):
        """Add entry to CHANGELOG.md (create if missing)."""
        try:
            user_message = state.get("user_message", "")
            summary = user_message[:80] if user_message else task_type

            entry = "\n## [%s] - %s\n\n" % (state.get("version", "Unreleased"), date_str)

            category = (
                "Added"
                if task_type.lower() in ("feature", "new feature")
                else (
                    "Changed"
                    if task_type.lower() in ("enhancement", "refactor", "refactoring")
                    else "Fixed" if "fix" in task_type.lower() else "Changed"
                )
            )

            entry += "### %s\n\n" % category
            entry += "- %s\n" % summary
            if modified_files:
                for f in modified_files[:5]:
                    entry += "  - %s\n" % f

            if path.is_file():
                existing = path.read_text(encoding="utf-8", errors="replace")
                # Insert after the first heading line
                insert_pos = existing.find("\n## ")
                if insert_pos >= 0:
                    new_content = existing[:insert_pos] + entry + existing[insert_pos:]
                else:
                    new_content = existing + "\n" + entry
                path.write_text(new_content, encoding="utf-8")
            else:
                header = "# Changelog\n\n"
                header += "All notable changes to this project will be "
                header += "documented in this file.\n"
                path.write_text(header + entry, encoding="utf-8")

        except Exception as e:
            logger.warning("Could not update CHANGELOG.md: %s", e)

    def _update_srs(self, path: Path, state: Dict, date_str: str):
        """Add feature entry to SRS document."""
        try:
            existing = path.read_text(encoding="utf-8", errors="replace")
            user_message = state.get("user_message", "")
            feature_desc = user_message[:120] if user_message else "New feature"

            entry = "\n### FR-NEW: %s\n\n" % feature_desc
            entry += "- **Added**: %s\n" % date_str
            entry += "- **Priority**: Normal\n"
            entry += "- **Status**: Implemented\n"

            # Append before the non-functional requirements section if found
            nfr_pos = existing.find("## Non-Functional Requirements")
            if nfr_pos >= 0:
                new_content = existing[:nfr_pos] + entry + "\n" + existing[nfr_pos:]
            else:
                new_content = existing + entry

            path.write_text(new_content, encoding="utf-8")

        except Exception as e:
            logger.warning("Could not update SRS: %s", e)

    def _update_readme(self, path: Path, state: Dict, date_str: str):
        """Light-touch README update for major changes."""
        try:
            existing = path.read_text(encoding="utf-8", errors="replace")

            # Update "Last Updated" date if present
            import re

            updated = re.sub(
                r"\*\*Last Updated:\*\* \d{4}-\d{2}-\d{2}",
                "**Last Updated:** %s" % date_str,
                existing,
            )
            if updated != existing:
                path.write_text(updated, encoding="utf-8")

        except Exception as e:
            logger.warning("Could not update README.md: %s", e)

    def _apply_doc_requirements(self, requirements: Dict, state: Dict) -> List[str]:
        """Apply additional doc requirements from standards system."""
        extra_updated = []
        try:
            # Standards system may specify additional files to update
            files_to_update = requirements.get("files", [])
            for file_spec in files_to_update:
                if isinstance(file_spec, str):
                    fpath = self.project_root / file_spec
                    if fpath.is_file():
                        logger.info(
                            "Standards doc requirement: %s (exists, skipping " "auto-update - manual review needed)",
                            file_spec,
                        )
        except Exception as e:
            logger.warning("Could not apply doc requirements: %s", e)
        return extra_updated
