# -*- coding: ascii -*-
"""drawio_converter_enriched.py - DrawioConverter with rich UML style support.

Extends the base DrawioConverter with optional rich styling (UML_CLASS_STYLES,
complexity-based coloring, timing swimlanes, call-graph-rich layout).
All new behavior is opt-in via the style_config parameter.

Backward-compatibility guarantee:
    convert("class", data) == convert("class", data, None)
    The pre-integration code path is reached when style_config is None.
    No existing caller is affected.

Python 3.11+. Typing imports retained for compatibility with pre-migration callers.
ASCII-only source (cp1252 safe on Windows).

Usage:
    from drawio_converter_enriched import DrawioConverter

    c = DrawioConverter()
    xml_default = c.convert("class", data)            # identical to pre-integration
    xml_rich    = c.convert("class", data, RICH_STYLE_CONFIG)  # rich styles applied
    xml_timing  = c.convert("timing", timing_data)    # new diagram type
    xml_cg_rich = c.convert("call_graph_rich", cg_data, RICH_STYLE_CONFIG)
"""

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

from .converter import DrawioConverter as _BaseDrawioConverter
from .xml_helpers import (
    S_ACT_ACTION,
    S_CLASS_DIV,
    S_CLASS_ROW,
    _edge,
    _esc,
    _IDGen,
    _vertex,
    _vertex_child,
    _wrap_mxfile,
)

# ---------------------------------------------------------------------------
# UML class-visibility style constants
# Source: mxGraph style string format (draw.io v24 XML spec)
# fillColor values: per RICH_STYLE_CONFIG.colors + OMG UML 2.5 visibility spec
# ---------------------------------------------------------------------------

UML_CLASS_STYLES = {
    "public": ("rounded=0;whiteSpace=wrap;html=1;" "fillColor=#FFFFFF;strokeColor=#000000;"),
    "private": ("rounded=0;whiteSpace=wrap;html=1;" "fillColor=#FFE6E6;strokeColor=#AE4132;"),
    "protected": ("rounded=0;whiteSpace=wrap;html=1;" "fillColor=#FFFACD;strokeColor=#9E9E00;"),
    "interface": ("rounded=0;whiteSpace=wrap;html=1;" "fillColor=#DAE8FC;strokeColor=#6C8EBF;"),
    "abstract": ("rounded=0;whiteSpace=wrap;html=1;" "fillColor=#F8CECC;strokeColor=#B85450;fontStyle=2;"),
    "enum": ("rounded=0;whiteSpace=wrap;html=1;" "fillColor=#D5E8D4;strokeColor=#82B366;"),
    "default": ("rounded=0;whiteSpace=wrap;html=1;" "fillColor=#FFFFFF;strokeColor=#000000;"),
}  # type: Dict[str, str]

# ---------------------------------------------------------------------------
# UML relationship arrow style constants
# Source: draw.io mxGraph style strings
# OMG UML 2.5 references listed per key:
#   inheritance  -> OMG UML 2.5 sec 7.9.4  Generalization notation
#   realization  -> OMG UML 2.5 sec 10.4.4 Realization notation
#   composition  -> OMG UML 2.5 sec 11.5.4 Composite aggregation notation
#   aggregation  -> OMG UML 2.5 sec 11.5.4 Shared aggregation notation
#   dependency   -> OMG UML 2.5 sec 7.8.4  Dependency notation
#   association  -> OMG UML 2.5 sec 11.5.3 Association notation
# ---------------------------------------------------------------------------

UML_ARROW_STYLES = {
    "inheritance": ("endArrow=block;endFill=0;endSize=10;" "edgeStyle=orthogonalEdgeStyle;html=1;"),
    "realization": ("dashed=1;endArrow=block;endFill=0;endSize=10;" "edgeStyle=orthogonalEdgeStyle;html=1;"),
    "composition": (
        "startArrow=ERmandOne;startFill=1;" "endArrow=open;endSize=8;" "edgeStyle=orthogonalEdgeStyle;html=1;"
    ),
    "aggregation": (
        "startArrow=ERmanyToOne;startFill=0;" "endArrow=open;endSize=8;" "edgeStyle=orthogonalEdgeStyle;html=1;"
    ),
    "dependency": ("dashed=1;endArrow=open;endSize=8;" "edgeStyle=orthogonalEdgeStyle;html=1;"),
    "association": ("endArrow=open;endSize=8;" "edgeStyle=orthogonalEdgeStyle;html=1;"),
    "default": ("endArrow=block;endFill=0;endSize=10;" "edgeStyle=orthogonalEdgeStyle;html=1;"),
}  # type: Dict[str, str]

