"""
Deployment Diagram Generator - Tier 3 LLM-powered.

Generates PlantUML deployment diagram from infrastructure files
(Dockerfile, docker-compose, k8s manifests, GitHub Actions workflows).
"""

import logging

from .base import AbstractDiagramGenerator
from .templates import clean_plantuml, plantuml_stub

logger = logging.getLogger(__name__)

# Infrastructure file patterns to auto-detect
_INFRA_PATTERNS = [
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "*.k8s.yml",
    "*.k8s.yaml",
    "deployment.yml",
    "Procfile",
    ".github/workflows/*.yml",
]


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


class DeploymentDiagramGenerator(AbstractDiagramGenerator):
    """Generate PlantUML deployment diagram from infrastructure files.

    Tier 3: LLM-powered.
    Auto-detects Dockerfile, docker-compose, k8s, and CI workflow files
    from the project root when infra_content is not explicitly provided.
    """

    @property
    def diagram_type(self):
        return "deployment"

    def generate(self, analysis_data, format="mermaid"):
        """Generate PlantUML deployment diagram.

        Args:
            analysis_data: Dict with keys:
                - infra_content: str pre-assembled infrastructure file content
                - project_root: str project root for auto-detection (optional)
            format: Ignored - always produces PlantUML syntax.

        Returns:
            PlantUML deployment diagram string.
        """
        infra_content = ""
        project_root = ""
        if analysis_data:
            infra_content = analysis_data.get("infra_content") or ""
            project_root = analysis_data.get("project_root") or ""

        if not infra_content and project_root:
            from pathlib import Path
            root = Path(project_root)
            for pattern in _INFRA_PATTERNS:
                for f in root.glob(pattern):
                    try:
                        infra_content += "\n--- %s ---\n" % f.name
                        infra_content += f.read_text(
                            encoding="utf-8", errors="replace"
                        )[:1000]
                    except OSError:
                        pass

        if not infra_content and project_root:
            from pathlib import Path
            root = Path(project_root)
            try:
                dirs = ", ".join(
                    d.name for d in root.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                )
                infra_content = "Python project with modules: %s" % dirs
            except OSError:
                pass

        if not infra_content:
            return plantuml_stub("deployment", "No infrastructure files found")

        prompt = (
            "Generate a PlantUML deployment diagram for this project. "
            "Output ONLY PlantUML syntax (@startuml to @enduml).\n\n%s"
            % infra_content[:3000]
        )

        result = _llm_call(prompt)
        if result:
            return clean_plantuml(result)

        return plantuml_stub("deployment", "LLM generation unavailable")


def _register():
    try:
        from . import DiagramFactory
        DiagramFactory.register("deployment", DeploymentDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
