"""
Base class for all UML diagram generators (Strategy Pattern + Template Method).

Each concrete generator implements generate() for its specific diagram type.
The Template Method pattern defines the standard workflow:
    analyze -> generate -> render (optional)
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AbstractDiagramGenerator(ABC):
    """Base class for all UML diagram generators (Strategy Pattern).

    Each concrete generator implements the generate() method for its
    specific diagram type. The Template Method pattern defines the
    standard workflow: analyze -> generate -> render.
    """

    @property
    @abstractmethod
    def diagram_type(self):
        # type: () -> str
        """Return the diagram type name (e.g. 'class', 'sequence')."""
        pass

    @abstractmethod
    def generate(self, analysis_data, format="mermaid"):
        # type: (Dict[str, Any], str) -> str
        """Generate diagram markup from analysis data.

        Args:
            analysis_data: Dict from AST analyzer containing classes, methods, etc.
            format: Output format - "mermaid" or "plantuml"

        Returns:
            Diagram markup string.
        """
        pass

    def render_to_svg(self, markup):
        # type: (str) -> Optional[bytes]
        """Render markup to SVG using Kroki (optional).

        Returns bytes of SVG data or None on failure.
        """
        try:
            from .kroki_renderer import KrokiRenderer
            renderer = KrokiRenderer()
            return renderer.render(markup, self.diagram_type)
        except Exception as e:
            logger.debug("SVG render failed for %s: %s", self.diagram_type, e)
            return None
