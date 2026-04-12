"""
Class Diagram Generator - Tier 1 AST-based (no LLM).

Generates Mermaid classDiagram from Python AST analysis via UMLAstAnalyzer
or CallGraph class/method data.
"""

import logging

from .base import AbstractDiagramGenerator
from .templates import simplify_type

logger = logging.getLogger(__name__)


class ClassDiagramGenerator(AbstractDiagramGenerator):
    """Generate Mermaid classDiagram from Python AST analysis.

    Tier 1: AST-based, no LLM required.
    Uses CallGraph as primary data source when available; falls back to
    UMLAstAnalyzer for pure AST extraction.
    """

    @property
    def diagram_type(self):
        return "class"

    def generate(self, analysis_data, format="mermaid"):
        """Generate Mermaid classDiagram.

        Args:
            analysis_data: Dict with keys:
                - classes: list of ClassInfo dicts (required)
            format: Ignored - always produces Mermaid syntax.

        Returns:
            Mermaid classDiagram string.
        """
        classes = analysis_data.get("classes") if analysis_data else None
        if not classes:
            return 'classDiagram\n    note "No classes found"'

        lines = ["classDiagram"]

        for cls in classes:
            lines.append("    class %s {" % cls["name"])

            for attr in cls.get("attributes", [])[:10]:
                vis = attr.get("visibility", "+")
                hint = attr.get("type_hint", "")
                type_str = ""
                if hint:
                    type_str = simplify_type(hint)
                    type_str = ": %s" % type_str if type_str else ""
                lines.append("        %s%s%s" % (vis, attr["name"], type_str))

            for method in cls.get("methods", [])[:15]:
                vis = method.get("visibility", "+")
                params = ", ".join(method.get("params", [])[:4])
                ret = ""
                if method.get("return_type"):
                    ret = " %s" % simplify_type(method["return_type"])
                lines.append("        %s%s(%s)%s" % (vis, method["name"], params, ret))

            lines.append("    }")

        # Add inheritance relationships
        for cls in classes:
            for base in cls.get("bases", []):
                if any(c["name"] == base for c in classes):
                    lines.append("    %s <|-- %s" % (base, cls["name"]))

        return "\n".join(lines)


# Auto-register with DiagramFactory at import time
def _register():
    try:
        from . import DiagramFactory

        DiagramFactory.register("class", ClassDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
