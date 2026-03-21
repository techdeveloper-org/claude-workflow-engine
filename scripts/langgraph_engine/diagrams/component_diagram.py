"""
Component Diagram Generator - Tier 1 AST-based (no LLM).

Generates Mermaid flowchart TB with subgraphs grouped by top-level directory.
Uses CallGraph or AST dependency graph as data source.
"""

import logging
from pathlib import Path

from .base import AbstractDiagramGenerator

logger = logging.getLogger(__name__)


class ComponentDiagramGenerator(AbstractDiagramGenerator):
    """Generate Mermaid flowchart TB component diagram.

    Tier 1: AST-based, no LLM required.
    Modules are grouped into subgraphs by top-level directory.
    """

    @property
    def diagram_type(self):
        return "component"

    def generate(self, analysis_data, format="mermaid"):
        """Generate Mermaid flowchart TB component diagram.

        Args:
            analysis_data: Dict with keys:
                - dep_graph: dict {module_name: set_of_deps} (optional)
                - project_root: str project root path (required for grouping)
            format: Ignored - always produces Mermaid syntax.

        Returns:
            Mermaid flowchart TB string.
        """
        dep_graph = None
        project_root = None
        if analysis_data:
            dep_graph = analysis_data.get("dep_graph")
            project_root = analysis_data.get("project_root") or ""

        if not dep_graph:
            return "flowchart TB\n    note[No components found]"

        lines = ["flowchart TB"]
        root = Path(project_root) if project_root else Path(".")

        # Group modules by top-level directory
        groups = {}  # group_name -> list of module names
        for module in dep_graph:
            placed = False
            if project_root:
                for py_file in root.rglob("%s.py" % module):
                    try:
                        rel = py_file.relative_to(root)
                        parts = rel.parts
                        group = parts[0] if len(parts) > 1 else "root"
                        if group not in groups:
                            groups[group] = []
                        groups[group].append(module)
                        placed = True
                    except ValueError:
                        pass
                    break
            if not placed:
                if "root" not in groups:
                    groups["root"] = []
                groups["root"].append(module)

        for group, modules in sorted(groups.items()):
            safe_group = group.replace("-", "_").replace(".", "_")
            lines.append("    subgraph %s[%s]" % (safe_group, group))
            for mod in sorted(set(modules)):
                lines.append("        %s[%s]" % (mod, mod))
            lines.append("    end")

        # Add cross-group dependency arrows
        project_modules = set(dep_graph.keys())
        for module, deps in dep_graph.items():
            for dep in deps:
                if dep in project_modules and dep != module:
                    lines.append("    %s --> %s" % (module, dep))

        return "\n".join(lines)


def _register():
    try:
        from . import DiagramFactory
        DiagramFactory.register("component", ComponentDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
