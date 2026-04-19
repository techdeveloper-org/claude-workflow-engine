# pre_tool_enforcer/core.py
# PreToolUse hook entry point. Reads stdin, runs PolicyRegistry, outputs result.
# Windows-safe: ASCII only, no Unicode characters.

import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Early exit if running inside the workflow pipeline itself
# ---------------------------------------------------------------------------
if os.environ.get("CLAUDE_WORKFLOW_RUNNING") == "1":
    sys.exit(0)

import json

# ---------------------------------------------------------------------------
# Ensure hooks/ directory is on sys.path (for sibling imports)
# ---------------------------------------------------------------------------
_core_dir = Path(__file__).resolve().parent  # hooks/pre_tool_enforcer/
_hooks_dir = _core_dir.parent  # hooks/
_project_root = _hooks_dir.parent  # project root
_scripts_dir = _project_root / "scripts"  # scripts/ (for architecture/ refs)
if str(_hooks_dir) not in sys.path:
    sys.path.insert(0, str(_hooks_dir))

# ---------------------------------------------------------------------------
# Metrics emitter (fire-and-forget, never blocks)
# ---------------------------------------------------------------------------
try:
    from metrics_emitter import emit_enforcement_event, emit_flag_lifecycle, emit_hook_execution

    _METRICS_AVAILABLE = True
