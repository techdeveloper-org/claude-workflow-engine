"""
post_tool_tracker/core.py - PostToolUse hook entry point.

Reads tool name, input, and response from Claude Code hook stdin (JSON),
then dispatches to policy and tracking modules.

This module contains main() which is the sole public entry point.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Guard: skip entirely when running inside the pipeline itself
# ---------------------------------------------------------------------------
if os.environ.get("CLAUDE_WORKFLOW_RUNNING") == "1":

    def main():
        """No-op main when running inside the workflow pipeline."""
        sys.exit(0)

else:
    # ------------------------------------------------------------------
    # Resolve paths to hooks/ directory (parent of this package)
    # ------------------------------------------------------------------
    _HOOKS_DIR = str(Path(__file__).resolve().parent.parent)
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
    _SCRIPTS_DIR = str(Path(_PROJECT_ROOT) / "scripts")
    if _HOOKS_DIR not in sys.path:
        sys.path.insert(0, _HOOKS_DIR)

    # ------------------------------------------------------------------
    # Metrics emitter (fire-and-forget, never blocks)
    # ------------------------------------------------------------------
    try:
        from metrics_emitter import emit_context_sample, emit_flag_lifecycle, emit_hook_execution

        _METRICS_AVAILABLE = True
    except Exception:

        def emit_hook_execution(*a, **kw):
            """No-op fallback when metrics_emitter is unavailable."""

        def emit_context_sample(*a, **kw):
            """No-op fallback when metrics_emitter is unavailable."""

        def emit_flag_lifecycle(*a, **kw):
            """No-op fallback when metrics_emitter is unavailable."""

        _METRICS_AVAILABLE = False

    # ------------------------------------------------------------------
    # Policy tracking integration
    # ------------------------------------------------------------------
    _policy_tracking_available = False
    try:
        # policy_tracking_helper.py is a sibling in hooks/ (already on sys.path)
        from policy_tracking_helper import get_session_id, record_policy_execution, record_sub_operation

        _policy_tracking_available = True
    except ImportError:

        def record_policy_execution(*a, **kw):
            """No-op fallback when policy_tracking_helper is unavailable."""

        def record_sub_operation(*a, **kw):
            """No-op fallback when policy_tracking_helper is unavailable."""

        def get_session_id(*a, **kw):
            """No-op fallback when policy_tracking_helper is unavailable."""
            return None

    # ------------------------------------------------------------------
    # Failure detection integration (3.7 middleware)
    # ------------------------------------------------------------------
    _failure_detector = None
    try:
        _fp_path = Path(_SCRIPTS_DIR) / "architecture" / "03-execution-system" / "failure-prevention"
        sys.path.insert(0, str(_fp_path))
        from common_failures_prevention import FailureDetector

        _failure_detector = FailureDetector()
    except Exception:
        pass

    # ------------------------------------------------------------------
    # Path constants (with ide_paths fallback)
    # ------------------------------------------------------------------
    try:
        from ide_paths import FLAG_DIR, SESSION_STATE_FILE, TRACKER_LOG
    except ImportError:
        SESSION_STATE_FILE = Path.home() / ".claude" / "memory" / "logs" / "session-progress.json"
        TRACKER_LOG = Path.home() / ".claude" / "memory" / "logs" / "tool-tracker.jsonl"
        FLAG_DIR = Path.home() / ".claude"

    # ------------------------------------------------------------------
    # Package-level imports
    # ------------------------------------------------------------------
    # Use importlib file-path loading to avoid sys.modules["post_tool_tracker"]
    # collision when tests register the shim script under that module name.
    import importlib.util as _pkg_ilu

    def _load_submodule(name, filename):
        """Load a post_tool_tracker submodule by file path."""
        _sub_path = Path(__file__).resolve().parent / filename
        _sub_spec = _pkg_ilu.spec_from_file_location(name, str(_sub_path))
        _sub_mod = _pkg_ilu.module_from_spec(_sub_spec)
        _sub_spec.loader.exec_module(_sub_mod)
        return _sub_mod

    _loaders = _load_submodule("_ptt_loaders", "loaders.py")
    _load_flow_trace_context = _loaders._load_flow_trace_context
    _get_session_id_from_progress = _loaders._get_session_id_from_progress

    _progress = _load_submodule("_ptt_progress", "progress_tracker.py")
    PROGRESS_DELTA = _progress.PROGRESS_DELTA
    load_session_progress = _progress.load_session_progress
    save_session_progress = _progress.save_session_progress
    log_tool_entry = _progress.log_tool_entry
    _clear_session_flags = _progress._clear_session_flags
    get_response_content_length = _progress.get_response_content_length
    estimate_context_pct = _progress.estimate_context_pct
    is_error_response = _progress.is_error_response

    _gh_int = _load_submodule("_ptt_github", "github_integration.py")
    _get_github_issue_manager = _gh_int._get_github_issue_manager
    close_github_issues_on_completion = _gh_int.close_github_issues_on_completion

    _pol_uncommitted = _load_submodule("_ptt_pol_uncommitted", os.path.join("policies", "uncommitted_push.py"))
    check_uncommitted_before_push = _pol_uncommitted.check_uncommitted_before_push
    check_level_3_11_git_status = _pol_uncommitted.check_level_3_11_git_status

    _pol_merge = _load_submodule("_ptt_pol_merge", os.path.join("policies", "post_merge_update.py"))
    run_post_merge_version_update = _pol_merge.run_post_merge_version_update

    _pol_task = _load_submodule("_ptt_pol_task", os.path.join("policies", "task_tracking.py"))
    enforce_task_update_frequency = _pol_task.enforce_task_update_frequency

    _pol_phase = _load_submodule("_ptt_pol_phase", os.path.join("policies", "phase_complexity.py"))
    check_level_3_8_phase_requirement = _pol_phase.check_level_3_8_phase_requirement
    warn_phase_complexity = _pol_phase.warn_phase_complexity

    _pol_breakdown = _load_submodule("_ptt_pol_breakdown", os.path.join("policies", "task_breakdown_clear.py"))
    handle_task_create = _pol_breakdown.handle_task_create

    _pol_skill = _load_submodule("_ptt_pol_skill", os.path.join("policies", "skill_selection_clear.py"))
    handle_skill_selection = _pol_skill.handle_skill_selection

    # ------------------------------------------------------------------
    # Level 3.9 / 3.10 blocking checks (defined inline - depend on state)
    # ------------------------------------------------------------------

    def check_level_3_9_build_validation(tool_name, tool_input, is_error, state):
        """Level 3.9: BLOCK TaskUpdate(completed) when the last build failed."""
        if tool_name != "TaskUpdate" or is_error:
            return False, ""
        task_status = (tool_input or {}).get("status", "")
        if task_status != "completed":
            return False, ""
        if not state.get("last_build_failed", False):
            return False, ""
        failed_label = state.get("last_build_failed_label", "unknown build step")
        msg = (
            "[BLOCKED L3.9] Cannot mark task completed - build is FAILING!\n"
            "  Failed build : " + failed_label + "\n"
            "  Policy       : build-validation-policy.md\n"
            "  Rule         : A task CANNOT be completed while the build is broken.\n"
            "  Action       : Fix the build errors first, then re-mark as completed.\n"
            "  Tip          : Run the failing build step and resolve all errors."
        )
        return True, msg

    def check_level_3_10_version_release(tool_name, tool_input, state):
        """Level 3.10: BLOCK git push when VERSION file was not modified."""
        if tool_name != "Bash":
            return False, ""
        cmd = (tool_input or {}).get("command", "").lower()
        if "git push" not in cmd or "--dry-run" in cmd or "--delete" in cmd:
            return False, ""
        import subprocess as _sp

        try:
            _diff_result = _sp.run(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"], capture_output=True, text=True, timeout=5
            )
            committed_files = _diff_result.stdout.strip().split("\n") if _diff_result.returncode == 0 else []
            version_in_commit = any(
                f.strip().lower().endswith("version") or f.strip().lower().endswith("version.txt")
                for f in committed_files
                if f.strip()
            )
            if version_in_commit:
                return False, ""
            if not committed_files or committed_files == [""]:
                return False, ""
        except Exception:
            pass

        modified = state.get("modified_files_since_commit", [])
        version_modified = any(f.lower().endswith("version") or f.lower().endswith("version.txt") for f in modified)
        if version_modified:
            return False, ""
        if not modified:
            return False, ""
        msg = (
            "[BLOCKED L3.10] git push blocked - VERSION file not updated!\n"
            "  Modified files : " + ", ".join(modified[-5:]) + ("" if len(modified) <= 5 else " ...") + "\n"
            "  VERSION file   : NOT in modified list\n"
            "  Policy         : version-release-policy.md\n"
            "  Rule           : Every push MUST include a VERSION file update.\n"
            "  Action         : Update the VERSION file, then push again.\n"
            '  Example        : echo "0.X.Y" > VERSION && git add VERSION'
        )
        return True, msg

    # ------------------------------------------------------------------
    # Hook start time (measured once at import to cover full hook wall time)
    # ------------------------------------------------------------------
    _HOOK_START = datetime.now()

    # Module-level blocking result; set inside main()'s try block
    _BLOCKING_RESULT = None

    def _detect_result_failure(tool_response):
        """Level 3.7: Detect failure patterns in tool result using FailureDetector."""
        if not _failure_detector or not tool_response:
            return None
        try:
            result_str = str(tool_response)[:2000]
            return _failure_detector.detect_failure_in_message(result_str)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # main()
    # ------------------------------------------------------------------

    def main():
        """PostToolUse hook entry point.

        Reads tool name, input, and response from Claude Code hook stdin
        (JSON), then in order:
          1. Loads task-progress-tracking-policy.py (with 3 retries).
          2. Determines success/error status of the completed tool call.
          3. Loads flow-trace context to get task complexity and skill.
          4. Calculates a complexity-weighted progress delta.
          5. Appends a rich entry to tool-tracker.jsonl.
          6. Updates session-progress.json (with file locking).
          7. Enforces task-update frequency and phase-complexity rules.
          8. Clears task-breakdown and skill-selection flags as appropriate.
          9. Triggers auto-commit, build validation, and GitHub issue
             management on task completion.
         10. Runs BLOCKING checks (Levels 3.8-3.11) and exits 2 on violation.
         11. Runs non-blocking Level 3.12 GitHub issue close.

        Exits 2 on policy violations (blocking).  Exits 0 otherwise.
        """
        sys.stderr.write("[L3.9] Post-tool tracking...\n")
        sys.stderr.flush()

        # Debug log (always-on lightweight file logger)
        debug_file = Path.home() / ".claude" / "memory" / "logs" / "post-tool-tracker-debug.log"

        def debug_log(msg):
            try:
                with open(debug_file, "a", encoding="utf-8") as f:
                    f.write("[" + datetime.now().isoformat() + "] " + msg + "\n")
            except Exception:
                pass

        _track_start_time = datetime.now()
        _sub_operations = []

        # MCP warm-up (non-blocking)
        try:
            _src_mcp_dir = Path(__file__).resolve().parent.parent.parent / "src" / "mcp"
            if str(_src_mcp_dir) not in sys.path:
                sys.path.insert(0, str(_src_mcp_dir))
        except Exception:
            pass

        # Read tool result from stdin
        try:
            raw = sys.stdin.read()
            if not raw or not raw.strip():
                sys.stderr.write("[L3.9] Post-tool tracking complete (no stdin)\n")
                sys.stderr.flush()
                sys.exit(0)
            data = json.loads(raw)
        except Exception as e:
            sys.stderr.write("[L3.9] Post-tool tracking complete (read error: " + str(e)[:30] + ")\n")
            sys.stderr.flush()
            sys.exit(0)

        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        tool_response = data.get("tool_response", {})

        debug_log("POST-TOOL-TRACKER CALLED: tool_name=" + tool_name)
        debug_log("  tool_input keys: " + str(list(tool_input.keys()) if tool_input else "None"))

        try:
            # Determine status
            is_error = is_error_response(tool_response)
            status = "error" if is_error else "success"
            debug_log("  is_error=" + str(is_error) + ", status=" + status)

            # CONTEXT CHAIN: Load flow-trace context from 3-level-flow
            flow_ctx = _load_flow_trace_context(SESSION_STATE_FILE)
            debug_log("  flow_ctx loaded")

            # Level 3.7 - Detect failures in tool result
            failure_info = _detect_result_failure(tool_response)
            debug_log("  failure_info detected")

            # Calculate progress delta (complexity-aware weighting)
            base_delta = 0 if is_error else PROGRESS_DELTA.get(tool_name, 0)
            debug_log("  progress delta calculated: base_delta=" + str(base_delta))
            complexity = flow_ctx.get("complexity", 0)
            if complexity >= 15 and base_delta > 0:
                delta = max(1, base_delta // 4)
            elif complexity >= 8 and base_delta > 0:
                delta = max(1, base_delta // 2)
            else:
                delta = base_delta

            # Build log entry (enriched with task context from flow-trace)
            debug_log("  building log entry")
            entry = {
                "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "tool": tool_name,
                "status": status,
                "progress_delta": delta,
            }
            debug_log("  log entry built, now checking STEP 3.1")

            # Add task context
            debug_log("  [GRANULAR] Step 3.1.1: Adding task context from flow_ctx")
            try:
                if flow_ctx.get("task_type"):
                    entry["task_type"] = flow_ctx["task_type"]
                if flow_ctx.get("complexity"):
                    entry["complexity"] = flow_ctx["complexity"]
                if flow_ctx.get("skill"):
                    entry["skill"] = flow_ctx["skill"]
                debug_log("  [GRANULAR] Step 3.1.1: ? Task context added")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.1: ? EXCEPTION in task context: " + type(e).__name__ + ": " + str(e)[:200]
                )
                raise

            # Rich activity data per tool type
            debug_log("  [GRANULAR] Step 3.1.2: Processing rich activity data for tool_type")
            inp = tool_input or {}

            if tool_name in ("Read", "Write", "Edit", "NotebookEdit"):
                file_path = inp.get("file_path", "") or inp.get("notebook_path", "") or ""
                if file_path:
                    parts = file_path.replace("\\", "/").split("/")
                    entry["file"] = "/".join(parts[-3:]) if len(parts) > 3 else file_path

            if tool_name == "Bash":
                cmd = inp.get("command", "")
                if cmd:
                    entry["command"] = cmd[:200]
                desc = inp.get("description", "")
                if desc:
                    entry["desc"] = desc[:150]

            elif tool_name == "Edit":
                old_s = inp.get("old_string", "")
                new_s = inp.get("new_string", "")
                if old_s or new_s:
                    entry["edit_size"] = len(new_s) - len(old_s)
                    if old_s:
                        entry["old_hint"] = old_s[:80].replace("\n", " ").strip()
                    if new_s:
                        entry["new_hint"] = new_s[:80].replace("\n", " ").strip()

            elif tool_name == "Write":
                content = inp.get("content", "")
                if content:
                    entry["content_lines"] = content.count("\n") + 1

            elif tool_name == "Grep":
                entry["pattern"] = inp.get("pattern", "")[:100]
                if inp.get("path"):
                    parts = inp["path"].replace("\\", "/").split("/")
                    entry["search_path"] = "/".join(parts[-2:]) if len(parts) > 2 else inp["path"]

            elif tool_name == "Glob":
                entry["pattern"] = inp.get("pattern", "")[:100]

            elif tool_name == "Agent":
                entry["desc"] = inp.get("description", "")[:150]
                entry["agent_type"] = inp.get("subagent_type", "")

            elif tool_name == "TaskCreate":
                entry["task_subject"] = inp.get("subject", "")[:150]

            elif tool_name == "TaskUpdate":
                entry["task_status"] = inp.get("status", "")
                entry["task_id"] = inp.get("taskId", "")

            elif tool_name == "Skill":
                entry["skill_name"] = inp.get("skill", "")

            elif tool_name in ("WebSearch", "WebFetch"):
                entry["query"] = inp.get("query", inp.get("url", ""))[:150]

            debug_log("  [GRANULAR] Step 3.1.2: ? Rich activity data processed for " + tool_name)

            # Enrich with failure detection results (3.7 middleware)
            debug_log("  [GRANULAR] Step 3.1.3: Enriching with failure detection")
            try:
                if failure_info:
                    entry["failure_detected"] = True
                    entry["failure_type"] = failure_info.get("type", "unknown")
                    entry["failure_severity"] = failure_info.get("severity", "medium")
                else:
                    entry["failure_detected"] = False
                debug_log("  [GRANULAR] Step 3.1.3: ? Failure detection enriched")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.3: ? EXCEPTION in failure enrichment: "
                    + type(e).__name__
                    + ": "
                    + str(e)[:200]
                )
                raise

            # Log the entry
            debug_log("  [GRANULAR] Step 3.1.4: About to call log_tool_entry()")
            try:
                log_tool_entry(entry, TRACKER_LOG)
                debug_log("  [GRANULAR] Step 3.1.4: ? log_tool_entry() completed")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.4: ? EXCEPTION in log_tool_entry: " + type(e).__name__ + ": " + str(e)[:200]
                )
                raise

            # Update session progress
            debug_log("  [GRANULAR] Step 3.1.5: Loading session progress")
            try:
                state = load_session_progress(SESSION_STATE_FILE)
                debug_log("  [GRANULAR] Step 3.1.5: ? Session progress loaded")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.5: ? EXCEPTION in load_session_progress: "
                    + type(e).__name__
                    + ": "
                    + str(e)[:200]
                )
                raise

            debug_log("  [GRANULAR] Step 3.1.6: Updating progress counters")
            try:
                state["total_progress"] = min(100, state["total_progress"] + delta)
                state["tool_counts"][tool_name] = state["tool_counts"].get(tool_name, 0) + 1
                state["last_tool"] = tool_name
                state["last_tool_at"] = entry["ts"]
                debug_log("  [GRANULAR] Step 3.1.6: ? Progress counters updated")
            except Exception as e:
                debug_log("  [GRANULAR] Step 3.1.6: ? EXCEPTION in counters: " + type(e).__name__ + ": " + str(e)[:200])
                raise

            # Track file modifications since last commit (for git reminder)
            debug_log("  [GRANULAR] Step 3.1.7: Tracking file modifications")
            try:
                if tool_name in ("Write", "Edit", "NotebookEdit") and not is_error:
                    fp = (tool_input or {}).get("file_path", "") or (tool_input or {}).get("notebook_path", "")
                    if fp:
                        modified_files = state.get("modified_files_since_commit", [])
                        short_path = "/".join(fp.replace("\\", "/").split("/")[-3:])
                        if short_path not in modified_files:
                            modified_files.append(short_path)
                        state["modified_files_since_commit"] = modified_files

                if is_error:
                    state["errors_seen"] = state.get("errors_seen", 0) + 1
                debug_log("  [GRANULAR] Step 3.1.7: ? File tracking done")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.7: ? EXCEPTION in file tracking: " + type(e).__name__ + ": " + str(e)[:200]
                )
                raise

            # Track actual response content size for accurate context estimation
            debug_log("  [GRANULAR] Step 3.1.8: Computing context estimates")
            try:
                resp_chars = get_response_content_length(tool_response)
                state["content_chars"] = state.get("content_chars", 0) + resp_chars
                ctx_est = estimate_context_pct(state["tool_counts"], state.get("content_chars", 0))
                state["context_estimate_pct"] = ctx_est
                debug_log("  [GRANULAR] Step 3.1.8: ? Context estimates computed")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.8: ? EXCEPTION in context estimation: "
                    + type(e).__name__
                    + ": "
                    + str(e)[:200]
                )
                raise

            # Track tool optimization statistics (3.7 middleware)
            debug_log("  [GRANULAR] Step 3.1.9: Tracking tool optimization stats")
            try:
                if "tool_optimization_stats" not in state:
                    state["tool_optimization_stats"] = {
                        "total_failures_detected_in_results": 0,
                        "per_tool_failure_counts": {},
                    }
                if failure_info:
                    state["tool_optimization_stats"]["total_failures_detected_in_results"] += 1
                    per_tool = state["tool_optimization_stats"].get("per_tool_failure_counts", {})
                    per_tool[tool_name] = per_tool.get(tool_name, 0) + 1
                    state["tool_optimization_stats"]["per_tool_failure_counts"] = per_tool
                debug_log("  [GRANULAR] Step 3.1.9: ? Tool optimization stats tracked")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.9: ? EXCEPTION in optimization stats: "
                    + type(e).__name__
                    + ": "
                    + str(e)[:200]
                )
                raise

            debug_log("  [GRANULAR] Step 3.1.10: Saving session progress")
            try:
                save_session_progress(state, SESSION_STATE_FILE)
                debug_log("  [GRANULAR] Step 3.1.10: ? Session progress saved")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.10: ? EXCEPTION in save_session_progress: "
                    + type(e).__name__
                    + ": "
                    + str(e)[:200]
                )
                raise

            debug_log("  [GRANULAR] Step 3.1.11: Emitting context sample")
            try:
                _sid_ctx = _get_session_id_from_progress(SESSION_STATE_FILE) or ""
                emit_context_sample(ctx_est, session_id=_sid_ctx, source="post-tool-tracker", tool_name=tool_name)
                debug_log("  [GRANULAR] Step 3.1.11: ? Context sample emitted")
            except Exception as e:
                debug_log(
                    "  [GRANULAR] Step 3.1.11: ?? EXCEPTION in emit_context_sample (non-fatal): "
                    + type(e).__name__
                    + ": "
                    + str(e)[:200]
                )
                # Non-fatal: do not re-raise

            # Policy: Task Progress Update Frequency
            enforce_task_update_frequency(tool_name, flow_ctx, state, debug_log)
            save_session_progress(state, SESSION_STATE_FILE)

            # Policy: Complexity-Aware Phase Reminder
            warn_phase_complexity(tool_name, flow_ctx, state, debug_log)

            # Level 3.1: Clear task-breakdown flag / create GitHub issue on TaskCreate
            sid = _get_session_id_from_progress(SESSION_STATE_FILE)
            handle_task_create(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_response=tool_response,
                is_error=is_error,
                state=state,
                session_id=sid,
                flag_dir=FLAG_DIR,
                get_github_issue_manager=_get_github_issue_manager,
                clear_session_flags=_clear_session_flags,
                save_session_progress=save_session_progress,
                session_state_file=SESSION_STATE_FILE,
                emit_flag_lifecycle=emit_flag_lifecycle,
                debug_log=debug_log,
            )

            # Level 3.5: Clear skill-selection flag
            handle_skill_selection(
                tool_name=tool_name,
                tool_input=tool_input,
                is_error=is_error,
                session_id=sid,
                flag_dir=FLAG_DIR,
                clear_session_flags=_clear_session_flags,
                emit_flag_lifecycle=emit_flag_lifecycle,
                debug_log=debug_log,
            )

            # Loophole #6 fix 2: Subagent Return Reminder
            if tool_name == "Task" and not is_error:
                try:
                    subagent_type = (tool_input or {}).get("subagent_type", "unknown")
                    sys.stderr.write(
                        "[POST-TOOL L6.2] Subagent returned! (type: " + subagent_type + ")\n"
                        "  REMINDER: Subagent cannot call TaskUpdate - YOU must do it.\n"
                        "  ACTION: Review subagent result -> TaskUpdate(completed) if task is done.\n"
                        "  RULE: Parent = Orchestrator. Only parent mutates task state.\n"
                    )
                    sys.stderr.flush()
                except Exception:
                    pass

            # Level 3.11 + Loophole #6 fix 3: Phase Completion Guard
            if tool_name == "TaskUpdate" and not is_error:
                try:
                    task_status = (tool_input or {}).get("status", "")
                    if task_status == "completed":
                        state["tasks_completed"] = state.get("tasks_completed", 0) + 1
                        completed_count = state.get("tasks_completed", 1)
                        state["modified_files_since_commit"] = []
                        save_session_progress(state, SESSION_STATE_FILE)
                        sys.stderr.write(
                            "[POST-TOOL L3.11] Task marked COMPLETED (#" + str(completed_count) + ")!\n"
                            "  PHASE GUARD: Check ALL tasks in current phase.\n"
                            "  IF no tasks remain in_progress in this phase" + ": " + "\n"
                            "    -> Phase is COMPLETE -> git add + git commit + git push IMMEDIATELY.\n"
                            "  IF tasks still in_progress" + ": " + "\n"
                            "    -> Continue working on remaining tasks.\n"
                            "  RULE: Phase completion = ALL tasks done, not just this one.\n"
                            "  RULE: DO NOT skip git commit on phase completion.\n"
                        )
                        sys.stderr.flush()

                        sys.stderr.write(
                            "[POST-TOOL VOICE] Task #" + str(completed_count) + " completed.\n"
                            "  CHECK: Are ALL tasks now completed?\n"
                            "  IF YES -> Write ~/.claude/.session-work-done with session summary.\n"
                            '  Command: python -c "from pathlib import Path; '
                            "Path.home().joinpath('.claude','.session-work-done')"
                            ".write_text('Sir, all tasks completed. [YOUR SUMMARY HERE]', encoding='utf-8')\"\n"
                        )
                        sys.stderr.flush()

                        # GitHub Issues: Close issue for completed task
                        try:
                            gim = _get_github_issue_manager()
                            if gim:
                                closed_task_id = (tool_input or {}).get("taskId", "")
                                if closed_task_id:
                                    closed = gim.close_github_issue(closed_task_id)
                                    if closed:
                                        sys.stderr.write("[GH] Issue closed for task " + str(closed_task_id) + "\n")
                                        sys.stderr.flush()

                                # SESSION-ISSUE-BASED WORK_DONE
                                try:
                                    mapping = gim._load_mapping()
                                    task_issues = mapping.get("task_to_issue", {})
                                    branch = mapping.get("branch", "")
                                    if task_issues and branch:
                                        all_closed = all(d.get("status") == "closed" for d in task_issues.values())
                                        if all_closed:
                                            work_done_flag = Path.home() / ".claude" / ".session-work-done"
                                            if not work_done_flag.exists():
                                                work_done_flag.parent.mkdir(parents=True, exist_ok=True)
                                                issue_count = len(task_issues)
                                                work_done_flag.write_text(
                                                    "All "
                                                    + str(issue_count)
                                                    + " session issues closed on branch "
                                                    + branch
                                                    + ". Auto-written by post-tool-tracker (issue-based).",
                                                    encoding="utf-8",
                                                )
                                                sys.stderr.write(
                                                    "[AUTO] .session-work-done written (all "
                                                    + str(issue_count)
                                                    + " issues closed on "
                                                    + branch
                                                    + ") -> PR workflow will trigger on Stop hook\n"
                                                )
                                                sys.stderr.flush()
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # AUTO-COMMIT: Check via MCP if commit should trigger
                        try:
                            _src_mcp = Path(__file__).resolve().parent.parent.parent / "src" / "mcp"
                            if str(_src_mcp) not in sys.path:
                                sys.path.insert(0, str(_src_mcp))
                            from post_tool_tracker_mcp_server import check_commit_readiness

                            _commit_check = json.loads(check_commit_readiness())
                            if _commit_check.get("should_commit"):
                                sys.stderr.write(
                                    "[POST-TOOL L3.11] Auto-commit ready: " + _commit_check.get("reason", "") + "\n"
                                )
                                sys.stderr.flush()
                                import subprocess as _subprocess

                                _script_dir = _SCRIPTS_DIR
                                _commit_enforcer = os.path.join(
                                    _script_dir,
                                    "architecture",
                                    "03-execution-system",
                                    "09-git-commit",
                                    "auto-commit-enforcer.py",
                                )
                                if os.path.exists(_commit_enforcer):
                                    _subprocess.run(
                                        [sys.executable, _commit_enforcer, "--enforce-now"],
                                        timeout=60,
                                        capture_output=True,
                                    )
                            else:
                                sys.stderr.write(
                                    "[POST-TOOL L3.11] Auto-commit: " + _commit_check.get("reason", "not ready") + "\n"
                                )
                                sys.stderr.flush()
                        except Exception:
                            pass

                        # BUILD VALIDATION: Compile check on task completion
                        try:
                            if _SCRIPTS_DIR not in sys.path:
                                sys.path.insert(0, _SCRIPTS_DIR)
                            import auto_build_validator

                            modified = state.get("modified_files_since_commit", [])
                            build_result = auto_build_validator.validate_build(modified_files=modified)
                            if build_result["all_passed"]:
                                state["last_build_failed"] = False
                                state["last_build_failed_label"] = ""
                                save_session_progress(state, SESSION_STATE_FILE)
                                sys.stderr.write("[BUILD] " + build_result["summary"] + "\n")
                                sys.stderr.flush()
                            else:
                                failed_labels = [
                                    r["label"] for r in build_result.get("results", []) if not r.get("passed")
                                ]
                                state["last_build_failed"] = True
                                state["last_build_failed_label"] = (
                                    ", ".join(failed_labels)
                                    if failed_labels
                                    else build_result.get("summary", "unknown")
                                )
                                save_session_progress(state, SESSION_STATE_FILE)
                                sys.stderr.write(
                                    "[BUILD FAILED] " + build_result["summary"] + "\n"
                                    "  ACTION: FIX the build errors below BEFORE moving to next task!\n"
                                    "  DO NOT mark this task complete until build passes.\n"
                                    "  NOTE: Next TaskUpdate(completed) will be BLOCKED until build passes (L3.9).\n"
                                )
                                for r in build_result["results"]:
                                    if not r["passed"]:
                                        sys.stderr.write(
                                            "  --- " + r["label"] + " ---\n" + r.get("output", "")[:1500] + "\n"
                                        )
                                sys.stderr.flush()
                        except Exception:
                            pass

                        # AUTO WORK-DONE: Write .session-work-done flag when ALL tasks complete
                        try:
                            tasks_created = state.get("tasks_created", 0)
                            tasks_completed_now = state.get("tasks_completed", 0)
                            if tasks_created > 0 and tasks_completed_now >= tasks_created:
                                work_done_flag = Path.home() / ".claude" / ".session-work-done"
                                work_done_flag.parent.mkdir(parents=True, exist_ok=True)
                                summary_text = "All " + str(tasks_completed_now) + " tasks completed successfully."
                                work_done_flag.write_text(summary_text, encoding="utf-8")
                                sys.stderr.write(
                                    "[AUTO] .session-work-done written ("
                                    + str(tasks_completed_now)
                                    + "/"
                                    + str(tasks_created)
                                    + " tasks done)\n"
                                )
                                sys.stderr.flush()

                                # Call stop-notifier.py immediately with summary context
                                try:
                                    import subprocess as _subprocess

                                    _stop_script = os.path.join(_HOOKS_DIR, "stop-notifier.py")
                                    if os.path.exists(_stop_script):
                                        _env = os.environ.copy()
                                        _env["WORK_DONE_SUMMARY"] = summary_text
                                        _sr = _subprocess.run(
                                            [sys.executable, _stop_script], timeout=90, capture_output=True, env=_env
                                        )
                                        if _sr.returncode == 0:
                                            sys.stderr.write("[VOICE] Voice notification triggered with task summary\n")
                                        else:
                                            sys.stderr.write(
                                                "[VOICE] Voice trigger sent (result: " + str(_sr.returncode) + ")\n"
                                            )
                                        sys.stderr.flush()
                                except Exception:
                                    sys.stderr.write("[VOICE] Voice notification attempt made (may be async)\n")
                                    sys.stderr.flush()
                        except Exception:
                            pass

                except Exception:
                    pass

            # -----------------------------------------------------------------------
            # BLOCKING ENFORCEMENT: Levels 3.8-3.12 (v4.0.0)
            # -----------------------------------------------------------------------
            global _BLOCKING_RESULT
            try:
                _block, _msg = check_level_3_8_phase_requirement(tool_name, flow_ctx, state)
                if not _block:
                    _block, _msg = check_level_3_9_build_validation(tool_name, tool_input, is_error, state)
                if not _block:
                    _block, _msg = check_level_3_10_version_release(tool_name, tool_input, state)
                if not _block:
                    _block, _msg = check_uncommitted_before_push(tool_name, tool_input)
                if _block:
                    _BLOCKING_RESULT = (2, _msg)
                # Level 3.12: non-blocking GitHub issue close (runs regardless)
                close_github_issues_on_completion(tool_name, tool_input, tool_response, is_error, state)
                # Level 3.10+: Post-merge version auto-update (non-blocking)
                run_post_merge_version_update(tool_name, tool_input, is_error)
            except Exception:
                pass  # Never block on enforcement errors (fail-open)

            # GIT REMINDER: When 10+ files modified without commit
            modified_count = len(state.get("modified_files_since_commit", []))
            if modified_count >= 10 and tool_name in ("Write", "Edit", "NotebookEdit"):
                sys.stderr.write(
                    "[POST-TOOL GIT] WARNING: " + str(modified_count) + " files modified since last commit!\n"
                    "  ACTION: Consider running git add + git commit + git push.\n"
                    "  FILES: " + ", ".join(state.get("modified_files_since_commit", [])[-5:]) + "...\n"
                )
                sys.stderr.flush()

            # Write .context-usage (context-monitor fallback path)
            try:
                context_usage_file = Path.home() / ".claude" / "memory" / ".context-usage"
                context_usage_file.parent.mkdir(parents=True, exist_ok=True)
                with open(context_usage_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "percentage": ctx_est,
                            "updated_at": entry["ts"],
                            "source": "post-tool-tracker dynamic estimate",
                            "tool_counts": state["tool_counts"],
                        },
                        f,
                    )
            except Exception:
                pass

        except Exception:
            pass  # NEVER block on tracking errors

        # Emit hook execution metrics
        try:
            _sid_fin = _get_session_id_from_progress(SESSION_STATE_FILE) or ""
            _dur_fin = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
            emit_hook_execution(
                "post-tool-tracker.py",
                _dur_fin,
                session_id=_sid_fin,
                exit_code=0,
                extra={"tool": tool_name if "tool_name" in dir() else ""},
            )
        except Exception:
            pass

        # Policy execution tracking
        try:
            _resolved_tool = tool_name if "tool_name" in dir() else "unknown"
            _resolved_sid = get_session_id()

            _op1_start = datetime.now()
            _op1_duration = int((datetime.now() - _op1_start).total_seconds() * 1000)
            _sub_operations.append(
                record_sub_operation(
                    session_id=_resolved_sid,
                    policy_name="post-tool-tracker",
                    operation_name="process_tool_call",
                    input_params={"tool_name": _resolved_tool},
                    output_results={"tracked": True},
                    duration_ms=_op1_duration,
                )
            )

            _op2_start = datetime.now()
            _op2_duration = int((datetime.now() - _op2_start).total_seconds() * 1000)
            _sub_operations.append(
                record_sub_operation(
                    session_id=_resolved_sid,
                    policy_name="post-tool-tracker",
                    operation_name="update_session_progress",
                    input_params={"tool_name": _resolved_tool},
                    output_results={"progress_updated": True},
                    duration_ms=_op2_duration,
                )
            )

            _op3_start = datetime.now()
            _op3_duration = int((datetime.now() - _op3_start).total_seconds() * 1000)
            _sub_operations.append(
                record_sub_operation(
                    session_id=_resolved_sid,
                    policy_name="post-tool-tracker",
                    operation_name="enforce_policy_rules",
                    input_params={"tool_name": _resolved_tool},
                    output_results={"enforcement_checked": True},
                    duration_ms=_op3_duration,
                )
            )

            _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
            record_policy_execution(
                session_id=_resolved_sid,
                policy_name="post-tool-tracker",
                policy_script="post-tool-tracker.py",
                policy_type="Utility Hook",
                input_params={"tool_name": _resolved_tool},
                output_results={"status": "success", "tool_tracked": _resolved_tool},
                decision="Tracked tool call: " + _resolved_tool,
                duration_ms=_duration_ms,
                sub_operations=_sub_operations if _sub_operations else None,
            )
        except Exception:
            pass

        # BLOCKING RESULT EVALUATION (must be outside broad try/except)
        if _BLOCKING_RESULT is not None:
            exit_code, block_msg = _BLOCKING_RESULT
            sys.stderr.write(block_msg + "\n")
            sys.stderr.flush()
            try:
                _sid_blk = _get_session_id_from_progress(SESSION_STATE_FILE) or ""
                _dur_blk = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
                emit_hook_execution(
                    "post-tool-tracker.py",
                    _dur_blk,
                    session_id=_sid_blk,
                    exit_code=exit_code,
                    extra={"blocked": True, "block_level": block_msg[:30]},
                )
            except Exception:
                pass
            sys.exit(exit_code)

        sys.stderr.write("[L3.9] Post-tool tracking complete\n")
        sys.stderr.flush()
        sys.exit(0)