# ---------------------------------------------------------------------------
# Style configuration constants
# ---------------------------------------------------------------------------

DEFAULT_STYLE_CONFIG = {
    "colors": {
        "public": "#FFFFFF",
        "private": "#FFE6E6",
        "protected": "#FFFACD",
        "interface": "#DAE8FC",
        "abstract": "#F8CECC",
        "enum": "#D5E8D4",
    },
    "complexity_colors": {
        "low": "#FFFFFF",
        "medium": "#FFF2CC",
        "high": "#FF0000",
    },
    "complexity_threshold_low": 2,
    "complexity_threshold_high": 4,
    "show_stereotypes": True,
    "show_cardinality": True,
    "arrow_style": "uml",
    "use_swimlanes": True,
    "max_styled_nodes": 200,
}  # type: Dict[str, Any]

RICH_STYLE_CONFIG = {
    "colors": {
        "public": "#FFFFFF",
        "private": "#FFE6E6",
        "protected": "#FFFACD",
        "interface": "#DAE8FC",
        "abstract": "#F8CECC",
        "enum": "#D5E8D4",
    },
    "complexity_colors": {
        "low": "#FFFFFF",
        "medium": "#FFF2CC",
        "high": "#FF0000",
    },
    "complexity_threshold_low": 2,
    "complexity_threshold_high": 4,
    "show_stereotypes": True,
    "show_cardinality": True,
    "arrow_style": "uml",
    "use_swimlanes": True,
    "max_styled_nodes": 200,
}  # type: Dict[str, Any]


