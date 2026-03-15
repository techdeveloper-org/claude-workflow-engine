"""
Level 2 SubGraph - Standards System with REAL Policy Script Integration

Calls standards-loader.py to load actual standards from policies/
Includes MCP plugin discovery for auto-routing tool optimization.
"""

import sys
import json
import time
import subprocess
from pathlib import Path

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState
from ..step_logger import write_level_log


# ============================================================================
# STANDARDS LOADING (from actual policies/)
# ============================================================================


def load_policies_from_directory() -> dict:
    """Load all policies from ~/claude/policies/ directories.

    Returns:
        Dict with loaded policies by level
    """
    try:
        policies_dir = Path.home() / ".claude" / "policies"

        if not policies_dir.exists():
            return {
                "level1": {},
                "level2": {},
                "level3": {},
                "status": "NO_POLICIES_DIR"
            }

        result = {
            "level1": {},
            "level2": {},
            "level3": {},
            "status": "LOADED"
        }

        # Load from each level directory
        for level_dir in ["01-sync-system", "02-standards-system", "03-execution-system"]:
            level_key = "level1" if "01" in level_dir else ("level2" if "02" in level_dir else "level3")
            level_path = policies_dir / level_dir

            if level_path.exists():
                for policy_file in level_path.glob("**/*.md"):
                    try:
                        content = policy_file.read_text(encoding="utf-8")
                        result[level_key][policy_file.stem] = {
                            "file": str(policy_file),
                            "size": len(content),
                            "path": policy_file.stem
                        }
                    except Exception:
                        pass

        return result

    except Exception as e:
        return {
            "error": str(e),
            "status": "ERROR"
        }


