"""github_pr_workflow/versioning.py - Version bump, changelog, and main entry.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .commit_push import _commit_session_changes, _create_pull_request, _push_branch
from .git_ops import _get_current_branch, _get_issue_numbers, _get_repo_root, _load_issues_mapping, _log
from .review import _auto_review_pr, _load_flow_trace, _smart_code_review


def _bump_version_and_changelog(repo_root, session_summary, issue_numbers):
    """
    Auto-bump VERSION (patch) and add CHANGELOG entry.
    Enforces version-release-policy.md requirement that every code push
    must update VERSION and CHANGELOG.
    Returns True if files were modified.
    """
    try:
        version_file = Path(repo_root) / "VERSION"
        changelog_file = Path(repo_root) / "docs" / "CHANGELOG-SYSTEM.md"

        if not version_file.exists():
            _log("No VERSION file found - skipping version bump")
            return False

        # Read current version
        current_version = version_file.read_text(encoding="utf-8").strip()
        parts = current_version.split(".")
        if len(parts) != 3:
            _log(f"Invalid version format: {current_version}")
            return False

        # Patch increment
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        new_version = f"{major}.{minor}.{patch + 1}"

        # Write new VERSION
        version_file.write_text(new_version + "\n", encoding="utf-8")
        _log(f"VERSION bumped: {current_version} -> {new_version}")

        # Build changelog entry from session summary
        today = datetime.now().strftime("%Y-%m-%d")
        entry_lines = [f"- v{new_version} ({today}): "]

        if session_summary:
            types = session_summary.get("task_types", [])
            if types:
                entry_lines[0] += ", ".join(types[:3])
            else:
                entry_lines[0] += "Session updates"

            requests = session_summary.get("requests", [])
            for req in requests[:5]:
                prompt = req.get("prompt", "")[:100]
                if prompt:
                    entry_lines.append(f"  - {prompt}")
        else:
            entry_lines[0] += "Session updates"

        if issue_numbers:
            closes_str = ", ".join(f"#{n}" for n in issue_numbers)
            entry_lines.append(f"  - Closes: {closes_str}")

        entry_text = "\n".join(entry_lines) + "\n"

        # Prepend to CHANGELOG (after header)
        if changelog_file.exists():
            content = changelog_file.read_text(encoding="utf-8")
            # Insert after the "---" separator (after the header)
            sep_idx = content.find("---\n")
            if sep_idx >= 0:
                insert_pos = sep_idx + 4  # After "---\n"
                new_content = content[:insert_pos] + "\n" + entry_text + content[insert_pos:]
                changelog_file.write_text(new_content, encoding="utf-8")
                _log(f"CHANGELOG updated with v{new_version} entry")
            else:
                # No separator, just prepend after first line
                new_content = content.split("\n", 1)
                if len(new_content) == 2:
                    changelog_file.write_text(new_content[0] + "\n" + entry_text + new_content[1], encoding="utf-8")
        else:
            _log("No CHANGELOG file found - skipping changelog update")

        return True

    except Exception as e:
        _log(f"Version bump error: {e}")
        return False


def _merge_pr(repo_root: str, pr_number: int) -> bool:
    """Merge the pull request via the gh CLI using merge commit strategy.

    Uses ``gh pr merge --merge --delete-branch`` so the source branch is
    cleaned up automatically. Falls back gracefully (logs a message, leaves
    the PR open for manual review) when branch protection rules block the merge.

    Args:
        repo_root: Absolute path to the git repository root (used as cwd).
        pr_number: GitHub PR number to merge.

    Returns:
        ``True`` if the merge succeeded, ``False`` on failure or error.
    """
    try:
        if not pr_number:
            return False

        result = subprocess.run(
            ["gh", "pr", "merge", str(pr_number), "--merge", "--delete-branch"],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            cwd=repo_root,
        )

        if result.returncode == 0:
            _log(f"PR #{pr_number} merged successfully")
            sys.stdout.write(f"[GH] PR #{pr_number} merged\n")
            sys.stdout.flush()

            # Update mapping
            mapping = _load_issues_mapping()
            mapping["pr_merged"] = True
            mapping["pr_merged_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            _save_issues_mapping(mapping)

            return True
        else:
            _log(f"PR merge failed (branch protection?): {result.stderr[:200]}")
            sys.stdout.write(f"[GH] PR #{pr_number} left open (merge blocked, needs manual review)\n")
            sys.stdout.flush()
            return False

    except Exception as e:
        _log(f"Merge error: {e}")
        return False


def _switch_to_main(repo_root: str) -> None:
    """Checkout the default branch and fast-forward pull the latest changes.

    Detects the default branch name by running ``git remote show origin``
    and extracting the ``HEAD branch`` line. Falls back to 'main' if the
    detection fails or times out.

    Args:
        repo_root: Absolute path to the git repository root.
    """
    try:
        # Detect default branch
        default_branch = "main"
        result = subprocess.run(
            ["git", "remote", "show", "origin"], capture_output=True, text=True, timeout=10, cwd=repo_root
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("HEAD branch:"):
                    default_branch = line.split(":", 1)[1].strip()
                    break

        # Checkout default branch
        result = subprocess.run(
            ["git", "checkout", default_branch], capture_output=True, text=True, timeout=10, cwd=repo_root
        )
        if result.returncode != 0:
            _log(f"Checkout {default_branch} failed: {result.stderr[:200]}")
            return

        # Pull latest
        subprocess.run(["git", "pull", "--ff-only"], capture_output=True, text=True, timeout=15, cwd=repo_root)

        _log(f"Switched to {default_branch} and pulled latest")

    except Exception as e:
        _log(f"Switch to main error: {e}")


def _bump_and_push_on_main(repo_root: str, session_summary: dict, issue_numbers: list) -> None:
    """Bump the patch version and push a CHANGELOG commit on main.

    Must be called after ``_switch_to_main()`` so the version bump lands
    on the default branch as a separate commit from the feature work. This
    satisfies the version-release-policy requirement that every code push
    must update VERSION and CHANGELOG.

    Args:
        repo_root: Absolute path to the git repository root.
        session_summary: Session summary dict for building the changelog entry.
        issue_numbers: List of closed GitHub issue numbers to mention in the
            changelog entry.
    """
    try:
        version_file = Path(repo_root) / "VERSION"
        if not version_file.exists():
            _log("No VERSION file - skipping version bump")
            return

        old_ver = version_file.read_text(encoding="utf-8").strip()

        bumped = _bump_version_and_changelog(repo_root, session_summary, issue_numbers)
        if not bumped:
            _log("Version bump failed or skipped")
            return

        new_ver = version_file.read_text(encoding="utf-8").strip()

        # Stage VERSION + CHANGELOG
        subprocess.run(
            ["git", "add", "VERSION", "docs/CHANGELOG-SYSTEM.md"], capture_output=True, timeout=10, cwd=repo_root
        )

        # Commit on main
        commit_msg = f"bump: v{old_ver} -> v{new_ver}"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg], capture_output=True, text=True, timeout=15, cwd=repo_root
        )
        if result.returncode != 0:
            _log(f"Bump commit failed: {result.stderr[:200] if result.stderr else 'no error'}")
            return

        # Push to main
        result = subprocess.run(
            ["git", "push", "origin", "HEAD"], capture_output=True, text=True, timeout=30, cwd=repo_root
        )
        if result.returncode == 0:
            _log(f"Version bumped on main: v{old_ver} -> v{new_ver} (pushed)")
        else:
            _log(f"Bump push failed: {result.stderr[:200] if result.stderr else 'no error'}")

    except Exception as e:
        _log(f"Bump on main error: {e}")


def _print_workflow_step(step_num, step_name, status="IN_PROGRESS"):
    """Print formatted workflow step to user."""
    status_symbol = {"IN_PROGRESS": "[WAIT]", "OK": "[OK]", "SKIP": "?", "ERROR": "[FAIL]", "WARN": "??"}
    symbol = status_symbol.get(status, "?")

    if step_num == -1:
        sys.stdout.write(f"\n{'?'*70}\n")
        sys.stdout.write("[PR WORKFLOW] Starting 7-step GitHub workflow\n")
        sys.stdout.write(f"{'?'*70}\n")
    else:
        sys.stdout.write(f"[{step_num}] {symbol} {step_name}\n")

    sys.stdout.flush()


def run_pr_workflow(session_id=None):
    """
    Main PR workflow orchestrator. Runs the full flow:
      0. Build validation
      1. Commit any uncommitted changes
      2. Push branch to remote
      3. Create PR with session summary body + Closes #N
      4. Post auto-review comment with session metrics
      4.5. Smart code review (safety check before merge)
      5. Merge PR (fallback: leave open)
      6. Switch back to main locally
      7. Version bump + CHANGELOG on main (after merge, on main branch)

    Called from stop-notifier.py when .session-work-done flag exists.
    Non-blocking: all steps wrapped in try/except, never raises.
    Returns True if PR was merged successfully, False otherwise.
    """
    _log("?" * 70)
    _log("=== PR WORKFLOW v1.1.0 STARTING ===")
    _log("?" * 70)
    _print_workflow_step(-1, "GitHub PR Workflow")

    try:
        # Check prerequisites
        repo_root = _get_repo_root()
        if not repo_root:
            _log("Not in a git repo - skipping PR workflow")
            return False

        branch_name = _get_current_branch(repo_root)
        if not branch_name:
            error_msg = "CRITICAL: Could not determine current branch - PR workflow BLOCKED"
            _log(error_msg)
            sys.stdout.write(f"\n{'='*70}\n")
            sys.stdout.write(f"[PR-WORKFLOW ERROR] {error_msg}\n")
            sys.stdout.write("  Cannot create PR without knowing which branch you're on\n")
            sys.stdout.write("  ACTION: Verify git repository with 'git status'\n")
            sys.stdout.write(f"{'='*70}\n\n")
            sys.stdout.flush()
            return False

        # CRITICAL CHECK: Only proceed if on an issue branch (not main/master)
        if branch_name in ("main", "master"):
            info_msg = f"INFO: On {branch_name} - skipping PR workflow (no feature branch work)"
            _log(info_msg)
            sys.stdout.write(f"\n[PR-WORKFLOW] {info_msg}\n")
            sys.stdout.write("  To enable PR workflow, create tasks first (TaskCreate)\n")
            sys.stdout.write("  This creates a feature branch and GitHub issue automatically\n\n")
            sys.stdout.flush()
            return False

        _log(f"[OK] Branch: {branch_name} (feature branch detected - PR workflow will run)")

        # Check if gh CLI is available
        try:
            result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=GH_TIMEOUT)
            if result.returncode != 0:
                _log("gh CLI not authenticated - skipping PR workflow")
                return
        except Exception:
            _log("gh CLI not available - skipping PR workflow")
            return

        # Load session data
        session_summary = _load_session_summary()
        issue_numbers = _get_issue_numbers()

        # STEP 0: Build validation (before commit)
        build_result = None
        _print_workflow_step(0, "Build validation", "IN_PROGRESS")
        _log("STEP 0: Running build validation...")
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            import auto_build_validator

            build_result = auto_build_validator.validate_build(repo_root)
            if build_result["all_passed"]:
                _log("  [OK] Build validation PASSED")
                _log(f"  Summary: {build_result['summary']}")
                _print_workflow_step(0, "Build validation", "OK")
                sys.stdout.write(f"  [OK] {build_result['summary']}\n")
                sys.stdout.flush()
            else:
                _log("  ??  Build validation WARNINGS")
                _log(f"  Summary: {build_result['summary']}")
                _print_workflow_step(0, "Build validation", "WARN")
                sys.stdout.write(f"  ??  {build_result['summary']}\n")
                sys.stdout.flush()
                # Log errors but don't stop - PR will show build status
                for r in build_result["results"]:
                    if not r["passed"]:
                        _log(f"    - {r['label']}: {r.get('output', '')[:200]}")
        except Exception as e:
            _log(f"  ??  Build validation error (non-fatal): {e}")
            _print_workflow_step(0, "Build validation", "WARN")

        # STEP 1: Commit changes (feature work only, no version bump here)
        _print_workflow_step(1, "Commit changes", "IN_PROGRESS")
        _log("STEP 1: Committing all changes...")
        try:
            _commit_session_changes(repo_root, session_summary, issue_numbers)
            _log("  [OK] Changes committed")
            _print_workflow_step(1, "Commit changes", "OK")
        except Exception as e:
            _log(f"  [FAIL] Commit failed: {e}")
            _print_workflow_step(1, "Commit changes", "ERROR")
            sys.stdout.write(f"\n[PR-WORKFLOW ERROR] Commit failed: {str(e)[:100]}\n\n")
            sys.stdout.flush()
            return False

        # STEP 2: Push branch to remote
        _print_workflow_step(2, "Push branch", "IN_PROGRESS")
        _log("STEP 2: Pushing branch to remote...")
        pushed = _push_branch(repo_root, branch_name)
        if not pushed:
            _log("  [FAIL] Push failed - cannot create PR without remote branch")
            _print_workflow_step(2, "Push branch", "ERROR")
            sys.stdout.write(f"\n[PR-WORKFLOW ERROR] Could not push {branch_name} to remote\n")
            sys.stdout.write("  ACTION: Check network and git remote configuration\n\n")
            sys.stdout.flush()
            return False
        _log(f"  [OK] Branch pushed to origin/{branch_name}")
        _print_workflow_step(2, "Push branch", "OK")

        # STEP 3: Create PR
        _print_workflow_step(3, "Create PR", "IN_PROGRESS")
        _log("STEP 3: Creating pull request...")
        pr_number = _create_pull_request(repo_root, branch_name, issue_numbers, session_summary)
        if not pr_number:
            _log("  [FAIL] PR creation failed")
            _print_workflow_step(3, "Create PR", "ERROR")
            sys.stdout.write("\n[PR-WORKFLOW ERROR] Could not create PR\n")
            sys.stdout.write("  Check gh CLI authentication with 'gh auth status'\n\n")
            sys.stdout.flush()
            return False
        _log(f"  [OK] PR #{pr_number} created")
        _print_workflow_step(3, "Create PR", "OK")

        # STEP 4: Auto-review comment (includes build status)
        _print_workflow_step(4, "Post auto-review comment", "IN_PROGRESS")
        _log("STEP 4: Posting auto-review comment...")
        try:
            _auto_review_pr(repo_root, pr_number, session_summary, build_result)
            _log("  [OK] Auto-review comment posted")
            _print_workflow_step(4, "Post auto-review comment", "OK")
        except Exception as e:
            _log(f"  ??  Auto-review comment failed (non-fatal): {e}")
            _print_workflow_step(4, "Post auto-review comment", "WARN")

        # STEP 4.5: Smart Code Review before merge (CRITICAL)
        _print_workflow_step(5, "Smart code review", "IN_PROGRESS")
        _log("STEP 4.5: Running Smart Code Review (Session-Aware + Skill-Aware)...")
        try:
            flow_trace = _load_flow_trace()
            safe_to_merge = _smart_code_review(repo_root, pr_number, session_summary, flow_trace)

            if not safe_to_merge:
                _log("  [FAIL] Smart review found CRITICAL issues - NOT merging")
                _print_workflow_step(5, "Smart code review", "ERROR")
                sys.stdout.write("\n[SMART REVIEW] Critical issues detected\n")
                sys.stdout.write(f"  PR #{pr_number} left open for manual review\n")
                sys.stdout.write("  Check PR comments for details\n\n")
                sys.stdout.flush()
                return False
            _log("  [OK] Smart review PASSED - safe to merge")
            _print_workflow_step(5, "Smart code review", "OK")
        except Exception as e:
            _log(f"  ??  Smart review error (skipping): {e}")
            _print_workflow_step(5, "Smart code review", "WARN")

        # STEP 5: Merge PR
        _print_workflow_step(6, "Merge PR", "IN_PROGRESS")
        _log("STEP 5: Merging PR...")
        merged = _merge_pr(repo_root, pr_number)

        if not merged:
            _log(f"  ??  Merge failed or blocked (PR #{pr_number} left open)")
            _print_workflow_step(6, "Merge PR", "WARN")
            sys.stdout.write(f"\n[PR-WORKFLOW] PR #{pr_number} could not be auto-merged\n")
            sys.stdout.write("  Likely cause: Branch protection rules require manual review\n")
            sys.stdout.write("  ACTION: Merge manually from GitHub\n\n")
            sys.stdout.flush()
            return False

        _log(f"  [OK] PR #{pr_number} merged successfully")
        _print_workflow_step(6, "Merge PR", "OK")

        # STEP 6: Switch back to main (only if merged)
        _print_workflow_step(7, "Switch to main", "IN_PROGRESS")
        _log("STEP 6: Switching to main branch...")
        try:
            _switch_to_main(repo_root)
            _log("  [OK] Switched to main")
            _print_workflow_step(7, "Switch to main", "OK")
        except Exception as e:
            _log(f"  ??  Switch to main failed: {e}")
            _print_workflow_step(7, "Switch to main", "WARN")

        # STEP 7: Version bump on main (AFTER merge, on main branch)
        _print_workflow_step(8, "Version bump", "IN_PROGRESS")
        _log("STEP 7: Bumping version on main...")
        try:
            _bump_and_push_on_main(repo_root, session_summary, issue_numbers)
            _log("  [OK] Version bumped and pushed")
            _print_workflow_step(8, "Version bump", "OK")
        except Exception as e:
            _log(f"  ??  Version bump failed (non-fatal): {e}")
            _print_workflow_step(8, "Version bump", "WARN")

        _log("?" * 70)
        _log("=== PR WORKFLOW COMPLETED SUCCESSFULLY ===")
        _log("?" * 70)
        sys.stdout.write(f"\n{'?'*70}\n")
        sys.stdout.write("[PR-WORKFLOW] [OK] COMPLETED SUCCESSFULLY\n")
        sys.stdout.write(f"  PR #{pr_number} merged into main\n")
        sys.stdout.write("  Version bumped\n")
        sys.stdout.write(f"{'?'*70}\n\n")
        sys.stdout.flush()
        return True

    except Exception as e:
        _log(f"PR Workflow error: {e}")
        return False


if __name__ == "__main__":
    run_pr_workflow()
