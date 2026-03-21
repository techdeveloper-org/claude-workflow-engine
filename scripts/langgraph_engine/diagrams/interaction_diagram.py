"""
Interaction Overview Diagram Generator - Tier 3 LLM-powered.

Generates PlantUML interaction overview diagram (activity diagram with
interaction fragments) from call chain data.
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


class InteractionDiagramGenerator(AbstractDiagramGenerator):
    """Generate PlantUML interaction overview diagram.

    Tier 3: LLM-powered.
    Builds a call chain summary and asks the LLM to produce a PlantUML
    interaction overview (activity diagram with interaction fragments).
    """

    @property
    def diagram_type(self):
        return "interaction"

    def generate(self, analysis_data, format="mermaid"):
        """Generate PlantUML interaction overview diagram.

        Args:
            analysis_data: Dict with keys:
                - call_chains: list of call chain dicts (optional)
                - context: str additional context (optional)
                - project_root: str project root for AST fallback (optional)
            format: Ignored - always produces PlantUML syntax.

        Returns:
            PlantUML interaction overview diagram string.
        """
        call_chains = None
        context = ""
        project_root = ""
        if analysis_data:
            call_chains = analysis_data.get("call_chains")
            context = analysis_data.get("context") or ""
            project_root = analysis_data.get("project_root") or ""

        if call_chains is None and project_root:
            from .ast_analyzer import UMLAstAnalyzer
            from pathlib import Path
            analyzer = UMLAstAnalyzer(project_root)
            call_chains = []
            root = Path(project_root)
            for py_file in root.rglob("*.py"):
                rel = str(py_file.relative_to(root))
                if any(skip in rel for skip in ["__pycache__", ".venv", "test"]):
                    continue
                chains = analyzer.extract_call_chains(py_file)
                call_chains.extend(chains[:10])
                if len(call_chains) >= 40:
                    break

        if not call_chains:
            return plantuml_stub("interaction", "No call chains found")

        chain_summary = "\n".join(
            "- %s calls %s" % (c["caller"], c["callee"])
            for c in call_chains[:20]
        )

        prompt = (
            "Generate a PlantUML interaction overview diagram (activity "
            "diagram with interaction fragments) for these call flows. "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s\n\n%s"
            % (chain_summary, context[:500])
        )

        result = _llm_call(prompt)
        if result:
            return clean_plantuml(result)

        return plantuml_stub("interaction", "LLM generation unavailable")


def _register():
    try:
        from . import DiagramFactory
        DiagramFactory.register("interaction", InteractionDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
