"""
Draw.io XML Converter - Professional quality .drawio file generation.

Generates all 12 UML diagram types used in SDLC workflows as editable
.drawio files. No external API or library required - pure XML generation
using the mxGraph/draw.io XML format.

Features:
  - Proper <mxfile> XML wrapper (draw.io v24+ format)
  - Professional Enterprise Architect color palette
  - UML-correct shapes: mxgraph.uml.actor, shape=cube, shape=folder, etc.
  - 3-section class boxes (header + attributes + methods with dividers)
  - Sequence lifelines via mxgraph.uml.lifeline (participant + dashed line)
  - Orthogonal edge routing on all connectors
  - HTML=1 on all cells for rich text support
  - Activity/State final nodes via shape=doubleEllipse
  - Shareable app.diagrams.net URLs (encoded or GitHub-hosted)

Usage:
    from langgraph_engine.diagrams.drawio_converter import DrawioConverter, get_shareable_url

    c = DrawioConverter()
    xml = c.convert("class", analysis_data)

    with open("class-diagram.drawio", "w", encoding="utf-8") as f:
        f.write(xml)

    # Shareable URL (no upload needed)
    url = get_shareable_url(xml)
"""

# ruff: noqa: F821

import logging

logger = logging.getLogger(__name__)

# ======================================================================
# Color palette (Enterprise Architect / Professional UML standard)
# ======================================================================

C_CLASS_FILL = "#E1D5E7"  # Light purple - concrete classes
C_CLASS_STROKE = "#9673A6"  # Dark purple
C_IFACE_FILL = "#F0E6FF"  # Lighter purple - interfaces
C_ABST_FILL = "#F0F0F0"  # Light gray - abstract classes
C_ABST_STROKE = "#666666"
C_ENUM_FILL = "#FFF2CC"  # Light yellow - enumerations
C_ENUM_STROKE = "#D6B656"
C_STATE_FILL = "#D5E8D4"  # Light green - states
C_STATE_STROKE = "#82B366"
C_ACT_FILL = "#E1D5E7"  # Activity action nodes
C_BLUE_FILL = "#DAE8FC"  # Light blue - objects, nodes
C_BLUE_STROKE = "#6C8EBF"
C_NODE_FILL = "#FFE6CC"  # Light orange - deployment nodes
C_NODE_STROKE = "#D79B00"
C_WHITE = "#FFFFFF"
C_BLACK = "#000000"
C_GRAY_FILL = "#F5F5F5"
C_GRAY_STROKE = "#666666"

# ======================================================================
# Style string constants
# ======================================================================

# --- Class Diagram ---
S_CLASS_HDR = (
    "swimlane;fontStyle=1;align=center;startSize=26;"
    "container=1;collapsible=0;expand=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_CLASS_FILL, C_CLASS_STROKE)
)
S_IFACE_HDR = (
    "swimlane;fontStyle=3;align=center;startSize=26;"  # italic+bold = interface
    "container=1;collapsible=0;expand=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_IFACE_FILL, C_CLASS_STROKE)
)
S_ABST_HDR = (
    "swimlane;fontStyle=2;align=center;startSize=26;"  # italic = abstract
    "container=1;collapsible=0;expand=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_ABST_FILL, C_ABST_STROKE)
)
S_ENUM_HDR = (
    "swimlane;fontStyle=1;align=center;startSize=26;"
    "container=1;collapsible=0;expand=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_ENUM_FILL, C_ENUM_STROKE)
)
S_CLASS_ROW = (
    "text;html=1;strokeColor=none;fillColor=none;"
    "align=left;verticalAlign=middle;spacingLeft=6;spacingRight=4;"
    "overflow=hidden;rotatable=0;"
)
S_CLASS_DIV = "line;html=1;strokeColor=%s;strokeWidth=1;fillColor=none;" % C_CLASS_STROKE

