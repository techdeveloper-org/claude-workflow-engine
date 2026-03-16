"""
Policy Enforcement MCP Server - FastMCP migration of enforcement_server.py.

Replaces the custom JSON-RPC class with proper FastMCP decorator-based tools.
Includes flow-trace recording, policy execution tracking, and full step mapping.
Backend: Direct file I/O (JSON state files, policy directory scanning)
Transport: stdio

Tools (8):
  check_enforcement_status, enforce_policy_step, log_tool_usage,
  verify_compliance, list_policies, record_policy_execution,
  get_flow_trace_summary, get_session_id
Resources (2):
  enforcement://status, enforcement://compliance
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("policy-enforcement", instructions="Policy enforcement and compliance tracking")

# Paths
MEMORY_PATH = Path.home() / ".claude" / "memory"
ENFORCER_STATE_FILE = MEMORY_PATH / ".blocking-enforcer-state.json"
LOGS_PATH = MEMORY_PATH / "logs" / "sessions"
CURRENT_SESSION_FILE = MEMORY_PATH / ".current-session.json"
# Policy directories - check project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
POLICIES_DIR = _PROJECT_ROOT / "policies"


def _json(data: dict) -> str:
    """Return compact JSON string."""
    return json.dumps(data, indent=2, default=str)


def _load_state() -> dict:
    """Load enforcer state from disk."""
    try:
        if ENFORCER_STATE_FILE.exists():
            with open(ENFORCER_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_state(state: dict):
    """Save enforcer state to disk."""
    try:
        ENFORCER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ENFORCER_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass


# =============================================================================
# TOOLS (5)
# =============================================================================

@mcp.tool()
def check_enforcement_status() -> str:
    """Check current policy enforcement status for all steps."""
    try:
        state = _load_state()
        return _json({
            "success": True,
            "state": state,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return _json({
            "success": False,
            "error": str(e),
            "state": {},
            "timestamp": datetime.now().isoformat()
        })


@mcp.tool()
def enforce_policy_step(step_number: int, step_name: str) -> str:
    """Enforce a specific policy step in the execution pipeline.

    Args:
        step_number: Step number (0-13)
        step_name: Human-readable step name
    """
    try:
        # Complete step mapping for all 14 steps
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
        state = _load_state()
        state[f"step_{step_number}"] = {
            "name": step_name,
            "status": "ENFORCED",
            "timestamp": datetime.now().isoformat()
        }
        _save_state(state)

        policy_path = script_map.get(step_number)
        policy_exists = False
        full_path_str = ""
        if policy_path:
            full_path = POLICIES_DIR / "03-execution-system" / policy_path
            policy_exists = full_path.exists()
            full_path_str = str(full_path)

        return _json({
            "success": True,
            "step": step_number,
            "name": step_name,
            "policy_file": policy_path,
            "policy_exists": policy_exists,
            "policy_path": full_path_str,
            "message": f"Step {step_number} ({step_name}) enforced"
        })
    except Exception as e:
        return _json({
            "success": False,
            "error": str(e),
            "step": step_number,
            "name": step_name
        })


@mcp.tool()
def log_tool_usage(
    tool_name: str,
    operation: str,
    parameters: str = "{}",
    result: str = "SUCCESS"
) -> str:
    """Log a tool call made by Claude for tracking.

    Args:
        tool_name: Tool name (Read, Write, Edit, Bash, etc.)
        operation: Description of what was done
        parameters: JSON string of tool parameters
        result: Result status (SUCCESS, ERROR, OPTIMIZED)
    """
    try:
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

        return _json({
            "success": True,
            "tool": tool_name,
            "operation": operation,
            "logged": True,
            "timestamp": entry["timestamp"]
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def verify_compliance() -> str:
    """Verify that all required policy steps have been enforced."""
    try:
        state = _load_state()

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

        return _json({
            "compliant": compliant,
            "completed_steps": len(completed),
            "total_steps": len(required_steps),
            "missing_steps": missing,
            "legacy_completed": legacy_completed,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return _json({
            "compliant": False,
            "error": str(e),
            "missing_steps": []
        })


@mcp.tool()
def list_policies(level: str = "all") -> str:
    """List all policy files with their status.

    Args:
        level: Filter by level - 'all', '01-sync', '02-standards', '03-execution', 'testing'
    """
    try:
        if not POLICIES_DIR.exists():
            return _json({
                "success": False,
                "error": f"Policies directory not found: {POLICIES_DIR}"
            })

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

        return _json({
            "success": True,
            "policies": policies,
            "count": len(policies),
            "policies_dir": str(POLICIES_DIR)
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
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
) -> str:
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
    try:
        # Get session ID
        sid = session_id
        if not sid:
            sid = _get_current_session_id()

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

        return _json({
            "success": True,
            "session_id": sid,
            "policy": policy_name,
            "total_recorded": len(flow_trace["all_policies_executed"])
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


def _get_current_session_id() -> str:
    """Get current session ID from .current-session.json."""
    try:
        if CURRENT_SESSION_FILE.exists():
            data = json.loads(CURRENT_SESSION_FILE.read_text(encoding="utf-8"))
            sid = data.get("current_session_id", "")
            if sid.startswith("SESSION-"):
                return sid
    except Exception:
        pass
    return "unknown"


@mcp.tool()
def get_session_id() -> str:
    """Get the current session ID from .current-session.json."""
    try:
        sid = _get_current_session_id()
        return _json({
            "success": True,
            "session_id": sid,
            "is_valid": sid.startswith("SESSION-")
        })
    except Exception as e:
        return _json({"success": False, "error": str(e), "session_id": "unknown"})


@mcp.tool()
def get_flow_trace_summary(session_id: Optional[str] = None) -> str:
    """Get summary statistics from a session's flow-trace.

    Args:
        session_id: Session ID (auto-detected if empty)
    """
    try:
        sid = session_id or _get_current_session_id()
        flow_trace_file = LOGS_PATH / sid / "flow-trace.json"

        if not flow_trace_file.exists():
            return _json({
                "success": True,
                "session_id": sid,
                "message": "No flow-trace found for this session"
            })

        flow_trace = json.loads(flow_trace_file.read_text(encoding="utf-8"))
        policies = flow_trace.get("all_policies_executed", [])

        sorted_by_speed = sorted(policies, key=lambda p: p.get("duration_ms", 0))

        summary = {
            "success": True,
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

        return _json(summary)
    except Exception as e:
        return _json({"success": False, "error": str(e)})


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
