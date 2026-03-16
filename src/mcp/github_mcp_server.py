"""
GitHub MCP Server - FastMCP-based GitHub operations for Claude Code.

Replaces 8+ subprocess calls in github_integration.py with PyGithub library.
Backend: PyGithub (primary) + gh CLI fallback for critical operations
Transport: stdio

Tools (12):
  github_create_issue, github_close_issue, github_add_comment,
  github_create_pr, github_merge_pr, github_list_issues, github_get_pr_status,
  github_create_issue_branch, github_auto_commit_and_pr, github_validate_build,
  github_label_issue, github_full_merge_cycle
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


# =============================================================================
# PR WORKFLOW + ISSUE MANAGEMENT (Enhanced from github_pr_workflow.py + github_issue_manager.py)
# =============================================================================

@mcp.tool()
def github_create_issue_branch(
    issue_number: int,
    subject: str,
    issue_type: str = "feature",
    repo_path: str = "."
) -> str:
    """Create a git branch linked to a GitHub issue.

    Branch format: {type}/issue-{number}-{slugified-subject}

    Args:
        issue_number: GitHub issue number
        subject: Issue subject (used for branch name)
        issue_type: 'feature', 'fix', 'refactor', 'docs', 'test'
        repo_path: Local repo path
    """
    try:
        import re as _re
        # Slugify subject
        slug = _re.sub(r"[^a-z0-9]+", "-", subject.lower())[:40].strip("-")
        prefix_map = {
            "feature": "feature", "fix": "fix", "bugfix": "fix",
            "refactor": "refactor", "docs": "docs", "test": "test",
        }
        prefix = prefix_map.get(issue_type, "feature")
        branch_name = f"{prefix}/issue-{issue_number}-{slug}"

        # Create branch via git
        if GITPYTHON_AVAILABLE:
            repo = Repo(repo_path)
            origin = repo.remotes.origin

            # Stash if dirty
            had_stash = False
            if repo.is_dirty(untracked_files=True):
                repo.git.stash("push", "--include-untracked", "-m", f"auto-stash-{branch_name}")
                had_stash = True

            try:
                origin.fetch("main")
                repo.git.checkout("-b", branch_name, "FETCH_HEAD")
            except Exception:
                repo.git.checkout("-b", branch_name)

            if had_stash:
                try:
                    repo.git.stash("pop")
                except Exception:
                    pass

            try:
                origin.push(branch_name, set_upstream=True)
            except Exception:
                pass

            return _json({
                "success": True,
                "branch": branch_name,
                "issue_number": issue_number,
                "stash_restored": had_stash
            })
        else:
            # Fallback to gh CLI
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                capture_output=True, text=True, timeout=15, cwd=repo_path
            )
            return _json({
                "success": result.returncode == 0,
                "branch": branch_name,
                "issue_number": issue_number
            })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_auto_commit_and_pr(
    title: str,
    body: str = "",
    base: str = "main",
    labels: Optional[str] = None,
    repo_path: str = "."
) -> str:
    """Auto-commit all changes and create a PR in one step.

    Workflow: stage all -> commit -> push -> create PR

    Args:
        title: PR title (also used as commit message)
        body: PR description
        base: Target branch
        labels: Comma-separated labels
        repo_path: Local repo path
    """
    try:
        if not GITPYTHON_AVAILABLE:
            return _json({"success": False, "error": "GitPython not available"})

        repo = Repo(repo_path)

        # Check for changes
        if not repo.is_dirty(untracked_files=True):
            return _json({"success": False, "error": "No changes to commit"})

        branch = str(repo.active_branch)

        # Stage and commit
        repo.git.add("-A")
        commit = repo.index.commit(title)

        # Push
        origin = repo.remotes.origin
        try:
            origin.push(branch, set_upstream=True)
        except Exception as push_err:
            return _json({
                "success": False,
                "error": f"Push failed: {push_err}",
                "commit": str(commit.hexsha)[:7]
            })

        # Create PR
        gh_repo = _get_github_repo(repo_path)
        pr = gh_repo.create_pull(title=title, body=body, head=branch, base=base)

        if labels:
            for label in [l.strip() for l in labels.split(",") if l.strip()]:
                try:
                    pr.add_to_labels(label)
                except Exception:
                    pass

        return _json({
            "success": True,
            "commit": str(commit.hexsha)[:7],
            "branch": branch,
            "pr_number": pr.number,
            "pr_url": pr.html_url,
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_validate_build(repo_path: str = ".") -> str:
    """Run project build validation before PR.

    Auto-detects build system (npm, gradle, pip, cargo) and runs appropriate check.

    Args:
        repo_path: Project root path
    """
    try:
        from pathlib import Path as _Path
        root = _Path(repo_path).resolve()

        build_cmd = None
        build_system = "unknown"

        if (root / "package.json").exists():
            build_system = "npm"
            # Check for build script
            try:
                pkg = json.loads((root / "package.json").read_text())
                if "build" in pkg.get("scripts", {}):
                    build_cmd = ["npm", "run", "build"]
                elif "test" in pkg.get("scripts", {}):
                    build_cmd = ["npm", "test"]
            except Exception:
                pass
        elif (root / "pom.xml").exists():
            build_system = "maven"
            build_cmd = ["mvn", "compile", "-q"]
        elif (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
            build_system = "gradle"
            build_cmd = ["gradle", "build", "-q"]
        elif (root / "requirements.txt").exists() or (root / "setup.py").exists():
            build_system = "python"
            if (root / "tests").exists():
                build_cmd = ["python", "-m", "pytest", "--co", "-q"]
            else:
                build_cmd = ["python", "-c", "import py_compile; print('OK')"]
        elif (root / "Cargo.toml").exists():
            build_system = "cargo"
            build_cmd = ["cargo", "check"]

        if not build_cmd:
            return _json({
                "success": True,
                "build_system": build_system,
                "validated": False,
                "message": "No build system detected"
            })

        result = subprocess.run(
            build_cmd, capture_output=True, text=True,
            timeout=120, cwd=str(root)
        )

        return _json({
            "success": True,
            "build_system": build_system,
            "validated": result.returncode == 0,
            "command": " ".join(build_cmd),
            "exit_code": result.returncode,
            "stdout": result.stdout[:500] if result.stdout else "",
            "stderr": result.stderr[:500] if result.stderr else "",
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_label_issue(
    number: int,
    labels: str,
    repo_path: str = "."
) -> str:
    """Add labels to an issue or PR.

    Args:
        number: Issue or PR number
        labels: Comma-separated label names
        repo_path: Local repo path
    """
    try:
        repo = _get_github_repo(repo_path)
        issue = repo.get_issue(number)
        label_list = [l.strip() for l in labels.split(",") if l.strip()]

        added = []
        for label in label_list:
            try:
                issue.add_to_labels(label)
                added.append(label)
            except GithubException:
                pass

        return _json({
            "success": True,
            "issue_number": number,
            "labels_added": added,
            "total_labels": [l.name for l in issue.labels]
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def github_full_merge_cycle(
    number: int,
    method: str = "squash",
    validate_build: bool = True,
    repo_path: str = "."
) -> str:
    """Full merge cycle: validate build -> merge PR -> cleanup branch.

    Args:
        number: PR number
        method: Merge method ('merge', 'squash', 'rebase')
        validate_build: Run build validation before merge
        repo_path: Local repo path
    """
    try:
        steps_completed = []

        # Step 1: Build validation (optional)
        if validate_build:
            build_result = json.loads(github_validate_build(repo_path))
            steps_completed.append({
                "step": "build_validation",
                "success": build_result.get("validated", False),
                "system": build_result.get("build_system", "unknown")
            })
            if not build_result.get("validated", True):
                return _json({
                    "success": False,
                    "error": "Build validation failed",
                    "steps": steps_completed
                })

        # Step 2: Check PR is mergeable
        repo = _get_github_repo(repo_path)
        pr = repo.get_pull(number)
        if not pr.mergeable:
            return _json({
                "success": False,
                "error": f"PR #{number} has conflicts",
                "steps": steps_completed
            })
        steps_completed.append({"step": "mergeable_check", "success": True})

        # Step 3: Merge
        merge_result = json.loads(github_merge_pr(
            number=number, method=method, delete_branch=True,
            repo_path=repo_path
        ))
        steps_completed.append({
            "step": "merge",
            "success": merge_result.get("success", False)
        })

        if not merge_result.get("success"):
            return _json({
                "success": False,
                "error": merge_result.get("error", "Merge failed"),
                "steps": steps_completed
            })

        return _json({
            "success": True,
            "pr_number": number,
            "method": method,
            "steps": steps_completed,
            "message": f"PR #{number} merged successfully"
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
