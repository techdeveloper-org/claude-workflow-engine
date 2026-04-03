#!/usr/bin/env python
"""
BACKWARD-COMPAT SHIM for pre-tool-enforcer.py

Pre-tool enforcement logic has been refactored into scripts/pre_tool_enforcer/
package. This file delegates to that package while preserving the original
script invocation contract (Claude Code hooks call this file directly).

All public symbols are re-exported so that tests and other consumers that
load this file via importlib continue to find every attribute they expect.

Script Name: pre-tool-enforcer.py (shim)
Version:     4.0.0 (package refactor)
Last Modified: 2026-04-03

Windows-safe: ASCII only, no Unicode characters.
"""
import importlib.util as _ilu
import os
import sys
from pathlib import Path as _Path

# Guard: skip entirely when running inside the pipeline itself
if os.environ.get("CLAUDE_WORKFLOW_RUNNING") == "1":
    sys.exit(0)

# Load core.py by file path to avoid sys.modules["pre_tool_enforcer"]
# collision when tests register this shim under that module name.
_PACKAGE_DIR = _Path(__file__).resolve().parent / "pre_tool_enforcer"
_CORE_PATH = _PACKAGE_DIR / "core.py"

_core_spec = _ilu.spec_from_file_location(
    "_pre_tool_enforcer_core",
    str(_CORE_PATH),
    submodule_search_locations=[str(_PACKAGE_DIR)],
)
_core_mod = _ilu.module_from_spec(_core_spec)
_core_spec.loader.exec_module(_core_mod)

# Re-export every name from core into THIS module's namespace.
# This makes core's attributes accessible as pte.X when tests do
# importlib.util.spec_from_file_location("pre_tool_enforcer", ...).
main = _core_mod.main

for _name in dir(_core_mod):
    if _name.startswith("__") and _name.endswith("__"):
        continue
    globals()[_name] = getattr(_core_mod, _name)

# Explicit references for names injected by the loop above (ruff F821 fix)
get_current_session_id = globals()["get_current_session_id"]
find_session_flag = globals()["find_session_flag"]
_load_raw_flow_trace = globals()["_load_raw_flow_trace"]
_pipeline_step_present = globals()["_pipeline_step_present"]


# -----------------------------------------------------------------------
# BACKWARD-COMPAT WRAPPERS
#
# These functions are defined HERE (in this shim module) so that their
# __globals__ dict points to this module's namespace.  When tests do
# patch.object(pte, "get_current_session_id", ...) they patch THIS
# module's global, and these wrappers pick up the mocked version.
#
# The new-signature functions (in the policy files) import their own
# copy of get_current_session_id/find_session_flag, which tests cannot
# patch via pte.  So we must re-implement the old signatures here.
# -----------------------------------------------------------------------

BLOCKED_WHILE_CHECKPOINT_PENDING = {"Write", "Edit", "NotebookEdit"}


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
    return [], []


def check_level1_sync_complete(tool_name):
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return [], []
    sid = get_current_session_id()
    if not sid:
        return [], []
    trace = _load_raw_flow_trace()
    if trace is None:
        return [], []  # Fail-open: no trace yet
    l1_ctx = _pipeline_step_present(trace, "LEVEL_1_CONTEXT")
    l1_ses = _pipeline_step_present(trace, "LEVEL_1_SESSION")
    if l1_ctx and l1_ses:
        return [], []
    missing = []
    if not l1_ctx:
        missing.append("LEVEL_1_CONTEXT (context reading)")
    if not l1_ses:
        missing.append("LEVEL_1_SESSION (session init)")
    msg = (
        "[PRE-TOOL BLOCKED] Level 1 Sync System not complete yet!\n"
        "  Session  : " + sid + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until Level 1 finishes.\n"
        "  Missing  : " + ", ".join(missing) + "\n"
        "  Required : Need context reading, session init, pattern detection.\n"
        "  Reason   : 3-level-flow.py Level 1 must complete before code changes.\n"
        "  Action   : Wait for 3-level-flow.py to finish Level 1 Sync System."
    )
    return [], [msg]