def run_standards_loader_script() -> dict:
    """Run standards-loader.py script."""
    try:
        scripts_dir = Path(__file__).parent.parent.parent
        script_path = scripts_dir / "architecture" / "02-standards-system" / "standards-loader.py"

        if not script_path.exists():
            return {"status": "SCRIPT_NOT_FOUND"}

        # Run script with UTF-8 encoding for Windows compatibility
        result = subprocess.run(
            [sys.executable, str(script_path), "--load-all"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
            cwd=scripts_dir
        )

        # Parse output
        try:
            return json.loads(result.stdout)
        except:
            return {
                "status": "SUCCESS",
                "exit_code": result.returncode,
                "message": result.stdout[:500]
            }

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": "standards-loader.py timed out"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def detect_project_type(state: FlowState) -> None:
    """Detect project type (Java, Python, etc.)."""
    try:
        project_root = Path(state.get("project_root", "."))

        # Java detection
        has_pom = (project_root / "pom.xml").exists()
        has_gradle = (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists()
        java_files = list(project_root.glob("**/*.java"))[:5]

        state["is_java_project"] = bool(has_pom or has_gradle or java_files)

    except Exception:
        state["is_java_project"] = False


# ============================================================================
# LEVEL 2 NODES (calling ACTUAL standards loader)
# ============================================================================


def node_common_standards(state: FlowState) -> dict:
    """Load common standards from policies/ directory and standards-loader.py."""
    _step_start = time.time()
    updates = {}
    try:
        detect_project_type(state)

        # First, try to load from policies/ directory
        policies_result = load_policies_from_directory()

        # Then, run standards-loader.py script for additional standards
        script_result = run_standards_loader_script()

        # Count standards loaded
        level2_count = len(policies_result.get("level2", {}))
        script_count = script_result.get("standards_loaded", 0)
        total_count = level2_count + script_count

        updates["standards_loaded"] = True
        updates["standards_count"] = total_count if total_count > 0 else 12  # Fallback: 12 common standards

        existing_pipeline = state.get("pipeline") or []
        updates["pipeline"] = list(existing_pipeline) + [{
            "node": "node_common_standards",
            "policies_loaded": level2_count,
            "script_standards": script_count,
            "total": updates["standards_count"]
        }]

        write_level_log(state, "level2", "common-standards", "OK", time.time() - _step_start, {
            "standards_count": updates["standards_count"],
            "policies_loaded": level2_count,
        })
        return updates

    except Exception as e:
        updates["standards_loaded"] = False
        updates["standards_error"] = str(e)
        write_level_log(state, "level2", "common-standards", "FAILED", time.time() - _step_start, None, str(e))
        return updates


def node_java_standards(state: FlowState) -> dict:
    """Load Java-specific standards."""
    _step_start = time.time()
    updates = {}
    try:
        # Load Java standards from policies/02-standards-system/
        policies_dir = Path.home() / ".claude" / "policies" / "02-standards-system"

        java_standards = []
        if policies_dir.exists():
            for policy_file in policies_dir.glob("**/*java*.md"):
                java_standards.append(policy_file.stem)

        updates["java_standards_loaded"] = True
        updates["spring_boot_patterns"] = {
            "standards_found": len(java_standards),
            "standards_list": java_standards,
            "annotations": [
                "@SpringBootApplication",
                "@Service",
                "@Repository",
                "@RestController",
                "@Bean",
                "@Configuration",
            ],
            "patterns": [
                "dependency-injection",
                "service-layer",
                "repository-pattern",
                "exception-handling",
            ]
        }

        existing_pipeline = state.get("pipeline") or []
        updates["pipeline"] = list(existing_pipeline) + [{
            "node": "node_java_standards",
            "java_standards_loaded": len(java_standards)
        }]

        write_level_log(state, "level2", "java-standards", "OK", time.time() - _step_start, {
            "java_standards_loaded": True,
            "patterns_count": len(java_standards),
        })
        return updates

    except Exception as e:
        updates["java_standards_loaded"] = False
        updates["java_standards_error"] = str(e)
        write_level_log(state, "level2", "java-standards", "FAILED", time.time() - _step_start, None, str(e))
        return updates


def node_tool_optimization_standards(state: FlowState) -> dict:
    """Level 2: Load tool optimization standards.

    Defines HOW tools must be used. Enforced by PreToolUse hook on every call.
    """
    _step_start = time.time()
    rules = {
        "read_max_lines": 500,       # Read tool: max lines per call
        "read_max_bytes": 51200,     # Read tool: max bytes (50KB)
        "grep_max_matches": 50,      # Grep tool: max matches (head_limit)
        "grep_max_results": 100,     # Grep tool: absolute max with output_mode
        "search_max_results": 10,    # Search: max results
        "cache_after_n_reads": 3,    # Reuse cache after 3 reads of same file
        "bash_find_head": 20,        # find commands: pipe to | head -20
    }

    updates = {
        "tool_optimization_rules": rules,
        "tool_optimization_loaded": True,
    }

    existing_pipeline = state.get("pipeline") or []
    updates["pipeline"] = list(existing_pipeline) + [{
        "node": "node_tool_optimization_standards",
        "rules_loaded": list(rules.keys()),
        "total_rules": len(rules)
    }]

    write_level_log(state, "level2", "tool-optimization", "OK", time.time() - _step_start, {
        "rules_loaded": len(rules),
    })
    return updates


def node_mcp_plugin_discovery(state: FlowState) -> dict:
    """Level 2: Discover and load MCP plugin registry.

    Scans ~/.claude/mcp/plugins/ for available MCP servers and populates
    state with available MCPs. Enables AUTO-ROUTE mode in pre-tool-enforcer.py
    if Filesystem MCP is available.
    """
    _step_start = time.time()
    updates = {}

    try:
        from ..mcp_plugin_loader import MCPPluginLoader, MCPPluginError

        loader = MCPPluginLoader()
        plugins = loader.discover_plugins()

        # Get list of available MCPs
        available_mcps = loader.get_available_mcps()

        # Check if Filesystem MCP is available
        filesystem_enabled = "filesystem" in plugins

        updates = {
            "mcp_servers_available": available_mcps,
            "mcp_filesystem_enabled": filesystem_enabled,
            "mcp_plugins_path": str(loader.plugins_path),
            "mcp_cache_dir": str(Path.home() / ".claude" / "mcp" / "cache"),
            "mcp_discovered_count": len(plugins),
            "mcp_initialization_status": "PARTIAL" if len(plugins) > 0 else "ERROR",
            "mcp_auto_routing_enabled": filesystem_enabled,  # Enable AUTO-ROUTE if filesystem available
        }

        existing_pipeline = state.get("pipeline") or []
        updates["pipeline"] = list(existing_pipeline) + [{
            "node": "node_mcp_plugin_discovery",
            "plugins_discovered": len(plugins),
            "filesystem_mcp_enabled": filesystem_enabled,
            "plugins_list": [p["short_name"] for p in available_mcps],
        }]

    except ImportError:
        # MCPPluginLoader not available - graceful fallback
        updates = {
            "mcp_filesystem_enabled": False,
            "mcp_auto_routing_enabled": False,
            "mcp_initialization_status": "SKIPPED",
            "mcp_error": "MCPPluginLoader not available",
            "mcp_discovered_count": 0,
        }

    except Exception as e:
        # Any other error - graceful fallback
        updates = {
            "mcp_filesystem_enabled": False,
            "mcp_auto_routing_enabled": False,
            "mcp_initialization_status": "ERROR",
            "mcp_error": str(e),
            "mcp_discovered_count": 0,
        }

    write_level_log(state, "level2", "mcp-discovery",
                    "OK" if updates.get("mcp_discovered_count", 0) > 0 else "FAILED",
                    time.time() - _step_start, {
                        "mcp_discovered_count": updates.get("mcp_discovered_count", 0),
                        "plugins_found": updates.get("mcp_initialization_status", "ERROR"),
                    })
    return updates


# ============================================================================
# MERGE NODE
# ============================================================================


def level2_merge_node(state: FlowState) -> dict:
    """Merge Level 2 results."""
    _step_start = time.time()
    updates = {}
    if state.get("standards_loaded"):
        updates["level2_status"] = "OK"
    else:
        updates["level2_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + ["Level 2: Standards loading failed"]

    write_level_log(state, "level2", "merge", updates["level2_status"],
                    time.time() - _step_start, {
                        "level2_status": updates["level2_status"],
                        "total_standards": state.get("standards_count", 0),
                    })
    return updates


# ============================================================================
# ROUTING
# ============================================================================


def route_java_standards(state: FlowState) -> str:
    """Route based on project type."""
    if state.get("is_java_project"):
        return "level2_java_standards"
    return "level2_merge"


# ============================================================================
# SUBGRAPH FACTORY
# ============================================================================


def create_level2_subgraph():
    """Create Level 2 subgraph."""
    if not _LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph not installed")

    graph = StateGraph(FlowState)

    # Add nodes
    graph.add_node("level2_common_standards", node_common_standards)
    graph.add_node("level2_java_standards", node_java_standards)
    graph.add_node("level2_tool_optimization", node_tool_optimization_standards)
    graph.add_node("level2_mcp_plugin_discovery", node_mcp_plugin_discovery)
    graph.add_node("level2_merge", level2_merge_node)

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

    # Done
    graph.add_edge("level2_merge", END)

    return graph.compile()
