"""
State Diagram Generator - Tier 2 AST + LLM hybrid.

Generates Mermaid stateDiagram-v2 from state/context information.
Requires LLM for meaningful output; falls back to a minimal stub.
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


class StateDiagramGenerator(AbstractDiagramGenerator):
    """Generate Mermaid stateDiagram-v2 from system state information.

    Tier 2: LLM-powered with minimal fallback.
    """

    @property
    def diagram_type(self):
        return "state"

    def generate(self, analysis_data, format="mermaid"):
        """Generate Mermaid stateDiagram-v2.

        Args:
            analysis_data: Dict with keys:
                - state_info: str describing states/transitions (optional)
                - context: str context for LLM (optional)
            format: Ignored - always produces Mermaid syntax.

        Returns:
            Mermaid stateDiagram-v2 string.
        """
        state_info = ""
        context = ""
        if analysis_data:
            state_info = analysis_data.get("state_info") or ""
            context = analysis_data.get("context") or ""

        if not state_info and not context:
            return "stateDiagram-v2\n    [*] --> Idle\n    Idle --> [*]"

        prompt = (
            "Generate a Mermaid stateDiagram-v2 for the following "
            "system/context. Output ONLY the Mermaid syntax, "
            "no markdown fences.\n\n%s\n\n%s"
            % (state_info[:2000], context[:500])
        )

        result = _llm_call(prompt)
        if result:
            return clean_mermaid(result)

        return "stateDiagram-v2\n    [*] --> Idle\n    Idle --> [*]"


def _register():
    try:
        from . import DiagramFactory
        DiagramFactory.register("state", StateDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
