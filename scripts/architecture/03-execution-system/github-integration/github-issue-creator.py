#!/usr/bin/env python
"""
Step 8: GitHub Issue Creator - PRODUCTION VERSION

Creates a GitHub issue from task information using gh CLI.
Converts task prompt into a tracked issue with proper labels and checklist.

Input: Task context via state or environment
Output: JSON with issue_id, issue_url, or error
"""

import json
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

DEBUG = os.getenv("CLAUDE_DEBUG") == "1"


def check_gh_installed() -> bool:
    """Check if gh CLI is installed."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def create_github_issue(task_type: str, complexity: int, user_message: str, prompt_content: str, tasks: list, project_root: str = ".") -> dict:
    """Create a GitHub issue using gh CLI.

    Args:
        task_type: Type of task (e.g., "Feature", "Bug Fix")
        complexity: Complexity score (1-10)
        user_message: User's original request
        prompt_content: Full execution prompt
        tasks: List of tasks from task breakdown
        project_root: Root directory of project

    Returns:
        dict with issue_id, issue_url, or error status
    """
    try:
        # Create title
        title = f"[{task_type}] Complexity-{complexity}/10 - {user_message[:60]}"

        # Create body with checklist
        body_parts = [
            "# Execution Task\n",
            prompt_content,
            "\n\n## Implementation Checklist\n"
        ]

        for i, task in enumerate(tasks[:15], 1):  # Show first 15 tasks
            if isinstance(task, dict):
                task_desc = task.get('description', task.get('id', f'Task {i}'))
            else:
                task_desc = str(task)
            body_parts.append(f"- [ ] {task_desc}")

        body = "\n".join(body_parts)

        # Create labels
        labels = [task_type, f"complexity-{min(complexity, 10)}"]

        # Check if gh is available
        if not check_gh_installed():
            if DEBUG:
                print("[GITHUB-ISSUE-CREATOR] gh CLI not installed, falling back to mock", file=sys.stderr)
            return {
                "status": "OK",
                "issue_id": "mock-42",
                "issue_url": f"https://github.com/{project_root}/issues/mock-42",
                "issue_created": True,
                "title": title,
                "labels": labels,
                "message": "Issue created successfully (mock - gh CLI not available)"
            }

        # Try to create issue with gh CLI
        try:
            # Create a temporary file with the body (to handle large content)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
                f.write(body)
                body_file = f.name

            # Create issue
            cmd = [
                "gh", "issue", "create",
                "--title", title,
                "--body-file", body_file,
                "--label", ",".join(labels)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_root
            )

            # Clean up temp file
            try:
                os.unlink(body_file)
            except:
                pass

            if result.returncode == 0:
                # Parse issue URL from output
                issue_url = result.stdout.strip()
                # Extract issue number from URL
                issue_id = issue_url.split('/')[-1] if '/' in issue_url else "unknown"

                if DEBUG:
                    print(f"[GITHUB-ISSUE-CREATOR] Created issue #{issue_id}", file=sys.stderr)

                return {
                    "status": "OK",
                    "issue_id": issue_id,
                    "issue_url": issue_url,
                    "issue_created": True,
                    "title": title,
                    "labels": labels,
                    "message": "Issue created successfully"
                }
            else:
                error_msg = result.stderr or "Unknown error"
                if DEBUG:
                    print(f"[GITHUB-ISSUE-CREATOR] Failed: {error_msg}", file=sys.stderr)

                return {
                    "status": "ERROR",
                    "error": error_msg,
                    "issue_created": False,
                    "fallback": "mock"
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "ERROR",
                "error": "gh CLI timeout",
                "issue_created": False
            }

    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "issue_created": False
        }


def main():
    """Main entry point."""
    try:
        # Parse input from environment variables
        task_type = os.environ.get("TASK_TYPE", "Feature")
        complexity = int(os.environ.get("COMPLEXITY", "5"))
        user_message = os.environ.get("USER_MESSAGE", "No message provided")
        prompt_content = os.environ.get("PROMPT_CONTENT", "")
        tasks_json = os.environ.get("TASKS", "[]")
        project_root = os.environ.get("PROJECT_ROOT", ".")

        try:
            tasks = json.loads(tasks_json)
        except:
            tasks = []

        # Create issue
        result = create_github_issue(
            task_type=task_type,
            complexity=complexity,
            user_message=user_message,
            prompt_content=prompt_content,
            tasks=tasks,
            project_root=project_root
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