# Relationship arrows
S_INHERIT = (
    "endArrow=block;endFill=0;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_REALIZE = (
    "endArrow=block;endFill=0;dashed=1;html=1;"
    "strokeColor=%s;strokeWidth=2;"
    "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_COMPOSE = (
    "endArrow=diamond;endFill=1;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_AGGREGATE = (
    "endArrow=diamond;endFill=0;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_ASSOCIATE = (
    "endArrow=open;endSize=8;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_DEPEND = (
    "endArrow=open;endSize=8;dashed=1;html=1;"
    "strokeColor=%s;strokeWidth=1;"
    "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)

# --- Sequence Diagram ---
S_LIFELINE = (
    "shape=mxgraph.uml.lifeline;align=center;startSize=40;"
    "strokeColor=%s;strokeWidth=2;"
    "fillColor=%s;html=1;resizable=0;" % (C_BLACK, C_WHITE)
)
S_ACTOR_LIFE = (
    "shape=mxgraph.uml.actor;align=center;"
    "strokeColor=%s;fillColor=%s;"
    "html=1;verticalLabelPosition=bottom;verticalAlign=top;" % (C_BLACK, C_WHITE)
)
S_ACTIVATION = "html=1;strokeColor=%s;fillColor=%s;" "strokeWidth=2;" % (C_BLACK, C_WHITE)
S_MSG_SYNC = "endArrow=block;endFill=1;html=1;" "strokeColor=%s;strokeWidth=2;" % C_BLACK
S_MSG_ASYNC = "endArrow=open;html=1;" "strokeColor=%s;strokeWidth=2;" % C_BLACK
S_MSG_RETURN = "dashed=1;endArrow=open;html=1;" "strokeColor=%s;strokeWidth=1;" % C_BLACK
S_FRAGMENT = "shape=umlFrame;html=1;strokeColor=%s;" "strokeWidth=2;fillColor=none;whiteSpace=wrap;" % C_BLACK

# --- Activity Diagram ---
S_ACT_INIT = "ellipse;html=1;" "strokeColor=%s;fillColor=%s;" % (C_BLACK, C_BLACK)
S_ACT_FINAL = "shape=doubleEllipse;html=1;" "strokeColor=%s;fillColor=%s;" % (C_BLACK, C_BLACK)
S_ACT_ACTION = "rounded=1;whiteSpace=wrap;html=1;" "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (
    C_ACT_FILL,
    C_CLASS_STROKE,
)
S_ACT_CALL = (
    "rounded=1;whiteSpace=wrap;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;"
    "shape=mxgraph.flowchart.start_2;" % (C_ACT_FILL, C_CLASS_STROKE)
)
S_ACT_DIAMOND = (
    "rhombus;html=1;"
    "strokeColor=%s;strokeWidth=2;"
    "fillColor=%s;perimeter=rhombusPerimeter;whiteSpace=wrap;" % (C_BLACK, C_WHITE)
)
S_ACT_FORK = "html=1;strokeColor=%s;strokeWidth=3;" "fillColor=%s;" % (C_BLACK, C_BLACK)
S_ACT_ARROW = "endArrow=classic;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK

# --- State Diagram ---
S_ST_INIT = "ellipse;html=1;" "strokeColor=%s;fillColor=%s;" % (C_BLACK, C_BLACK)
S_ST_FINAL = "shape=doubleEllipse;html=1;" "strokeColor=%s;fillColor=%s;" % (C_BLACK, C_BLACK)
S_ST_BOX = (
    "rounded=1;whiteSpace=wrap;html=1;"
    "fillColor=%s;strokeColor=%s;"
    "strokeWidth=2;arcSize=25;" % (C_STATE_FILL, C_STATE_STROKE)
)
S_ST_COMP = (
    "swimlane;fontStyle=1;align=center;startSize=26;"
    "rounded=1;arcSize=12;container=1;collapsible=0;expand=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_IFACE_FILL, C_CLASS_STROKE)
)
S_ST_CHOICE = (
    "rhombus;html=1;" "strokeColor=%s;strokeWidth=2;" "fillColor=%s;perimeter=rhombusPerimeter;" % (C_BLACK, C_WHITE)
)
S_ST_ARROW = "endArrow=classic;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
S_ST_SELF = "endArrow=classic;html=1;" "strokeColor=%s;strokeWidth=2;curved=1;" % C_BLACK