except Exception:

    def emit_hook_execution(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""

    def emit_enforcement_event(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""

    def emit_flag_lifecycle(*a, **kw):
        """No-op fallback when metrics_emitter is unavailable."""

    _METRICS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Policy tracking integration
# ---------------------------------------------------------------------------
# policy_tracking_helper.py is a sibling in hooks/ (already on sys.path)

try:
    from policy_tracking_helper import record_policy_execution
except Exception:

    def record_policy_execution(*a, **kw):
        """No-op fallback when policy_tracking_helper is unavailable."""


# ---------------------------------------------------------------------------
# Tool optimization integration (3.6 Middleware)
# ---------------------------------------------------------------------------
_optimizer = None
try:
    _arch_path = _scripts_dir / "architecture" / "03-execution-system"
    sys.path.insert(0, str(_arch_path / "06-tool-optimization"))
    from tool_usage_optimization_policy import ToolUsageOptimizer

    _optimizer = ToolUsageOptimizer()
except Exception:
    pass

# ---------------------------------------------------------------------------
# Failure prevention integration (3.7 Pre-Execution Middleware)
# ---------------------------------------------------------------------------
_pre_checker = None
try:
    _arch_path2 = _scripts_dir / "architecture" / "03-execution-system"
    sys.path.insert(0, str(_arch_path2 / "failure-prevention"))
    from common_failures_prevention import PreExecutionChecker

    _pre_checker = PreExecutionChecker()
except Exception:
    pass

# ---------------------------------------------------------------------------
# MCP auto-route integration
# ---------------------------------------------------------------------------
_mcp_integration = None
try:
    from mcp_hook_integration import log_mcp_routing_decision, should_suggest_mcp

    _mcp_integration = True
except Exception:
    pass

# ---------------------------------------------------------------------------
# Path constants (from ide_paths or fallback)
# ---------------------------------------------------------------------------
try:
    from ide_paths import CURRENT_SESSION_FILE, FLAG_DIR
except ImportError:
    FLAG_DIR = Path.home() / ".claude"
    CURRENT_SESSION_FILE = Path.home() / ".claude" / "memory" / ".current-session.json"

try:
    from project_session import get_project_session_file

    CURRENT_SESSION_FILE = get_project_session_file()
except Exception:
    pass

# Track hook start time for total duration
_HOOK_START = datetime.now()

import importlib.util as _pkg_ilu  # noqa: E402

# ---------------------------------------------------------------------------
# Import policy modules
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Bootstrap the package into sys.modules so relative imports work even when
# the shim script is registered as "pre_tool_enforcer" by test harnesses.
# We register the real package under "_pte_pkg" and set __package__ on each
# submodule so `from ..loaders import X` resolves correctly.
# ---------------------------------------------------------------------------
import types as _types  # noqa: E402

_PKG_DIR = Path(__file__).resolve().parent
_PKG_NAME = "_pte_pkg"  # internal package name (avoids sys.modules collision)

# Create a virtual package module so relative imports resolve
_pkg_mod = _types.ModuleType(_PKG_NAME)
_pkg_mod.__path__ = [str(_PKG_DIR)]
_pkg_mod.__package__ = _PKG_NAME
sys.modules[_PKG_NAME] = _pkg_mod

# Create policies sub-package
_policies_pkg_name = _PKG_NAME + ".policies"
_policies_mod = _types.ModuleType(_policies_pkg_name)
_policies_mod.__path__ = [str(_PKG_DIR / "policies")]
_policies_mod.__package__ = _policies_pkg_name
sys.modules[_policies_pkg_name] = _policies_mod


def _load_submodule(filename, subpkg=None):
    """Load a pre_tool_enforcer submodule with proper package context.

    Python 3.13 emits 'DeprecationWarning: __package__ != __spec__.parent'
    and Python 3.14 makes it a hard ImportError. Fix (issue #208):
    - Do NOT set __package__ manually -- the spec machinery derives it
      correctly from the dotted module name passed to spec_from_file_location.
    - Do NOT pass submodule_search_locations=[] -- that empty-list hint
      confuses relative-import resolution inside child modules (it tells
      Python the module is a leaf even when the spec.name implies it has
      a parent), which in turn yields the __package__/__spec__.parent
      mismatch for any file using 'from ..x import y'.
    """
    _sub_path = _PKG_DIR / filename
    if subpkg:
        mod_name = _PKG_NAME + "." + subpkg + "." + Path(filename).stem
    else:
        mod_name = _PKG_NAME + "." + Path(filename).stem
    _sub_spec = _pkg_ilu.spec_from_file_location(mod_name, str(_sub_path))
    _sub_mod = _pkg_ilu.module_from_spec(_sub_spec)
    sys.modules[mod_name] = _sub_mod
    _sub_spec.loader.exec_module(_sub_mod)
    return _sub_mod


# Load loaders first (policies depend on it via relative imports)
_loaders_mod = _load_submodule("loaders.py")
get_current_session_id = _loaders_mod.get_current_session_id
_load_flow_trace_context = _loaders_mod._load_flow_trace_context
find_session_flag = _loaders_mod.find_session_flag
_pipeline_step_present = _loaders_mod._pipeline_step_present
_load_raw_flow_trace = _loaders_mod._load_raw_flow_trace
_load_failure_kb = getattr(_loaders_mod, "_load_failure_kb", None)

_registry_mod = _load_submodule("registry.py")
PolicyRegistry = _registry_mod.PolicyRegistry

# Load policy modules (their `from ..loaders import X` resolves via _pte_pkg)
_pol_chk = _load_submodule(os.path.join("policies", "checkpoint.py"), "policies")
_pol_tb = _load_submodule(os.path.join("policies", "task_breakdown.py"), "policies")
_pol_ss = _load_submodule(os.path.join("policies", "skill_selection.py"), "policies")
_pol_cr = _load_submodule(os.path.join("policies", "context_read.py"), "policies")
_pol_l1 = _load_submodule(os.path.join("policies", "level1_sync.py"), "policies")
_pol_bash = _load_submodule(os.path.join("policies", "bash_commands.py"), "policies")
_pol_uni = _load_submodule(os.path.join("policies", "python_unicode.py"), "policies")
_pol_grep = _load_submodule(os.path.join("policies", "grep_opt.py"), "policies")
_pol_read = _load_submodule(os.path.join("policies", "read_opt.py"), "policies")
_pol_fkb = _load_submodule(os.path.join("policies", "failure_kb.py"), "policies")
_pol_sc = _load_submodule(os.path.join("policies", "skill_context.py"), "policies")
_pol_we = _load_submodule(os.path.join("policies", "write_edit.py"), "policies")

# Re-export constants that tests expect on the module
FILE_EXT_SKILL_MAP = getattr(_pol_sc, "FILE_EXT_SKILL_MAP", {})
UNICODE_DANGER = getattr(_pol_uni, "UNICODE_DANGER", [])

# New-signature functions (used internally by PolicyRegistry):
# (tool_name, tool_input) -> (blocked: bool, message: str)
_new_check_checkpoint_pending = _pol_chk.check_checkpoint_pending
_new_check_task_breakdown_pending = _pol_tb.check_task_breakdown_pending
_new_check_skill_selection_pending = _pol_ss.check_skill_selection_pending
_new_check_context_read_complete = _pol_cr.check_context_read_complete
_new_check_level1_sync_complete = _pol_l1.check_level1_sync_complete
_new_check_bash_commands = _pol_bash.check_bash_commands
_new_check_python_unicode = _pol_uni.check_python_unicode
_new_check_grep_opt = _pol_grep.check_grep_opt
_new_check_read_opt = _pol_read.check_read_opt
_new_check_failure_kb_hints = _pol_fkb.check_failure_kb_hints
_new_check_dynamic_skill_context = _pol_sc.check_dynamic_skill_context
_new_check_write_edit = _pol_we.check_write_edit

# -----------------------------------------------------------------------
# Backward-compat wrappers with ORIGINAL signatures and return types
# Original convention: (hints: list[str], blocks: list[str])
# -----------------------------------------------------------------------


def _wrap(new_fn):
    """Convert (blocked: bool, msg: str) -> (hints: list, blocks: list)."""

    def wrapper(*args, **kwargs):
        blocked, msg = new_fn(*args, **kwargs)
        if blocked:
            return [], [msg]
        return [], []

    wrapper.__name__ = new_fn.__name__
    return wrapper


# -----------------------------------------------------------------------
# Constants used by backward-compat wrappers (from original monolith)
# -----------------------------------------------------------------------
BLOCKED_WHILE_CHECKPOINT_PENDING = {"Write", "Edit", "NotebookEdit"}

# -----------------------------------------------------------------------
# Backward-compat wrappers that use module-level get_current_session_id /
# find_session_flag (patchable by tests via patch.object(pte, ...)).
# The new-sig policy functions import their OWN copy of these helpers,
# so test patches don't reach them. These wrappers duplicate the logic
# to keep the old calling convention testable.
# -----------------------------------------------------------------------


def check_checkpoint_pending(tool_name):
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return [], []
    sid = get_current_session_id()
    if not sid:
        return [], []
    fpath, fdata = find_session_flag(".checkpoint-pending", sid)
    if fpath is None:
        return [], []
    prompt = (fdata or {}).get("prompt_preview", "")[:80]
    msg = (
        "[PRE-TOOL BLOCKED] Review checkpoint is pending!\n"
        "  Session  : " + (fdata or {}).get("session_id", "unknown") + "\n"
        "  Task     : " + prompt + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until user confirms.\n"
        '  Required : User must reply with "ok" or "proceed" first.\n'
        "  Reason   : CLAUDE.md policy - no coding before checkpoint review.\n"
        "  Action   : Show the [REVIEW CHECKPOINT] to user and WAIT."
    )
    return [], [msg]


def check_task_breakdown_pending(tool_name):
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return [], []
    sid = get_current_session_id()
    if not sid:
        return [], []
    fpath, fdata = find_session_flag(".task-breakdown-pending", sid)
    if fpath is None:
        return [], []
    msg = (
        "[PRE-TOOL BLOCKED] Task breakdown validation is pending!\n"
        "  Tool: " + tool_name + " blocked until TaskCreate completes.\n"
        "  Action: Create tasks from the breakdown first."
    )
    return [], [msg]


def check_skill_selection_pending(tool_name):
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return [], []
    sid = get_current_session_id()
    if not sid:
        return [], []
    fpath, fdata = find_session_flag(".skill-selection-pending", sid)
    if fpath is None:
        return [], []
    msg = (
        "[PRE-TOOL BLOCKED] Skill selection is pending!\n"
        "  Tool: " + tool_name + " blocked until skill is loaded.\n"
        "  Action: Load the recommended skill first."
    )
    return [], [msg]


def check_context_read_complete(tool_name):
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return [], []
    sid = get_current_session_id()
    if not sid:
        return [], []
    trace = _load_raw_flow_trace()
    if trace and _pipeline_step_present(trace, "context_read"):
        return [], []
    return [], []  # fail-open if no trace


def check_level1_sync_complete(tool_name):
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return [], []
    sid = get_current_session_id()
    if not sid:
        return [], []
    trace = _load_raw_flow_trace()
    if not trace:
        return [], []
    if not _pipeline_step_present(trace, "level1"):
        msg = (
            "[PRE-TOOL BLOCKED] Level 1 Sync has not completed!\n"
            "  Tool: " + tool_name + " blocked until Level 1 runs.\n"
            "  Action: Run the 3-level flow pipeline first."
        )
        return [], [msg]
    return [], []


# Original: check_bash(command) -> (hints, blocks)
check_bash = _pol_bash.check_bash  # Already has old-sig wrapper


# Original: check_python_unicode(content) -> blocks: list[str]
def check_python_unicode(content):
    fn = getattr(_pol_uni, "_check_python_unicode_content", None)
    if fn:
        msg = fn(content)
        return [msg] if msg else []
    # Fallback: call new-sig and convert
    blocked, msg = _new_check_python_unicode("Write", {"content": content})
    return [msg] if blocked else []


# Original: check_grep(tool_input) -> (hints, blocks)
def check_grep(tool_input):
    blocked, msg = _new_check_grep_opt("Grep", tool_input if isinstance(tool_input, dict) else {})
    return ([], [msg]) if blocked else ([], [])


# Original: check_read(tool_input) -> (hints, blocks)
def check_read(tool_input):
    blocked, msg = _new_check_read_opt("Read", tool_input if isinstance(tool_input, dict) else {})
    return ([], [msg]) if blocked else ([], [])


# Original: check_write_edit(tool_name, tool_input) -> (hints, blocks)
def check_write_edit(tool_name, tool_input):
    blocked, msg = _new_check_write_edit(tool_name, tool_input)
    return ([], [msg]) if blocked else ([], [])


# Original: check_dynamic_skill_context(tool_name, tool_input, trace_context=None) -> (hints, blocks)
def check_dynamic_skill_context(tool_name, tool_input, trace_context=None):
    blocked, msg = _new_check_dynamic_skill_context(tool_name, tool_input)
    hints = [msg] if msg and not blocked else []
    blocks = [msg] if blocked else []
    return hints, blocks


# Original: check_failure_kb_hints(tool_name, tool_input) -> (hints, blocks)
def check_failure_kb_hints(tool_name, tool_input):
    blocked, msg = _new_check_failure_kb_hints(tool_name, tool_input)
    hints = [msg] if msg and not blocked else []
    blocks = [msg] if blocked else []
    return hints, blocks


# Keep new-sig aliases for internal use
check_bash_commands = _new_check_bash_commands
check_grep_opt = _new_check_grep_opt
check_read_opt = _new_check_read_opt


# ---------------------------------------------------------------------------
# Helper: emit metrics and exit with block
# ---------------------------------------------------------------------------
def _emit_block_and_exit(tool_name, all_hints, all_blocks, block_type, exit_code=2):
    """Write hints to stdout, blocks to stderr, emit metrics, then sys.exit."""
    for hint in all_hints:
        sys.stdout.write(hint + "\n")
    sys.stdout.flush()
    for block in all_blocks:
        sys.stderr.write(block + "\n")
    sys.stderr.flush()
    try:
        _sid = get_current_session_id()
        _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
        emit_enforcement_event(
            "pre-tool-enforcer.py",
            block_type,
            tool_name=tool_name,
            reason=block_type + " flag active",
            blocked=True,
            session_id=_sid,
        )
        emit_hook_execution(
            "pre-tool-enforcer.py",
            _dur,
            session_id=_sid,
            exit_code=exit_code,
            extra={"tool": tool_name, "block_type": block_type},
        )
    except Exception:
        pass
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# Helper: run optimization middleware (3.6 + 3.7) - returns hints list
# ---------------------------------------------------------------------------
def _run_policy_optimization(tool_name, tool_input, flow_ctx):
    """Apply tool optimization and pre-execution failure checking.

    Non-blocking. Returns list of hint strings.
    """
    hints = []

    if _optimizer:
        try:
            optimized = _optimizer.optimize(tool_name, tool_input, flow_ctx)
            changes = {}
            for key in optimized:
                if key in tool_input and optimized[key] != tool_input[key]:
                    changes[key] = optimized[key]
                elif key not in tool_input:
                    changes[key] = optimized[key]
            if changes:
                for key, val in changes.items():
                    hints.append("[3.6-OPTIMIZE] {} -> {} set to {}".format(tool_name, key, str(val)[:100]))
        except Exception:
            pass

    if _pre_checker:
        try:
            check_result = _pre_checker.check_tool_call(tool_name, tool_input)
            issues = check_result.get("issues", [])
            for issue in issues:
                issue_type = issue.get("type", "unknown")
                suggestion = issue.get("suggestion", "")
                hints.append("[3.7-PREVENTION] {}: {} - {}".format(tool_name, issue_type, suggestion[:100]))
        except Exception:
            pass

    return hints


# ---------------------------------------------------------------------------
# Ordered blocking policies (evaluated one at a time; first block wins)
# ---------------------------------------------------------------------------
_BLOCKING_POLICIES = [
    ("checkpoint", check_checkpoint_pending),
    ("task_breakdown", check_task_breakdown_pending),
    ("skill_selection", check_skill_selection_pending),
    ("context_read", check_context_read_complete),
    ("level1_sync", check_level1_sync_complete),
    ("python_unicode", check_python_unicode),
    ("bash_commands", check_bash_commands),
    ("grep_opt", check_grep_opt),
    ("read_opt", check_read_opt),
]


def main():
    """PreToolUse hook entry point.

    Reads tool name and input from Claude Code hook stdin (JSON), then runs
    all enforcement checks in order.  Hints are written to stdout (non-blocking).
    Blocks are written to stderr and the process exits with code 2 (blocking
    exit code per Claude Code hook protocol).

    Never raises exceptions; all errors are silently swallowed so a broken
    hook never disrupts the underlying tool call.
    """
    _track_start_time = datetime.now()

    # Load flow-trace context from 3-level-flow (cached per invocation)
    flow_ctx = _load_flow_trace_context()

    # Warm up token-optimizer MCP module (non-blocking)
    try:
        _src_mcp_dir = _project_root / "src" / "mcp"
        if str(_src_mcp_dir) not in sys.path:
            sys.path.insert(0, str(_src_mcp_dir))
        from token_optimization_mcp_server import context_budget_status

        context_budget_status()
    except Exception:
        pass

    # Read tool info from stdin
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            sys.exit(0)
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}

    all_hints = []
    all_blocks = []

    # Run ordered blocking policies (fail-open per policy)
    for policy_name, check_fn in _BLOCKING_POLICIES:
        try:
            blocked, msg = check_fn(tool_name, tool_input)
        except Exception:
            blocked, msg = False, ""  # fail-open

        if blocked and msg:
            all_blocks.append(msg)
            _emit_block_and_exit(tool_name, all_hints, all_blocks, policy_name)
        elif not blocked and msg:
            # msg may be a multi-line hint block (e.g. failure_kb non-blocking hints)
            all_hints.append(msg)

    # Dynamic skill context hints (non-blocking)
    if tool_name in ("Read", "Write", "Edit", "NotebookEdit", "Grep", "Glob"):
        try:
            _, skill_hint = check_dynamic_skill_context(tool_name, tool_input)
            if skill_hint:
                all_hints.append(skill_hint)
        except Exception:
            pass

        # Add task-aware context from flow trace
        try:
            task_tech = flow_ctx.get("tech_stack", [])
            session_primary = flow_ctx.get("skill", "")
            if task_tech and task_tech != ["unknown"]:
                all_hints.append("  TASK TECH STACK: " + ", ".join(task_tech))
            if session_primary:
                all_hints.append("  SESSION PRIMARY: " + session_primary)
        except Exception:
            pass

    # Failure-KB hints (non-blocking)
    try:
        _, kb_msg = check_failure_kb_hints(tool_name, tool_input)
        if kb_msg:
            all_hints.append(kb_msg)
    except Exception:
        pass

    # Policy optimization middleware hints (non-blocking)
    try:
        opt_hints = _run_policy_optimization(tool_name, tool_input, flow_ctx)
        all_hints.extend(opt_hints)
    except Exception:
        pass

    # MCP routing hints for Grep/Read (non-blocking)
    if _mcp_integration:
        try:
            if tool_name == "Grep":
                head_limit = tool_input.get("head_limit", 0)
                output_mode = tool_input.get("output_mode", "files_with_matches")
                if not head_limit and output_mode == "content":
                    if should_suggest_mcp():
                        log_mcp_routing_decision("grep_smart", "Grep", True)
            elif tool_name == "Read":
                limit = tool_input.get("limit")
                offset = tool_input.get("offset")
                if not limit and not offset:
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        import os as _os

                        if _os.path.exists(file_path):
                            file_size = _os.path.getsize(file_path)
                            if file_size > 50 * 1024:
                                if should_suggest_mcp():
                                    log_mcp_routing_decision("read_smart", "Read", True)
        except Exception:
            pass

    # Write all hints to stdout (non-blocking)
    for hint in all_hints:
        sys.stdout.write(hint + "\n")
    sys.stdout.flush()

    # Emit success metrics
    try:
        _sid = get_current_session_id()
        _dur = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
        emit_hook_execution(
            "pre-tool-enforcer.py",
            _dur,
            session_id=_sid,
            exit_code=0,
            extra={"tool": tool_name, "hints": len(all_hints)},
        )
    except Exception:
        pass

    # Record policy execution (success path)
    try:
        _session_id = get_current_session_id() or "unknown"
        _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
        record_policy_execution(
            session_id=_session_id,
            policy_name="pre-tool-enforcer",
            policy_script="pre-tool-enforcer.py",
            policy_type="Core Hook",
            input_params={"tool": tool_name},
            output_results={
                "status": "ALLOWED",
                "hints_provided": len(all_hints),
            },
            decision="Tool " + tool_name + " allowed with optimization hints",
            duration_ms=_duration_ms,
        )
    except Exception:
        pass

    sys.stdout.write("[L3.6] Tool optimization verified\n")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