def check_level2_standards_complete(tool_name):
    if tool_name not in BLOCKED_WHILE_CHECKPOINT_PENDING:
        return [], []
    sid = get_current_session_id()
    if not sid:
        return [], []
    trace = _load_raw_flow_trace()
    if trace is None:
        return [], []  # Fail-open: no trace yet
    l2_done = _pipeline_step_present(trace, "LEVEL_2_STANDARDS")
    if l2_done:
        return [], []
    msg = (
        "[PRE-TOOL BLOCKED] Level 2 Standards have not loaded!\n"
        "  Session  : " + sid + "\n"
        "  Tool     : " + tool_name + " is BLOCKED until Level 2 finishes.\n"
        "  Missing  : LEVEL_2_STANDARDS\n"
        "  Action   : Wait for 3-level-flow.py to finish Level 2 Standards."
    )
    return [], [msg]


def check_bash(command):
    """Backward-compat: check_bash(command) -> (hints, blocks)."""
    _pol_bash = getattr(_core_mod, "_pol_bash", None)
    if _pol_bash and hasattr(_pol_bash, "check_bash"):
        return _pol_bash.check_bash(command)
    # Fallback
    blocked, msg = _core_mod.check_bash_commands("Bash", {"command": command})
    return ([], [msg]) if blocked else ([], [])


def check_python_unicode(content):
    """Backward-compat: check_python_unicode(content) -> blocks: list."""
    _pol_uni = getattr(_core_mod, "_pol_uni", None)
    if _pol_uni and hasattr(_pol_uni, "_check_python_unicode_content"):
        msg = _pol_uni._check_python_unicode_content(content)
        return [msg] if msg else []
    return []


def check_grep(tool_input):
    """Backward-compat: check_grep(tool_input) -> (hints, blocks)."""
    inp = tool_input if isinstance(tool_input, dict) else {}
    blocked, msg = _core_mod._new_check_grep_opt("Grep", inp)
    return ([], [msg]) if blocked else ([], [])


def check_read(tool_input):
    """Backward-compat: check_read(tool_input) -> (hints, blocks)."""
    inp = tool_input if isinstance(tool_input, dict) else {}
    blocked, msg = _core_mod._new_check_read_opt("Read", inp)
    return ([], [msg]) if blocked else ([], [])


def check_write_edit(tool_name, tool_input):
    """Backward-compat: check_write_edit(tool_name, tool_input) -> (hints, blocks).

    Original combined unicode check + optimization hints in one function.
    """
    hints = []
    blocks = []
    if tool_name not in ("Write", "Edit", "NotebookEdit"):
        return hints, blocks
    file_path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "") or ""
    content = (
        tool_input.get("content", "") or tool_input.get("new_string", "") or tool_input.get("new_source", "") or ""
    )
    # Unicode check for .py files (the original combined this here)
    if file_path.endswith(".py") and content:
        uni_blocks = check_python_unicode(content)
        if uni_blocks:
            blocks.extend(uni_blocks)
    return hints, blocks


def check_dynamic_skill_context(tool_name, tool_input, trace_context=None):
    """Backward-compat: returns (hints, blocks)."""
    blocked, msg = _core_mod._new_check_dynamic_skill_context(tool_name, tool_input)
    hints = [msg] if msg and not blocked else []
    blocks = [msg] if blocked else []
    return hints, blocks


def check_failure_kb_hints(tool_name, tool_input):
    """Backward-compat: returns (hints, blocks)."""
    blocked, msg = _core_mod._new_check_failure_kb_hints(tool_name, tool_input)
    hints = [msg] if msg and not blocked else []
    blocks = [msg] if blocked else []
    return hints, blocks


if __name__ == "__main__":
    main()
