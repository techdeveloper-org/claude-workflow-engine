"""
GitHub MCP Server - FastMCP-based GitHub operations for Claude Code.

Replaces 8+ subprocess calls in github_integration.py with PyGithub library.
Backend: PyGithub (primary) + gh CLI fallback for critical operations
Transport: stdio

Tools (7):
  github_create_issue, github_close_issue, github_add_comment,
  github_create_pr, github_merge_pr, github_list_issues, github_get_pr_status
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

try:
    from github import Github, GithubException
    PYGITHUB_AVAILABLE = True
except ImportError:
    PYGITHUB_AVAILABLE = False
    GithubException = Exception  # Fallback so except clauses don't fail

try:
    from git import Repo
    GITPYTHON_AVAILABLE = True
except ImportError:
    GITPYTHON_AVAILABLE = False

mcp = FastMCP("github-api", instructions="GitHub operations via PyGithub (no subprocess)")

# Cached state (initialized once at startup)
_github_client = None
_github_token = None


def _json(data: dict) -> str:
    """Return compact JSON string."""
    return json.dumps(data, indent=2, default=str)


def _get_token() -> Optional[str]:
    """Get GitHub token: env var -> gh CLI keyring (one-time)."""
    global _github_token
    if _github_token:
        return _github_token

    # Try env var first
    token = os.getenv("GITHUB_TOKEN")
    if token:
        _github_token = token
        return token

    # Try gh CLI keyring (one-time subprocess)
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            _github_token = result.stdout.strip()
            return _github_token
    except Exception:
        pass

    return None


def _get_client():
    """Get or create cached GitHub client."""
    global _github_client
    if _github_client:
        return _github_client

    if not PYGITHUB_AVAILABLE:
        raise RuntimeError("PyGithub not installed. Install with: pip install PyGithub")

    token = _get_token()
    if not token:
        raise RuntimeError(
            "No GitHub token. Set GITHUB_TOKEN env var or login with: gh auth login"
        )

    _github_client = Github(token)
    return _github_client


def _get_repo_info(repo_path: str = ".") -> tuple:
    """Get owner/repo from git remote (no subprocess - uses GitPython)."""
    if not GITPYTHON_AVAILABLE:
        return None, None

    try:
        repo = Repo(repo_path)
        remote_url = repo.remotes.origin.url

        if "github.com" not in remote_url:
            return None, None

        if remote_url.startswith("git@"):
            parts = remote_url.split(":")[-1].replace(".git", "").split("/")
        else:
            parts = remote_url.rstrip("/").replace(".git", "").split("/")[-2:]

        return parts[0], parts[1]
    except Exception:
        return None, None


def _get_github_repo(repo_path: str = "."):
    """Get PyGithub repo object."""
    client = _get_client()
    owner, repo_name = _get_repo_info(repo_path)
    if not owner or not repo_name:
        raise RuntimeError(f"Cannot detect GitHub repo from: {repo_path}")
    return client.get_repo(f"{owner}/{repo_name}")


@mcp.tool()
def github_create_issue(
    title: str,
    body: str = "",
    labels: Optional[str] = None,
    assignee: Optional[str] = None,
    repo_path: str = "."
) -> str:
    """Create a GitHub issue.

    Args:
        title: Issue title
        body: Issue description (markdown supported)
        labels: Comma-separated label names (e.g., 'bug,priority-high')
        assignee: GitHub username to assign the issue to
        repo_path: Local repo path for auto-detecting owner/repo
    """
    try:
        repo = _get_github_repo(repo_path)
        label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else []

        kwargs = {"title": title, "body": body, "labels": label_list}
        if assignee:
            kwargs["assignee"] = assignee

        issue = repo.create_issue(**kwargs)

        return _json({
            "success": True,
            "issue_number": issue.number,
            "issue_url": issue.html_url,
            "assignee": assignee,
            "created_at": issue.created_at.isoformat()
        })
    except GithubException as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_close_issue(
    number: int,
    comment: Optional[str] = None,
    repo_path: str = "."
) -> str:
    """Close a GitHub issue with optional closing comment.

    Args:
        number: Issue number
        comment: Optional comment to add before closing
        repo_path: Local repo path
    """
    try:
        repo = _get_github_repo(repo_path)
        issue = repo.get_issue(number)

        if comment:
            issue.create_comment(comment)

        issue.edit(state="closed")

        return _json({
            "success": True,
            "issue_number": number,
            "state": "closed"
        })
    except GithubException as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_add_comment(
    number: int,
    body: str,
    type: str = "issue",
    repo_path: str = "."
) -> str:
    """Add a comment to an issue or pull request.

    Args:
        number: Issue or PR number
        body: Comment text (markdown supported)
        type: 'issue' or 'pr'
        repo_path: Local repo path
    """
    try:
        repo = _get_github_repo(repo_path)

        if type == "pr":
            pr = repo.get_pull(number)
            comment = pr.create_issue_comment(body)
        else:
            issue = repo.get_issue(number)
            comment = issue.create_comment(body)

        return _json({
            "success": True,
            "comment_url": comment.html_url,
            "type": type
        })
    except GithubException as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_create_pr(
    title: str,
    body: str = "",
    head: str = "",
    base: str = "main",
    labels: Optional[str] = None,
    repo_path: str = "."
) -> str:
    """Create a pull request.

    Args:
        title: PR title
        body: PR description (markdown)
        head: Source branch name
        base: Target branch (default: main)
        labels: Comma-separated label names
        repo_path: Local repo path
    """
    try:
        if not head:
            return _json({"success": False, "error": "head branch is required"})

        repo = _get_github_repo(repo_path)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)

        if labels:
            label_list = [l.strip() for l in labels.split(",") if l.strip()]
            for label in label_list:
                try:
                    pr.add_to_labels(label)
                except GithubException:
                    pass

        return _json({
            "success": True,
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "created_at": pr.created_at.isoformat()
        })
    except GithubException as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


def _gh_cli_merge_fallback(number: int, method: str, delete_branch: bool,
                           commit_message: str) -> Optional[dict]:
    """Fallback: merge PR via gh CLI if PyGithub fails."""
    try:
        cmd = ["gh", "pr", "merge", str(number), f"--{method}"]
        if delete_branch:
            cmd.append("--delete-branch")
        if commit_message:
            cmd.extend(["--body", commit_message])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {
                "success": True,
                "pr_number": number,
                "merged": True,
                "method": method,
                "branch_deleted": delete_branch,
                "fallback": "gh_cli"
            }
    except Exception:
        pass
    return None


@mcp.tool()
def github_merge_pr(
    number: int,
    method: str = "squash",
    delete_branch: bool = True,
    commit_message: Optional[str] = None,
    repo_path: str = "."
) -> str:
    """Merge a pull request with gh CLI fallback for safety.

    Args:
        number: PR number
        method: Merge method - 'merge', 'squash', or 'rebase'
        delete_branch: Delete source branch after merge
        commit_message: Custom merge commit message (default: 'Merge PR #N')
        repo_path: Local repo path
    """
    merge_msg = commit_message or f"Merge PR #{number}"

    # Primary: PyGithub
    try:
        repo = _get_github_repo(repo_path)
        pr = repo.get_pull(number)

        if not pr.mergeable:
            return _json({
                "success": False,
                "error": f"PR #{number} is not mergeable (conflicts exist)"
            })

        pr.merge(
            commit_message=merge_msg,
            merge_method=method
        )

        if delete_branch:
            try:
                ref = repo.get_git_ref(f"heads/{pr.head.ref}")
                ref.delete()
            except GithubException:
                pass

        return _json({
            "success": True,
            "pr_number": number,
            "merged": True,
            "method": method,
            "branch_deleted": delete_branch
        })
    except (GithubException, Exception) as e:
        # Fallback: gh CLI for critical merge operation
        fallback = _gh_cli_merge_fallback(number, method, delete_branch, merge_msg)
        if fallback:
            return _json(fallback)
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_list_issues(
    labels: Optional[str] = None,
    state: str = "open",
    repo_path: str = "."
) -> str:
    """List issues in the repository.

    Args:
        labels: Comma-separated label filter
        state: 'open', 'closed', or 'all'
        repo_path: Local repo path
    """
    try:
        repo = _get_github_repo(repo_path)

        kwargs = {"state": state}
        if labels:
            label_list = [l.strip() for l in labels.split(",") if l.strip()]
            kwargs["labels"] = [repo.get_label(l) for l in label_list]

        issues = []
        for issue in repo.get_issues(**kwargs)[:25]:
            if not issue.pull_request:  # Exclude PRs
                issues.append({
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "labels": [l.name for l in issue.labels],
                    "created_at": issue.created_at.isoformat()
                })

        return _json({
            "success": True,
            "issues": issues,
            "count": len(issues)
        })
    except GithubException as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_get_pr_status(number: int, repo_path: str = ".") -> str:
    """Get pull request status and check details.

    Args:
        number: PR number
        repo_path: Local repo path
    """
    try:
        repo = _get_github_repo(repo_path)
        pr = repo.get_pull(number)

        checks = []
        try:
            commit = repo.get_commit(pr.head.sha)
            for status in commit.get_statuses():
                checks.append({
                    "context": status.context,
                    "state": status.state,
                    "description": status.description
                })
        except Exception:
            pass

        return _json({
            "success": True,
            "pr_number": number,
            "title": pr.title,
            "state": pr.state,
            "mergeable": pr.mergeable,
            "merged": pr.merged,
            "head": pr.head.ref,
            "base": pr.base.ref,
            "checks": checks,
            "review_comments": pr.review_comments,
            "commits": pr.commits
        })
    except GithubException as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
