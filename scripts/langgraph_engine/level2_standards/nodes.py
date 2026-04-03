"""Level 2 Standards System - Node functions.

Canonical location: langgraph_engine/level2_standards/nodes.py
Windows-safe: ASCII only, no Unicode characters.
"""

import time

from .helpers import (
    _LEVEL2_CLAUDE_HOME,
    _LEVEL2_POLICIES_DIR,
    _detect_linter,
    _run_flake8_check,
    _run_ruff_check,
    detect_project_type,
    load_policies_from_directory,
    run_standards_loader_script,
    write_level_log,
)

# ============================================================================
# LEVEL 2 NODES (calling ACTUAL standards loader)
# ============================================================================


def node_common_standards(state):
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
        updates["pipeline"] = list(existing_pipeline) + [
            {
                "node": "node_common_standards",
                "policies_loaded": level2_count,
                "script_standards": script_count,
                "total": updates["standards_count"],
            }
        ]

        write_level_log(
            state,
            "level2",
            "common-standards",
            "OK",
            time.time() - _step_start,
            {
                "standards_count": updates["standards_count"],
                "policies_loaded": level2_count,
            },
        )
        return updates

    except Exception as e:
        updates["standards_loaded"] = False
        updates["standards_error"] = str(e)
        write_level_log(state, "level2", "common-standards", "FAILED", time.time() - _step_start, None, str(e))
        return updates


def node_java_standards(state):
    """Load Java-specific standards."""
    _step_start = time.time()
    updates = {}
    try:
        # Load Java standards from policies/02-standards-system/
        policies_dir = _LEVEL2_POLICIES_DIR / "02-standards-system"

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
            ],
        }

        existing_pipeline = state.get("pipeline") or []
        updates["pipeline"] = list(existing_pipeline) + [
            {"node": "node_java_standards", "java_standards_loaded": len(java_standards)}
        ]

        write_level_log(
            state,
            "level2",
            "java-standards",
            "OK",
            time.time() - _step_start,
            {
                "java_standards_loaded": True,
                "patterns_count": len(java_standards),
            },
        )
        return updates

    except Exception as e:
        updates["java_standards_loaded"] = False
        updates["java_standards_error"] = str(e)
        write_level_log(state, "level2", "java-standards", "FAILED", time.time() - _step_start, None, str(e))
        return updates


def node_tool_optimization_standards(state):
    """Level 2: Load tool optimization standards.

    Defines HOW tools must be used. Enforced by PreToolUse hook on every call.
    """
    _step_start = time.time()
    rules = {
        "read_max_lines": 500,  # Read tool: max lines per call
        "read_max_bytes": 51200,  # Read tool: max bytes (50KB)
        "grep_max_matches": 50,  # Grep tool: max matches (head_limit)
        "grep_max_results": 100,  # Grep tool: absolute max with output_mode
        "search_max_results": 10,  # Search: max results
        "cache_after_n_reads": 3,  # Reuse cache after 3 reads of same file
        "bash_find_head": 20,  # find commands: pipe to | head -20
    }

    updates = {
        "tool_optimization_rules": rules,
        "tool_optimization_loaded": True,
    }

    existing_pipeline = state.get("pipeline") or []
    updates["pipeline"] = list(existing_pipeline) + [
        {"node": "node_tool_optimization_standards", "rules_loaded": list(rules.keys()), "total_rules": len(rules)}
    ]

    write_level_log(
        state,
        "level2",
        "tool-optimization",
        "OK",
        time.time() - _step_start,
        {
            "rules_loaded": len(rules),
        },
    )
    return updates


def node_mcp_plugin_discovery(state):
    """Level 2: Discover and load MCP plugin registry.

    Scans ~/.claude/mcp/plugins/ for available MCP servers and populates
    state with available MCPs. Enables AUTO-ROUTE mode in pre-tool-enforcer.py
    if Filesystem MCP is available.
    """
    _step_start = time.time()
    updates = {}

    try:
        from .mcp_plugin_loader import MCPPluginError, MCPPluginLoader  # noqa: F401

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
            "mcp_cache_dir": str(_LEVEL2_CLAUDE_HOME / "mcp" / "cache"),
            "mcp_discovered_count": len(plugins),
            "mcp_initialization_status": "PARTIAL" if len(plugins) > 0 else "ERROR",
            "mcp_auto_routing_enabled": filesystem_enabled,  # Enable AUTO-ROUTE if filesystem available
        }

        existing_pipeline = state.get("pipeline") or []
        updates["pipeline"] = list(existing_pipeline) + [
            {
                "node": "node_mcp_plugin_discovery",
                "plugins_discovered": len(plugins),
                "filesystem_mcp_enabled": filesystem_enabled,
                "plugins_list": [p["short_name"] for p in available_mcps],
            }
        ]

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

    write_level_log(
        state,
        "level2",
        "mcp-discovery",
        "OK" if updates.get("mcp_discovered_count", 0) > 0 else "FAILED",
        time.time() - _step_start,
        {
            "mcp_discovered_count": updates.get("mcp_discovered_count", 0),
            "plugins_found": updates.get("mcp_initialization_status", "ERROR"),
        },
    )
    return updates


# ============================================================================
# STANDARDS ENFORCEMENT NODE
# ============================================================================


def node_standards_enforcement(state):
    """Run linting on project source files and store violations in state.

    Non-blocking: violations are warnings, not pipeline blockers.
    Results feed into Step 11 code review for targeted feedback.

    Checks available linters in order: ruff -> flake8.
    Skips Java and TypeScript linting (optional, rarely available in env).
    """
    _step_start = time.time()
    updates = {}

    try:
        project_root = state.get("project_root", ".")

        linter_name, _ = _detect_linter()

        if linter_name is None:
            updates["standards_enforcement_ran"] = False
            updates["standards_violations"] = []
            updates["standards_violations_count"] = 0
            updates["standards_linter_used"] = "none"
            write_level_log(
                state,
                "level2",
                "standards-enforcement",
                "SKIPPED",
                time.time() - _step_start,
                {"reason": "no linter found"},
            )
            return updates

        if linter_name == "ruff":
            violations = _run_ruff_check(project_root)
        else:
            violations = _run_flake8_check(project_root)

        updates["standards_enforcement_ran"] = True
        updates["standards_violations"] = violations
        updates["standards_violations_count"] = len(violations)
        updates["standards_linter_used"] = linter_name

        existing_pipeline = state.get("pipeline") or []
        updates["pipeline"] = list(existing_pipeline) + [
            {
                "node": "node_standards_enforcement",
                "linter": linter_name,
                "violations_found": len(violations),
            }
        ]

        write_level_log(
            state,
            "level2",
            "standards-enforcement",
            "OK",
            time.time() - _step_start,
            {
                "linter": linter_name,
                "violations_count": len(violations),
            },
        )

    except Exception as e:
        # Always non-blocking
        updates["standards_enforcement_ran"] = False
        updates["standards_violations"] = []
        updates["standards_violations_count"] = 0
        updates["standards_linter_used"] = "none"
        write_level_log(state, "level2", "standards-enforcement", "FAILED", time.time() - _step_start, None, str(e))

    return updates
