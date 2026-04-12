"""
Kroki.io renderer for PlantUML/Mermaid diagrams.

Extracted from uml_generators.py (KrokiRenderer class).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class KrokiRenderer:
    """Render PlantUML/Mermaid via Kroki.io free API."""

    KROKI_URL = "https://kroki.io"

    def render(self, diagram_text, diagram_type="plantuml", output_format="svg"):
        """Render diagram via Kroki.io API.

        Args:
            diagram_text: PlantUML or Mermaid source text.
            diagram_type: "plantuml", "mermaid", etc.
            output_format: "svg", "png", etc.

        Returns bytes or None on failure.
        """
        try:
            import requests
        except ImportError:
            logger.warning("requests not available for Kroki rendering")
            return None

        url = "%s/%s/%s" % (self.KROKI_URL, diagram_type, output_format)

        try:
            resp = requests.post(
                url,
                data=diagram_text.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.content
            logger.warning("Kroki API returned %d: %s", resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            logger.warning("Kroki rendering failed: %s", e)
            return None

    def render_to_file(self, diagram_text, output_path, diagram_type="plantuml", output_format="svg"):
        """Render and save to file. Returns path or None."""
        data = self.render(diagram_text, diagram_type, output_format)
        if data is None:
            return None

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return str(output_path)