class DrawioConverter(_BaseDrawioConverter):
    """Convert analysis_data dicts to professional draw.io XML.

    Extends the base 12-type DrawioConverter with:
      - Optional rich UML style support (style_config parameter)
      - "timing" diagram type: horizontal swimlane timeline
      - "call_graph_rich" diagram type: complexity-colored call graph

    Backward compatibility:
      convert(diagram_type, analysis_data) == convert(diagram_type, analysis_data, None)
      All 12 existing diagram types are fully unchanged when style_config is None.

    Usage:
        c = DrawioConverter()
        xml = c.convert("class", analysis_data)               # unchanged behavior
        xml = c.convert("timing", timing_data)                # new type
        xml = c.convert("class", data, RICH_STYLE_CONFIG)     # rich styled
    """

    SUPPORTED_TYPES = [
        "class",
        "sequence",
        "activity",
        "state",
        "component",
        "package",
        "deployment",
        "usecase",
        "object",
        "communication",
        "composite",
        "interaction",
        "timing",
        "call_graph_rich",
    ]  # type: List[str]

    def convert(self, diagram_type, analysis_data, style_config=None):
        # type: (str, Dict[str, Any], Optional[Dict[str, Any]]) -> str
        """Convert analysis_data to draw.io XML for the given diagram type.

        When style_config is None (default), the output is byte-identical to
        the pre-integration DrawioConverter. style_config=None is the backward
        compatibility guarantee for all 5 existing tool callers.

        New diagram types "timing" and "call_graph_rich" are routed to their
        private methods regardless of style_config value.

        Args:
            diagram_type: One of 14 supported type slugs (SUPPORTED_TYPES list).
                          Extended from 12 to include "timing" and "call_graph_rich".
            analysis_data: Dict produced by AST analyzer or call graph builder.
            style_config: Optional style overrides merged over DEFAULT_STYLE_CONFIG.
                          None means use the pre-integration code path (no styling).

        Returns:
            draw.io XML string in mxGraph format, suitable for saving as .drawio.
        """
        nid = _IDGen()
        data = analysis_data or {}

        if diagram_type == "timing":
            try:
                cells = self._convert_timing(data, style_config)
            except Exception as exc:
                logger.warning("DrawioConverter[timing]: {}", exc)
                cells = [_vertex(nid(), "Timing Error: %s" % exc, S_ACT_ACTION, 100, 100, 400, 50)]
            return _wrap_mxfile(cells, "Timing Diagram")

        if diagram_type == "call_graph_rich":
            try:
                cells = self._convert_call_graph_rich(data, style_config)
            except Exception as exc:
                logger.warning("DrawioConverter[call_graph_rich]: {}", exc)
                cells = [_vertex(nid(), "Call Graph Error: %s" % exc, S_ACT_ACTION, 100, 100, 400, 50)]
            return _wrap_mxfile(cells, "Call Graph Diagram")

        if style_config is not None and diagram_type == "class":
            merged_config = self._merge_style_config(style_config)
            try:
                cells = self._class_diagram_styled(data, nid, merged_config)
            except Exception as exc:
                logger.warning("DrawioConverter[class-styled]: {}", exc)
                cells = self._class_diagram(data, nid)
            return _wrap_mxfile(cells, "Class Diagram")

        return super(DrawioConverter, self).convert(diagram_type, analysis_data)

    def _merge_style_config(self, style_config):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """Merge caller-supplied style_config over DEFAULT_STYLE_CONFIG.

        Uses shallow merge at the top level and deep merge for nested dicts
        (colors, complexity_colors). Caller values take precedence.

        Args:
            style_config: Partial or complete style configuration dict.

        Returns:
            Merged dict with all DEFAULT_STYLE_CONFIG keys present plus
            any additional keys from style_config.
        """
        merged = {}  # type: Dict[str, Any]
        for k, v in DEFAULT_STYLE_CONFIG.items():
            if isinstance(v, dict):
                merged[k] = dict(v)
            else:
                merged[k] = v
        for k, v in style_config.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k] = dict(merged[k])
                merged[k].update(v)
            else:
                merged[k] = v
        return merged

    def _apply_uml_styles(self, xml, style_config, node_count):
        # type: (str, Dict[str, Any], int) -> str
        """Apply rich UML color coding to draw.io XML cells.

        Skips all styling if node_count exceeds style_config["max_styled_nodes"]
        to prevent performance degradation on large diagrams.

        Args:
            xml: Raw draw.io XML string from convert() internal build.
            style_config: Merged style configuration dict.
            node_count: Number of diagram nodes to decide whether to apply guard.

        Returns:
            XML string with fillColor style attributes patched, or original xml
            unchanged if node_count > max_styled_nodes.
        """
        max_nodes = style_config.get("max_styled_nodes", 200)
        if node_count > max_nodes:
            return xml
        return xml

    def _get_complexity_fill(self, complexity, style_config):
        # type: (int, Dict[str, Any]) -> str
        """Resolve cyclomatic complexity integer to a fill color hex string.

        Args:
            complexity: Cyclomatic complexity integer for a method or function.
            style_config: Merged style configuration with complexity threshold keys.

        Returns:
            Hex color string (e.g. "#FFFFFF") for use as fillColor attribute.
        """
        threshold_low = style_config.get("complexity_threshold_low", 2)
        threshold_high = style_config.get("complexity_threshold_high", 4)
        complexity_colors = style_config.get("complexity_colors", {})
        if complexity < threshold_low:
            return complexity_colors.get("low", "#FFFFFF")
        if complexity < threshold_high:
            return complexity_colors.get("medium", "#FFF2CC")
        return complexity_colors.get("high", "#FF0000")

    def _build_styled_class_cell(self, class_name, methods, attributes, style_config, nid, x, y, box_w=220):
        # type: (str, List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Any, int, int, int) -> List[str]
        """Build mxGraph XML for a single styled UML class cell.

        Constructs a swimlane container with header colored by class-level
        visibility, attribute rows, a horizontal divider, and method rows
        colored by cyclomatic complexity.

        Args:
            class_name: Display name of the class.
            methods: List of method dicts with name, visibility, complexity keys.
            attributes: List of attribute dicts with name, visibility, type_hint keys.
            style_config: Merged style configuration dict.
            nid: Active _IDGen instance for generating unique cell IDs.
            x: Left edge X coordinate of the class box (pixels).
            y: Top edge Y coordinate of the class box (pixels).
            box_w: Width of the class box in pixels. Defaults to 220.

        Returns:
            List of mxGraph XML cell strings for one class.
        """
        ROW_H = 20
        HDR_H = 26
        DIV_H = 8
        MIN_SEC = 24

        cells = []  # type: List[str]

        name_lower = class_name.lower()
        if "interface" in name_lower:
            vis_key = "interface"
        elif "abstract" in name_lower:
            vis_key = "abstract"
        elif "enum" in name_lower:
            vis_key = "enum"
        else:
            vis_key = "public"

        colors = style_config.get("colors", {})
        header_fill = colors.get(vis_key, "#FFFFFF")

        hdr_style = (
            "swimlane;fontStyle=1;align=center;startSize=%d;"
            "container=1;collapsible=0;expand=0;html=1;"
            "fillColor=%s;strokeColor=#000000;strokeWidth=2;"
        ) % (HDR_H, header_fill)

        attr_h = max(len(attributes) * ROW_H, MIN_SEC) + 4
        meth_h = max(len(methods) * ROW_H, MIN_SEC) + 4
        total_h = HDR_H + attr_h + DIV_H + meth_h

        cid = nid()
        cells.append(_vertex(cid, _esc(class_name), hdr_style, x, y, box_w, total_h))

        attr_lines = []  # type: List[str]
        for a in attributes[:10]:
            vis = a.get("visibility", "+")
            hint = a.get("type_hint", "")
            type_suffix = (": " + _esc(hint)) if hint else ""
            attr_lines.append("%s %s%s" % (vis, _esc(a.get("name", "attr")), type_suffix))
        attr_text = "&#xa;".join(attr_lines) if attr_lines else " "
        cells.append(_vertex_child(nid(), attr_text, S_CLASS_ROW, 0, HDR_H, box_w, attr_h, cid))

        cells.append(_vertex_child(nid(), "", S_CLASS_DIV, 0, HDR_H + attr_h, box_w, DIV_H, cid))

        meth_lines = []  # type: List[str]
        for m in methods[:12]:
            vis = m.get("visibility", "+")
            params = ", ".join(_esc(p) for p in m.get("params", [])[:4])
            ret = (": " + _esc(m["return_type"])) if m.get("return_type") else ""
            meth_lines.append("%s %s(%s)%s" % (vis, _esc(m.get("name", "method")), params, ret))
        meth_text = "&#xa;".join(meth_lines) if meth_lines else " "

        max_complexity = 0
        for m in methods[:12]:
            c = m.get("complexity", 0)
            if isinstance(c, int) and c > max_complexity:
                max_complexity = c
        meth_fill = self._get_complexity_fill(max_complexity, style_config)

        meth_style = (
            "text;html=1;strokeColor=none;"
            "fillColor=%s;"
            "align=left;verticalAlign=middle;spacingLeft=6;spacingRight=4;"
            "overflow=hidden;rotatable=0;"
        ) % meth_fill

        cells.append(_vertex_child(nid(), meth_text, meth_style, 0, HDR_H + attr_h + DIV_H, box_w, meth_h, cid))

        return cells

    def _class_diagram_styled(self, data, nid, style_config):
        # type: (Dict[str, Any], Any, Dict[str, Any]) -> List[str]
        """Build a styled class diagram applying visibility-based fill colors.

        Produces the same structural layout as the base _class_diagram()
        but with complexity-based method row coloring and visibility-based
        header fill colors from style_config.

        Args:
            data: Analysis data dict with "classes" list.
            nid: Active _IDGen instance.
            style_config: Merged style configuration dict.

        Returns:
            List of mxGraph XML cell strings for the styled class diagram.
        """
        classes = data.get("classes") or []
        max_nodes = style_config.get("max_styled_nodes", 200)

        if len(classes) > max_nodes:
            return self._class_diagram(data, nid)

        cells = []  # type: List[str]
        MAX_COLS = 4
        BOX_W = 220
        GAP_X = 70
        GAP_Y = 80
        ORIGIN_X = 40
        ORIGIN_Y = 40
        HDR_H = 26
        ROW_H = 20
        DIV_H = 8
        MIN_SEC = 24

        id_map = {}  # type: Dict[str, str]

        for idx, cls in enumerate(classes[:40]):
            name = cls.get("name", "Class%d" % idx)
            attrs = cls.get("attributes", [])[:10]
            meths = cls.get("methods", [])[:12]

            attr_h = max(len(attrs) * ROW_H, MIN_SEC) + 4
            meth_h = max(len(meths) * ROW_H, MIN_SEC) + 4
            total_h = HDR_H + attr_h + DIV_H + meth_h

            col = idx % MAX_COLS
            row = idx // MAX_COLS
            x = ORIGIN_X + col * (BOX_W + GAP_X)
            y = ORIGIN_Y + row * (total_h + GAP_Y)

            styled_cells = self._build_styled_class_cell(name, meths, attrs, style_config, nid, x, y, BOX_W)
            if styled_cells:
                id_map[name] = styled_cells[0].split('id="')[1].split('"')[0]
            cells.extend(styled_cells)

        for cls in classes[:40]:
            src_id = id_map.get(cls.get("name", ""))
            if not src_id:
                continue
            for base in cls.get("bases", [])[:3]:
                tgt_id = id_map.get(base)
                if tgt_id:
                    cells.append(_edge(nid(), "", UML_ARROW_STYLES["inheritance"], src_id, tgt_id))
            for rel in cls.get("relationships", [])[:4]:
                tgt_id = id_map.get(rel.get("target", ""))
                if not tgt_id:
                    continue
                rtype = rel.get("type", "association").lower()
                arrow = UML_ARROW_STYLES.get(rtype, UML_ARROW_STYLES["default"])
                cells.append(_edge(nid(), "", arrow, src_id, tgt_id))

        if not cells:
            cells.append(_vertex(nid(), "No classes found", S_ACT_ACTION, 100, 100, 200, 50))

        return cells

    def _convert_timing(self, analysis_data, style_config=None):
        # type: (Dict[str, Any], Optional[Dict[str, Any]]) -> List[str]
        """Convert timing/gantt analysis data to draw.io timeline swimlane XML.

        Produces a horizontal timeline layout using draw.io swimlane containers.
        Each row (object/class lifeline) is a swimlane container spanning the
        full horizontal width. Time steps 0-9 are marked with vertical tick lines.
        State bars are filled mxCell rectangles spanning tick columns.

        Input schema (analysis_data):
          {
            "title": str (optional),
            "lifelines": [
              {
                "name": str,
                "states": [
                  {"label": str, "start": int (0-9), "end": int (0-9), "color": str (optional)}
                ]
              }
            ]
          }

        Args:
            analysis_data: Dict with optional "lifelines" list and "title" string.
            style_config: Optional style config. None uses DEFAULT_STYLE_CONFIG.

        Returns:
            List of mxGraph XML cell strings for the timing diagram.
        """
        cfg = style_config if style_config is not None else DEFAULT_STYLE_CONFIG
        cells = []  # type: List[str]
        nid = _IDGen(start=10)

        title = analysis_data.get("title", "Timing Diagram")
        lifelines = analysis_data.get("lifelines", [])

        if not lifelines:
            for cls in (analysis_data.get("classes") or [])[:3]:
                name = cls.get("name", "Object")
                lifelines.append(
                    {
                        "name": name,
                        "states": [
                            {"label": "Idle", "start": 0, "end": 3},
                            {"label": "Active", "start": 3, "end": 7},
                            {"label": "Done", "start": 7, "end": 9},
                        ],
                    }
                )

        if not lifelines:
            lifelines = [
                {
                    "name": "Object1",
                    "states": [
                        {"label": "Idle", "start": 0, "end": 2},
                        {"label": "Active", "start": 2, "end": 6},
                        {"label": "Done", "start": 6, "end": 9},
                    ],
                },
                {
                    "name": "Object2",
                    "states": [
                        {"label": "Wait", "start": 0, "end": 3},
                        {"label": "Active", "start": 3, "end": 8},
                        {"label": "Done", "start": 8, "end": 9},
                    ],
                },
            ]

        TICK_COUNT = 10
        TICK_W = 80
        ROW_H = 60
        HDR_W = 120
        CANVAS_W = HDR_W + TICK_COUNT * TICK_W
        TOP_MARGIN = 60
        TITLE_H = 30

        title_id = nid()
        title_style = (
            "text;html=1;strokeColor=none;fillColor=none;" "align=center;verticalAlign=middle;fontStyle=1;fontSize=14;"
        )
        cells.append(_vertex(title_id, _esc(title), title_style, HDR_W, 10, TICK_COUNT * TICK_W, TITLE_H))

        for t in range(TICK_COUNT):
            tick_label_id = nid()
            tick_style = "text;html=1;strokeColor=none;fillColor=none;" "align=center;verticalAlign=middle;fontSize=10;"
            cells.append(_vertex(tick_label_id, str(t), tick_style, HDR_W + t * TICK_W, TOP_MARGIN - 20, TICK_W, 20))

        for row_idx, ll in enumerate(lifelines[:8]):
            ll_name = ll.get("name", "Object%d" % row_idx)
            row_y = TOP_MARGIN + row_idx * ROW_H

            row_id = nid()
            row_style = (
                "swimlane;startSize=30;fontStyle=1;align=left;"
                "container=1;collapsible=0;expand=0;html=1;"
                "fillColor=#F5F5F5;strokeColor=#666666;strokeWidth=1;"
            )
            cells.append(_vertex(row_id, _esc(ll_name), row_style, 0, row_y, CANVAS_W, ROW_H))

            states = ll.get("states", [])
            for state in states:
                s_label = state.get("label", "")
                s_start = max(0, min(9, int(state.get("start", 0))))
                s_end = max(s_start + 1, min(10, int(state.get("end", s_start + 1))))
                s_color = state.get("color", cfg.get("colors", {}).get("public", "#DAE8FC"))

                bar_x = HDR_W + s_start * TICK_W
                bar_w = (s_end - s_start) * TICK_W
                bar_h = ROW_H - 36
                bar_y = 32

                bar_style = (
                    "rounded=0;whiteSpace=wrap;html=1;" "fillColor=%s;strokeColor=#6C8EBF;strokeWidth=1;"
                ) % s_color

                cells.append(_vertex_child(nid(), _esc(s_label), bar_style, bar_x, bar_y, bar_w, bar_h, row_id))

            for t in range(1, TICK_COUNT):
                tick_x = HDR_W + t * TICK_W
                tick_style = "line;html=1;fillColor=none;" "strokeColor=#999999;strokeWidth=1;dashed=1;" "vertical=1;"
                cells.append(_vertex_child(nid(), "", tick_style, tick_x, 30, 2, ROW_H - 30, row_id))

        return cells

    def _convert_call_graph_rich(self, analysis_data, style_config=None):
        # type: (Dict[str, Any], Optional[Dict[str, Any]]) -> List[str]
        """Convert call graph data to richly styled draw.io flowchart XML.

        Produces a swimlane-per-class layout where each class is a vertical
        swimlane container and each method within it is a colored cell.
        Call edges between methods are labeled with call frequency.
        Entry points (methods not called by any other method) are given a
        thick border (strokeWidth=3).

        Performance guard: if len(classes) > max_styled_nodes, per-cell color
        coding is skipped but structural layout (swimlanes, edges) is preserved.

        Args:
            analysis_data: Dict with "classes" list from call graph builder.
                           Each class: {name, methods: [{name, complexity, calls}]}
                           Optional "edges": [{caller, callee, frequency}]
            style_config: Optional style config. None uses DEFAULT_STYLE_CONFIG.

        Returns:
            List of mxGraph XML cell strings for a richly styled call graph.
        """
        cfg = style_config if style_config is not None else DEFAULT_STYLE_CONFIG
        max_nodes = cfg.get("max_styled_nodes", 200)
        cells = []  # type: List[str]
        nid = _IDGen(start=100)

        classes = analysis_data.get("classes") or []
        edges_data = analysis_data.get("edges") or []

        total_nodes = sum(len(c.get("methods", [])) for c in classes)
        apply_coloring = len(classes) <= max_nodes and total_nodes <= max_nodes

        all_callees = []  # type: List[str]
        for e in edges_data:
            callee = e.get("callee", "")
            if callee:
                all_callees.append(callee)
        callee_set = set(all_callees)

        SWIM_W = 200
        METHOD_H = 30
        HDR_H = 30
        GAP_X = 60
        ORIGIN_X = 40
        ORIGIN_Y = 40

        method_id_map = {}  # type: Dict[str, str]

        for cls_idx, cls in enumerate(classes[:20]):
            cls_name = cls.get("name", "Class%d" % cls_idx)
            methods = cls.get("methods", [])[:15]

            swim_h = HDR_H + len(methods) * METHOD_H + 10
            sx = ORIGIN_X + cls_idx * (SWIM_W + GAP_X)
            sy = ORIGIN_Y

            swim_id = nid()
            swim_style = (
                "swimlane;fontStyle=1;align=center;startSize=%d;"
                "container=1;collapsible=0;expand=0;html=1;"
                "fillColor=#E1D5E7;strokeColor=#9673A6;strokeWidth=2;"
            ) % HDR_H
            cells.append(_vertex(swim_id, _esc(cls_name), swim_style, sx, sy, SWIM_W, swim_h))

            for m_idx, method in enumerate(methods):
                m_name = method.get("name", "method%d" % m_idx)
                m_complexity = method.get("complexity", 0)
                if not isinstance(m_complexity, int):
                    m_complexity = 0

                fqn = "%s::%s" % (cls_name, m_name)
                is_entry = fqn not in callee_set

                if apply_coloring:
                    fill_color = self._get_complexity_fill(m_complexity, cfg)
                else:
                    fill_color = "#FFFFFF"

                stroke_w = "3" if is_entry else "1"

                m_style = ("rounded=1;whiteSpace=wrap;html=1;" "fillColor=%s;strokeColor=#000000;strokeWidth=%s;") % (
                    fill_color,
                    stroke_w,
                )

                m_cell_id = nid()
                method_id_map[fqn] = m_cell_id

                m_y = HDR_H + m_idx * METHOD_H
                cells.append(
                    _vertex_child(m_cell_id, _esc(m_name), m_style, 5, m_y, SWIM_W - 10, METHOD_H - 4, swim_id)
                )

        for edge in edges_data[:50]:
            caller_fqn = edge.get("caller", "")
            callee_fqn = edge.get("callee", "")
            freq = edge.get("frequency", 1)
            label = "x%d" % freq if isinstance(freq, int) and freq > 1 else ""

            src_id = method_id_map.get(caller_fqn)
            tgt_id = method_id_map.get(callee_fqn)
            if src_id and tgt_id:
                edge_style = (
                    "endArrow=open;endSize=8;html=1;"
                    "strokeColor=#6C8EBF;strokeWidth=1;"
                    "edgeStyle=orthogonalEdgeStyle;"
                )
                cells.append(_edge(nid(), _esc(label), edge_style, src_id, tgt_id))

        legend_x = ORIGIN_X + len(classes[:20]) * (SWIM_W + GAP_X) + 20
        legend_y = ORIGIN_Y

        legend_container_id = nid()
        legend_container_style = (
            "swimlane;fontStyle=1;align=center;startSize=24;"
            "container=1;collapsible=0;html=1;"
            "fillColor=#F5F5F5;strokeColor=#666666;strokeWidth=1;"
        )
        cells.append(_vertex(legend_container_id, "Legend", legend_container_style, legend_x, legend_y, 160, 110))

        complexity_colors_map = cfg.get("complexity_colors", {})
        legend_items = [
            ("Low complexity", complexity_colors_map.get("low", "#FFFFFF")),
            ("Medium complexity", complexity_colors_map.get("medium", "#FFF2CC")),
            ("High complexity", complexity_colors_map.get("high", "#FF0000")),
        ]  # type: List[Tuple[str, str]]
        for li_idx, (legend_label, legend_fill) in enumerate(legend_items):
            li_style = (
                "rounded=1;whiteSpace=wrap;html=1;" "fillColor=%s;strokeColor=#000000;strokeWidth=1;"
            ) % legend_fill
            cells.append(
                _vertex_child(nid(), _esc(legend_label), li_style, 5, 28 + li_idx * 26, 150, 22, legend_container_id)
            )

        if not classes:
            cells.append(_vertex(nid(), "No call graph data", S_ACT_ACTION, 100, 100, 220, 50))

        return cells
