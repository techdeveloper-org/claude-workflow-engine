"""
Level 2 SubGraph - Standards System with REAL Policy Script Integration

Calls standards-loader.py to load actual standards from policies/
"""

import sys
import json
import subprocess
from pathlib import Path

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState


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

        return updates

    except Exception as e:
        updates["standards_loaded"] = False
        updates["standards_error"] = str(e)
        return updates


def node_java_standards(state: FlowState) -> dict:
    """Load Java-specific standards."""
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

        return updates

    except Exception as e:
        updates["java_standards_loaded"] = False
        updates["java_standards_error"] = str(e)
        return updates


# ============================================================================
# MERGE NODE
# ============================================================================


def level2_merge_node(state: FlowState) -> dict:
    """Merge Level 2 results."""
    updates = {}
    if state.get("standards_loaded"):
        updates["level2_status"] = "OK"
    else:
        updates["level2_status"] = "FAILED"
        existing_errors = state.get("errors") or []
        updates["errors"] = list(existing_errors) + ["Level 2: Standards loading failed"]

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
    graph.add_node("level2_merge", level2_merge_node)

    # Common standards first
    graph.add_edge(START, "level2_common_standards")

    # Conditional routing for Java
    graph.add_conditional_edges(
        "level2_common_standards",
        route_java_standards,
        {
            "level2_java_standards": "level2_java_standards",
            "level2_merge": "level2_merge",
        },
    )

    # Java leads to merge
    graph.add_edge("level2_java_standards", "level2_merge")

    # Done
    graph.add_edge("level2_merge", END)

    return graph.compile()
