"""stop_notifier/post_impl.py - Post-implementation pipeline steps.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

import json
import os
import sys
from pathlib import Path

from .helpers import log_s


def _find_latest_session_dir():
    """Find the most recent session directory under ~/.claude/logs/sessions/.

    Checks the CURRENT_SESSION_ID environment variable first, then falls back
    to the most recently modified directory under the sessions base path.

    Returns:
        Path or None: Path to the session directory, or None if not found.
    """
    sessions_base = Path.home() / ".claude" / "logs" / "sessions"
    if not sessions_base.exists():
        return None

    session_id = os.environ.get("CURRENT_SESSION_ID", "")
    if session_id:
        session_dir = sessions_base / session_id
        if session_dir.exists():
            return session_dir

    # Fallback: find most recent session folder by mtime
    try:
        dirs = sorted(
            [d for d in sessions_base.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        return dirs[0] if dirs else None
    except Exception:
        return None


def _create_pr_from_pipeline_data():
    """Auto-create PR using pipeline Step 7 prompt data and Step 0 classification.

    Reads session folder for pipeline outputs and creates a GitHub PR
    if commits are detected ahead of main on the current feature branch.
    Wrapped in try/except so it never crashes the stop hook.
    """

    try:
        # 1. Check if we are on a feature branch with commits ahead of main
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10
        )
        current_branch = branch_result.stdout.strip()

        if current_branch in ("main", "master", "HEAD", ""):
            return  # Not on a feature branch

        # Check commits ahead
        ahead_result = subprocess.run(
            ["git", "rev-list", "--count", "main..HEAD"], capture_output=True, text=True, timeout=10
        )
        commits_ahead = int(ahead_result.stdout.strip() or "0")

        if commits_ahead == 0:
            return  # No new commits

        # 2. Find the latest session folder
        session_dir = _find_latest_session_dir()
        if not session_dir:
            return

        # 3. Read pipeline data
        task_type = "task"
        complexity = 5
        skill = ""
        user_msg = ""
        system_prompt_summary = ""

        # Read execution summary
        summary_file = session_dir / "execution-summary.txt"
        if summary_file.exists():
            try:
                summary_text = summary_file.read_text(encoding="utf-8")
                for part in summary_text.split(" | "):
                    if part.startswith("Task:"):
                        task_type = part.split(":", 1)[1].strip()
                    elif part.startswith("Complexity:"):
                        try:
                            complexity = int(part.split(":")[1].strip().split("/")[0])
                        except (ValueError, IndexError):
                            pass
                    elif part.startswith("Skill:"):
                        skill = part.split(":", 1)[1].strip()
            except Exception as e:
                log_s(f"[PR-AUTO] Could not read execution-summary.txt: {e}")

        # Read user message
        user_msg_file = session_dir / "user_message.txt"
        if user_msg_file.exists():
            try:
                user_msg = user_msg_file.read_text(encoding="utf-8").strip()
            except Exception as e:
                log_s(f"[PR-AUTO] Could not read user_message.txt: {e}")

        # Read system prompt for PR body
        system_prompt_file = session_dir / "system_prompt.txt"
        if system_prompt_file.exists():
            try:
                system_prompt_summary = system_prompt_file.read_text(encoding="utf-8")[:2000]
            except Exception as e:
                log_s(f"[PR-AUTO] Could not read system_prompt.txt: {e}")

        # 4. Build PR title and body
        first_line = (user_msg.split("\n")[0] if user_msg else "implementation").strip()
        if len(first_line) > 60:
            first_line = first_line[:57] + "..."

        # Map task type to conventional commit prefix
        prefix_map = {
            "Bug Fix": "fix",
            "Feature": "feat",
            "Enhancement": "feat",
            "Refactoring": "refactor",
            "Documentation": "docs",
            "Test": "test",
        }
        prefix = prefix_map.get(task_type, "feat")
        pr_title = f"{prefix}: {first_line}"

        # Build PR body
        pr_body_parts = [
            "## Summary",
            "",
            f"**Task Type:** {task_type}",
            f"**Complexity:** {complexity}/10",
        ]
        if skill:
            pr_body_parts.append(f"**Skill:** {skill}")
        pr_body_parts.append(f"**Commits:** {commits_ahead}")
        pr_body_parts.append(f"**Branch:** {current_branch}")
        pr_body_parts.append("")

        if system_prompt_summary:
            pr_body_parts.append("## Context")
            pr_body_parts.append("")
            pr_body_parts.append(system_prompt_summary[:500])
            pr_body_parts.append("")

        pr_body_parts.append("---")
        pr_body_parts.append("*Auto-generated by Claude Workflow Engine*")

        pr_body = "\n".join(pr_body_parts)

        # 5. Create PR via GitHub MCP (direct import)
        _src_mcp = Path(__file__).resolve().parent.parent / "src" / "mcp"
        if str(_src_mcp) not in sys.path:
            sys.path.insert(0, str(_src_mcp))

        from github_mcp_server import github_create_pr

        result_json = github_create_pr(
            title=pr_title,
            body=pr_body,
            head=current_branch,
            base="main",
        )

        result = json.loads(result_json)
        if result.get("success"):
            pr_url = result.get("url", result.get("html_url", ""))
            log_s(f"[PR-AUTO] PR created: {pr_url}")
            print(f"[STOP] PR created: {pr_url}", file=sys.stderr)
        else:
            error = result.get("error", "")
            if "already exists" in str(error).lower():
                log_s(f"[PR-AUTO] PR already exists for {current_branch}")
                print(f"[STOP] PR already exists for {current_branch}", file=sys.stderr)
            else:
                log_s(f"[PR-AUTO] PR creation note: {error}")
                print(f"[STOP] PR auto-create note: {error}", file=sys.stderr)

    except Exception as e:
        # Never crash the stop hook
        log_s(f"[PR-AUTO] PR auto-create skipped: {e}")
        print(f"[STOP] PR auto-create skipped: {e}", file=sys.stderr)


# =============================================================================
# POST-IMPLEMENTATION STEPS (11-14) - Hook mode autonomy
# =============================================================================


def _run_post_implementation_steps():
    """Run Steps 11-14 automatically after Claude finishes implementation.

    In hook mode, Steps 0-9 run in the pipeline before Claude works.
    Steps 10+ are Claude's implementation. When Claude stops and we
    detect commits on a feature branch, we run the remaining steps.
    """

    try:
        # Check if on feature branch with commits
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10
        )
        current_branch = branch_result.stdout.strip()

        if current_branch in ("main", "master", "HEAD", ""):
            return

        ahead_result = subprocess.run(
            ["git", "rev-list", "--count", "main..HEAD"], capture_output=True, text=True, timeout=10
        )
        commits_ahead = int(ahead_result.stdout.strip() or "0")

        if commits_ahead == 0:
            return

        print(f"[STOP] Detected {commits_ahead} commits on {current_branch}", file=sys.stderr)
        print("[STOP] Running post-implementation steps (11-14)...", file=sys.stderr)

        # Find session data
        session_dir = _find_latest_session_dir()
        if not session_dir:
            print("[STOP] No session dir found, skipping Steps 11-14", file=sys.stderr)
            return

        # Step 12: Close GitHub issue (if issue was created in Step 8)
        _step12_close_issue(session_dir)

        # Step 13: Update project docs
        _step13_update_docs()

        # Step 14: Generate summary
        _step14_generate_summary(session_dir, current_branch, commits_ahead)

        print("[STOP] Post-implementation steps complete", file=sys.stderr)

    except Exception as e:
        print(f"[STOP] Post-implementation steps error: {e}", file=sys.stderr)


def _step12_close_issue(session_dir):
    """Step 12: Close the GitHub issue created in Step 8."""
    try:
        import json

        # Read step 8 log to get issue ID
        step8_log = session_dir / "step-logs" / "step-08.json"
        if not step8_log.exists():
            return

        step8_data = json.loads(step8_log.read_text(encoding="utf-8"))
        result_summary = step8_data.get("result_summary", {})
        issue_id = result_summary.get("step8_issue_id", "")

        if not issue_id or issue_id == "0":
            return

        # Close issue via MCP
        _src_mcp = Path(__file__).resolve().parent.parent / "src" / "mcp"
        if str(_src_mcp) not in sys.path:
            sys.path.insert(0, str(_src_mcp))

        from github_mcp_server import github_close_issue

        github_close_issue(issue_number=int(issue_id))
        print(f"[STOP] Step 12: Issue #{issue_id} closed", file=sys.stderr)

    except Exception as e:
        print(f"[STOP] Step 12 skipped: {e}", file=sys.stderr)


def _step13_update_docs():
    """Step 13: Run version sync to update docs."""
    try:
        import subprocess

        sync_script = Path(__file__).resolve().parent / "sync-version.py"
        if sync_script.exists():
            subprocess.run([sys.executable, str(sync_script)], capture_output=True, timeout=15)
            print("[STOP] Step 13: Version synced", file=sys.stderr)
    except Exception as e:
        print(f"[STOP] Step 13 skipped: {e}", file=sys.stderr)


def _step14_generate_summary(session_dir, branch, commits):
    """Step 14: Write final summary to session dir."""
    try:
        from datetime import datetime

        summary = (
            f"Session completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Branch: {branch}\n"
            f"Commits: {commits}\n"
            f"Steps 11-14 executed by stop hook\n"
        )

        summary_file = session_dir / "final-summary.txt"
        summary_file.write_text(summary, encoding="utf-8")
        print(f"[STOP] Step 14: Summary saved to {summary_file.name}", file=sys.stderr)

    except Exception as e:
        print(f"[STOP] Step 14 skipped: {e}", file=sys.stderr)


# =============================================================================
# MAIN
# =============================================================================
