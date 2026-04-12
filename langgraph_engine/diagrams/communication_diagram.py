"""
Communication Diagram Generator - Tier 3 LLM-powered.

Generates PlantUML communication diagram showing how modules interact.
Uses module dependency graph as data source.
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


class CommunicationDiagramGenerator(AbstractDiagramGenerator):
    """Generate PlantUML communication diagram.

    Tier 3: LLM-powered.
    Builds a module dependency summary from dep_graph and asks the LLM
    to produce a PlantUML communication diagram showing module interactions.
    """

    @property
    def diagram_type(self):
        return "communication"

    def generate(self, analysis_data, format="mermaid"):
        """Generate PlantUML communication diagram.

        Args:
            analysis_data: Dict with keys:
                - dep_graph: dict {module_name: set_of_deps} (optional)
                - context: str additional context (optional)
                - project_root: str project root for AST fallback (optional)
            format: Ignored - always produces PlantUML syntax.

        Returns:
            PlantUML communication diagram string.
        """
        dep_graph = None
        context = ""
        project_root = ""
        if analysis_data:
            dep_graph = analysis_data.get("dep_graph")
            context = analysis_data.get("context") or ""
            project_root = analysis_data.get("project_root") or ""

        if dep_graph is None and project_root:
            from .ast_analyzer import UMLAstAnalyzer

            analyzer = UMLAstAnalyzer(project_root)
            dep_graph = analyzer.build_dependency_graph()

        if not dep_graph:
            return plantuml_stub("communication", "No module dependencies found")

        module_summary = "\n".join(
            "- %s depends on: %s" % (mod, ", ".join(sorted(deps)[:5])) for mod, deps in sorted(dep_graph.items())[:20]
        )

        prompt = (
            "Generate a PlantUML communication diagram showing how these "
            "modules interact. Output ONLY PlantUML syntax "
            "(@startuml to @enduml).\n\nModules:\n%s\n\n%s" % (module_summary, context[:500])
        )

        result = _llm_call(prompt)
        if result:
            return clean_plantuml(result)

        return plantuml_stub("communication", "LLM generation unavailable")


def _register():
    try:
        from . import DiagramFactory

        DiagramFactory.register("communication", CommunicationDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
