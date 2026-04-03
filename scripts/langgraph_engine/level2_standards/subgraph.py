"""Level 2 Standards System - Subgraph factory.

Canonical location: langgraph_engine/level2_standards/subgraph.py
Windows-safe: ASCII only, no Unicode characters.
"""

from .helpers import _LANGGRAPH_AVAILABLE
from .nodes import (
    node_common_standards,
    node_java_standards,
    node_mcp_plugin_discovery,
    node_standards_enforcement,
    node_tool_optimization_standards,
)
from .routing import level2_merge_node, route_java_standards


def create_level2_subgraph():
    """Create Level 2 subgraph."""
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    from langgraph.graph import END, START, StateGraph

    from ..flow_state import FlowState

    graph = StateGraph(FlowState)

    # Add nodes
    graph.add_node("level2_common_standards", node_common_standards)
    graph.add_node("level2_java_standards", node_java_standards)
    graph.add_node("level2_tool_optimization", node_tool_optimization_standards)
    graph.add_node("level2_mcp_plugin_discovery", node_mcp_plugin_discovery)
    graph.add_node("level2_merge", level2_merge_node)
    graph.add_node("level2_standards_enforcement", node_standards_enforcement)

    # Common standards and tool optimization run in parallel
    graph.add_edge(START, "level2_common_standards")
    graph.add_edge(START, "level2_tool_optimization")
    # MCP plugin discovery also runs in parallel
    graph.add_edge(START, "level2_mcp_plugin_discovery")

    # Conditional routing for Java (from common standards)
    graph.add_conditional_edges(
        "level2_common_standards",
        route_java_standards,
        {
            "level2_java_standards": "level2_java_standards",
            "level2_merge": "level2_merge",
        },
    )

    # Java, tool optimization, and MCP plugin discovery all lead to merge
    graph.add_edge("level2_java_standards", "level2_merge")
    graph.add_edge("level2_tool_optimization", "level2_merge")
    graph.add_edge("level2_mcp_plugin_discovery", "level2_merge")

    # Standards enforcement runs AFTER merge, BEFORE Level 3
    graph.add_edge("level2_merge", "level2_standards_enforcement")

    # Done
    graph.add_edge("level2_standards_enforcement", END)

    return graph.compile()
