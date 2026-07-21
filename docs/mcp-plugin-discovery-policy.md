# MCP Plugin Discovery Policy

**Version:** 1.0.0
**Priority:** MEDIUM
**Status:** ACTIVE
**Updated:** 2026-03-18

---

## Purpose

Defines how MCP (Model Context Protocol) servers and plugins are discovered, loaded,
and made available to the pipeline. MCP servers provide tool capabilities (git, GitHub,
session management, etc.) that the pipeline orchestrates.

---

## Discovery Process

### Step 1: Load Plugin Registry

1. Import `MCPPluginLoader` from `mcp_plugin_loader` module
2. Call `loader.discover_plugins()` to scan plugin directories
3. Call `loader.get_available_mcps()` to list all available MCP servers

### Step 2: Scan Locations

| Location | Purpose |
|----------|---------|
| `~/.claude/mcp/plugins/` | User-installed MCP plugins |
| `~/.claude/settings.json` | Registered MCP server configurations |

### Step 3: Check Critical MCPs

Check availability of critical MCP servers:
- **filesystem** MCP: Enables AUTO-ROUTE mode in pre-tool-enforcer

---

## AUTO-ROUTE Mode

When the `filesystem` MCP is available:
- Enable AUTO-ROUTE mode in `pre-tool-enforcer.py`
- Pre-tool hook can route file operations to MCP filesystem server
- Provides additional file operation capabilities beyond standard tools

---

## MCP Server Registry (13 Servers)

| Server | Tools | Critical |
|--------|-------|----------|
| git-ops | 14 | YES |
| github-api | 12 | YES |
| session-mgr | 14 | YES |
| policy-enforcement | 11 | YES |
| token-optimizer | 10 | NO |
| pre-tool-gate | 8 | NO |
| post-tool-tracker | 6 | NO |
| standards-loader | 7 | NO |
| uml-diagram | 15 | NO |
| drawio-diagram | 5 | NO |
| jira-api | 10 | NO |
| jenkins-ci | 10 | NO |
| figma-api | 10 | NO |

---

## Error Handling

| Scenario | Action | State Value |
|----------|--------|-------------|
| MCPPluginLoader not available | Skip discovery gracefully | `mcp_initialization_status: "SKIPPED"` |
| Plugin scan fails | Log error, continue pipeline | `mcp_initialization_status: "ERROR"` |
| Partial discovery | Use what's available | `mcp_initialization_status: "PARTIAL"` |
| All MCPs discovered | Full capability | `mcp_initialization_status: "OK"` |

**Non-blocking:** MCP discovery failures NEVER block the pipeline.

---

## State Fields

| Field | Type | Purpose |
|-------|------|---------|
| `mcp_servers_available` | list | Discovered MCP server names |
| `mcp_filesystem_enabled` | bool | Whether filesystem MCP available |
| `mcp_plugins_path` | str | Plugin directory path |
| `mcp_cache_dir` | str | MCP cache directory |
| `mcp_discovered_count` | int | Total MCPs found |
| `mcp_initialization_status` | str | "OK", "PARTIAL", "ERROR", "SKIPPED" |
| `mcp_auto_routing_enabled` | bool | AUTO-ROUTE mode active |

---

## Version Sync

All MCP servers share the same version number, managed by `scripts/sync-version.py`.
Version must match the project version in `version.json`.
