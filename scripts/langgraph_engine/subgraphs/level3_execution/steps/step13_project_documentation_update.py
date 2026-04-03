"""
Level 3 Execution - Step 13: Project Documentation Update
"""

from ....flow_state import FlowState


def step13_project_documentation_update(state: FlowState) -> dict:
    """Step 13: Documentation - CREATE for new projects, UPDATE for existing.

    Circular SDLC cycle: Step 0 reads docs, Step 13 writes/updates them.
    - Fresh projects: Creates SRS, README, CLAUDE.md, CHANGELOG via DocumentationGenerator
    - Existing projects: Smart per-file updates (CLAUDE.md insight, CHANGELOG entry, etc.)
    """
    from pathlib import Path

    try:
        from ....level3_execution.documentation_manager import Level3DocumentationManager

        manager = Level3DocumentationManager(
            project_root=state.get("project_root", "."),
            session_dir=state.get("session_dir", "") or state.get("session_path", ""),
        )

        is_fresh = state.get("is_fresh_project", False)

        if is_fresh:
            result = manager.create_all_docs(dict(state))
        else:
            result = manager.update_existing_docs(dict(state))

        # UML diagram generation (best-effort, non-blocking)
        uml_diagrams_generated = []
        try:
            from ....uml_generators import UmlGenerators

            uml_gen = UmlGenerators(
                project_root=state.get("project_root", "."),
                output_dir=str(Path(state.get("project_root", ".")) / "docs" / "uml"),
            )
            # Generate key diagrams: class, sequence, component
            for diagram_type in ["class", "component", "sequence"]:
                try:
                    uml_gen.generate(diagram_type)
                    uml_diagrams_generated.append(diagram_type)
                except Exception:
                    pass  # Individual diagram failures are non-blocking
        except ImportError:
            pass  # UML generators not available
        except Exception:
            pass  # UML generation is best-effort

        # Also write session-dir audit file (preserves existing behavior)
        session_path = state.get("session_dir") or state.get("session_path", "")
        if session_path:
            try:
                doc_file = Path(session_path) / "execution-docs.md"
                task_type = state.get("step0_task_type", "Unknown")
                complexity = state.get("step0_complexity", 5)
                content = "# Execution Documentation\n\n"
                content += "**Generated**: %s\n\n" % __import__("datetime").datetime.now().isoformat()
                content += "- Task Type: %s\n" % task_type
                content += "- Complexity: %d/10\n" % complexity
                content += "- Documentation Status: %s\n" % result.get("step13_documentation_status", "OK")
                content += "- Files Updated: %s\n" % ", ".join(result.get("step13_updated_files", []))
                doc_file.write_text(content, encoding="utf-8")
            except Exception:
                pass  # Audit file is non-critical

        return {
            "step13_updates_prepared": True,
            "step13_update_count": len(result.get("step13_updated_files", [])),
            "step13_updated_files": result.get("step13_updated_files", []),
            "step13_documentation_status": result.get("step13_documentation_status", "OK"),
            "step13_docs_created": result.get("step13_docs_created", []),
            "step13_uml_diagrams": uml_diagrams_generated,
        }

    except Exception as e:
        return {"step13_updates_prepared": False, "step13_documentation_status": "ERROR", "step13_error": str(e)}
