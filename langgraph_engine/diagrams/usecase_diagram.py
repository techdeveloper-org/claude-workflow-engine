"""
Use Case Diagram Generator - Tier 3 LLM-powered.

Generates PlantUML use case diagram from SRS/README requirements docs.
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


class UsecaseDiagramGenerator(AbstractDiagramGenerator):
    """Generate PlantUML use case diagram from requirements.

    Tier 3: LLM-powered.
    Reads SRS.md and README.md from project root when content is not
    provided in analysis_data.
    """

    @property
    def diagram_type(self):
        return "usecase"

    def generate(self, analysis_data, format="mermaid"):
        """Generate PlantUML use case diagram.

        Args:
            analysis_data: Dict with keys:
                - srs_content: str SRS document text (optional)
                - readme_content: str README text (optional)
                - project_root: str project root for auto-reading docs (optional)
            format: Ignored - always produces PlantUML syntax.

        Returns:
            PlantUML use case diagram string.
        """
        srs_content = ""
        readme_content = ""
        project_root = ""
        if analysis_data:
            srs_content = analysis_data.get("srs_content") or ""
            readme_content = analysis_data.get("readme_content") or ""
            project_root = analysis_data.get("project_root") or ""

        if not srs_content and project_root:
            from pathlib import Path

            srs_path = Path(project_root) / "SRS.md"
            if srs_path.is_file():
                try:
                    srs_content = srs_path.read_text(encoding="utf-8", errors="replace")[:3000]
                except OSError:
                    pass

        if not readme_content and project_root:
            from pathlib import Path

            readme_path = Path(project_root) / "README.md"
            if readme_path.is_file():
                try:
                    readme_content = readme_path.read_text(encoding="utf-8", errors="replace")[:2000]
                except OSError:
                    pass

        content = srs_content or readme_content
        if not content:
            return plantuml_stub("usecase", "No requirements docs found")

        prompt = (
            "Generate a PlantUML use case diagram from these requirements. "
            "Output ONLY PlantUML syntax starting with @startuml and ending "
            "with @enduml. Keep it concise (max 15 use cases).\n\n%s" % content
        )

        result = _llm_call(prompt)
        if result:
            return clean_plantuml(result)

        return plantuml_stub("usecase", "LLM generation unavailable")


def _register():
    try:
        from . import DiagramFactory

        DiagramFactory.register("usecase", UsecaseDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
