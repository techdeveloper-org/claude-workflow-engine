"""stop_notifier/core.py - Main entry point for Stop hook.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

import json
import os
import sys
from datetime import datetime

from .helpers import get_current_session_id, log_s, read_hook_stdin
from .post_impl import _create_pr_from_pipeline_data, _run_post_implementation_steps
from .voice import (
    get_session_start_default,
    get_session_summary_for_voice,
    get_task_complete_default,
    get_work_done_default,
    handle_voice_flag,
)


def main():
    """Stop hook entry point - run session maintenance then trigger voice notifications.

    Executed by Claude Code after every AI response (Stop event).  The function:
      1. Loads and runs auto-commit-enforcer.py with up to 3 retries.
      2. Runs auto-save-session.py, archive-old-sessions.py, and
         failure-detector.py for end-of-response session maintenance.
      3. Resolves PID-isolated voice flag files in priority order:
           a. .session-start-voice-{PID}  -> new session greeting
           b. .task-complete-voice-{PID}  -> task completion notification
           c. .session-work-done-{PID}    -> all work done wrap-up
      4. Falls back to legacy shared flag paths for backward compatibility.
      5. Generates voice messages via static defaults.
      6. Launches voice-notifier.py as a detached background process.

    Always exits 0.  Errors in any phase are caught and logged to
    stop-notifier.log without disrupting subsequent phases.
    """
    # INTEGRATION: Load git commit policies from scripts/architecture/
    # Retry up to 3 times per policy script. Warn on failure (Stop hook
    # should not hard-break; it runs AFTER the response is sent).
    try:
        import subprocess
        from pathlib import Path

        _scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
        git_commit_script = (
            _scripts_dir / "architecture" / "03-execution-system" / "09-git-commit" / "git-auto-commit-policy.py"
        )
        if git_commit_script.exists():
            _commit_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(git_commit_script), "--enforce"], timeout=60, capture_output=True
                    )
                    if _r.returncode == 0:
                        _commit_ok = True
                        break
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] auto-commit-enforcer failed, retrying...")
                except Exception:
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] auto-commit-enforcer error, retrying...")
            if not _commit_ok:
                log_s("[POLICY-WARN] auto-commit-enforcer failed after 3 retries")
    except Exception:
        pass

    read_hook_stdin()

    # =========================================================================
    # SESSION END MAINTENANCE (non-blocking, before voice)
    # Architecture scripts: auto-save-session, archive-old-sessions, failure-detector
    # =========================================================================
    # 1. Auto-save session state before cleanup (3 retries)
    # Architecture: 01-sync-system/session-management/auto-save-session.py
    try:
        save_script = _scripts_dir / "architecture" / "01-sync-system" / "session-management" / "auto-save-session.py"
        if save_script.exists():
            project_name = Path.cwd().name
            _save_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(save_script), "--project", project_name], timeout=10, capture_output=True
                    )
                    if _r.returncode == 0:
                        _save_ok = True
                        break
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] auto-save-session failed, retrying...")
                except Exception:
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] auto-save-session error, retrying...")
            if _save_ok:
                log_s("[SESSION-SAVE] Auto-saved session for: " + project_name)
            else:
                log_s("[POLICY-WARN] auto-save-session failed after 3 retries")
    except Exception as e:
        log_s("[SESSION-SAVE] Skipped: " + str(e))

    # 2. Archive old sessions - keep last 10, archive >30 days (3 retries)
    # Architecture: 01-sync-system/session-management/archive-old-sessions.py
    try:
        archive_script = (
            _scripts_dir / "architecture" / "01-sync-system" / "session-management" / "archive-old-sessions.py"
        )
        if archive_script.exists():
            _arch_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run([sys.executable, str(archive_script)], timeout=10, capture_output=True)
                    if _r.returncode == 0:
                        _arch_ok = True
                        break
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] archive-old-sessions failed, retrying...")
                except Exception:
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] archive-old-sessions error, retrying...")
            if _arch_ok:
                log_s("[SESSION-ARCHIVE] Old sessions archived")
            else:
                log_s("[POLICY-WARN] archive-old-sessions failed after 3 retries")
    except Exception as e:
        log_s("[SESSION-ARCHIVE] Skipped: " + str(e))

    # 2b. Session log pruning - prune old sessions (30-day max, keep 10)
    # Architecture: 01-sync-system/session-pruner.py
    try:
        pruner_script = _scripts_dir / "architecture" / "01-sync-system" / "session-pruner.py"
        if pruner_script.exists():
            _prune_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(pruner_script), "--max-age", "30", "--keep-min", "10"],
                        timeout=15,
                        capture_output=True,
                    )
                    if _r.returncode == 0:
                        _prune_ok = True
                        break
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] session-pruner failed, retrying...")
                except Exception:
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] session-pruner error, retrying...")
            if _prune_ok:
                log_s("[SESSION-PRUNE] Old session logs pruned")
            else:
                log_s("[POLICY-WARN] session-pruner failed after 3 retries")
    except Exception as e:
        log_s("[SESSION-PRUNE] Skipped: " + str(e))

    # 3. Failure detection analysis - learn from errors (3 retries)
    # Architecture: 03-execution-system/failure-prevention/common-failures-prevention.py --analyze
    try:
        failure_script = (
            _scripts_dir
            / "architecture"
            / "03-execution-system"
            / "failure-prevention"
            / "common-failures-prevention.py"
        )
        if failure_script.exists():
            _fail_ok = False
            for _attempt in range(1, 4):
                try:
                    _r = subprocess.run(
                        [sys.executable, str(failure_script), "--analyze"], timeout=10, capture_output=True
                    )
                    if _r.returncode == 0:
                        _fail_ok = True
                        break
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] failure-detector failed, retrying...")
                except Exception:
                    if _attempt < 3:
                        log_s("[RETRY " + str(_attempt) + "/3] failure-detector error, retrying...")
            if _fail_ok:
                log_s("[FAILURE-DETECT] Failure patterns analyzed")
            else:
                log_s("[POLICY-WARN] failure-detector failed after 3 retries")
    except Exception as e:
        log_s("[FAILURE-DETECT] Skipped: " + str(e))

    # 4. Preference auto-detection - learn user preferences from session
    # Architecture: 01-sync-system/user-preferences/preference-auto-tracker.py
    try:
        pref_script = (
            _scripts_dir / "architecture" / "01-sync-system" / "user-preferences" / "preference-auto-tracker.py"
        )
        if pref_script.exists():
            _r = subprocess.run([sys.executable, str(pref_script)], timeout=10, capture_output=True)
            if _r.returncode == 0:
                log_s("[PREFERENCES] Auto-detected from session")
            else:
                log_s("[PREFERENCES] Detection skipped (no new patterns)")
    except Exception:
        pass

    # 4. Archive plan file to session folder (if plan mode was used this session)
    # Policy: 03-execution-system/02-plan-mode/auto-plan-mode-suggestion-policy.md (v2.0)
    # Script: 03-execution-system/02-plan-mode/plan-session-archiver.py
    try:
        plan_archiver_script = (
            _scripts_dir / "architecture" / "03-execution-system" / "02-plan-mode" / "plan-session-archiver.py"
        )
        if plan_archiver_script.exists():
            _plan_session_id = get_current_session_id()
            if _plan_session_id:
                _plan_ok = False
                for _attempt in range(1, 4):
                    try:
                        _r = subprocess.run(
                            [sys.executable, str(plan_archiver_script), "--archive", _plan_session_id],
                            timeout=10,
                            capture_output=True,
                        )
                        if _r.returncode == 0:
                            _plan_ok = True
                            break
                        if _attempt < 3:
                            log_s("[RETRY " + str(_attempt) + "/3] plan-session-archiver failed, retrying...")
                    except Exception:
                        if _attempt < 3:
                            log_s("[RETRY " + str(_attempt) + "/3] plan-session-archiver error, retrying...")
                if _plan_ok:
                    log_s("[PLAN-ARCHIVE] Plan checked/archived for session: " + _plan_session_id)
                else:
                    log_s("[POLICY-WARN] plan-session-archiver failed after 3 retries")
    except Exception as e:
        log_s("[PLAN-ARCHIVE] Skipped: " + str(e))

    spoke_something = False

    # =========================================================================
    # PID-ISOLATED FLAG RESOLUTION (Loophole #11 fix)
    #
    # Resolution order for each flag type:
    #   1. PID-specific flag  (.session-start-voice-{PID}) - preferred
    #   2. Legacy shared flag (.session-start-voice)        - backward compat
    #
    # By checking PID-specific first, each window only processes its own flags.
    # The legacy shared flag path is checked as a fallback for compatibility
    # with scripts that have not yet been updated to write PID-specific flags.
    # =========================================================================

    def _resolve_flag(pid_flag, legacy_flag):
        """Return the first existing flag path (PID-specific preferred over legacy)."""
        if pid_flag.exists():
            log_s(f"[flag-resolve] Using PID-isolated flag: {pid_flag.name}")
            return pid_flag
        if legacy_flag.exists():
            log_s(f"[flag-resolve] Using legacy shared flag (backward compat): {legacy_flag.name}")
            return legacy_flag
        return None

    # PRIORITY 1: Session start voice
    _start_flag = _resolve_flag(SESSION_START_FLAG_PID, SESSION_START_FLAG)
    if _start_flag is not None:
        spoke_something = handle_voice_flag(
            _start_flag,
            "session_start",
            get_session_start_default,
        )

    # PRIORITY 2: Task complete voice (with session summary context)
    _task_flag = _resolve_flag(TASK_COMPLETE_FLAG_PID, TASK_COMPLETE_FLAG)
    if _task_flag is not None:
        summary_context = get_session_summary_for_voice()
        spoke_something = handle_voice_flag(
            _task_flag,
            "task_complete",
            get_task_complete_default,
            extra_context=summary_context,
        )

    # PRIORITY 3: All work done - trigger PR workflow first, then voice
    pr_triggered = False
    _work_done_flag = _resolve_flag(WORK_DONE_FLAG_PID, WORK_DONE_FLAG)
    if _work_done_flag is not None:
        # GitHub PR Workflow: commit, push, PR, review, merge (non-blocking)
        pr_merged = False
        try:
            script_dir = Path(__file__).parent
            if str(script_dir) not in sys.path:
                sys.path.insert(0, str(script_dir))
            import github_pr_workflow

            pr_merged = github_pr_workflow.run_pr_workflow()
            pr_triggered = True
        except Exception as e:
            log_s(f"[PR-WORKFLOW] Error: {e}")

        # Voice notification (after PR workflow)
        # v4.1.0: Check for WORK_DONE_SUMMARY env var (set by post-tool-tracker.py)
        summary_context = os.environ.get("WORK_DONE_SUMMARY", "")
        if not summary_context:
            summary_context = get_session_summary_for_voice()
        spoke_something = handle_voice_flag(
            _work_done_flag,
            "work_done",
            get_work_done_default,
            extra_context=summary_context,
        )

        # If PR workflow failed to merge, write a retry flag so next Stop can retry
        if pr_triggered and not pr_merged:
            try:
                retry_flag = FLAG_DIR / ".pr-workflow-retry"
                retry_flag.write_text("PR workflow ran but merge failed - retry on next Stop", encoding="utf-8")
                log_s("[PR-WORKFLOW] Merge failed - retry flag written for next Stop")
            except Exception:
                pass

    # PRIORITY 3b: PR workflow retry (from previous failed merge attempt)
    if not pr_triggered and (FLAG_DIR / ".pr-workflow-retry").exists():
        try:
            # Check if still on a feature branch - if on main, clean up stale flag
            _retry_branch = subprocess.run(
                ["git", "branch", "--show-current"], capture_output=True, text=True, timeout=5
            )
            _retry_current = _retry_branch.stdout.strip() if _retry_branch.returncode == 0 else ""
            if _retry_current in ("main", "master", ""):
                # On main/master - PR was already merged or branch deleted, clean up flag
                (FLAG_DIR / ".pr-workflow-retry").unlink(missing_ok=True)
                log_s("[PR-WORKFLOW] Retry flag cleaned (on main - nothing to retry)")
            else:
                script_dir = Path(__file__).parent
                if str(script_dir) not in sys.path:
                    sys.path.insert(0, str(script_dir))
                import github_pr_workflow

                pr_merged = github_pr_workflow.run_pr_workflow()
                if pr_merged:
                    (FLAG_DIR / ".pr-workflow-retry").unlink(missing_ok=True)
                    log_s("[PR-WORKFLOW] Retry succeeded - PR merged")
                else:
                    log_s("[PR-WORKFLOW] Retry failed - will try again on next Stop")
        except Exception as e:
            log_s(f"[PR-WORKFLOW] Retry error: {e}")

    # PRIORITY 4: Branch-based PR detection (fallback when work_done flag was never written)
    # This catches sessions where Claude works without TaskCreate/TaskUpdate
    # Also ensures version bump + PR workflow runs even for manual PR creation
    if not pr_triggered:
        try:
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"], capture_output=True, text=True, timeout=5
            )
            current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""

            if current_branch and current_branch not in ("main", "master"):
                # On a feature branch - check if work is done
                should_trigger = False
                trigger_reason = ""

                # Check 1: All session issues are closed
                session_issues_file = _get_session_issues_file()
                if session_issues_file and session_issues_file.exists():
                    try:
                        mapping = json.loads(session_issues_file.read_text(encoding="utf-8"))
                        task_issues = mapping.get("task_to_issue", {})
                        if task_issues:
                            all_closed = all(d.get("status") == "closed" for d in task_issues.values())
                            if all_closed:
                                should_trigger = True
                                trigger_reason = "all issues closed"
                    except Exception:
                        pass

                # Check 2: No tracked issues but all tasks completed
                # (covers manual PR creation where github-issues.json is missing)
                if not should_trigger:
                    try:
                        progress_file = MEMORY_BASE / "logs" / "session-progress.json"
                        if progress_file.exists():
                            with open(progress_file, "r", encoding="utf-8") as f:
                                progress = json.load(f)
                            tasks_created = progress.get("tasks_created", 0)
                            tasks_completed = progress.get("tasks_completed", 0)
                            if tasks_created > 0 and tasks_completed >= tasks_created:
                                should_trigger = True
                                trigger_reason = f"all {tasks_completed} tasks completed"
                    except Exception:
                        pass

                # Check 3: Feature branch has commits ahead + clean working tree + debounce
                # Debounce: Only ship after 60s of inactivity (no tool calls)
                # This prevents shipping mid-work when Claude is still coding
                if not should_trigger:
                    try:
                        ahead_result = subprocess.run(
                            ["git", "rev-list", "--count", f"main..{current_branch}"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        commits_ahead = int(ahead_result.stdout.strip()) if ahead_result.returncode == 0 else 0

                        if commits_ahead > 0:
                            # Also check: working tree must be clean (no uncommitted changes)
                            status_result = subprocess.run(
                                ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5
                            )
                            working_tree_clean = not status_result.stdout.strip()

                            if working_tree_clean:
                                # Debounce: write "ready" timestamp, only ship if 60s old
                                ready_flag = FLAG_DIR / ".pr-ready-timestamp"
                                now = time.time()

                                if ready_flag.exists():
                                    try:
                                        ready_ts = float(ready_flag.read_text(encoding="utf-8").strip())
                                        age = now - ready_ts
                                        if age >= 60:
                                            # 60s of quiet + clean tree + commits ahead = SHIP
                                            should_trigger = True
                                            trigger_reason = (
                                                f"{commits_ahead} commits ahead, " f"clean tree, {int(age)}s idle"
                                            )
                                            ready_flag.unlink(missing_ok=True)
                                        else:
                                            log_s(
                                                f"[PR-WORKFLOW] Ready to ship but debouncing "
                                                f"({int(age)}s/{60}s) - waiting for idle"
                                            )
                                    except (ValueError, OSError):
                                        ready_flag.write_text(str(now), encoding="utf-8")
                                else:
                                    # First time ready - write timestamp, ship on next Stop
                                    ready_flag.write_text(str(now), encoding="utf-8")
                                    log_s(
                                        f"[PR-WORKFLOW] Ready to ship: {commits_ahead} commits ahead, "
                                        f"clean tree. Debounce started (60s)."
                                    )
                            else:
                                # Uncommitted changes = still working, reset debounce
                                ready_flag = FLAG_DIR / ".pr-ready-timestamp"
                                ready_flag.unlink(missing_ok=True)
                    except Exception:
                        pass

                if should_trigger:
                    log_s(
                        f"[PR-WORKFLOW] Branch detection: on {current_branch} ({trigger_reason}) - triggering PR workflow (includes version bump)"
                    )
                    script_dir = Path(__file__).parent
                    if str(script_dir) not in sys.path:
                        sys.path.insert(0, str(script_dir))
                    import github_pr_workflow

                    github_pr_workflow.run_pr_workflow()
        except Exception as e:
            log_s(f"[PR-WORKFLOW] Branch detection error: {e}")

    if not spoke_something:
        log_s("[OK] Stop hook fired | No voice flags found (normal, most stops are silent)")

    # Post-implementation steps 11-14 (close issue, update docs, generate summary)
    _run_post_implementation_steps()

    # Auto-create PR from pipeline data (non-blocking)
    _create_pr_from_pipeline_data()

    try:
        _dur_stop = int((datetime.now() - _HOOK_START).total_seconds() * 1000)
        emit_hook_execution("stop-notifier.py", _dur_stop, session_id="", exit_code=0, extra={"spoke": spoke_something})
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
