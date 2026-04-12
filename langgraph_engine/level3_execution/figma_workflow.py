"""
Figma Design Workflow Integration for Level 3 Pipeline.

Extracts design tokens and component specs from Figma designs
and injects them into the pipeline at Steps 3, 7, and 11.

Active when ENABLE_FIGMA=1 and FIGMA_ACCESS_TOKEN is set.

Version: 1.0.0
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Figma URL pattern: matches file and design URLs
_FIGMA_URL_RE = re.compile(r"https://(www\.)?figma\.com/(file|design)/([a-zA-Z0-9]+)(/[^\s]*)?")


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _is_figma_enabled() -> bool:
    """Check if Figma integration is enabled via environment."""
    return os.environ.get("ENABLE_FIGMA", "0") == "1"


def _is_figma_configured() -> bool:
    """Return True when the Figma access token is present."""
    return bool(os.environ.get("FIGMA_ACCESS_TOKEN", "").strip())


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class Level3FigmaWorkflow:
    """Figma design workflow integration for pipeline Steps 3, 7, and 11.

    Extracts design tokens and component specs from Figma files and
    injects them into task breakdown (Step 3), prompt generation
    (Step 7), and code review (Step 11).

    Only active when ENABLE_FIGMA=1 and FIGMA_ACCESS_TOKEN is set.
    All operations are non-blocking; failures produce warning logs and
    return a result dict with success=False.
    """

    def __init__(self) -> None:
        """Initialize with lazy import of Figma MCP tools."""
        self._figma_tools = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_tools(self):
        """Lazy load Figma MCP server tools.

        Returns the figma_mcp_server module on success, or None when the
        module is not importable (e.g. missing optional dependencies).
        """
        if self._figma_tools is None:
            try:
                src_mcp_path = str(Path(__file__).resolve().parent.parent.parent / "src" / "mcp")
                if src_mcp_path not in sys.path:
                    sys.path.insert(0, src_mcp_path)
                import figma_mcp_server as figma  # type: ignore[import]

                self._figma_tools = figma
                logger.debug("[FigmaWorkflow] Figma MCP server loaded successfully")
            except ImportError as exc:
                logger.warning("[FigmaWorkflow] Figma MCP server not available: %s", exc)
                self._figma_tools = None
        return self._figma_tools

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_figma_url(self, user_message: str) -> Optional[str]:
        """Extract Figma file key from the user prompt.

        Scans the user message for a Figma file or design URL and returns
        the file key component, or None if no URL is found.

        Args:
            user_message: The raw user prompt text.

        Returns:
            Figma file key string (e.g. 'ABC123xyz') or None.
        """
        if not user_message:
            return None
        match = _FIGMA_URL_RE.search(user_message)
        if match:
            file_key = match.group(3)
            logger.info("[FigmaWorkflow] Detected Figma file key: %s", file_key)
            return file_key
        return None

    def step3_extract_components(self, file_key: str) -> Dict[str, Any]:
        """Extract Figma components for Step 3 (Task Breakdown).

        Calls figma_get_components and figma_get_file_info to build a
        structured component list that can drive UI subtask creation.

        Args:
            file_key: The Figma file key extracted from the user prompt.

        Returns:
            Dict with keys: success, components, pages, total_components.
            On failure returns {"success": False}.
        """
        logger.info("[FigmaWorkflow] Step 3 - Extract components from file: %s", file_key)

        if not _is_figma_enabled():
            logger.debug("[FigmaWorkflow] Figma disabled (ENABLE_FIGMA != 1)")
            return {"success": False, "reason": "Figma integration not enabled"}

        if not _is_figma_configured():
            logger.warning("[FigmaWorkflow] FIGMA_ACCESS_TOKEN not set; skipping")
            return {"success": False, "reason": "FIGMA_ACCESS_TOKEN not configured"}

        figma = self._get_tools()
        if figma is None:
            return {"success": False, "reason": "Figma MCP server unavailable"}

        try:
            # Fetch file metadata for page names
            file_info = figma.figma_get_file_info(file_key=file_key)
            pages = [p.get("name", "") for p in file_info.get("document", {}).get("children", []) if p.get("name")]

            # Fetch components
            components_resp = figma.figma_get_components(file_key=file_key)
            raw_components = components_resp.get("components", [])

            components: List[Dict[str, Any]] = []
            for comp in raw_components:
                comp_type = comp.get("type", "COMPONENT")
                entry: Dict[str, Any] = {
                    "name": comp.get("name", ""),
                    "type": comp_type,
                    "description": comp.get("description", ""),
                }
                # For component sets, list variant names
                if comp_type == "COMPONENT_SET":
                    variants = [child.get("name", "") for child in comp.get("children", []) if child.get("name")]
                    if variants:
                        entry["variants"] = variants
                components.append(entry)

            logger.info(
                "[FigmaWorkflow] Extracted %d components from %d pages",
                len(components),
                len(pages),
            )
            return {
                "success": True,
                "components": components,
                "pages": pages,
                "total_components": len(components),
            }

        except Exception as exc:
            logger.warning("[FigmaWorkflow] step3_extract_components failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    def step7_extract_design_tokens(self, file_key: str, node_ids: str = "") -> Dict[str, Any]:
        """Extract Figma design tokens for Step 7 (Final Prompt Generation).

        Calls figma_extract_design_tokens and figma_get_styles to build a
        comprehensive set of design tokens ready for prompt injection.

        Args:
            file_key: The Figma file key.
            node_ids: Optional comma-separated Figma node IDs to scope extraction.

        Returns:
            Dict with keys: success, design_tokens, prompt_snippet.
            On failure returns {"success": False}.
        """
        logger.info("[FigmaWorkflow] Step 7 - Extract design tokens from file: %s", file_key)

        if not _is_figma_enabled():
            logger.debug("[FigmaWorkflow] Figma disabled (ENABLE_FIGMA != 1)")
            return {"success": False, "reason": "Figma integration not enabled"}

        if not _is_figma_configured():
            logger.warning("[FigmaWorkflow] FIGMA_ACCESS_TOKEN not set; skipping")
            return {"success": False, "reason": "FIGMA_ACCESS_TOKEN not configured"}

        figma = self._get_tools()
        if figma is None:
            return {"success": False, "reason": "Figma MCP server unavailable"}

        try:
            # Extract raw design tokens
            token_kwargs: Dict[str, Any] = {"file_key": file_key}
            if node_ids:
                token_kwargs["node_ids"] = node_ids
            tokens_resp = figma.figma_extract_design_tokens(**token_kwargs)

            # Fetch named styles as additional context
            styles_resp = figma.figma_get_styles(file_key=file_key)

            # Build structured design tokens dict
            raw_colors = tokens_resp.get("colors", [])
            raw_typography = tokens_resp.get("typography", [])
            raw_spacing = tokens_resp.get("spacing", [])
            raw_radii = tokens_resp.get("radii", [])
            raw_shadows = tokens_resp.get("shadows", [])
            raw_styles = styles_resp.get("styles", [])

            # Normalise colors to hex strings
            colors: List[str] = []
            for c in raw_colors:
                if isinstance(c, str):
                    colors.append(c)
                elif isinstance(c, dict):
                    hex_val = c.get("hex") or c.get("value") or c.get("color", "")
                    if hex_val:
                        colors.append(str(hex_val))
            # Deduplicate while preserving order
            seen: set = set()
            colors = [x for x in colors if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

            # Normalise typography entries
            typography: List[Dict[str, Any]] = []
            for t in raw_typography:
                if isinstance(t, dict):
                    entry: Dict[str, Any] = {}
                    if t.get("fontFamily") or t.get("font"):
                        entry["font"] = t.get("fontFamily") or t.get("font")
                    if t.get("fontSize") or t.get("size"):
                        entry["size"] = t.get("fontSize") or t.get("size")
                    if t.get("fontWeight") or t.get("weight"):
                        entry["weight"] = t.get("fontWeight") or t.get("weight")
                    if t.get("lineHeightPx") or t.get("lineHeight"):
                        entry["lineHeight"] = t.get("lineHeightPx") or t.get("lineHeight")
                    if entry:
                        typography.append(entry)

            # Normalise spacing entries
            spacing: List[Dict[str, Any]] = []
            for s in raw_spacing:
                if isinstance(s, dict):
                    sp_entry: Dict[str, Any] = {}
                    if s.get("padding") or s.get("paddingTop"):
                        sp_entry["padding"] = s.get("padding") or str(s.get("paddingTop", ""))
                    if s.get("gap") or s.get("itemSpacing"):
                        sp_entry["gap"] = s.get("gap") or str(s.get("itemSpacing", ""))
                    if s.get("direction") or s.get("layoutMode"):
                        sp_entry["direction"] = s.get("direction") or s.get("layoutMode", "")
                    if sp_entry:
                        spacing.append(sp_entry)

            # Normalise radii
            radii: List[Any] = []
            for r in raw_radii:
                if isinstance(r, (int, float)):
                    radii.append(r)
                elif isinstance(r, dict):
                    val = r.get("cornerRadius") or r.get("value")
                    if val is not None:
                        radii.append(val)

            # Normalise shadows
            shadows: List[Dict[str, Any]] = []
            for s in raw_shadows:
                if isinstance(s, dict):
                    sh_entry: Dict[str, Any] = {}
                    offset_x = s.get("offsetX") or s.get("offset_x", 0)
                    offset_y = s.get("offsetY") or s.get("offset_y", 0)
                    blur = s.get("blur") or s.get("blurRadius", 0)
                    color = s.get("color", "")
                    if offset_x is not None or offset_y is not None or blur:
                        sh_entry["offset"] = "{} {}px".format(
                            str(offset_x) if offset_x else "0",
                            str(offset_y) if offset_y else "0",
                        )
                        sh_entry["blur"] = "{}px".format(blur)
                        if color:
                            sh_entry["color"] = color
                        shadows.append(sh_entry)

            design_tokens: Dict[str, Any] = {
                "colors": colors,
                "typography": typography,
                "spacing": spacing,
                "radii": radii,
                "shadows": shadows,
            }

            # Include named style references when available
            if raw_styles:
                named_colors = [s.get("name", "") for s in raw_styles if s.get("styleType") == "FILL"]
                named_text = [s.get("name", "") for s in raw_styles if s.get("styleType") == "TEXT"]
                if named_colors:
                    design_tokens["named_colors"] = named_colors
                if named_text:
                    design_tokens["named_text_styles"] = named_text

            # Build human-readable prompt snippet
            prompt_snippet = _build_prompt_snippet(design_tokens)

            logger.info(
                "[FigmaWorkflow] Extracted tokens: %d colors, %d typography, " "%d spacing, %d radii, %d shadows",
                len(colors),
                len(typography),
                len(spacing),
                len(radii),
                len(shadows),
            )
            return {
                "success": True,
                "design_tokens": design_tokens,
                "prompt_snippet": prompt_snippet,
            }

        except Exception as exc:
            logger.warning("[FigmaWorkflow] step7_extract_design_tokens failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    def step11_design_review(self, file_key: str, implementation_summary: str) -> Dict[str, Any]:
        """Generate design fidelity review checklist for Step 11 (Code Review).

        Fetches current design tokens and produces a review checklist that
        can be appended to the code review output, ensuring implementation
        matches the Figma design specifications.

        Args:
            file_key: The Figma file key.
            implementation_summary: Brief description of what was implemented.

        Returns:
            Dict with keys: success, review_items, checklist_text.
            On failure returns {"success": False}.
        """
        logger.info("[FigmaWorkflow] Step 11 - Design review for file: %s", file_key)

        if not _is_figma_enabled():
            logger.debug("[FigmaWorkflow] Figma disabled (ENABLE_FIGMA != 1)")
            return {"success": False, "reason": "Figma integration not enabled"}

        if not _is_figma_configured():
            logger.warning("[FigmaWorkflow] FIGMA_ACCESS_TOKEN not set; skipping")
            return {"success": False, "reason": "FIGMA_ACCESS_TOKEN not configured"}

        figma = self._get_tools()
        if figma is None:
            return {"success": False, "reason": "Figma MCP server unavailable"}

        try:
            # Re-fetch tokens for the review checklist
            tokens_resp = figma.figma_extract_design_tokens(file_key=file_key)

            review_items: List[str] = []

            colors = tokens_resp.get("colors", [])
            if colors:
                color_list = ", ".join(str(c) for c in colors[:6])
                review_items.append(
                    "Colors match Figma spec: {} {}".format(color_list, "(+more)" if len(colors) > 6 else "").strip()
                )

            typography = tokens_resp.get("typography", [])
            if typography:
                first = typography[0] if typography else {}
                font_name = first.get("fontFamily") or first.get("font", "")
                review_items.append(
                    "Typography matches Figma: {}{}".format(
                        font_name + " " if font_name else "",
                        "and {} more style(s)".format(len(typography) - 1) if len(typography) > 1 else "style applied",
                    )
                )

            spacing = tokens_resp.get("spacing", [])
            if spacing:
                first_sp = spacing[0] if spacing else {}
                padding = first_sp.get("padding", "")
                gap = first_sp.get("gap") or first_sp.get("itemSpacing", "")
                parts = []
                if padding:
                    parts.append("padding {}".format(padding))
                if gap:
                    parts.append("gap {}".format(gap))
                if parts:
                    review_items.append("Spacing matches Figma: {}".format(", ".join(parts)))

            radii = tokens_resp.get("radii", [])
            if radii:
                radii_str = ", ".join("{}px".format(r) for r in radii[:4])
                review_items.append("Border radius matches Figma: {}".format(radii_str))

            shadows = tokens_resp.get("shadows", [])
            if shadows:
                review_items.append("Box shadows applied: {} shadow(s) from Figma spec".format(len(shadows)))

            # Generic fidelity checks always added
            review_items.extend(
                [
                    "Component structure matches Figma page layout",
                    "Responsive breakpoints align with Figma frames",
                    "Interactive states (hover, active, disabled) match Figma prototypes",
                ]
            )

            checklist_text = _build_review_checklist(review_items)

            logger.info("[FigmaWorkflow] Design review checklist: %d items", len(review_items))
            return {
                "success": True,
                "review_items": review_items,
                "checklist_text": checklist_text,
            }

        except Exception as exc:
            logger.warning("[FigmaWorkflow] step11_design_review failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    # ------------------------------------------------------------------
    # Step 10: Comment on Figma that implementation started
    # ------------------------------------------------------------------

    def step10_implementation_started(
        self,
        file_key: str,
        components: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Add comment to Figma file that implementation has started.

        Called at the beginning of Step 10 (Implementation).

        Args:
            file_key: Figma file key.
            components: List of components being implemented.

        Returns:
            Dict with success (bool), comment_id.
        """
        logger.info("[FigmaWorkflow] Step 10 - Implementation started for file: %s", file_key)

        if not _is_figma_enabled() or not _is_figma_configured():
            return {"success": False, "reason": "Figma not enabled/configured"}

        figma = self._get_tools()
        if figma is None:
            return {"success": False, "reason": "Figma MCP server unavailable"}

        try:
            comp_names = ""
            if components:
                names = [c.get("name", "") for c in components[:10] if c.get("name")]
                if names:
                    comp_names = " Components: " + ", ".join(names)

            message = "Implementation started.{}".format(comp_names)
            result = figma.figma_add_comment(file_key=file_key, message=message)
            return {
                "success": True,
                "comment_id": result.get("comment_id", ""),
            }
        except Exception as exc:
            logger.warning("[FigmaWorkflow] step10 comment failed: %s", exc)
            return {"success": False, "reason": str(exc)}

    # ------------------------------------------------------------------
    # Step 12: Comment on Figma that implementation is complete
    # ------------------------------------------------------------------

    def step12_implementation_complete(
        self,
        file_key: str,
        pr_number: int = 0,
        pr_url: str = "",
    ) -> Dict[str, Any]:
        """Add comment to Figma file that implementation is complete.

        Called during Step 12 (Issue Closure).

        Args:
            file_key: Figma file key.
            pr_number: PR number.
            pr_url: PR URL.

        Returns:
            Dict with success (bool), comment_id.
        """
        logger.info("[FigmaWorkflow] Step 12 - Implementation complete for file: %s", file_key)

        if not _is_figma_enabled() or not _is_figma_configured():
            return {"success": False, "reason": "Figma not enabled/configured"}

        figma = self._get_tools()
        if figma is None:
            return {"success": False, "reason": "Figma MCP server unavailable"}

        try:
            parts = ["Implementation complete."]
            if pr_number:
                parts.append("PR #{}".format(pr_number))
            if pr_url:
                parts.append(pr_url)
            message = " ".join(parts)

            result = figma.figma_add_comment(file_key=file_key, message=message)
            return {
                "success": True,
                "comment_id": result.get("comment_id", ""),
            }
        except Exception as exc:
            logger.warning("[FigmaWorkflow] step12 comment failed: %s", exc)
            return {"success": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Private formatting helpers
# ---------------------------------------------------------------------------


def _build_prompt_snippet(tokens: Dict[str, Any]) -> str:
    """Build a human-readable design token block for prompt injection."""
    lines: List[str] = ["## Design Tokens (from Figma)", ""]

    colors = tokens.get("colors", [])
    if colors:
        lines.append("Colors: {}".format(", ".join(str(c) for c in colors)))

    typography = tokens.get("typography", [])
    for t in typography:
        font = t.get("font", "")
        size = t.get("size", "")
        weight = t.get("weight", "")
        line_height = t.get("lineHeight", "")
        parts = []
        if font:
            parts.append(str(font))
        if size:
            parts.append("{}px".format(size))
        if line_height:
            parts.append("/{}px".format(line_height))
        if weight:
            parts.append("weight {}".format(weight))
        if parts:
            lines.append("Typography: {}".format(" ".join(parts)))

    spacing = tokens.get("spacing", [])
    for s in spacing:
        padding = s.get("padding", "")
        gap = s.get("gap", "")
        direction = s.get("direction", "")
        parts = []
        if padding:
            parts.append("padding {}".format(padding))
        if gap:
            parts.append("gap {}".format(gap))
        if direction:
            parts.append("{} layout".format(direction.lower()))
        if parts:
            lines.append("Spacing: {}".format(", ".join(parts)))

    radii = tokens.get("radii", [])
    if radii:
        lines.append("Border Radius: {}".format(", ".join("{}px".format(r) for r in radii)))

    shadows = tokens.get("shadows", [])
    for s in shadows:
        offset = s.get("offset", "")
        blur = s.get("blur", "")
        color = s.get("color", "")
        parts = [p for p in [offset, blur, color] if p]
        if parts:
            lines.append("Shadows: {}".format(" ".join(parts)))

    return "\n".join(lines)


def _build_review_checklist(items: List[str]) -> str:
    """Format review items as a Markdown checklist."""
    if not items:
        return ""
    lines = ["## Design Fidelity Review (Figma)", ""]
    for item in items:
        lines.append("- [ ] {}".format(item))
    return "\n".join(lines)
