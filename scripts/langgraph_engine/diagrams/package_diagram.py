"""
Package Diagram Generator - Tier 1 AST-based (no LLM).

Generates Mermaid flowchart LR showing internal module dependencies.
Uses CallGraph or AST dependency graph as data source.
"""

import logging

from .base import AbstractDiagramGenerator

logger = logging.getLogger(__name__)


class PackageDiagramGenerator(AbstractDiagramGenerator):
    """Generate Mermaid flowchart LR package/dependency diagram.

    Tier 1: AST-based, no LLM required.
    Only project-internal module dependencies are shown.
    Isolated modules (no internal deps) are listed as standalone nodes.
    """

    @property
    def diagram_type(self):
        return "package"

    def generate(self, analysis_data, format="mermaid"):
        """Generate Mermaid flowchart LR package diagram.

        Args:
            analysis_data: Dict with keys:
                - dep_graph: dict {module_name: set_of_deps} (optional)
            format: Ignored - always produces Mermaid syntax.

        Returns:
            Mermaid flowchart LR string.
        """
        dep_graph = None
        if analysis_data:
            dep_graph = analysis_data.get("dep_graph")

        if not dep_graph:
            return "flowchart LR\n    note[No modules found]"

        lines = ["flowchart LR"]
        project_modules = set(dep_graph.keys())

        # Draw only internal dependency edges
        for module, deps in sorted(dep_graph.items()):
            for dep in sorted(deps):
                if dep in project_modules:
                    lines.append("    %s --> %s" % (module, dep))

        # Add isolated modules (no internal deps at all)
        connected = set()
        for module, deps in dep_graph.items():
            internal_deps = deps & project_modules
            if internal_deps:
                connected.add(module)
                connected.update(internal_deps)

        for module in sorted(project_modules - connected):
            lines.append("    %s" % module)

        return "\n".join(lines)


def _register():
    try:
        from . import DiagramFactory
        DiagramFactory.register("package", PackageDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
