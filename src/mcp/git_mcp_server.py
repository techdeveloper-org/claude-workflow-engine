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

import sys
from pathlib import Path
from typing import Optional

# Ensure src/mcp/ is in path for base package imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from git import InvalidGitRepositoryError, GitCommandError

from base.decorators import mcp_tool_handler
from base.clients import GitRepoClient

mcp = FastMCP("git-ops", instructions="Git operations via GitPython (no subprocess)")


@mcp.tool()
@mcp_tool_handler
def git_status(repo_path: str = ".") -> dict:
    """Get repository status (modified, staged, untracked files)."""
    repo = GitRepoClient.for_path(repo_path)
    changed = [item.a_path for item in repo.index.diff(None)]
    staged = [item.a_path for item in repo.index.diff("HEAD")]
    untracked = repo.untracked_files

    return {
        "branch": str(repo.active_branch),
        "is_dirty": repo.is_dirty(untracked_files=True),
        "modified": changed,
        "staged": staged,
        "untracked": untracked,
        "total_changes": len(changed) + len(staged) + len(untracked)
    }


@mcp.tool()
@mcp_tool_handler
def git_branch_create(name: str, from_branch: str = "main", repo_path: str = ".") -> dict:
    """Create a new branch from specified base with stash safety.

    Workflow: stash -> fetch -> create branch from FETCH_HEAD -> pop stash -> push
    """
    repo = GitRepoClient.for_path(repo_path)
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

    return {
        "branch": name,
        "from": from_branch,
        "stash_restored": had_stash
    }


@mcp.tool()
@mcp_tool_handler
def git_branch_switch(name: str, repo_path: str = ".") -> dict:
    """Switch to an existing branch."""
    repo = GitRepoClient.for_path(repo_path)
    repo.git.checkout(name)
    return {"branch": name}


@mcp.tool()
@mcp_tool_handler
def git_branch_list(repo_path: str = ".") -> dict:
    """List all local and remote branches."""
    repo = GitRepoClient.for_path(repo_path)
    local = [str(b) for b in repo.branches]
    current = str(repo.active_branch)
    remote = []
    for remote_obj in repo.remotes:
        for ref in remote_obj.refs:
            remote.append(str(ref))

    return {
        "current": current,
        "local": local,
        "remote": remote
    }


@mcp.tool()
@mcp_tool_handler
def git_branch_delete(name: str, force: bool = False, repo_path: str = ".") -> dict:
    """Delete a local branch."""
    repo = GitRepoClient.for_path(repo_path)
    flag = "-D" if force else "-d"
    repo.git.branch(flag, name)
    return {"deleted": name, "force": force}


@mcp.tool()
@mcp_tool_handler
def git_commit(message: str, files: Optional[str] = None, repo_path: str = ".") -> dict:
    """Stage files and create a commit.

    Args:
        message: Commit message (can be multi-line)
        files: Comma-separated file paths to stage. If empty, stages all changes.
        repo_path: Repository path
    """
    repo = GitRepoClient.for_path(repo_path)

    # Stage files
    if files:
        file_list = [f.strip() for f in files.split(",") if f.strip()]
        repo.index.add(file_list)
    else:
        repo.git.add("-A")

    # Check if there are staged changes
    if not repo.index.diff("HEAD") and not repo.untracked_files:
        return {"message": "No changes to commit"}

    # Commit
    commit = repo.index.commit(message)

    return {
        "commit_hash": str(commit.hexsha)[:7],
        "message": message,
        "author": str(commit.author)
    }


@mcp.tool()
@mcp_tool_handler
def git_push(
    branch: Optional[str] = None,
    set_upstream: bool = False,
    force: bool = False,
    repo_path: str = "."
) -> dict:
    """Push branch to remote origin.

    Args:
        branch: Branch to push (current if None)
        set_upstream: Set upstream tracking
        force: Force push (use with caution)
        repo_path: Repository path
    """
    repo = GitRepoClient.for_path(repo_path)
    origin = repo.remotes.origin
    push_branch = branch or str(repo.active_branch)

    kwargs = {}
    if set_upstream:
        kwargs["set_upstream"] = True
    if force:
        kwargs["force"] = True

    origin.push(push_branch, **kwargs)

    return {
        "branch": push_branch,
        "remote": "origin",
        "force": force
    }


@mcp.tool()
@mcp_tool_handler
def git_pull(branch: Optional[str] = None, repo_path: str = ".") -> dict:
    """Pull latest changes from remote origin."""
    repo = GitRepoClient.for_path(repo_path)
    origin = repo.remotes.origin
    pull_branch = branch or str(repo.active_branch)

    result = origin.pull(pull_branch)
    flags = [info.flags for info in result]

    return {
        "branch": pull_branch,
        "flags": flags
    }


