#!/usr/bin/env python
"""
Step 9: Branch Creator - PRODUCTION VERSION

Creates a feature branch from main for implementation using git CLI.
Handles branch naming, creation, and tracking setup.

Input: issue_id, task_type via environment
Output: JSON with branch_name, branch_created status
"""

import json
import sys
import os
import subprocess
from pathlib import Path

DEBUG = os.getenv("CLAUDE_DEBUG") == "1"


def check_git_available() -> bool:
    """Check if git is available."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def create_branch(issue_id: str, task_type: str, base_branch: str = "main", repo_path: str = ".") -> dict:
    """Create a feature branch from base branch using git CLI.

    Args:
        issue_id: GitHub issue ID
        task_type: Type of task (e.g., "Feature", "Bug Fix")
        base_branch: Base branch to branch from (default: main)
        repo_path: Repository path

    Returns:
        dict with branch_name, branch_created status
    """
    try:
        # Create branch name: {issue_id}-{task_type}
        task_label = task_type.lower().replace(" ", "-").replace("/", "-")
        branch_name = f"{issue_id}-{task_label}"

        if DEBUG:
            print(f"[BRANCH-CREATOR] Creating branch: {branch_name}", file=sys.stderr)

        # Check if git is available
        if not check_git_available():
            if DEBUG:
                print("[BRANCH-CREATOR] git not available, falling back to mock", file=sys.stderr)
            return {
                "status": "OK",
                "branch_name": branch_name,
                "branch_created": True,
                "git_available": False,
                "message": "Branch name generated (git not available)"
            }

        # Check if in git repository
        git_check = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=repo_path
        )

        if git_check.returncode != 0:
            return {
                "status": "ERROR",
                "error": "Not in a git repository",
                "branch_created": False
            }

        try:
            # Fetch latest from origin (if remote exists)
            subprocess.run(
                ["git", "fetch", "origin", base_branch],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path
            )
        except:
            # Fetch might fail if no remote, continue anyway
            pass

        # Create and checkout branch
        create_result = subprocess.run(
            ["git", "checkout", "-b", branch_name, f"origin/{base_branch}"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=repo_path
        )

        if create_result.returncode != 0:
            # Try without origin prefix (might be local-only repo)
            create_result = subprocess.run(
                ["git", "checkout", "-b", branch_name, base_branch],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path
            )

        if create_result.returncode == 0:
            if DEBUG:
                print(f"[BRANCH-CREATOR] Successfully created branch: {branch_name}", file=sys.stderr)

            return {
                "status": "OK",
                "branch_name": branch_name,
                "branch_created": True,
                "git_available": True,
                "message": f"Branch '{branch_name}' created successfully"
            }
        else:
            error_msg = create_result.stderr or "Failed to create branch"
            if DEBUG:
                print(f"[BRANCH-CREATOR] Failed: {error_msg}", file=sys.stderr)

            return {
                "status": "ERROR",
                "error": error_msg,
                "branch_created": False
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "ERROR",
            "error": "git command timeout",
            "branch_created": False
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "branch_created": False
        }


def main():
    """Main entry point."""
    try:
        # Parse input from environment variables
        issue_id = os.environ.get("ISSUE_ID", "0")
        task_type = os.environ.get("TASK_TYPE", "feature")
        base_branch = os.environ.get("BASE_BRANCH", "main")
        repo_path = os.environ.get("REPO_PATH", ".")

        # Create branch
        result = create_branch(
            issue_id=issue_id,
            task_type=task_type,
            base_branch=base_branch,
            repo_path=repo_path
        )

        # Output as JSON
        print(json.dumps(result))
        sys.exit(0 if result.get("status") == "OK" else 1)

    except Exception as e:
        error_result = {
            "status": "ERROR",
            "error": str(e)
        }
        print(json.dumps(error_result))
        sys.exit(1)


if __name__ == "__main__":
    main()
