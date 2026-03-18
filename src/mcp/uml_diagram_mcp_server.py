"""
UML Diagram MCP Server - Auto-generate 12 UML diagram types from codebase.

Tier 1 (AST-based): Class, Package, Component
Tier 2 (AST + LLM): Sequence, Activity, State
Tier 3 (LLM-powered): Use Case, Object, Deployment, Communication,
                       Composite Structure, Interaction Overview

14 tools total (12 diagram types + generate_all + render).
"""

import sys
from pathlib import Path
from typing import Optional

# Path setup for local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP
from base.decorators import mcp_tool_handler

mcp = FastMCP(
    "uml-diagram",
    instructions=(
        "UML diagram generation from codebase analysis. "
        "Generates 12 UML diagram types using AST analysis, "
        "LLM enrichment, and Kroki.io rendering."
    ),
)


def _get_generator(project_path, output_dir="docs/uml"):
    """Lazy import and create UMLDiagramGenerator."""
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from langgraph_engine.uml_generators import UMLDiagramGenerator
    return UMLDiagramGenerator(project_path, output_dir)


def _get_renderer():
    """Lazy import and create KrokiRenderer."""
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from langgraph_engine.uml_generators import KrokiRenderer
    return KrokiRenderer()


# ==================================================================
# Tier 1: AST-based diagrams (no LLM required)
# ==================================================================

