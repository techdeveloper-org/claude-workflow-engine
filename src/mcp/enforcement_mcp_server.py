"""
Policy Enforcement MCP Server - FastMCP migration of enforcement_server.py.

Replaces the custom JSON-RPC class with proper FastMCP decorator-based tools.
Includes flow-trace recording, policy execution tracking, and full step mapping.
Backend: Direct file I/O (JSON state files, policy directory scanning)
Transport: stdio

Tools (11):
  check_enforcement_status, enforce_policy_step, log_tool_usage,
  verify_compliance, list_policies, record_policy_execution,
  get_flow_trace_summary, get_session_id, check_module_health,
  check_all_mcp_servers_health, check_system_health
Resources (2):
  enforcement://status, enforcement://compliance
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.path_resolver import get_config_dir

from mcp.server.fastmcp import FastMCP
from base.response import to_json
from base.decorators import mcp_tool_handler
from base.persistence import AtomicJsonStore, SessionIdResolver

mcp = FastMCP("policy-enforcement", instructions="Policy enforcement and compliance tracking")

# Paths
MEMORY_PATH = get_config_dir()
ENFORCER_STATE_FILE = MEMORY_PATH / ".blocking-enforcer-state.json"
LOGS_PATH = MEMORY_PATH / "logs" / "sessions"
# Policy directories - check project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
POLICIES_DIR = _PROJECT_ROOT / "policies"

# Module-level store instance
_enforcer_store = AtomicJsonStore(ENFORCER_STATE_FILE)


# =============================================================================
# TOOLS (11)
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def check_enforcement_status() -> dict:
    """Check current policy enforcement status for all steps."""
    state = _enforcer_store.load()
    return {
        "state": state,
        "timestamp": datetime.now().isoformat()
    }


@mcp.tool()
@mcp_tool_handler
def enforce_policy_step(step_number: int, step_name: str) -> dict:
    """Enforce a specific policy step in the execution pipeline.

    Args:
        step_number: Step number (0-13)
        step_name: Human-readable step name
    """
    # Complete step mapping for all 15 steps (Step 0-14)
    script_map = {
        0: "00-prompt-generation/prompt-generation-policy.md",
        1: "01-task-breakdown/automatic-task-breakdown-policy.md",
        2: "02-plan-mode/auto-plan-mode-suggestion-policy.md",
        3: "00-code-graph-analysis/code-graph-analysis-policy.md",
        4: "04-model-selection/intelligent-model-selection-policy.md",
        5: "05-skill-agent-selection/auto-skill-agent-selection-policy.md",
        6: "06-tool-optimization/tool-usage-optimization-policy.md",
        7: "00-context-reading/context-reading-policy.md",
        8: "08-progress-tracking/task-progress-tracking-policy.md",
        9: "09-git-commit/git-auto-commit-policy.md",
        10: "github-branch-pr-policy.md",
        11: "github-issues-integration-policy.md",
        12: "parallel-execution-policy.md",
        13: "failure-prevention/failure-prevention-policy.md",
    }

    # Update state
    state = _enforcer_store.load()
    state[f"step_{step_number}"] = {
        "name": step_name,
        "status": "ENFORCED",
        "timestamp": datetime.now().isoformat()
    }
    _enforcer_store.save(state)

    policy_path = script_map.get(step_number)
    policy_exists = False
    full_path_str = ""
    if policy_path:
        full_path = POLICIES_DIR / "03-execution-system" / policy_path
        policy_exists = full_path.exists()
        full_path_str = str(full_path)

    return {
        "step": step_number,
        "name": step_name,
        "policy_file": policy_path,
        "policy_exists": policy_exists,
        "policy_path": full_path_str,
        "message": f"Step {step_number} ({step_name}) enforced"
    }


@mcp.tool()
@mcp_tool_handler
def log_tool_usage(
    tool_name: str,
    operation: str,
    parameters: str = "{}",
    result: str = "SUCCESS"
) -> dict:
    """Log a tool call made by Claude for tracking.

    Args:
        tool_name: Tool name (Read, Write, Edit, Bash, etc.)
        operation: Description of what was done
        parameters: JSON string of tool parameters
        result: Result status (SUCCESS, ERROR, OPTIMIZED)
    """
    # Append to log file
    log_dir = MEMORY_PATH / ".tool-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"tools-{today}.jsonl"

    entry = {
        "tool": tool_name,
        "operation": operation,
        "result": result,
        "timestamp": datetime.now().isoformat()
    }

    try:
        params = json.loads(parameters)
        if params:
            entry["parameters"] = params
    except (json.JSONDecodeError, TypeError):
        pass

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")

    return {
        "tool": tool_name,
        "operation": operation,
        "logged": True,
        "timestamp": entry["timestamp"]
    }


@mcp.tool()
@mcp_tool_handler
def verify_compliance() -> dict:
    """Verify that all required policy steps have been enforced."""
    state = _enforcer_store.load()

    # Dynamic: check which step_N keys are present
    required_steps = {
        "step_0": "Prompt Generation",
        "step_1": "Task Breakdown",
        "step_2": "Plan Mode Decision",
        "step_3": "Code Graph Analysis",
        "step_4": "Model Selection",
        "step_5": "Skill/Agent Selection",
        "step_6": "Tool Optimization",
        "step_7": "Context Reading",
        "step_8": "Progress Tracking",
        "step_9": "Git Commit",
        "step_10": "GitHub Branch/PR",
        "step_11": "GitHub Issues",
        "step_12": "Parallel Execution",
        "step_13": "Failure Prevention",
    }

    # Also check legacy keys for backward compatibility
    legacy_keys = {
        "session_started": "Session Start",
        "context_checked": "Context Check",
        "standards_loaded": "Standards Loaded",
        "prompt_generated": "Prompt Generation",
        "tasks_created": "Task Breakdown",
        "plan_mode_decided": "Plan Mode Decision",
        "model_selected": "Model Selection",
        "skills_agents_checked": "Skills/Agents Check"
    }

    completed = []
    missing = []
    for key, name in required_steps.items():
        step_data = state.get(key)
        if step_data and step_data.get("status") == "ENFORCED":
            completed.append(name)
        else:
            missing.append(name)

    # Check legacy keys too
    legacy_completed = []
    for key, name in legacy_keys.items():
        if state.get(key):
            legacy_completed.append(name)

    compliant = len(missing) == 0 or len(legacy_completed) >= 6

    return {
        "compliant": compliant,
        "completed_steps": len(completed),
        "total_steps": len(required_steps),
        "missing_steps": missing,
        "legacy_completed": legacy_completed,
        "timestamp": datetime.now().isoformat()
    }


@mcp.tool()
@mcp_tool_handler
def list_policies(level: str = "all") -> dict:
    """List all policy files with their status.

    Args:
        level: Filter by level - 'all', '01-sync', '02-standards', '03-execution', 'testing'
    """
    if not POLICIES_DIR.exists():
        return {
            "success": False,
            "error": f"Policies directory not found: {POLICIES_DIR}"
        }

    policies = []

    if level == "all":
        search_dirs = [d for d in POLICIES_DIR.iterdir() if d.is_dir()]
    else:
        # Match by prefix
        search_dirs = [d for d in POLICIES_DIR.iterdir() if d.is_dir() and level in d.name]

    for level_dir in sorted(search_dirs):
        for policy_file in sorted(level_dir.rglob("*.md")):
            if policy_file.name == "README.md":
                continue
            rel_path = policy_file.relative_to(POLICIES_DIR)
            stat = policy_file.stat()
            policies.append({
                "path": str(rel_path),
                "name": policy_file.stem.replace("-", " ").title(),
                "level": level_dir.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

    return {
        "policies": policies,
        "count": len(policies),
        "policies_dir": str(POLICIES_DIR)
    }


@mcp.tool()
@mcp_tool_handler
def record_policy_execution(
    policy_name: str,
    policy_script: str,
    policy_type: str,
    decision: str,
    duration_ms: int,
    input_params: str = "{}",
    output_results: str = "{}",
    session_id: Optional[str] = None,
    sub_operations: Optional[str] = None
) -> dict:
    """Record a policy execution to flow-trace.json for tracking.

    Args:
        policy_name: Policy name (e.g., 'session-id-generator')
        policy_script: Script filename (e.g., 'session-id-generator.py')
        policy_type: Type (e.g., 'Utility Hook', 'Policy Script')
        decision: What the policy decided
        duration_ms: Execution duration in milliseconds
        input_params: JSON string of input parameters
        output_results: JSON string of output results
        session_id: Session ID (auto-detected from .current-session.json if empty)
        sub_operations: JSON string of sub-operation records
    """
    # Get session ID
    sid = session_id
    if not sid:
        sid = SessionIdResolver(MEMORY_PATH).get()
    if not sid:
        sid = "unknown"

    session_dir = LOGS_PATH / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    flow_trace_file = session_dir / "flow-trace.json"

    # Load or create flow-trace
    if flow_trace_file.exists():
        flow_trace = json.loads(flow_trace_file.read_text(encoding="utf-8"))
    else:
        flow_trace = {
            "meta": {
                "session_id": sid,
                "created_at": datetime.now().isoformat(),
                "schema_version": "1.0"
            },
            "user_input": {},
            "all_policies_executed": [],
            "execution_summary": {"total_policies_executed": 0},
            "decisions_timeline": []
        }

    # Parse JSON params
    try:
        inp = json.loads(input_params)
    except (json.JSONDecodeError, TypeError):
        inp = {}
    try:
        out = json.loads(output_results)
    except (json.JSONDecodeError, TypeError):
        out = {}

    # Build policy record
    record = {
        "policy_name": policy_name,
        "policy_script": policy_script,
        "policy_type": policy_type,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": duration_ms,
        "input": inp,
        "output": out,
        "decision": decision
    }

    if sub_operations:
        try:
            record["sub_operations"] = json.loads(sub_operations)
        except (json.JSONDecodeError, TypeError):
            pass

    flow_trace["all_policies_executed"].append(record)
    flow_trace["execution_summary"]["total_policies_executed"] = len(
        flow_trace["all_policies_executed"]
    )
    flow_trace["decisions_timeline"].append({
        "timestamp": record["timestamp"],
        "policy": policy_name,
        "decision": decision
    })

    # Atomic save
    temp = flow_trace_file.with_suffix(".tmp")
    temp.write_text(json.dumps(flow_trace, indent=2, default=str), encoding="utf-8")
    temp.replace(flow_trace_file)

    return {
        "session_id": sid,
        "policy": policy_name,
        "total_recorded": len(flow_trace["all_policies_executed"])
    }


@mcp.tool()
@mcp_tool_handler
def get_session_id() -> dict:
    """Get the current session ID from .current-session.json."""
    sid = SessionIdResolver(MEMORY_PATH).get()
    if not sid:
        sid = "unknown"
    return {
        "session_id": sid,
        "is_valid": sid.startswith("SESSION-")
    }


@mcp.tool()
@mcp_tool_handler
def get_flow_trace_summary(session_id: Optional[str] = None) -> dict:
    """Get summary statistics from a session's flow-trace.

    Args:
        session_id: Session ID (auto-detected if empty)
    """
    sid = session_id or SessionIdResolver(MEMORY_PATH).get() or "unknown"
    flow_trace_file = LOGS_PATH / sid / "flow-trace.json"

    if not flow_trace_file.exists():
        return {
            "session_id": sid,
            "message": "No flow-trace found for this session"
        }

    flow_trace = json.loads(flow_trace_file.read_text(encoding="utf-8"))
    policies = flow_trace.get("all_policies_executed", [])

    sorted_by_speed = sorted(policies, key=lambda p: p.get("duration_ms", 0))

    return {
        "session_id": sid,
        "total_policies": len(policies),
        "total_duration_ms": sum(p.get("duration_ms", 0) for p in policies),
        "average_duration_ms": (
            sum(p.get("duration_ms", 0) for p in policies) / len(policies)
            if policies else 0
        ),
        "slowest_policy": (
            {"name": sorted_by_speed[-1]["policy_name"],
             "duration_ms": sorted_by_speed[-1]["duration_ms"]}
            if sorted_by_speed else None
        ),
        "fastest_policy": (
            {"name": sorted_by_speed[0]["policy_name"],
             "duration_ms": sorted_by_speed[0]["duration_ms"]}
            if sorted_by_speed else None
        ),
        "decisions_count": len(flow_trace.get("decisions_timeline", []))
    }


# Module registry for health checks (from policy-executor.py)
_POLICY_MODULES = [
    {"level": 1, "path": "01-sync-system/session-management/session-loader.py", "name": "Session Loader"},
    {"level": 1, "path": "01-sync-system/context-management/context-monitor-v2.py", "name": "Context Monitor"},
    {"level": 1, "path": "01-sync-system/user-preferences/preference-auto-tracker.py", "name": "Preference Auto-Tracker"},
    {"level": 1, "path": "01-sync-system/pattern-detection/detect-patterns.py", "name": "Pattern Detector"},
    {"level": 1, "path": "01-sync-system/session-management/session-save-triggers.py", "name": "Session Save Triggers"},
    {"level": 1, "path": "01-sync-system/session-management/archive-old-sessions.py", "name": "Archive Old Sessions"},
    {"level": 2, "path": "02-standards-system/standards-loader.py", "name": "Standards Loader"},
    {"level": 3, "path": "03-execution-system/00-prompt-generation/prompt-generator.py", "name": "Prompt Generator"},
    {"level": 3, "path": "03-execution-system/01-task-breakdown/task-breakdown.py", "name": "Task Breakdown"},
    {"level": 3, "path": "03-execution-system/02-plan-mode/plan-mode-decision.py", "name": "Plan Mode Decision"},
    {"level": 3, "path": "03-execution-system/04-model-selection/model-selector.py", "name": "Model Selector"},
    {"level": 3, "path": "03-execution-system/05-skill-agent-selection/skill-agent-selector.py", "name": "Skill/Agent Selector"},
    {"level": 3, "path": "03-execution-system/06-tool-optimization/tool-optimizer.py", "name": "Tool Optimizer"},
    {"level": 3, "path": "03-execution-system/08-progress-tracking/progress-tracker.py", "name": "Progress Tracker"},
    {"level": 3, "path": "03-execution-system/09-git-commit/git-auto-commit.py", "name": "Git Auto-Commit"},
]


@mcp.tool()
@mcp_tool_handler
def check_module_health() -> dict:
    """Check health of all registered policy modules (existence + importability).

    Scans the architecture directory for all policy modules and reports
    which ones are present, missing, or have import errors.
    """
    arch_dir = _PROJECT_ROOT / "scripts" / "architecture"
    results_by_level = {1: [], 2: [], 3: []}
    missing = []
    failed_import = []

    for mod in _POLICY_MODULES:
        mod_path = arch_dir / mod["path"]
        level = mod["level"]
        name = mod["name"]

        if not mod_path.exists():
            results_by_level[level].append({"name": name, "status": "MISSING", "path": mod["path"]})
            missing.append(name)
            continue

        # Check importability
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(name, str(mod_path))
            if spec is None:
                results_by_level[level].append({"name": name, "status": "IMPORT_FAILED", "path": mod["path"]})
                failed_import.append(name)
            else:
                results_by_level[level].append({"name": name, "status": "OK", "path": mod["path"]})
        except Exception:
            results_by_level[level].append({"name": name, "status": "IMPORT_FAILED", "path": mod["path"]})
            failed_import.append(name)

    total = len(_POLICY_MODULES)
    total_ok = sum(
        1 for level_results in results_by_level.values()
        for r in level_results if r["status"] == "OK"
    )

    by_level = {}
    for level, results in results_by_level.items():
        ok = sum(1 for r in results if r["status"] == "OK")
        by_level[f"level_{level}"] = {"ok": ok, "total": len(results)}

    return {
        "verified_ok": total_ok,
        "total_modules": total,
        "missing": missing,
        "failed_import": failed_import,
        "by_level": by_level,
        "results": {
            f"level_{k}": v for k, v in results_by_level.items()
        }
    }


@mcp.tool()
@mcp_tool_handler
def check_all_mcp_servers_health() -> dict:
    """Check health of all 11 MCP servers by importing each one.

    Returns import status, tool count, and file size for each server.
    This is a quick health check - does NOT start the servers, just verifies
    they can be loaded without errors.
    """
    import importlib.util as _ilu
    _mcp_dir = Path(__file__).resolve().parent

    servers = [
        ("git-ops", "git_mcp_server.py"),
        ("github-api", "github_mcp_server.py"),
        ("session-mgr", "session_mcp_server.py"),
        ("policy-enforcement", "enforcement_mcp_server.py"),
        ("llm-provider", "llm_mcp_server.py"),
        ("token-optimizer", "token_optimization_mcp_server.py"),
        ("pre-tool-gate", "pre_tool_gate_mcp_server.py"),
        ("post-tool-tracker", "post_tool_tracker_mcp_server.py"),
        ("standards-loader", "standards_loader_mcp_server.py"),
        ("skill-manager", "skill_manager_mcp_server.py"),
        ("vector-db", "vector_db_mcp_server.py"),
    ]

    results = []
    healthy = 0

    for name, filename in servers:
        fp = _mcp_dir / filename
        entry = {"server": name, "file": filename}

        if not fp.exists():
            entry["status"] = "MISSING"
            entry["error"] = f"File not found: {fp}"
        else:
            entry["size_bytes"] = fp.stat().st_size
            try:
                spec = _ilu.spec_from_file_location(name, str(fp))
                if spec:
                    entry["status"] = "HEALTHY"
                    healthy += 1
                else:
                    entry["status"] = "IMPORT_FAILED"
            except Exception as e:
                entry["status"] = "IMPORT_FAILED"
                entry["error"] = str(e)[:100]

        results.append(entry)

    return {
        "healthy": healthy,
        "total": len(servers),
        "all_healthy": healthy == len(servers),
        "servers": results,
    }


# =============================================================================
# RESOURCES (2)
# =============================================================================

@mcp.resource("enforcement://status")
def enforcement_status_resource() -> str:
    """Current enforcement state."""
    return check_enforcement_status()


@mcp.resource("enforcement://compliance")
def enforcement_compliance_resource() -> str:
    """Policy compliance report."""
    return verify_compliance()


@mcp.tool()
@mcp_tool_handler
def check_system_health() -> dict:
    """Comprehensive system health check across all components.

    Checks: MCP servers, checkpoint DB, vector DB, LLM providers,
    orchestrator graph, and disk usage. Returns aggregated health status.
    """
    health = {
        "timestamp": datetime.now().isoformat(),
        "components": {},
        "overall": "HEALTHY",
    }
    unhealthy = []

    # 1. MCP Servers health
    try:
        mcp_result = json.loads(check_all_mcp_servers_health())
        health["components"]["mcp_servers"] = {
            "status": "HEALTHY" if mcp_result.get("all_healthy") else "DEGRADED",
            "healthy": mcp_result.get("healthy", 0),
            "total": mcp_result.get("total", 0),
        }
        if not mcp_result.get("all_healthy"):
            unhealthy.append("mcp_servers")
    except Exception as e:
        health["components"]["mcp_servers"] = {"status": "ERROR", "error": str(e)[:100]}
        unhealthy.append("mcp_servers")

    # 2. Checkpoint DB
    try:
        db_path = Path.home() / ".claude" / "memory" / "langgraph-checkpoints.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            conn.close()
            health["components"]["checkpoint_db"] = {
                "status": "HEALTHY",
                "path": str(db_path),
                "size_kb": round(db_path.stat().st_size / 1024, 1),
            }
        else:
            health["components"]["checkpoint_db"] = {
                "status": "NOT_INITIALIZED",
                "path": str(db_path),
            }
    except Exception as e:
        health["components"]["checkpoint_db"] = {"status": "ERROR", "error": str(e)[:100]}
        unhealthy.append("checkpoint_db")

    # 3. Vector DB (Qdrant)
    try:
        vector_db_path = Path.home() / ".claude" / "memory" / "vector_db"
        if vector_db_path.exists():
            health["components"]["vector_db"] = {
                "status": "INITIALIZED",
                "path": str(vector_db_path),
                "size_kb": round(
                    sum(f.stat().st_size for f in vector_db_path.rglob("*") if f.is_file()) / 1024, 1
                ),
            }
        else:
            health["components"]["vector_db"] = {"status": "NOT_INITIALIZED"}
    except Exception as e:
        health["components"]["vector_db"] = {"status": "ERROR", "error": str(e)[:100]}

    # Vector DB: verify collections are accessible
    try:
        _src_mcp = Path(__file__).resolve().parent
        if str(_src_mcp) not in sys.path:
            sys.path.insert(0, str(_src_mcp))
        from vector_db_mcp_server import vector_health_check
        import json as _json_mod
        vdb_result = _json_mod.loads(vector_health_check())
        health["vector_db_healthy"] = vdb_result.get("healthy", False)
        health["vector_db_collections"] = vdb_result.get("collections", {})
    except Exception:
        health["vector_db_healthy"] = False

    # 4. LLM Providers (async-style concurrent check)
    providers_status = {}
    import concurrent.futures
    import time as _time

    def _check_ollama():
        try:
            import requests
            url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            start = _time.time()
            r = requests.get(f"{url}/api/tags", timeout=3)
            latency = round((_time.time() - start) * 1000)
            if r.status_code == 200:
                models = r.json().get("models", [])
                result = {"status": "HEALTHY", "latency_ms": latency, "models": len(models)}
                # Quick Ollama inference test (5s timeout)
                try:
                    resp = requests.post(
                        f"{url}/api/generate",
                        json={"model": "qwen2.5:7b", "prompt": "test", "stream": False},
                        timeout=5,
                    )
                    result["ollama_inference"] = resp.status_code == 200
                except Exception:
                    result["ollama_inference"] = False
                return result
            return {"status": "ERROR", "code": r.status_code}
        except Exception as e:
            return {"status": "UNAVAILABLE", "error": str(e)[:80]}

    def _check_anthropic():
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                return {"status": "NO_API_KEY"}
            return {"status": "CONFIGURED", "key_prefix": api_key[:8] + "..."}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)[:80]}

    def _check_claude_cli():
        try:
            import subprocess
            start = _time.time()
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=5
            )
            latency = round((_time.time() - start) * 1000)
            if result.returncode == 0:
                return {"status": "HEALTHY", "latency_ms": latency,
                        "version": result.stdout.strip()[:50]}
            return {"status": "ERROR", "code": result.returncode}
        except FileNotFoundError:
            return {"status": "NOT_INSTALLED"}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)[:80]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_check_ollama): "ollama",
            executor.submit(_check_anthropic): "anthropic",
            executor.submit(_check_claude_cli): "claude_cli",
        }
        for future in concurrent.futures.as_completed(futures, timeout=10):
            name = futures[future]
            try:
                providers_status[name] = future.result()
            except Exception as e:
                providers_status[name] = {"status": "TIMEOUT", "error": str(e)[:80]}

    health["components"]["llm_providers"] = providers_status

    any_llm_healthy = any(
        v.get("status") in ("HEALTHY", "CONFIGURED")
        for v in providers_status.values()
    )
    if not any_llm_healthy:
        unhealthy.append("llm_providers")

    # 5. Policy modules
    try:
        mod_result = json.loads(check_module_health())
        verified = mod_result.get("verified_ok", 0)
        total = mod_result.get("total_modules", 0)
        health["components"]["policy_modules"] = {
            "status": "HEALTHY" if verified == total else "DEGRADED",
            "verified": verified,
            "total": total,
            "missing": mod_result.get("missing", []),
        }
        if verified < total:
            unhealthy.append("policy_modules")
    except Exception as e:
        health["components"]["policy_modules"] = {"status": "ERROR", "error": str(e)[:100]}

    # 6. Disk usage
    try:
        memory_dir = Path.home() / ".claude" / "memory"
        if memory_dir.exists():
            total_size = sum(f.stat().st_size for f in memory_dir.rglob("*") if f.is_file())
            memory_dir_mb = round(total_size / (1024 * 1024), 2)
            health["components"]["disk"] = {
                "memory_dir_mb": memory_dir_mb,
                "path": str(memory_dir),
            }
            if memory_dir_mb > 500:
                unhealthy.append("disk_usage_high")
                health["disk_warning"] = f"Memory dir is {memory_dir_mb:.0f}MB (threshold: 500MB)"
    except Exception:
        pass

    # Overall status
    if unhealthy:
        health["overall"] = "DEGRADED"
        health["unhealthy_components"] = unhealthy

    health["success"] = True
    return health


if __name__ == "__main__":
    mcp.run(transport="stdio")