@mcp.tool()
@mcp_tool_handler
def git_diff(staged: bool = False, from_ref: Optional[str] = None, repo_path: str = ".") -> dict:
    """Get diff output.

    Args:
        staged: If True, show staged changes (--cached)
        from_ref: Compare against this ref (e.g., 'main')
        repo_path: Repository path
    """
    repo = GitRepoClient.for_path(repo_path)

    if from_ref:
        diff_text = repo.git.diff(from_ref, "HEAD", "--stat")
    elif staged:
        diff_text = repo.git.diff("--cached", "--stat")
    else:
        diff_text = repo.git.diff("--stat")

    return {
        "diff_summary": diff_text,
        "staged": staged,
        "from_ref": from_ref
    }


@mcp.tool()
@mcp_tool_handler
def git_stash(action: str = "push", message: Optional[str] = None, repo_path: str = ".") -> dict:
    """Manage git stash.

    Args:
        action: 'push' to stash changes, 'pop' to restore, 'list' to show stashes
        message: Stash message (only for push)
        repo_path: Repository path
    """
    repo = GitRepoClient.for_path(repo_path)

    if action == "push":
        args = ["push", "--include-untracked"]
        if message:
            args.extend(["-m", message])
        try:
            result = repo.git.stash(*args)
        except GitCommandError as e:
            error_msg = str(e)
            if "No local changes" in error_msg or "No stash entries" in error_msg:
                return {"action": action, "result": "Nothing to stash/pop"}
            raise
        return {"action": "push", "result": result}

    elif action == "pop":
        try:
            result = repo.git.stash("pop")
        except GitCommandError as e:
            error_msg = str(e)
            if "No local changes" in error_msg or "No stash entries" in error_msg:
                return {"action": action, "result": "Nothing to stash/pop"}
            raise
        return {"action": "pop", "result": result}

    elif action == "list":
        result = repo.git.stash("list")
        stashes = [line for line in result.split("\n") if line]
        return {"action": "list", "stashes": stashes}

    else:
        raise ValueError(f"Unknown stash action: {action}")


@mcp.tool()
@mcp_tool_handler
def git_log(count: int = 10, repo_path: str = ".") -> dict:
    """Get recent commit log.

    Args:
        count: Number of commits to show (default: 10)
        repo_path: Repository path
    """
    repo = GitRepoClient.for_path(repo_path)
    commits = []
    for commit in repo.iter_commits(max_count=count):
        commits.append({
            "hash": str(commit.hexsha)[:7],
            "message": commit.message.strip().split("\n")[0],
            "author": str(commit.author),
            "date": commit.committed_datetime.isoformat()
        })

    return {
        "commits": commits,
        "count": len(commits),
        "current_branch": str(repo.active_branch)
    }


@mcp.tool()
@mcp_tool_handler
def git_fetch(remote: str = "origin", branch: Optional[str] = None, prune: bool = False, repo_path: str = ".") -> dict:
    """Fetch from remote.

    Args:
        remote: Remote name (default: origin)
        branch: Specific branch to fetch (None = all)
        prune: Remove stale remote-tracking branches
        repo_path: Repository path
    """
    repo = GitRepoClient.for_path(repo_path)
    remote_obj = repo.remote(remote)

    kwargs = {}
    if prune:
        kwargs["prune"] = True

    if branch:
        result = remote_obj.fetch(branch, **kwargs)
    else:
        result = remote_obj.fetch(**kwargs)

    fetched = [str(info.ref) for info in result]

    return {
        "remote": remote,
        "fetched_refs": fetched,
        "pruned": prune
    }


@mcp.tool()
@mcp_tool_handler
def git_post_merge_cleanup(
    merged_branch: str,
    main_branch: str = "main",
    repo_path: str = "."
) -> dict:
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
    repo = GitRepoClient.for_path(repo_path)
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

    return {
        "cleaned_branch": merged_branch,
        "current_branch": main_branch,
        "branch_deleted": branch_deleted,
        "message": f"Cleaned up {merged_branch}, now on {main_branch} (synced)"
    }


@mcp.tool()
@mcp_tool_handler
def git_get_origin_url(repo_path: str = ".") -> dict:
    """Get the remote origin URL of the repository."""
    repo = GitRepoClient.for_path(repo_path)
    url = repo.remotes.origin.url
    return {
        "origin_url": url,
        "is_github": "github.com" in url
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