@mcp.tool()
@mcp_tool_handler
def generate_class_diagram(
    project_path: str,
    scope: str = "all",
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML class diagram from Python AST analysis.

    Produces Mermaid classDiagram syntax showing classes, attributes,
    methods, and inheritance. Saved to docs/uml/class-diagram.md.

    Args:
        project_path: Root path of the project to analyze.
        scope: "all" for full project, or a specific directory/file path.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_class_diagram(scope=scope)
    path = gen.save_diagram("class-diagram", syntax)
    return {
        "diagram_type": "class",
        "format": "mermaid",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_package_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML package diagram from module import analysis.

    Produces Mermaid flowchart showing module dependencies.
    Saved to docs/uml/package-diagram.md.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_package_diagram()
    path = gen.save_diagram("package-diagram", syntax)
    return {
        "diagram_type": "package",
        "format": "mermaid",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_component_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML component diagram from project structure.

    Produces Mermaid flowchart with subgraphs representing components.
    Saved to docs/uml/component-diagram.md.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_component_diagram()
    path = gen.save_diagram("component-diagram", syntax)
    return {
        "diagram_type": "component",
        "format": "mermaid",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


# ==================================================================
# Tier 2: AST + LLM hybrid diagrams
# ==================================================================

@mcp.tool()
@mcp_tool_handler
def generate_sequence_diagram(
    project_path: str,
    entry_function: str = "",
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML sequence diagram from call chain analysis.

    Uses AST to extract call chains and optionally LLM to enrich labels.
    Produces Mermaid sequenceDiagram syntax.

    Args:
        project_path: Root path of the project to analyze.
        entry_function: Optional entry function to trace from.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_sequence_diagram(context=entry_function)
    path = gen.save_diagram("sequence-diagram", syntax)
    return {
        "diagram_type": "sequence",
        "format": "mermaid",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_activity_diagram(
    project_path: str,
    function_path: str = "",
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML activity diagram from function logic.

    Uses LLM to analyze control flow and produce Mermaid flowchart TD.

    Args:
        project_path: Root path of the project to analyze.
        function_path: Optional file:function to analyze (e.g., "src/main.py:run").
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)

    func_code = ""
    if function_path and ":" in function_path:
        file_part, func_name = function_path.rsplit(":", 1)
        file_full = Path(project_path) / file_part
        if file_full.is_file():
            func_code = file_full.read_text(
                encoding="utf-8", errors="replace"
            )[:3000]

    syntax = gen.generate_activity_diagram(func_code)
    path = gen.save_diagram("activity-diagram", syntax)
    return {
        "diagram_type": "activity",
        "format": "mermaid",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_state_diagram(
    project_path: str,
    context: str = "",
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML state diagram from state pattern detection.

    Uses LLM to identify states and transitions, produces
    Mermaid stateDiagram-v2 syntax.

    Args:
        project_path: Root path of the project to analyze.
        context: Additional context about states in the system.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_state_diagram(context=context)
    path = gen.save_diagram("state-diagram", syntax)
    return {
        "diagram_type": "state",
        "format": "mermaid",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


# ==================================================================
# Tier 3: LLM-powered diagrams
# ==================================================================

@mcp.tool()
@mcp_tool_handler
def generate_usecase_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML use case diagram from requirements docs.

    Reads SRS.md and README.md, uses LLM to produce PlantUML
    use case diagram syntax.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_usecase_diagram()
    path = gen.save_diagram("usecase-diagram", syntax)
    return {
        "diagram_type": "usecase",
        "format": "plantuml",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_object_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML object diagram showing class instances.

    Uses AST class extraction + LLM to produce PlantUML object diagram
    with realistic field values.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_object_diagram()
    path = gen.save_diagram("object-diagram", syntax)
    return {
        "diagram_type": "object",
        "format": "plantuml",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_deployment_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML deployment diagram from infrastructure files.

    Reads Dockerfile, docker-compose, K8s manifests, and uses LLM
    to produce PlantUML deployment diagram.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_deployment_diagram()
    path = gen.save_diagram("deployment-diagram", syntax)
    return {
        "diagram_type": "deployment",
        "format": "plantuml",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_communication_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML communication diagram from module interactions.

    Uses dependency graph + LLM to show numbered message flows
    between modules in PlantUML.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_communication_diagram()
    path = gen.save_diagram("communication-diagram", syntax)
    return {
        "diagram_type": "communication",
        "format": "plantuml",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_composite_structure_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML composite structure diagram.

    Shows internal structure of classes (ports, parts, connectors)
    using PlantUML.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_composite_structure_diagram()
    path = gen.save_diagram("composite-structure-diagram", syntax)
    return {
        "diagram_type": "composite_structure",
        "format": "plantuml",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_interaction_overview_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a UML interaction overview diagram.

    Combines activity and sequence diagram elements showing
    combined interaction flows in PlantUML.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    syntax = gen.generate_interaction_overview()
    path = gen.save_diagram("interaction-overview-diagram", syntax)
    return {
        "diagram_type": "interaction_overview",
        "format": "plantuml",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


@mcp.tool()
@mcp_tool_handler
def generate_call_graph_diagram(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate a Mermaid flowchart showing the project call graph.

    Tier 1 diagram: AST-based, no LLM required. Classes are rendered
    as subgraphs with methods as nodes. Call edges connect methods
    across classes. Entry points (public methods not called by others)
    are highlighted with bold borders. High-complexity methods
    (cyclomatic complexity >= 5) are highlighted in red.

    Limits output to 40 methods and 60 edges for readability.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)

    # generate_call_graph_diagram uses _get_call_graph() internally
    # which handles lazy import and fallback to stub
    syntax = gen.generate_call_graph_diagram()
    path = gen.save_diagram("call-graph-diagram", syntax)
    return {
        "diagram_type": "call_graph",
        "format": "mermaid",
        "output_file": path,
        "lines": len(syntax.split("\n")),
    }


# ==================================================================
# Utility tools
# ==================================================================

@mcp.tool()
@mcp_tool_handler
def generate_all_diagrams(
    project_path: str,
    output_dir: str = "docs/uml",
) -> dict:
    """Generate all applicable UML diagrams for a project.

    Generates Tier 1 (AST-based) diagrams always, and attempts
    Tier 2/3 (LLM-powered) diagrams on best-effort basis.

    Args:
        project_path: Root path of the project to analyze.
        output_dir: Output directory relative to project root.
    """
    gen = _get_generator(project_path, output_dir)
    results = gen.generate_all()

    saved = []
    for name, syntax in results.items():
        path = gen.save_diagram(name, syntax)
        saved.append({"name": name, "file": path})

    return {
        "diagrams_generated": len(saved),
        "diagrams": saved,
        "output_dir": str(gen.output_dir),
    }


@mcp.tool()
@mcp_tool_handler
def render_diagram(
    diagram_text: str,
    diagram_type: str = "plantuml",
    output_format: str = "svg",
    output_path: str = "",
) -> dict:
    """Render any diagram via Kroki.io free API.

    Converts PlantUML/Mermaid source to SVG/PNG using the free
    Kroki.io rendering service (no Java required).

    Args:
        diagram_text: PlantUML or Mermaid source text.
        diagram_type: "plantuml", "mermaid", "graphviz", etc.
        output_format: "svg" or "png".
        output_path: Optional file path to save rendered output.
    """
    renderer = _get_renderer()

    if output_path:
        result_path = renderer.render_to_file(
            diagram_text, output_path, diagram_type, output_format
        )
        if result_path:
            return {
                "rendered": True,
                "output_path": result_path,
                "format": output_format,
            }
        return {
            "rendered": False,
            "error": "Kroki rendering failed",
        }
    else:
        data = renderer.render(diagram_text, diagram_type, output_format)
        if data:
            return {
                "rendered": True,
                "format": output_format,
                "size_bytes": len(data),
                "note": "Use output_path parameter to save to file",
            }
        return {
            "rendered": False,
            "error": "Kroki rendering failed",
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