# --- Component Diagram ---
S_COMP_BOX = (
    "shape=mxgraph.uml.component;html=1;whiteSpace=wrap;"
    "strokeColor=%s;fillColor=%s;"
    "strokeWidth=2;" % (C_GRAY_STROKE, C_GRAY_FILL)
)
S_COMP_PROV = "ellipse;html=1;" "strokeColor=%s;fillColor=%s;" "strokeWidth=1;" % (C_BLACK, C_WHITE)
S_COMP_REQ = "ellipse;html=1;" "strokeColor=%s;fillColor=none;" "strokeWidth=2;" % (C_BLACK)
S_COMP_DEP = (
    "endArrow=open;endSize=8;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_COMP_REAL = (
    "endArrow=block;endFill=0;dashed=1;html=1;"
    "strokeColor=%s;strokeWidth=1;"
    "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)

# --- Package Diagram ---
S_PKG_BOX = (
    "shape=folder;html=1;whiteSpace=wrap;fontStyle=1;"
    "tabWidth=42;tabHeight=14;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_ENUM_FILL, C_ENUM_STROKE)
)
S_PKG_IMPORT = (
    "endArrow=open;endSize=8;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_PKG_ACCESS = (
    "endArrow=open;endSize=8;dashed=1;html=1;"
    "strokeColor=%s;strokeWidth=1;"
    "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)

# --- Deployment Diagram ---
S_DEP_NODE = (
    "shape=cube;html=1;whiteSpace=wrap;fontStyle=1;"
    "perimeter=cubePerimeter;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_NODE_FILL, C_NODE_STROKE)
)
S_DEP_DEVICE = (
    "shape=cube;html=1;whiteSpace=wrap;"
    "perimeter=cubePerimeter;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_BLUE_FILL, C_BLUE_STROKE)
)
S_DEP_ARTIFACT = "shape=mxgraph.uml.artifact;html=1;whiteSpace=wrap;" "fillColor=%s;strokeColor=%s;strokeWidth=1;" % (
    C_WHITE,
    C_BLACK,
)
S_DEP_COMP = "rounded=0;whiteSpace=wrap;html=1;" "fillColor=%s;strokeColor=%s;" % (C_BLUE_FILL, C_BLUE_STROKE)
S_DEP_CONN = (
    "endArrow=open;endSize=8;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_DEP_ENV = (
    "swimlane;fontStyle=1;align=center;startSize=24;" "fillColor=none;strokeColor=%s;strokeWidth=2;html=1;" % C_BLACK
)

# --- Use Case Diagram ---
S_UC_ACTOR = (
    "shape=mxgraph.uml.actor;html=1;"
    "fillColor=%s;strokeColor=%s;"
    "verticalLabelPosition=bottom;verticalAlign=top;" % (C_WHITE, C_BLACK)
)
S_UC_CASE = (
    "ellipse;html=1;whiteSpace=wrap;"
    "fillColor=%s;strokeColor=%s;"
    "strokeWidth=2;perimeter=ellipsePerimeter;" % (C_STATE_FILL, C_STATE_STROKE)
)
S_UC_SYSTEM = (
    "rounded=0;html=1;fillColor=none;" "strokeColor=%s;strokeWidth=2;" "verticalAlign=top;fontStyle=1;" % C_BLACK
)
S_UC_ASSOC = "endArrow=none;html=1;strokeColor=%s;strokeWidth=1;" % C_BLACK
S_UC_INCL = (
    "endArrow=open;endSize=8;dashed=1;html=1;"
    "strokeColor=%s;strokeWidth=1;"
    "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)
S_UC_EXTEND = (
    "endArrow=open;endSize=8;dashed=1;html=1;"
    "strokeColor=%s;strokeWidth=1;"
    "edgeStyle=orthogonalEdgeStyle;" % C_BLACK
)

# --- Object Diagram ---
S_OBJ_HDR = (
    "swimlane;fontStyle=5;align=center;startSize=26;"  # 4+1=underline+bold
    "container=1;collapsible=0;expand=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_BLUE_FILL, C_BLUE_STROKE)
)
S_OBJ_ROW = "text;html=1;strokeColor=none;fillColor=none;" "align=left;verticalAlign=middle;spacingLeft=6;"
S_OBJ_DIV = "line;html=1;strokeColor=%s;strokeWidth=1;fillColor=none;" % C_BLUE_STROKE
S_OBJ_LINK = "endArrow=none;html=1;" "strokeColor=%s;strokeWidth=1;" % C_BLACK

# --- Communication ---
S_COMM_OBJ = (
    "swimlane;fontStyle=1;align=center;startSize=24;"
    "container=0;collapsible=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_CLASS_FILL, C_CLASS_STROKE)
)
S_COMM_MSG = "endArrow=open;endSize=8;html=1;" "strokeColor=%s;strokeWidth=2;" % C_BLACK

# --- Composite Structure ---
S_CS_CLASS = (
    "swimlane;fontStyle=1;align=center;startSize=26;"
    "container=1;collapsible=0;expand=0;html=1;"
    "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (C_CLASS_FILL, C_CLASS_STROKE)
)
S_CS_PART = "rounded=0;whiteSpace=wrap;html=1;" "fillColor=%s;strokeColor=%s;" % (C_ABST_FILL, C_ABST_STROKE)
S_CS_PORT = "html=1;strokeColor=%s;fillColor=%s;" "strokeWidth=1;" % (C_BLACK, C_WHITE)
S_CS_CONN = "endArrow=none;html=1;" "strokeColor=%s;strokeWidth=1;" % C_BLACK

# --- Interaction Overview ---
S_IO_REF = "swimlane;fontStyle=1;startSize=20;html=1;" "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (
    C_ENUM_FILL,
    C_ENUM_STROKE,
)
S_IO_INIT = "ellipse;html=1;" "strokeColor=%s;fillColor=%s;" % (C_BLACK, C_BLACK)
S_IO_FINAL = "shape=doubleEllipse;html=1;" "strokeColor=%s;fillColor=%s;" % (C_BLACK, C_BLACK)
S_IO_DECISION = (
    "rhombus;html=1;strokeColor=%s;strokeWidth=2;"
    "fillColor=%s;perimeter=rhombusPerimeter;whiteSpace=wrap;" % (C_BLACK, C_WHITE)
)
S_IO_ARROW = "endArrow=classic;html=1;" "strokeColor=%s;strokeWidth=2;" "edgeStyle=orthogonalEdgeStyle;" % C_BLACK


# ======================================================================
# ID generator
# ======================================================================


class _IDGen:
    def __init__(self, start=2):
        self._n = start

    def __call__(self):
        v = str(self._n)
        self._n += 1
        return v


# ======================================================================
# XML builder helpers
# ======================================================================


def _esc(text):
    """Escape XML special characters for cell values."""
    s = str(text)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    return s


def _vertex(cid, value, style, x, y, w, h, parent="1"):
    """Create a vertex mxCell string."""
    return (
        '    <mxCell id="%s" value="%s" style="%s" vertex="1" parent="%s">\n'
        '      <mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry" />\n'
        "    </mxCell>" % (cid, _esc(value), style, parent, x, y, w, h)
    )


def _vertex_child(cid, value, style, x, y, w, h, parent):
    """Vertex that is a child of a container (uses parent-relative coords)."""
    return (
        '    <mxCell id="%s" value="%s" style="%s" vertex="1" parent="%s">\n'
        '      <mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry" />\n'
        "    </mxCell>" % (cid, _esc(value), style, parent, x, y, w, h)
    )


def _edge(cid, value, style, src, tgt, parent="1"):
    """Create an edge mxCell string connecting two cells."""
    return (
        '    <mxCell id="%s" value="%s" style="%s" edge="1" '
        'source="%s" target="%s" parent="%s">\n'
        '      <mxGeometry relative="1" as="geometry" />\n'
        "    </mxCell>" % (cid, _esc(value), style, src, tgt, parent)
    )


def _edge_points(cid, value, style, x1, y1, x2, y2, parent="1"):
    """Create an edge with explicit source/target points (no cell attachment).
    Used in sequence diagrams where messages connect at specific Y positions.
    """
    return (
        '    <mxCell id="%s" value="%s" style="%s" edge="1" parent="%s">\n'
        '      <mxGeometry relative="1" as="geometry">\n'
        '        <mxPoint x="%s" y="%s" as="sourcePoint" />\n'
        '        <mxPoint x="%s" y="%s" as="targetPoint" />\n'
        "      </mxGeometry>\n"
        "    </mxCell>" % (cid, _esc(value), style, parent, x1, y1, x2, y2)
    )


def _wrap_mxfile(cells, title="Diagram", diagram_id="diagram1"):
    """Wrap cells in proper draw.io mxfile XML (draw.io v24 format)."""
    body = "\n".join(cells)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile host="app.diagrams.net" type="diagram" version="24.0.0">\n'
        '  <diagram id="%s" name="%s">\n'
        '    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        'pageWidth="1169" pageHeight="827" math="0" shadow="0">\n'
        "      <root>\n"
        '        <mxCell id="0" />\n'
        '        <mxCell id="1" parent="0" />\n'
        "%s\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>"
    ) % (diagram_id, _esc(title), body)


# ======================================================================
# DrawioConverter - Public API
# ======================================================================
