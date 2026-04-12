"""
Composite Structure Diagram Generator - Tier 3 LLM-powered.

Generates PlantUML composite structure diagram showing internal structure
of classes (ports, parts, connectors).
"""

import logging

from .base import AbstractDiagramGenerator
from .templates import clean_plantuml, plantuml_stub

logger = logging.getLogger(__name__)


def _llm_call(prompt):
    """Call LLM via llm_call.py (lazy import, graceful fallback)."""
    try:
        from langgraph_engine.llm_call import llm_call

        return llm_call(prompt, model="fast", timeout=60)
    except ImportError:
        logger.debug("llm_call not available, skipping LLM generation")
        return None
    except Exception as e:
        logger.debug("LLM call failed: %s", e)
        return None


class CompositeDiagramGenerator(AbstractDiagramGenerator):
    """Generate PlantUML composite structure diagram.

    Tier 3: LLM-powered.
    Builds a class summary (methods + attrs) from the classes list and asks
    the LLM to produce a PlantUML composite structure diagram with ports,
    parts, and connectors.
    """

    @property
    def diagram_type(self):
        return "composite"

    def generate(self, analysis_data, format="mermaid"):
        """Generate PlantUML composite structure diagram.

        Args:
            analysis_data: Dict with keys:
                - classes: list of ClassInfo dicts (optional)
                - context: str additional context (optional)
                - project_root: str project root for AST fallback (optional)
            format: Ignored - always produces PlantUML syntax.

        Returns:
            PlantUML composite structure diagram string.
        """
        classes = None
        context = ""
        project_root = ""
        if analysis_data:
            classes = analysis_data.get("classes")
            context = analysis_data.get("context") or ""
            project_root = analysis_data.get("project_root") or ""

        if classes is None and project_root:
            from .ast_analyzer import UMLAstAnalyzer

            analyzer = UMLAstAnalyzer(project_root)
            classes = analyzer.extract_all_classes()

        if not classes:
            return plantuml_stub("composite", "No classes found")

        class_summary = "\n".join(
            "- %s: methods=%s, attrs=%s"
            % (
                c["name"],
                ", ".join(m["name"] for m in c.get("methods", [])[:5]),
                ", ".join(a["name"] for a in c.get("attributes", [])[:5]),
            )
            for c in classes[:10]
        )

        prompt = (
            "Generate a PlantUML composite structure diagram showing "
            "internal structure of these classes (ports, parts, connectors). "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s\n\n%s" % (class_summary, context[:500])
        )

        result = _llm_call(prompt)
        if result:
            return clean_plantuml(result)

        return plantuml_stub("composite", "LLM generation unavailable")


def _register():
    try:
        from . import DiagramFactory

        DiagramFactory.register("composite", CompositeDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
