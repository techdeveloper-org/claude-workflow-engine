"""
Git MCP Server - FastMCP-based Git operations for Claude Code.

Replaces 13+ subprocess calls in git_operations.py with GitPython library.
Backend: GitPython (already in requirements.txt)
Transport: stdio (Claude Code communicates via stdin/stdout)

Tools (14):
  git_status, git_branch_create, git_branch_switch, git_branch_list,
  git_branch_delete, git_commit, git_push, git_pull, git_diff,
  git_stash, git_log, git_fetch, git_post_merge_cleanup, git_get_origin_url
"""

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

try:
    from git import Repo, InvalidGitRepositoryError, GitCommandError
    GITPYTHON_AVAILABLE = True
except ImportError:
    GITPYTHON_AVAILABLE = False

mcp = FastMCP("git-ops", instructions="Git operations via GitPython (no subprocess)")


def _get_repo(repo_path: str = ".") -> Repo:
    """Get a Repo object, raising clear errors."""
    if not GITPYTHON_AVAILABLE:
        raise RuntimeError("GitPython not installed. Install with: pip install GitPython")
    return Repo(repo_path)


def _json(data: dict) -> str:
    """Return compact JSON string."""
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
def git_status(repo_path: str = ".") -> str:
    """Get repository status (modified, staged, untracked files)."""
    try:
        repo = _get_repo(repo_path)
        changed = [item.a_path for item in repo.index.diff(None)]
        staged = [item.a_path for item in repo.index.diff("HEAD")]
        untracked = repo.untracked_files

        return _json({
            "success": True,
            "branch": str(repo.active_branch),
            "is_dirty": repo.is_dirty(untracked_files=True),
            "modified": changed,
            "staged": staged,
            "untracked": untracked,
            "total_changes": len(changed) + len(staged) + len(untracked)
        })
    except InvalidGitRepositoryError:
        return _json({"success": False, "error": f"Not a git repository: {repo_path}"})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_branch_create(name: str, from_branch: str = "main", repo_path: str = ".") -> str:
    """Create a new branch from specified base with stash safety.

    Workflow: stash -> fetch -> create branch from FETCH_HEAD -> pop stash -> push
    """
    try:
        repo = _get_repo(repo_path)
        origin = repo.remotes.origin

        # Stash uncommitted changes
        had_stash = False
        if repo.is_dirty(untracked_files=True):
            repo.git.stash("push", "--include-untracked", "-m", f"auto-stash-before-{name}")
            had_stash = True

        # Fetch base branch
        try:
            origin.fetch(from_branch)
            base_ref = "FETCH_HEAD"
        except GitCommandError:
            base_ref = from_branch

        # Create and checkout new branch
        repo.git.checkout("-b", name, base_ref)

        # Pop stash if we had one
        if had_stash:
            try:
                repo.git.stash("pop")
            except GitCommandError:
                pass  # Conflicts handled by user

        # Push with upstream tracking
        try:
            origin.push(name, set_upstream=True)
        except GitCommandError:
            pass  # Non-critical, branch exists locally

        return _json({
            "success": True,
            "branch": name,
            "from": from_branch,
            "stash_restored": had_stash
        })
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_branch_switch(name: str, repo_path: str = ".") -> str:
    """Switch to an existing branch."""
    try:
        repo = _get_repo(repo_path)
        repo.git.checkout(name)
        return _json({"success": True, "branch": name})
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_branch_list(repo_path: str = ".") -> str:
    """List all local and remote branches."""
    try:
        repo = _get_repo(repo_path)
        local = [str(b) for b in repo.branches]
        current = str(repo.active_branch)
        remote = []
        for remote_obj in repo.remotes:
            for ref in remote_obj.refs:
                remote.append(str(ref))

        return _json({
            "success": True,
            "current": current,
            "local": local,
            "remote": remote
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_branch_delete(name: str, force: bool = False, repo_path: str = ".") -> str:
    """Delete a local branch."""
    try:
        repo = _get_repo(repo_path)
        flag = "-D" if force else "-d"
        repo.git.branch(flag, name)
        return _json({"success": True, "deleted": name, "force": force})
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_commit(message: str, files: Optional[str] = None, repo_path: str = ".") -> str:
    """Stage files and create a commit.

    Args:
        message: Commit message (can be multi-line)
        files: Comma-separated file paths to stage. If empty, stages all changes.
        repo_path: Repository path
    """
    try:
        repo = _get_repo(repo_path)

        # Stage files
        if files:
            file_list = [f.strip() for f in files.split(",") if f.strip()]
            repo.index.add(file_list)
        else:
            repo.git.add("-A")

        # Check if there are staged changes
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            return _json({"success": True, "message": "No changes to commit"})

        # Commit
        commit = repo.index.commit(message)

        return _json({
            "success": True,
            "commit_hash": str(commit.hexsha)[:7],
            "message": message,
            "author": str(commit.author)
        })
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_push(
    branch: Optional[str] = None,
    set_upstream: bool = False,
    force: bool = False,
    repo_path: str = "."
) -> str:
    """Push branch to remote origin.

    Args:
        branch: Branch to push (current if None)
        set_upstream: Set upstream tracking
        force: Force push (use with caution)
        repo_path: Repository path
    """
    try:
        repo = _get_repo(repo_path)
        origin = repo.remotes.origin
        push_branch = branch or str(repo.active_branch)

        kwargs = {}
        if set_upstream:
            kwargs["set_upstream"] = True
        if force:
            kwargs["force"] = True

        origin.push(push_branch, **kwargs)

        return _json({
            "success": True,
            "branch": push_branch,
            "remote": "origin",
            "force": force
        })
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_pull(branch: Optional[str] = None, repo_path: str = ".") -> str:
    """Pull latest changes from remote origin."""
    try:
        repo = _get_repo(repo_path)
        origin = repo.remotes.origin
        pull_branch = branch or str(repo.active_branch)

        result = origin.pull(pull_branch)
        flags = [info.flags for info in result]

        return _json({
            "success": True,
            "branch": pull_branch,
            "flags": flags
        })
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_diff(staged: bool = False, from_ref: Optional[str] = None, repo_path: str = ".") -> str:
    """Get diff output.

    Args:
        staged: If True, show staged changes (--cached)
        from_ref: Compare against this ref (e.g., 'main')
        repo_path: Repository path
    """
    try:
        repo = _get_repo(repo_path)

        if from_ref:
            diff_text = repo.git.diff(from_ref, "HEAD", "--stat")
        elif staged:
            diff_text = repo.git.diff("--cached", "--stat")
        else:
            diff_text = repo.git.diff("--stat")

        return _json({
            "success": True,
            "diff_summary": diff_text,
            "staged": staged,
            "from_ref": from_ref
        })
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_stash(action: str = "push", message: Optional[str] = None, repo_path: str = ".") -> str:
    """Manage git stash.

    Args:
        action: 'push' to stash changes, 'pop' to restore, 'list' to show stashes
        message: Stash message (only for push)
        repo_path: Repository path
    """
    try:
        repo = _get_repo(repo_path)

        if action == "push":
            args = ["push", "--include-untracked"]
            if message:
                args.extend(["-m", message])
            result = repo.git.stash(*args)
            return _json({"success": True, "action": "push", "result": result})

        elif action == "pop":
            result = repo.git.stash("pop")
            return _json({"success": True, "action": "pop", "result": result})

        elif action == "list":
            result = repo.git.stash("list")
            stashes = [line for line in result.split("\n") if line]
            return _json({"success": True, "action": "list", "stashes": stashes})

        else:
            return _json({"success": False, "error": f"Unknown stash action: {action}"})

    except GitCommandError as e:
        error_msg = str(e)
        if "No local changes" in error_msg or "No stash entries" in error_msg:
            return _json({"success": True, "action": action, "result": "Nothing to stash/pop"})
        return _json({"success": False, "error": error_msg})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_log(count: int = 10, repo_path: str = ".") -> str:
    """Get recent commit log.

    Args:
        count: Number of commits to show (default: 10)
        repo_path: Repository path
    """
    try:
        repo = _get_repo(repo_path)
        commits = []
        for commit in repo.iter_commits(max_count=count):
            commits.append({
                "hash": str(commit.hexsha)[:7],
                "message": commit.message.strip().split("\n")[0],
                "author": str(commit.author),
                "date": commit.committed_datetime.isoformat()
            })

        return _json({
            "success": True,
            "commits": commits,
            "count": len(commits),
            "current_branch": str(repo.active_branch)
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_fetch(remote: str = "origin", branch: Optional[str] = None, prune: bool = False, repo_path: str = ".") -> str:
    """Fetch from remote.

    Args:
        remote: Remote name (default: origin)
        branch: Specific branch to fetch (None = all)
        prune: Remove stale remote-tracking branches
        repo_path: Repository path
    """
    try:
        repo = _get_repo(repo_path)
        remote_obj = repo.remote(remote)

        kwargs = {}
        if prune:
            kwargs["prune"] = True

        if branch:
            result = remote_obj.fetch(branch, **kwargs)
        else:
            result = remote_obj.fetch(**kwargs)

        fetched = [str(info.ref) for info in result]

        return _json({
            "success": True,
            "remote": remote,
            "fetched_refs": fetched,
            "pruned": prune
        })
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_post_merge_cleanup(
    merged_branch: str,
    main_branch: str = "main",
    repo_path: str = "."
) -> str:
    """Clean up after a PR merge: switch to main, pull, delete branch, prune.

    Orchestrated 4-step workflow:
    1. Checkout main branch
    2. Pull latest from remote (includes merged PR)
    3. Delete local merged branch (force if needed)
    4. Prune stale remote-tracking branches

    Args:
        merged_branch: Branch that was merged (will be deleted locally)
        main_branch: Target branch (default: main)
        repo_path: Repository path
    """
    try:
        repo = _get_repo(repo_path)
        origin = repo.remotes.origin

        # Step 1: Checkout main
        repo.git.checkout(main_branch)

        # Step 2: Pull latest (includes merged PR)
        origin.pull(main_branch)

        # Step 3: Delete local merged branch
        branch_deleted = False
        if merged_branch and merged_branch != main_branch:
            try:
                repo.git.branch("-d", merged_branch)
                branch_deleted = True
            except GitCommandError:
                try:
                    repo.git.branch("-D", merged_branch)
                    branch_deleted = True
                except GitCommandError:
                    pass

        # Step 4: Prune stale remote-tracking branches
        origin.fetch(prune=True)

        return _json({
            "success": True,
            "cleaned_branch": merged_branch,
            "current_branch": main_branch,
            "branch_deleted": branch_deleted,
            "message": f"Cleaned up {merged_branch}, now on {main_branch} (synced)"
        })
    except GitCommandError as e:
        return _json({"success": False, "error": str(e)})
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def git_get_origin_url(repo_path: str = ".") -> str:
    """Get the remote origin URL of the repository."""
    try:
        repo = _get_repo(repo_path)
        url = repo.remotes.origin.url
        return _json({
            "success": True,
            "origin_url": url,
            "is_github": "github.com" in url
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
