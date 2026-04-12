"""
Object Diagram Generator - Tier 3 LLM-powered.

Generates PlantUML object diagram showing example class instances
with realistic field values.
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


class ObjectDiagramGenerator(AbstractDiagramGenerator):
    """Generate PlantUML object diagram showing class instances.

    Tier 3: LLM-powered.
    Builds a class summary from the classes list, then asks the LLM
    to generate example object instances with realistic field values.
    """

    @property
    def diagram_type(self):
        return "object"

    def generate(self, analysis_data, format="mermaid"):
        """Generate PlantUML object diagram.

        Args:
            analysis_data: Dict with keys:
                - classes: list of ClassInfo dicts (optional)
                - context: str additional context (optional)
                - project_root: str project root for AST fallback (optional)
            format: Ignored - always produces PlantUML syntax.

        Returns:
            PlantUML object diagram string.
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
            return plantuml_stub("object", "No classes found")

        class_summary = "\n".join(
            "- %s (attrs: %s)" % (c["name"], ", ".join(a["name"] for a in c.get("attributes", [])[:5]))
            for c in classes[:15]
        )

        prompt = (
            "Generate a PlantUML object diagram showing example instances "
            "of these classes with realistic field values. Output ONLY "
            "PlantUML syntax (@startuml to @enduml).\n\nClasses:\n%s\n\n%s" % (class_summary, context[:500])
        )

        result = _llm_call(prompt)
        if result:
            return clean_plantuml(result)

        return plantuml_stub("object", "LLM generation unavailable")


def _register():
    try:
        from . import DiagramFactory

        DiagramFactory.register("object", ObjectDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
