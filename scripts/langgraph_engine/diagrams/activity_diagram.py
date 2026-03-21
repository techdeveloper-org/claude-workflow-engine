"""
Activity Diagram Generator - Tier 2 AST + LLM hybrid.

Generates Mermaid flowchart TD (activity diagram) from function logic.
Requires LLM for meaningful output; falls back to a basic structure stub.
"""

import logging

from .base import AbstractDiagramGenerator
from .templates import clean_mermaid

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


class ActivityDiagramGenerator(AbstractDiagramGenerator):
    """Generate Mermaid flowchart TD (activity diagram) from function logic.

    Tier 2: LLM-powered with AST-based fallback.
    """

    @property
    def diagram_type(self):
        return "activity"

    def generate(self, analysis_data, format="mermaid"):
        """Generate Mermaid flowchart TD activity diagram.

        Args:
            analysis_data: Dict with keys:
                - function_code: str source of the function/module (optional)
                - context: str context for LLM (optional)
            format: Ignored - always produces Mermaid syntax.

        Returns:
            Mermaid flowchart TD string.
        """
        function_code = ""
        context = ""
        if analysis_data:
            function_code = analysis_data.get("function_code") or ""
            context = analysis_data.get("context") or ""

        if not function_code and not context:
            return "flowchart TD\n    Start([Start]) --> End([End])"

        prompt = (
            "Generate a Mermaid flowchart TD (activity diagram) for "
            "the following code/context. Output ONLY the Mermaid syntax, "
            "no markdown fences.\n\n%s\n\n%s"
            % (function_code[:2000], context[:500])
        )

        result = _llm_call(prompt)
        if result:
            return clean_mermaid(result)

        # Fallback: basic structure
        return (
            "flowchart TD\n"
            "    Start([Start]) --> Process[Process] --> End([End])"
        )


def _register():
    try:
        from . import DiagramFactory
        DiagramFactory.register("activity", ActivityDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
