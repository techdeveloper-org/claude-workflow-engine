#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git Auto-Commit Policy - Unified Git Automation System
=======================================================

Consolidates all git auto-commit functionality into a single
enterprise-grade policy module covering:

  1. GitAutoCommitAI         - AI-powered semantic commit message generation
  2. AutoCommitDetector      - Detect files and triggers needing commits
  3. AutoCommitEnforcer      - Enforce commit policy requirements
  4. GitAutoCommitEngine     - Core auto-commit orchestration engine
  5. GitAutoCommitPolicy     - Unified policy interface (enforce/validate/report)

USAGE (CLI):
  python git-auto-commit-policy.py --detect
  python git-auto-commit-policy.py --commit [--push] [--dry-run]
  python git-auto-commit-policy.py --ai-message [--context "task context"]
  python git-auto-commit-policy.py --enforce [--enforce-now]
  python git-auto-commit-policy.py --stats
  python git-auto-commit-policy.py --validate
  python git-auto-commit-policy.py --report

PROGRAMMATIC:
  from git_auto_commit_policy import GitAutoCommitPolicy
  policy = GitAutoCommitPolicy()
  policy.enforce()
  policy.validate()
  policy.report()

SOURCES CONSOLIDATED:
  - git-auto-commit-ai.py     (AI-powered message generation)
  - auto-commit.py            (Core auto-commit engine)
  - auto-commit-detector.py   (Detect files needing commits)
  - auto-commit-enforcer.py   (Enforce commit requirements)
  - trigger-auto-commit.py    (Trigger commit automation)

VERSION: 2.0.0
"""

import os
import sys
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False

# ---------------------------------------------------------------------------
# Platform: fix Windows console encoding
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MEMORY_DIR = Path.home() / ".claude" / "memory"
LOGS_DIR = MEMORY_DIR / "logs"
SESSIONS_DIR = LOGS_DIR / "sessions"
POLICY_HIT_LOG = LOGS_DIR / "policy-hits.log"
COMMIT_LOG = LOGS_DIR / "git-auto-commit.log"

# Workspace discovery root (can be overridden by env var)
DEFAULT_WORKSPACE = (
    Path.home()
    / "Documents"
    / "workspace-spring-tool-suite-4-4.27.0-new"
)

# Commit trigger thresholds
THRESHOLDS = {
    "modified_files": 1,               # 1+ modified files  -> trigger
    "staged_files": 1,                 # 1+ staged files    -> trigger
    "time_since_last_commit_min": 30,  # 30+ minutes        -> trigger
    "phase_completion": True,          # phase complete      -> trigger
    "todo_completion": True,           # todo complete       -> trigger
}

# Keywords that signal a milestone completion in policy logs
MILESTONE_KEYWORDS = [
    "done",
    "finished",
    "complete",
    "completed",
    "phase complete",
    "milestone",
    "todo done",
    "feature complete",
    "bug fixed",
]

# Semantic commit types (conventional commits standard)
COMMIT_TYPES = ("feat", "fix", "refactor", "docs", "test", "chore", "style", "perf")

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger("git-auto-commit-policy")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _write_policy_log(source, action, context):
    """Append an entry to the central policy-hits.log file.

    Args:
        source:  Identifier of the subsystem writing the entry.
        action:  Short action label (e.g. 'commit-created').
        context: Free-form context string for the entry.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = "[{ts}] {src} | {act} | {ctx}\n".format(
        ts=timestamp, src=source, act=action, ctx=context
    )
    try:
        POLICY_HIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(POLICY_HIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(log_entry)
    except OSError as exc:
        _logger.warning("Could not write policy log: %s", exc)


def _run_git(args, cwd=None, timeout=30):
    """Run a git sub-command and return the CompletedProcess.

    Never raises on non-zero exit codes; callers must inspect returncode.

    Args:
        args:    List of arguments to pass after 'git'.
        cwd:     Working directory for the subprocess.
        timeout: Maximum execution time in seconds.

    Returns:
        subprocess.CompletedProcess (stdout/stderr as str), or a
        lightweight error object with returncode=1 on failure.
    """
    try:
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        _logger.warning("git %s timed out after %ds", " ".join(args), timeout)

        class _Timeout:
            """Stub result object returned when a git command times out."""

            returncode = 1
            stdout = ""
            stderr = "Timed out after {}s".format(timeout)

        return _Timeout()
    except Exception as exc:

        class _Error:
            """Stub result object returned when a git command raises an exception."""

            returncode = 1
            stdout = ""
            stderr = str(exc)

        return _Error()


def _is_git_repo(path):
    """Return True if *path* is inside a git working tree.

    Args:
        path: Directory path to check.

    Returns:
        bool: True if git rev-parse succeeds, False otherwise.
    """
    result = _run_git(["rev-parse", "--git-dir"], cwd=path, timeout=5)
    return result.returncode == 0


def _find_git_root(start_dir, max_levels=5):
    """Walk up the directory tree to find the nearest .git directory.

    Args:
        start_dir:  Starting directory for the search.
        max_levels: Maximum number of parent levels to traverse.

    Returns:
        str: Absolute path to the git root directory, or None if not found.
    """
    current = os.path.abspath(start_dir)
    for _ in range(max_levels):
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


# ===========================================================================
# Class 1: GitAutoCommitAI
# ===========================================================================

class GitAutoCommitAI:
    """AI-powered semantic commit message generator.

    Analyses the git diff and status of a repository to produce a structured,
    semantic commit message that follows conventional-commit conventions.

    Commit type precedence:
      1. Task context (session flow-trace / tool-tracker data)
      2. File-type heuristics (test files, doc files, source files)
      3. Change category (added > deleted > modified)

    Source: git-auto-commit-ai.py (consolidated)
    """

    # Extensions considered "source code" for 'feat' detection
    SOURCE_EXTENSIONS = (".java", ".py", ".js", ".ts", ".go", ".rb", ".rs", ".kt")
    TEST_MARKERS = ("test", "spec", "_test", ".test.", ".spec.")
    DOC_EXTENSIONS = (".md", ".txt", ".rst", ".adoc")

    def __init__(self):
        """Initialize GitAutoCommitAI with memory and log directory paths."""
        self.memory_path = MEMORY_DIR
        self.logs_path = LOGS_DIR
        self.commit_log = COMMIT_LOG

    # ------------------------------------------------------------------
    # Git query helpers
    # ------------------------------------------------------------------

    def check_git_repo(self, path="."):
        """Check if current directory is a git repo.

        Args:
            path: Directory path to check.

        Returns:
            bool: True if a valid git repository, False otherwise.
        """
        return _is_git_repo(path)

    def get_git_status(self, path="."):
        """Return the porcelain git status output for *path*.

        Args:
            path: Git repository root path.

        Returns:
            str: Raw porcelain status string, or None on failure.
        """
        result = _run_git(["status", "--porcelain"], cwd=path)
        return result.stdout.strip() if result.returncode == 0 else None

    def get_git_diff(self, path=".", staged=False):
        """Return the diff --stat output for *path*.

        Args:
            path:   Git repository root path.
            staged: If True, compares the index against HEAD.

        Returns:
            str: Diff stat string, or None on failure.
        """
        cmd = ["diff", "--stat"]
        if staged:
            cmd.append("--cached")
        result = _run_git(cmd, cwd=path)
        return result.stdout.strip() if result.returncode == 0 else None

    def get_recent_commit_style(self, path="."):
        """Analyse recent commits to detect the project's commit style.

        Inspects the last 10 commit subjects and returns a style dict with:
          - type_prefix (bool): whether <type>: prefixes are used
          - emoji (bool): whether emoji characters appear in subjects
          - length (str): 'short' | 'medium' | 'long'

        Args:
            path: Git repository root path.

        Returns:
            dict: Style dict, or empty dict on failure.
        """
        result = _run_git(["log", "-10", "--pretty=format:%s"], cwd=path, timeout=5)
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        messages = result.stdout.strip().split("\n")
        has_type_prefix = any(":" in msg[:20] for msg in messages)
        has_emoji = any(any(ord(c) > 127 for c in msg[:10]) for msg in messages)
        avg_len = sum(len(m) for m in messages) / max(len(messages), 1)
        length_label = "short" if avg_len < 50 else "medium" if avg_len < 80 else "long"
        return {
            "type_prefix": has_type_prefix,
            "emoji": has_emoji,
            "length": length_label,
        }

    # ------------------------------------------------------------------
    # Change analysis
    # ------------------------------------------------------------------

    def parse_status(self, status_output):
        """Parse porcelain git status into categorised file lists.

        Args:
            status_output: Raw output of ``git status --porcelain``.

        Returns:
            dict: Keys: added, modified, deleted, renamed (lists of file paths).
        """
        changes = {"added": [], "modified": [], "deleted": [], "renamed": []}
        if not status_output:
            return changes
        for line in status_output.splitlines():
            if not line:
                continue
            code = line[0:2].strip()
            filename = line[3:].strip()
            if code in ("A", "??"):
                changes["added"].append(filename)
            elif code in ("M", "AM", "MM"):
                changes["modified"].append(filename)
            elif code == "D":
                changes["deleted"].append(filename)
            elif code == "R":
                changes["renamed"].append(filename)
        return changes

    # Backwards-compatible alias used by auto-commit.py workflow
    def analyze_changes(self, status, diff):
        """Analyse git status and diff output.

        Args:
            status: Raw porcelain git status string.
            diff:   Git diff --stat output (used for context, not parsed).

        Returns:
            dict: Categorised changes, or None if status is empty.
        """
        if not status:
            return None
        return self.parse_status(status)

    def _has_source_files(self, filenames):
        """Return True if any filename ends with a recognised source-code extension.

        Args:
            filenames (list[str]): List of changed file names.

        Returns:
            bool: True if at least one file is a source file.
        """
        return any(f.endswith(self.SOURCE_EXTENSIONS) for f in filenames)

    def _has_test_files(self, filenames):
        """Return True if any filename contains a test or spec marker.

        Args:
            filenames (list[str]): List of changed file names.

        Returns:
            bool: True if at least one file is a test/spec file.
        """
        return any(
            any(marker in f.lower() for marker in self.TEST_MARKERS)
            for f in filenames
        )

    def _has_doc_files(self, filenames):
        """Return True if any filename ends with a documentation extension.

        Args:
            filenames (list[str]): List of changed file names.

        Returns:
            bool: True if at least one file is a documentation file.
        """
        return any(f.endswith(self.DOC_EXTENSIONS) for f in filenames)

    # ------------------------------------------------------------------
    # Task context loading (from session chain data)
    # ------------------------------------------------------------------

    def _load_task_context(self):
        """Load real task context from Claude session data.

        Reads session-progress.json, flow-trace.json, and tool-tracker.jsonl
        to extract the most recent task subject, task type, and edited files.

        Returns:
            dict: Keys: task_subject (str), task_type (str), edits_summary (list).
        """
        ctx = {"task_subject": "", "task_type": "", "edits_summary": []}
        try:
            # 1. Resolve the active session ID
            progress_file = LOGS_DIR / "session-progress.json"
            session_id = ""
            if progress_file.exists():
                with open(progress_file, "r", encoding="utf-8") as fh:
                    prog = json.load(fh)
                session_id = prog.get("session_id", "")

            # 2. Pull task_type from flow-trace
            if session_id:
                trace_file = SESSIONS_DIR / session_id / "flow-trace.json"
                if trace_file.exists():
                    with open(trace_file, "r", encoding="utf-8") as fh:
                        trace = json.load(fh)
                    ctx["task_type"] = trace.get("final_decision", {}).get("task_type", "")

            # 3. Extract task subject and edited file paths from tool-tracker.jsonl
            tracker_file = LOGS_DIR / "tool-tracker.jsonl"
            if tracker_file.exists():
                with open(tracker_file, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
                for raw in reversed(lines):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    tool = entry.get("tool", "")
                    if tool == "TaskCreate" and not ctx["task_subject"]:
                        ctx["task_subject"] = entry.get("task_subject", "")
                    if tool in ("Edit", "Write") and len(ctx["edits_summary"]) < 5:
                        fpath = entry.get("file", "")
                        if fpath:
                            ctx["edits_summary"].append(fpath)
        except Exception:
            pass
        return ctx

    # ------------------------------------------------------------------
    # Commit type determination
    # ------------------------------------------------------------------

    def determine_commit_type(self, changes, context=None):
        """Determine the semantic commit type from changes and optional context.

        Priority order:
          1. Explicit keywords in context string
          2. Context string partial matching against common verbs
          3. File-type heuristics (test files, doc files, source files)
          4. Change category heuristics (added > deleted > modified)

        Args:
            changes: Categorised changes dict from parse_status().
            context: Optional free-text context string (e.g. task subject).

        Returns:
            str: One of the COMMIT_TYPES values.
        """
        if context:
            ctx_lower = context.lower()
            if any(w in ctx_lower for w in ("fix", "bug", "error", "broken", "crash", "resolve")):
                return "fix"
            if any(w in ctx_lower for w in ("refactor", "cleanup", "reorganize", "simplify", "clean")):
                return "refactor"
            if any(w in ctx_lower for w in ("doc", "readme", "documentation", "comment")):
                return "docs"
            if any(w in ctx_lower for w in ("test", "spec", "coverage")):
                return "test"
            if any(w in ctx_lower for w in ("style", "format", "lint")):
                return "style"
            if any(w in ctx_lower for w in ("perf", "performance", "optimiz", "speed")):
                return "perf"

        all_files = (
            changes.get("added", [])
            + changes.get("modified", [])
            + changes.get("deleted", [])
            + changes.get("renamed", [])
        )

        if self._has_test_files(all_files):
            return "test"
        if self._has_doc_files(all_files):
            return "docs"
        if changes.get("added") and self._has_source_files(changes["added"]):
            return "feat"
        if changes.get("deleted"):
            return "refactor"
        if changes.get("added"):
            return "feat"

        return "chore"

    # ------------------------------------------------------------------
    # Summary and body generation
    # ------------------------------------------------------------------

    def generate_summary(self, changes, commit_type, task_subject=""):
        """Generate the subject line of the commit message.

        Uses task_subject when available for precise, context-aware summaries.

        Args:
            changes:      Categorised changes dict.
            commit_type:  Determined semantic commit type.
            task_subject: Optional task subject from session data.

        Returns:
            str: Short summary string (no trailing period, max 72 chars).
        """
        if task_subject:
            trimmed = task_subject.strip().rstrip(".")
            return trimmed[:72] if len(trimmed) > 72 else trimmed

        all_added = changes.get("added", [])
        all_modified = changes.get("modified", [])
        all_deleted = changes.get("deleted", [])

        if commit_type == "feat":
            if len(all_added) == 1:
                return "add {}".format(Path(all_added[0]).stem)
            return "add {} new files".format(len(all_added))

        if commit_type == "fix":
            if len(all_modified) == 1:
                return "fix issue in {}".format(Path(all_modified[0]).stem)
            return "fix issues in {} files".format(len(all_modified))

        if commit_type == "refactor":
            if all_deleted:
                return "remove {} obsolete files".format(len(all_deleted))
            return "refactor {} files".format(len(all_modified))

        if commit_type == "test":
            return "add/update tests"

        if commit_type == "docs":
            return "update documentation"

        if commit_type == "style":
            return "apply formatting and style fixes"

        if commit_type == "perf":
            return "improve performance"

        total = len(all_added) + len(all_modified) + len(all_deleted)
        return "update {} files".format(total)

    def generate_details(self, changes):
        """Generate body lines of the commit message listing affected files.

        Lists up to 5 affected files per category with 'and N more' truncation.

        Args:
            changes: Categorised changes dict from parse_status().

        Returns:
            list: Body lines (may be empty).
        """
        body = []
        _MAX = 5

        def _section(label, files):
            """Append a labelled file list (up to _MAX entries) to body.

            Args:
                label (str): Section label string (e.g., 'Added files').
                files (list[str]): Files to list under this label.
            """
            if not files:
                return
            body.append("{} ({}):".format(label, len(files)))
            for f in files[:_MAX]:
                body.append("  - {}".format(f))
            if len(files) > _MAX:
                body.append("  - ... and {} more".format(len(files) - _MAX))

        _section("Added files", changes.get("added", []))
        if changes.get("modified") and changes.get("added"):
            body.append("")
        _section("Modified files", changes.get("modified", []))
        if changes.get("deleted"):
            body.append("")
        _section("Deleted files", changes.get("deleted", []))
        if changes.get("renamed"):
            body.append("")
        _section("Renamed files", changes.get("renamed", []))

        return body

    # ------------------------------------------------------------------
    # Public API: build and generate commit messages
    # ------------------------------------------------------------------

    def generate_commit_message(self, changes, context=None):
        """Generate a complete conventional commit message.

        This is the primary method used by the legacy auto-commit.py workflow.
        Loads task context from session data automatically.

        Args:
            changes: Categorised changes dict from parse_status().
            context: Optional override context string.

        Returns:
            str: Full commit message ready for ``git commit -m``.
        """
        if not changes or all(not v for v in changes.values()):
            return "chore: update files\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

        task_ctx = self._load_task_context()
        task_subject = context or task_ctx.get("task_subject", "")

        commit_type = self.determine_commit_type(changes, task_subject)
        summary = self.generate_summary(changes, commit_type, task_subject)
        body_lines = self.generate_details(changes)

        subject = "{}: {}".format(commit_type, summary)
        parts = [subject]
        if body_lines:
            parts.append("")
            parts.extend(body_lines)
        parts.append("")
        parts.append("Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>")

        return "\n".join(parts)

    def build_commit_message(self, changes, context=None, task_subject="", style=None):
        """Build a complete conventional commit message with style awareness.

        Combines type, subject, optional body, and co-author trailer.
        Respects the project's existing commit style when provided.

        Args:
            changes:      Categorised changes dict.
            context:      Optional context string used for type detection.
            task_subject: Optional task subject for the summary line.
            style:        Optional style dict from get_recent_commit_style().

        Returns:
            str: Full commit message string ready for ``git commit -m``.
        """
        if not changes or all(not v for v in changes.values()):
            return "chore: update files\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

        effective_context = context or task_subject
        commit_type = self.determine_commit_type(changes, effective_context)
        summary = self.generate_summary(changes, commit_type, task_subject)
        body_lines = self.generate_details(changes)

        # Respect project style: omit prefix if repo never uses it
        if style and not style.get("type_prefix", True):
            subject = summary.capitalize() if summary else "Update implementation"
        else:
            subject = "{}: {}".format(commit_type, summary)

        # For larger changesets, add file count to subject if no task subject
        staged_count = (
            len(changes.get("added", []))
            + len(changes.get("modified", []))
            + len(changes.get("deleted", []))
        )
        if not task_subject and staged_count > 5:
            if not body_lines:
                body_lines = ["{} files modified".format(staged_count)]

        parts = [subject]
        if body_lines:
            parts.append("")
            parts.extend(body_lines)
        parts.append("")
        parts.append("Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>")

        return "\n".join(parts)

    def generate_message_for_path(self, path=".", context=None):
        """Convenience: generate a commit message for a repository path.

        Reads the current git status and combines AI type detection with
        any available session task context.

        Args:
            path:    Git repository path.
            context: Optional override context string.

        Returns:
            str: Commit message string, or None if no changes detected.
        """
        status_raw = self.get_git_status(path)
        if not status_raw:
            return None
        changes = self.parse_status(status_raw)
        task_ctx = self._load_task_context()
        task_subject = context or task_ctx.get("task_subject", "")
        style = self.get_recent_commit_style(path)
        return self.build_commit_message(changes, context=context, task_subject=task_subject, style=style)

    def find_git_repos(self, base_path):
        """Find all git repositories in base path up to two levels deep.

        Useful when running from a non-git directory such as ~/.claude.

        Args:
            base_path: Base directory to search.

        Returns:
            list: Absolute repository path strings.
        """
        git_repos = []
        try:
            base = Path(base_path)
            if not base.exists():
                return []
            for item in base.iterdir():
                if item.is_dir():
                    if (item / ".git").exists():
                        git_repos.append(str(item))
                    try:
                        for subitem in item.iterdir():
                            if subitem.is_dir() and (subitem / ".git").exists():
                                git_repos.append(str(subitem))
                    except PermissionError:
                        pass
        except PermissionError:
            pass
        return git_repos

    def log_commit(self, result):
        """Persist a compact commit result entry to the commit log.

        Args:
            result: Result dict returned by the commit operation.
        """
        self.logs_path.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": result.get("timestamp", datetime.now().isoformat()),
            "path": result.get("path", ""),
            "success": result.get("success", False),
            "dry_run": result.get("dry_run", False),
            "file_count": sum(len(v) for v in result.get("changes", {}).values()),
        }
        with open(self.commit_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    # Keep backwards-compat alias
    def log_commit_result(self, result):
        """Alias for log_commit for backward compatibility."""
        self.log_commit(result)

    def auto_commit(self, path=".", context=None, push=False, dry_run=False, auto_find=True):
        """Main entry point compatible with git-auto-commit-ai.py CLI.

        Args:
            path:      Git repo path (or base path to search).
            context:   Task context for better messages.
            push:      Auto-push after commit.
            dry_run:   Do not actually commit.
            auto_find: Auto-find git repos if current dir is not a repo.

        Returns:
            dict: Result dict with success, changes, commit_message, etc.
        """
        if not self.check_git_repo(path):
            if auto_find and (".claude" in str(Path(path).resolve()) or path == "."):
                workspace_path = DEFAULT_WORKSPACE
                if workspace_path.exists():
                    git_repos = self.find_git_repos(workspace_path)
                    if git_repos:
                        results = []
                        for repo_path in git_repos:
                            r = self._commit_single_repo(repo_path, context, push, dry_run)
                            results.append(r)
                        return {
                            "success": True,
                            "multi_repo": True,
                            "repos": results,
                            "total_repos": len(git_repos),
                        }
                    return {
                        "success": False,
                        "error": "No git repositories found in {}".format(workspace_path),
                        "path": path,
                        "suggestion": "Run this script from a project directory with .git",
                    }
                return {
                    "success": False,
                    "error": "Workspace not found: {}".format(workspace_path),
                    "path": path,
                    "suggestion": "Run this script from a project directory with .git",
                }
            return {
                "success": False,
                "error": "Not a git repository",
                "path": path,
                "suggestion": "Run this script from a project directory with .git",
            }
        return self._commit_single_repo(path, context, push, dry_run)

    def _commit_single_repo(self, path, context, push, dry_run):
        """Commit to a single repository (internal helper for auto_commit).

        Args:
            path:    Absolute path to the git repository.
            context: Optional context string for commit message.
            push:    Whether to push after committing.
            dry_run: Whether to skip the actual commit.

        Returns:
            dict: Result dict with success, changes, commit_message, etc.
        """
        status = self.get_git_status(path)
        if not status:
            return {
                "success": True,
                "skipped": True,
                "reason": "No changes to commit",
                "path": path,
                "timestamp": datetime.now().isoformat(),
                "dry_run": dry_run,
            }

        diff = self.get_git_diff(path, staged=False)
        changes = self.analyze_changes(status, diff)
        commit_message = self.generate_commit_message(changes, context)

        result = {
            "path": path,
            "changes": changes,
            "commit_message": commit_message,
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat(),
        }

        if not dry_run:
            try:
                subprocess.run(
                    ["git", "add", "."],
                    cwd=path,
                    check=True,
                    timeout=10,
                )
            except Exception as exc:
                result["success"] = False
                result["error"] = "Failed to stage changes: {}".format(exc)
                return result

            try:
                subprocess.run(
                    ["git", "commit", "-m", commit_message],
                    cwd=path,
                    check=True,
                    timeout=10,
                )
                result["success"] = True
                result["committed"] = True
            except Exception as exc:
                result["success"] = False
                result["error"] = "Failed to commit: {}".format(exc)
                return result

            if push:
                try:
                    subprocess.run(
                        ["git", "push"],
                        cwd=path,
                        check=True,
                        timeout=30,
                    )
                    result["pushed"] = True
                except Exception as exc:
                    result["push_error"] = str(exc)
        else:
            result["success"] = True

        self.log_commit(result)
        return result

    def print_result(self, result):
        """Print a formatted commit result to stdout.

        Args:
            result: Result dict from auto_commit() or _commit_single_repo().
        """
        print("\n" + "=" * 70)
        print("Git Auto-Commit with AI")
        print("=" * 70 + "\n")

        if result.get("multi_repo"):
            print("Found {} git repositories\n".format(result["total_repos"]))
            for i, repo_result in enumerate(result["repos"], 1):
                repo_path = Path(repo_result["path"]).name
                print("[{}/{}] Repository: {}".format(i, result["total_repos"], repo_path))
                if repo_result.get("skipped"):
                    print("   SKIPPED: {}".format(repo_result.get("reason", "No changes")))
                elif repo_result.get("success"):
                    changes = repo_result.get("changes", {})
                    total_changes = sum(len(v) for v in changes.values())
                    print("   OK: Committed {} changes".format(total_changes))
                    if repo_result.get("pushed"):
                        print("   OK: Pushed to remote")
                else:
                    print("   ERROR: {}".format(repo_result.get("error", "Unknown error")))
                print()
            print("=" * 70 + "\n")
            return

        if result.get("skipped"):
            print("SKIPPED: {}".format(result.get("reason")))
            print("Path: {}".format(result.get("path")))
            print("\n" + "=" * 70 + "\n")
            return

        if not result.get("success", False) and result.get("error"):
            print("ERROR: {}".format(result["error"]))
            if result.get("suggestion"):
                print("\nSuggestion: {}".format(result["suggestion"]))
            print("\n" + "=" * 70 + "\n")
            return

        changes = result.get("changes", {})
        print("Changes Summary:")
        print("   Added:    {}".format(len(changes.get("added", []))))
        print("   Modified: {}".format(len(changes.get("modified", []))))
        print("   Deleted:  {}".format(len(changes.get("deleted", []))))

        print("\nGenerated Commit Message:")
        print("-" * 70)
        print(result.get("commit_message", "(none)"))
        print("-" * 70)

        if result.get("dry_run"):
            print("\n[DRY RUN] No actual commit was created")
        else:
            if result.get("committed"):
                print("\n[OK] Changes committed successfully!")
            if result.get("pushed"):
                print("[OK] Changes pushed to remote!")
            elif result.get("push_error"):
                print("[WARN] Push failed: {}".format(result["push_error"]))

        print("\n" + "=" * 70 + "\n")


# ===========================================================================
# Class 2: AutoCommitDetector
# ===========================================================================

class AutoCommitDetector:
    """Detect which files and repositories need commits, and when.

    Evaluates six independent trigger categories:
      1. Modified (unstaged) files above threshold
      2. Staged files above threshold
      3. Time elapsed since last commit above threshold
      4. Phase-completion signal in recent policy logs
      5. Todo-completion signal in recent policy logs
      6. Milestone keyword signals in recent policy logs

    Also provides repository discovery utilities for workspace-wide scans.

    Source: auto-commit-detector.py (consolidated)
    """

    def __init__(self, thresholds=None, milestone_keywords=None):
        """Initialise the detector.

        Args:
            thresholds:         Override global THRESHOLDS dict.
            milestone_keywords: Override global MILESTONE_KEYWORDS list.
        """
        self.thresholds = thresholds or THRESHOLDS.copy()
        self.milestone_keywords = milestone_keywords or list(MILESTONE_KEYWORDS)

    # ------------------------------------------------------------------
    # Git status queries
    # ------------------------------------------------------------------

    def get_full_git_status(self, project_dir):
        """Retrieve staged, modified, and untracked file lists.

        Args:
            project_dir: Git repository root path.

        Returns:
            dict: Keys: staged, modified, untracked, staged_count,
                  modified_count, untracked_count. Returns None on error.
        """
        try:
            def _list(args):
                """Run a git command and return its output as a list of non-empty lines.

                Args:
                    args (list[str]): Git sub-command arguments.

                Returns:
                    list[str]: Output lines, or an empty list on failure.
                """
                r = _run_git(args, cwd=project_dir, timeout=5)
                if r.returncode == 0:
                    return [f for f in r.stdout.strip().split("\n") if f]
                return []

            staged = _list(["diff", "--cached", "--name-only"])
            modified = _list(["diff", "--name-only"])
            untracked = _list(["ls-files", "--others", "--exclude-standard"])

            return {
                "staged": staged,
                "modified": modified,
                "untracked": untracked,
                "staged_count": len(staged),
                "modified_count": len(modified),
                "untracked_count": len(untracked),
            }
        except Exception as exc:
            _logger.warning("Could not get git status for %s: %s", project_dir, exc)
            return None

    def get_last_commit_time(self, project_dir):
        """Return the datetime of the most recent commit in the repository.

        Args:
            project_dir: Git repository root path.

        Returns:
            datetime: Datetime of last commit, or None if unavailable.
        """
        result = _run_git(["log", "-1", "--format=%ct"], cwd=project_dir, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            try:
                return datetime.fromtimestamp(int(result.stdout.strip()))
            except ValueError:
                pass
        return None

    # ------------------------------------------------------------------
    # Signal detectors (read from policy-hits.log)
    # ------------------------------------------------------------------

    def _read_recent_log_lines(self, minutes=15, tail=100):
        """Return recent policy log lines within the past *minutes* window.

        Args:
            minutes: Look-back window in minutes.
            tail:    Maximum number of lines to scan from the end of the file.

        Returns:
            list: Recent log lines (strings).
        """
        if not POLICY_HIT_LOG.exists():
            return []
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent = []
        try:
            with open(POLICY_HIT_LOG, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
            for line in lines[-tail:]:
                line = line.strip()
                if not line.startswith("["):
                    continue
                try:
                    ts_str = line[1:20]
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    if ts > cutoff:
                        recent.append(line)
                except ValueError:
                    continue
        except OSError:
            pass
        return recent

    def detect_milestone_signals(self):
        """Return a deduplicated list of milestone keywords found in recent logs.

        Returns:
            list: Matched milestone keyword strings.
        """
        found = set()
        for line in self._read_recent_log_lines(minutes=15, tail=100):
            line_lower = line.lower()
            for kw in self.milestone_keywords:
                if kw in line_lower:
                    found.add(kw)
        return list(found)

    def detect_phase_completion(self):
        """Return True if a phase-completion signal appears in recent logs.

        Returns:
            bool: True if phase completion detected.
        """
        for line in self._read_recent_log_lines(minutes=15, tail=50):
            if "phase-complete" in line.lower() or "phase completed" in line.lower():
                return True
        return False

    def detect_todo_completion(self):
        """Return True if a todo-completion signal appears in recent logs.

        Returns:
            bool: True if todo completion detected.
        """
        for line in self._read_recent_log_lines(minutes=15, tail=50):
            if "todo-complete" in line.lower() or "task completed" in line.lower():
                return True
        return False

    # ------------------------------------------------------------------
    # Trigger evaluation
    # ------------------------------------------------------------------

    def check_commit_triggers(self, project_dir):
        """Evaluate all commit triggers for *project_dir*.

        Args:
            project_dir: Absolute path to the git repository.

        Returns:
            dict: Keys:
              should_commit  (bool)
              triggers_met   (list of str)
              trigger_count  (int)
              details        (dict)
              git_status     (dict, optional)
              project_dir    (str)
              timestamp      (str ISO-8601)
        """
        base = {
            "should_commit": False,
            "triggers_met": [],
            "trigger_count": 0,
            "details": {},
            "project_dir": project_dir,
            "timestamp": datetime.now().isoformat(),
        }

        if not _is_git_repo(project_dir):
            base["reason"] = "Not a git repository"
            return base

        git_status = self.get_full_git_status(project_dir)
        if not git_status:
            base["reason"] = "Could not retrieve git status"
            return base

        base["git_status"] = git_status

        if git_status["staged_count"] == 0 and git_status["modified_count"] == 0:
            base["reason"] = "No changes to commit"
            return base

        triggers_met = []
        details = {}

        # Trigger 1a: modified (unstaged) files
        if git_status["modified_count"] >= self.thresholds["modified_files"]:
            triggers_met.append("modified_files")
            details["modified_files"] = {
                "count": git_status["modified_count"],
                "threshold": self.thresholds["modified_files"],
                "reason": "{} modified files (threshold: {})".format(
                    git_status["modified_count"], self.thresholds["modified_files"]
                ),
            }

        # Trigger 1b: staged files
        if git_status["staged_count"] >= self.thresholds["staged_files"]:
            triggers_met.append("staged_files")
            details["staged_files"] = {
                "count": git_status["staged_count"],
                "threshold": self.thresholds["staged_files"],
                "reason": "{} files staged (threshold: {})".format(
                    git_status["staged_count"], self.thresholds["staged_files"]
                ),
            }

        # Trigger 2: time since last commit
        last_commit_dt = self.get_last_commit_time(project_dir)
        if last_commit_dt:
            elapsed = (datetime.now() - last_commit_dt).total_seconds() / 60
            if elapsed >= self.thresholds["time_since_last_commit_min"]:
                triggers_met.append("time_since_commit")
                details["time_since_commit"] = {
                    "minutes": round(elapsed, 1),
                    "threshold": self.thresholds["time_since_last_commit_min"],
                    "reason": "{:.1f} minutes since last commit".format(elapsed),
                }

        # Trigger 3: phase completion
        if self.thresholds.get("phase_completion") and self.detect_phase_completion():
            triggers_met.append("phase_completion")
            details["phase_completion"] = {
                "reason": "Phase completion detected in recent policy logs"
            }

        # Trigger 4: todo completion
        if self.thresholds.get("todo_completion") and self.detect_todo_completion():
            triggers_met.append("todo_completion")
            details["todo_completion"] = {
                "reason": "Todo completion detected in recent policy logs"
            }

        # Trigger 5: milestone signals
        milestone_sigs = self.detect_milestone_signals()
        if milestone_sigs:
            triggers_met.append("milestone_signals")
            details["milestone_signals"] = {
                "signals": milestone_sigs,
                "reason": "Milestone signals: {}".format(", ".join(milestone_sigs)),
            }

        base["should_commit"] = len(triggers_met) > 0
        base["triggers_met"] = triggers_met
        base["trigger_count"] = len(triggers_met)
        base["details"] = details

        _write_policy_log(
            "auto-commit-detector",
            "trigger-check",
            "should_commit={}, triggers={}".format(base["should_commit"], len(triggers_met)),
        )

        return base

    # ------------------------------------------------------------------
    # Repository discovery
    # ------------------------------------------------------------------

    def find_git_repos_in_workspace(self, workspace_path=None):
        """Discover all git repositories up to two levels deep under *workspace_path*.

        Args:
            workspace_path: Base directory to search. Defaults to DEFAULT_WORKSPACE.

        Returns:
            list: Absolute repository path strings.
        """
        base = Path(workspace_path or DEFAULT_WORKSPACE)
        repos = []
        if not base.exists():
            _logger.warning("Workspace not found: %s", base)
            return repos
        try:
            for item in base.iterdir():
                if not item.is_dir():
                    continue
                if (item / ".git").exists():
                    repos.append(str(item))
                else:
                    try:
                        for sub in item.iterdir():
                            if sub.is_dir() and (sub / ".git").exists():
                                repos.append(str(sub))
                    except PermissionError:
                        pass
        except PermissionError:
            pass
        return repos

    def find_repos_with_changes(self, workspace_path=None):
        """Return paths of workspace git repos that have uncommitted changes.

        Args:
            workspace_path: Base directory to search. Defaults to environment
                            variable CLAUDE_WORKSPACE_DIR or current directory.

        Returns:
            list: Absolute repository path strings with uncommitted changes.
        """
        ws = workspace_path or os.environ.get("CLAUDE_WORKSPACE_DIR", os.getcwd())
        repos_with_changes = []
        for root, dirs, _files in os.walk(ws):
            if ".git" in root.split(os.sep):
                continue
            if ".git" in dirs:
                status = _run_git(["-C", root, "status", "--porcelain"], timeout=5)
                if status.returncode == 0 and status.stdout.strip():
                    repos_with_changes.append(root)
        return repos_with_changes

    # ------------------------------------------------------------------
    # Formatted output
    # ------------------------------------------------------------------

    def print_detection_report(self, result):
        """Print a human-readable trigger detection report to stdout.

        Args:
            result: Result dict from check_commit_triggers().
        """
        print("\n" + "=" * 70)
        print("AUTO-COMMIT TRIGGER DETECTION")
        print("=" * 70)
        print("\nProject:   {}".format(result.get("project_dir", "N/A")))
        print("Timestamp: {}".format(result.get("timestamp", "N/A")))

        if result["should_commit"]:
            print(
                "\n[RECOMMENDED] AUTO-COMMIT RECOMMENDED ({} triggers met)".format(
                    result["trigger_count"]
                )
            )
            gs = result.get("git_status", {})
            if gs:
                print("\nGit Status:")
                print("   Staged:    {} files".format(gs.get("staged_count", 0)))
                print("   Modified:  {} files".format(gs.get("modified_count", 0)))
                print("   Untracked: {} files".format(gs.get("untracked_count", 0)))
            print("\nTriggers Met:")
            for trigger in result["triggers_met"]:
                detail = result["details"].get(trigger, {})
                print(
                    "   [OK] {}: {}".format(
                        trigger.replace("_", " ").title(),
                        detail.get("reason", "N/A"),
                    )
                )
            print("\nAction: Auto-commit changes")
        else:
            print("\n[SKIPPED] NO COMMIT NEEDED")
            print("   Reason: {}".format(result.get("reason", "No triggers met")))

        print("\n" + "=" * 70)


# ===========================================================================
# Class 3: AutoCommitEnforcer
# ===========================================================================

class AutoCommitEnforcer:
    """Enforce commit policy requirements across all repositories.

    The enforcer is responsible for:
      - Validating branch naming conventions (semantic label format)
      - Validating commit message format (conventional commits)
      - Scanning the workspace for repos with uncommitted changes
      - Delegating commit execution to the engine
      - Logging all enforcement decisions to policy-hits.log

    Branch naming rules (from github-branch-pr-policy.md):
      Semantic label format: <label>/<issueId>
      Valid labels: feature, bugfix, refactor, docs, test, chore, hotfix, release

    Source: auto-commit-enforcer.py (consolidated)
    """

    VALID_BRANCH_LABELS = (
        "feature",
        "bugfix",
        "refactor",
        "docs",
        "test",
        "chore",
        "hotfix",
        "release",
    )

    def __init__(self, engine=None):
        """Initialise the enforcer.

        Args:
            engine: Optional GitAutoCommitEngine instance to reuse.
        """
        self._engine = engine

    @property
    def engine(self):
        """Lazy-initialise the engine on first access."""
        if self._engine is None:
            self._engine = GitAutoCommitEngine()
        return self._engine

    # ------------------------------------------------------------------
    # Branch validation
    # ------------------------------------------------------------------

    def validate_branch_name(self, branch):
        """Check whether *branch* follows the semantic label/issueId convention.

        Args:
            branch: Git branch name string.

        Returns:
            dict: Keys: valid (bool), branch (str), message (str).
        """
        if not branch or branch in ("main", "master", "develop", "HEAD"):
            return {
                "valid": True,
                "branch": branch,
                "message": "Protected branch - no format required",
            }

        parts = branch.split("/")
        if len(parts) < 2:
            return {
                "valid": False,
                "branch": branch,
                "message": (
                    "Branch '{}' lacks semantic label prefix. "
                    "Expected format: <label>/<issueId> "
                    "(e.g. feature/42, bugfix/123). "
                    "Valid labels: {}".format(branch, ", ".join(self.VALID_BRANCH_LABELS))
                ),
            }

        label = parts[0].lower()
        if label not in self.VALID_BRANCH_LABELS:
            return {
                "valid": False,
                "branch": branch,
                "message": (
                    "Branch label '{}' is not a recognised semantic label. "
                    "Valid labels: {}".format(label, ", ".join(self.VALID_BRANCH_LABELS))
                ),
            }

        return {
            "valid": True,
            "branch": branch,
            "message": "Branch '{}' follows semantic label convention.".format(branch),
        }

    def get_current_branch(self, repo_path):
        """Return the currently checked-out branch name for *repo_path*.

        Args:
            repo_path: Git repository root path.

        Returns:
            str: Branch name string, or 'unknown' on failure.
        """
        result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        return "unknown"

    # ------------------------------------------------------------------
    # Commit message validation
    # ------------------------------------------------------------------

    def validate_commit_message(self, message):
        """Validate a commit message against conventional commit format.

        Rules checked:
          - Non-empty subject line
          - Subject line <= 72 characters
          - Conventional prefix present: <type>: <summary>
          - Recognised commit type

        Args:
            message: Full commit message string.

        Returns:
            dict: Keys: valid (bool), violations (list of str), message (str).
        """
        violations = []
        lines = message.splitlines()
        subject = lines[0].strip() if lines else ""

        if not subject:
            violations.append("Commit message subject is empty")
        else:
            if len(subject) > 72:
                violations.append(
                    "Subject line is {} chars; limit is 72".format(len(subject))
                )
            if ":" in subject:
                prefix = subject.split(":")[0].strip()
                if prefix not in COMMIT_TYPES:
                    violations.append(
                        "Unrecognised commit type '{}'. Valid types: {}".format(
                            prefix, ", ".join(COMMIT_TYPES)
                        )
                    )
            else:
                violations.append(
                    "Subject lacks conventional commit prefix (<type>: <summary>)"
                )

        valid = len(violations) == 0
        return {
            "valid": valid,
            "violations": violations,
            "message": "Commit message is valid" if valid else "; ".join(violations),
        }

    # ------------------------------------------------------------------
    # Workspace scan helpers (from auto-commit-enforcer.py)
    # ------------------------------------------------------------------

    def find_git_repos_with_changes(self, workspace_path=None):
        """Find all git repos in workspace with uncommitted changes.

        Args:
            workspace_path: Base directory to scan. Defaults to
                            CLAUDE_WORKSPACE_DIR env var or cwd.

        Returns:
            list: Absolute repository path strings with changes.
        """
        workspace = workspace_path or os.environ.get("CLAUDE_WORKSPACE_DIR", os.getcwd())
        repos_with_changes = []

        if not os.path.exists(workspace):
            return repos_with_changes

        for root, dirs, _files in os.walk(workspace):
            if ".git" in root.split(os.sep):
                continue
            if ".git" in dirs:
                try:
                    result = _run_git(["-C", root, "status", "--porcelain"])
                    if result.returncode == 0 and result.stdout.strip():
                        repos_with_changes.append(root)
                except Exception:
                    pass

        return repos_with_changes

    def trigger_commit_for_repo(self, repo_path, push=False, dry_run=False):
        """Trigger auto-commit for a specific repo via the engine.

        Args:
            repo_path: Absolute path to the git repository.
            push:      Whether to push after committing.
            dry_run:   Whether to skip the actual commit.

        Returns:
            bool: True if commit was triggered successfully, False otherwise.
        """
        result = self.engine.commit_single_repo(
            path=repo_path,
            push=push,
            dry_run=dry_run,
            require_triggers=False,
        )
        if result.get("success") and not result.get("skipped"):
            _write_policy_log(
                "auto-commit-enforcer",
                "commit-triggered",
                "repo={}".format(os.path.basename(repo_path)),
            )
            return True
        elif result.get("skipped"):
            _write_policy_log(
                "auto-commit-enforcer",
                "commit-skipped",
                "repo={}, reason={}".format(
                    os.path.basename(repo_path), result.get("reason", "")
                ),
            )
            return True  # Skipped is not an error
        else:
            _write_policy_log(
                "auto-commit-enforcer",
                "commit-failed",
                "repo={}, error={}".format(
                    os.path.basename(repo_path), result.get("error", "")
                ),
            )
            return False

    # ------------------------------------------------------------------
    # Enforcement execution
    # ------------------------------------------------------------------

    def enforce_auto_commit(self, workspace_path=None, dry_run=False):
        """Scan all workspace repositories and trigger commits where needed.

        Args:
            workspace_path: Override workspace root for repository discovery.
            dry_run:        If True, stage and generate messages but do not commit.

        Returns:
            dict: Keys: success (bool), processed (int), total (int), repos (list).
        """
        print("\n" + "=" * 70)
        print("AUTO-COMMIT ENFORCER")
        print("=" * 70 + "\n")

        _write_policy_log(
            "auto-commit-enforcer",
            "enforce-start",
            "workspace={}".format(workspace_path or "default"),
        )

        repos = self.find_git_repos_with_changes(workspace_path)

        if not repos:
            print("[OK] No uncommitted changes found - nothing to commit\n")
            _write_policy_log("auto-commit-enforcer", "no-changes", "scan-complete")
            return {"success": True, "processed": 0, "total": 0, "repos": []}

        print("[FOUND] {} repository(ies) with changes:\n".format(len(repos)))
        for r in repos:
            print("   - {}".format(os.path.basename(r)))
        print()

        results = []
        success_count = 0

        for repo_path in repos:
            print("\n" + "=" * 70)
            print("Repository: {}".format(os.path.basename(repo_path)))
            print("=" * 70 + "\n")

            # Branch compliance check
            branch = self.get_current_branch(repo_path)
            branch_check = self.validate_branch_name(branch)
            if not branch_check["valid"]:
                print("[WARN] Branch validation: {}".format(branch_check["message"]))

            if self.trigger_commit_for_repo(repo_path, dry_run=dry_run):
                success_count += 1
                results.append({"path": repo_path, "success": True})
            else:
                results.append({"path": repo_path, "success": False})

        print("\n" + "=" * 70)
        label = "OK" if success_count == len(repos) else "PARTIAL"
        print(
            "[{}] Processed {}/{} repositories".format(label, success_count, len(repos))
        )
        print("=" * 70 + "\n")

        _write_policy_log(
            "auto-commit-enforcer",
            "enforce-complete",
            "success={}, total={}".format(success_count, len(repos)),
        )

        return {
            "success": True,  # Enforcement is best-effort
            "processed": success_count,
            "total": len(repos),
            "repos": results,
        }

    def check_task_requires_commit(self, task_id):
        """Check whether a completed task should trigger an auto-commit.

        Args:
            task_id: Task identifier string.

        Returns:
            dict: Keys: required (bool), task_id (str), message (str).
        """
        _write_policy_log("auto-commit-enforcer", "task-check", "task_id={}".format(task_id))
        return {
            "required": True,
            "task_id": task_id,
            "message": "Task {} completed - auto-commit recommended for any file changes".format(
                task_id
            ),
        }


# ===========================================================================
# Class 4: GitAutoCommitEngine
# ===========================================================================

class GitAutoCommitEngine:
    """Core auto-commit orchestration engine.

    Coordinates the full commit workflow:
      1. Validate repository
      2. Evaluate commit triggers (via AutoCommitDetector)
      3. Stage files
      4. Generate semantic commit message (via GitAutoCommitAI)
      5. Create commit
      6. Optionally push to remote
      7. Log result

    Supports single-repo and multi-repo (workspace) modes.

    Sources: auto-commit.py + trigger-auto-commit.py (consolidated)
    """

    def __init__(self):
        """Initialize GitAutoCommitEngine with AI and detector sub-components."""
        self._ai = GitAutoCommitAI()
        self._detector = AutoCommitDetector()

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def _stage_files(self, path, mode="all"):
        """Stage files for commit.

        Args:
            path: Git repository root path.
            mode: 'all' stages everything ('git add .'); 'tracked' stages
                  only tracked files ('git add -u').

        Returns:
            bool: True on success, False on failure.
        """
        if mode == "tracked":
            result = _run_git(["add", "-u"], cwd=path, timeout=10)
        else:
            result = _run_git(["add", "."], cwd=path, timeout=10)
        if result.returncode != 0:
            _logger.error("Failed to stage files in %s: %s", path, result.stderr)
            return False
        return True

    def _create_commit(self, path, message, dry_run=False):
        """Create a git commit with the given message.

        Args:
            path:    Git repository root path.
            message: Full commit message string.
            dry_run: If True, print message but do not commit.

        Returns:
            bool: True on success or dry_run, False on git failure.
        """
        if dry_run:
            print("\n[DRY RUN] Would create commit:")
            print("=" * 70)
            print(message)
            print("=" * 70)
            return True
        result = _run_git(["commit", "-m", message], cwd=path, timeout=30)
        if result.returncode == 0:
            print("\n[OK] Commit created successfully!")
            if result.stdout:
                print(result.stdout)
            return True
        _logger.error("Commit failed in %s: %s", path, result.stderr)
        print("\n[ERROR] Commit failed: {}".format(result.stderr), file=sys.stderr)
        return False

    def _push_to_remote(self, path, dry_run=False):
        """Push committed changes to the configured remote.

        Args:
            path:    Git repository root path.
            dry_run: If True, print what would be pushed but skip execution.

        Returns:
            bool: True on success or dry_run, False on failure.
        """
        if dry_run:
            print("\n[DRY RUN] Would push to remote")
            return True
        result = _run_git(["push"], cwd=path, timeout=60)
        if result.returncode == 0:
            print("\n[OK] Pushed to remote!")
            return True
        _logger.warning("Push failed for %s: %s", path, result.stderr)
        print("\n[WARN] Push failed: {}".format(result.stderr), file=sys.stderr)
        return False

    # ------------------------------------------------------------------
    # Single-repo commit
    # ------------------------------------------------------------------

    def commit_single_repo(
        self,
        path,
        context=None,
        push=False,
        dry_run=False,
        require_triggers=False,
    ):
        """Execute the full commit workflow for a single repository.

        Args:
            path:             Absolute path to the git repository.
            context:          Optional context string for commit message generation.
            push:             Push to remote after committing.
            dry_run:          Stage and generate message without creating a commit.
            require_triggers: If True, skip commit when no trigger conditions are met.

        Returns:
            dict: Result with keys: path, success, committed, pushed (optional),
                  skipped (optional), reason (optional), error (optional),
                  changes (dict), commit_message (str), timestamp (str).
        """
        now = datetime.now().isoformat()

        if not _is_git_repo(path):
            return {
                "path": path,
                "success": False,
                "error": "Not a git repository",
                "suggestion": "Run from a directory containing a .git folder",
                "timestamp": now,
            }

        # Gate on trigger conditions if requested
        if require_triggers:
            trigger_result = self._detector.check_commit_triggers(path)
            if not trigger_result["should_commit"]:
                return {
                    "path": path,
                    "success": True,
                    "skipped": True,
                    "reason": trigger_result.get("reason", "No trigger conditions met"),
                    "timestamp": now,
                }

        # Get current status
        status_raw = self._ai.get_git_status(path)
        if not status_raw:
            return {
                "path": path,
                "success": True,
                "skipped": True,
                "reason": "No changes to commit",
                "timestamp": now,
            }

        changes = self._ai.parse_status(status_raw)
        style = self._ai.get_recent_commit_style(path)
        task_ctx = self._ai._load_task_context()
        commit_msg = self._ai.build_commit_message(
            changes,
            context=context,
            task_subject=task_ctx.get("task_subject", ""),
            style=style,
        )

        result = {
            "path": path,
            "changes": changes,
            "commit_message": commit_msg,
            "dry_run": dry_run,
            "timestamp": now,
        }

        if not dry_run:
            if not self._stage_files(path, mode="all"):
                result["success"] = False
                result["error"] = "Failed to stage files"
                return result

            if not self._create_commit(path, commit_msg, dry_run=False):
                result["success"] = False
                result["error"] = "Failed to create commit"
                return result

            result["success"] = True
            result["committed"] = True

            _write_policy_log(
                "auto-commit-engine",
                "commit-created",
                "path={}, files={}".format(path, sum(len(v) for v in changes.values())),
            )

            if push:
                pushed = self._push_to_remote(path, dry_run=False)
                result["pushed"] = pushed
                if not pushed:
                    result["push_error"] = "Push failed (see stderr)"
        else:
            result["success"] = True

        self._ai.log_commit(result)
        return result

    # ------------------------------------------------------------------
    # Multi-repo (workspace) commit
    # ------------------------------------------------------------------

    def commit_workspace(
        self,
        workspace_path=None,
        context=None,
        push=False,
        dry_run=False,
        require_triggers=True,
    ):
        """Discover and commit to all repositories in the workspace.

        Args:
            workspace_path:   Override workspace root path.
            context:          Optional context for commit messages.
            push:             Push each repo after committing.
            dry_run:          Stage/generate messages without committing.
            require_triggers: Gate each commit on trigger conditions.

        Returns:
            dict: Keys: success (bool), multi_repo (bool), total_repos (int),
                  repos (list of result dicts).
        """
        ws = workspace_path or str(DEFAULT_WORKSPACE)
        repos = self._detector.find_git_repos_in_workspace(ws)

        if not repos:
            return {
                "success": False,
                "error": "No git repositories found in {}".format(ws),
                "multi_repo": True,
                "total_repos": 0,
                "repos": [],
            }

        results = []
        for repo_path in repos:
            r = self.commit_single_repo(
                path=repo_path,
                context=context,
                push=push,
                dry_run=dry_run,
                require_triggers=require_triggers,
            )
            results.append(r)

        return {
            "success": True,
            "multi_repo": True,
            "total_repos": len(repos),
            "repos": results,
        }

    # ------------------------------------------------------------------
    # Trigger-based auto-commit (from trigger-auto-commit.py)
    # ------------------------------------------------------------------

    def trigger_commit(
        self,
        project_dir,
        event="manual",
        push=True,
        dry_run=False,
    ):
        """Trigger an auto-commit in response to an event signal.

        Checks detector triggers before proceeding and logs the event.

        Args:
            project_dir: Starting directory; git root is discovered automatically.
            event:       Event label (e.g. 'task-completed', 'phase-complete').
            push:        Push after committing.
            dry_run:     Do not actually commit.

        Returns:
            dict: Result with success (bool) and event details.
        """
        print("\n" + "=" * 70)
        print("AUTO-COMMIT TRIGGER")
        print("=" * 70)
        print("\nEvent:     {}".format(event))
        print("Directory: {}".format(project_dir))
        print("Push:      {}".format("Yes" if push else "No"))
        print()

        git_root = _find_git_root(project_dir)
        if not git_root:
            msg = "No git repository found starting from {}".format(project_dir)
            print("[ERROR] {}".format(msg))
            _write_policy_log(
                "auto-commit-trigger",
                "no-git-repo",
                "event={}, dir={}".format(event, project_dir),
            )
            return {"success": False, "error": msg, "event": event}

        print("[OK] Git repository: {}".format(git_root))
        _write_policy_log(
            "auto-commit-trigger",
            "triggered",
            "event={}, repo={}".format(event, os.path.basename(git_root)),
        )

        # Check detector
        trigger_result = self._detector.check_commit_triggers(git_root)
        if not trigger_result["should_commit"]:
            reason = trigger_result.get("reason", "No triggers met")
            print("\n[SKIPPED] No commit needed: {}".format(reason))
            _write_policy_log(
                "auto-commit-trigger",
                "skipped",
                "event={}, reason={}".format(event, reason),
            )
            return {"success": False, "skipped": True, "reason": reason, "event": event}

        print("[OK] Commit recommended\n")

        result = self.commit_single_repo(
            path=git_root,
            push=push,
            dry_run=dry_run,
            require_triggers=False,
        )
        result["event"] = event

        if result.get("success") and result.get("committed"):
            print("\n[OK] AUTO-COMMIT SUCCESSFUL!")
            _write_policy_log(
                "auto-commit-trigger",
                "success",
                "event={}, repo={}, push={}".format(
                    event, os.path.basename(git_root), push
                ),
            )
        elif result.get("skipped"):
            _write_policy_log("auto-commit-trigger", "skipped", "event={}".format(event))
        else:
            _write_policy_log(
                "auto-commit-trigger",
                "failed",
                "event={}, error={}".format(event, result.get("error")),
            )

        return result

    # ------------------------------------------------------------------
    # Formatted output
    # ------------------------------------------------------------------

    def print_commit_result(self, result):
        """Print a formatted commit result summary to stdout.

        Args:
            result: Result dict from commit_single_repo() or commit_workspace().
        """
        print("\n" + "=" * 70)
        print("Git Auto-Commit Engine - Result")
        print("=" * 70 + "\n")

        if result.get("multi_repo"):
            total = result["total_repos"]
            print("Found {} git repositories\n".format(total))
            for i, r in enumerate(result.get("repos", []), 1):
                rname = Path(r.get("path", "?")).name
                print("[{}/{}] {}".format(i, total, rname))
                if r.get("skipped"):
                    print("   SKIPPED: {}".format(r.get("reason", "No changes")))
                elif r.get("success"):
                    ch = r.get("changes", {})
                    total_ch = sum(len(v) for v in ch.values())
                    print("   OK: Committed {} changes".format(total_ch))
                    if r.get("pushed"):
                        print("   OK: Pushed to remote")
                else:
                    print("   ERROR: {}".format(r.get("error", "Unknown error")))
                print()
            print("=" * 70 + "\n")
            return

        if result.get("skipped"):
            print("SKIPPED: {}".format(result.get("reason")))
            print("Path: {}".format(result.get("path")))
            print("\n" + "=" * 70 + "\n")
            return

        if not result.get("success") and result.get("error"):
            print("ERROR: {}".format(result["error"]))
            if result.get("suggestion"):
                print("\nSuggestion: {}".format(result["suggestion"]))
            print("\n" + "=" * 70 + "\n")
            return

        ch = result.get("changes", {})
        print("Changes Summary:")
        print("   Added:    {}".format(len(ch.get("added", []))))
        print("   Modified: {}".format(len(ch.get("modified", []))))
        print("   Deleted:  {}".format(len(ch.get("deleted", []))))
        print("   Renamed:  {}".format(len(ch.get("renamed", []))))

        print("\nGenerated Commit Message:")
        print("-" * 70)
        print(result.get("commit_message", "(none)"))
        print("-" * 70)

        if result.get("dry_run"):
            print("\n[DRY RUN] No actual commit was created")
        else:
            if result.get("committed"):
                print("\n[OK] Changes committed successfully!")
            if result.get("pushed"):
                print("[OK] Changes pushed to remote!")
            elif result.get("push_error"):
                print("[WARN] Push failed: {}".format(result["push_error"]))

        print("\n" + "=" * 70 + "\n")

    # ------------------------------------------------------------------
    # generate_commit_message compat shim (from auto-commit.py)
    # ------------------------------------------------------------------

    def generate_commit_message(self, git_status, triggers, style=None):
        """Generate a smart commit message using git status and trigger context.

        Backwards-compatible wrapper used by the legacy auto-commit.py workflow.

        Args:
            git_status: Git status dict (staged, modified, untracked lists).
            triggers:   Trigger details dict.
            style:      Optional style dict from get_recent_commit_style().

        Returns:
            str: Commit message string.
        """
        staged_files = git_status.get("staged", [])
        task_ctx = self._ai._load_task_context()
        task_subject = task_ctx.get("task_subject", "")

        # Build a synthetic changes dict from staged files
        changes = {
            "added": [f for f in staged_files if not f.endswith((".md", ".txt"))],
            "modified": git_status.get("modified", []),
            "deleted": [],
            "renamed": [],
        }

        return self._ai.build_commit_message(
            changes,
            task_subject=task_subject,
            style=style,
        )


# ===========================================================================
# Class 5: GitAutoCommitPolicy
# ===========================================================================

class GitAutoCommitPolicy:
    """Unified policy interface for git auto-commit operations.

    This is the primary entry point for external callers and the CLI.
    Delegates to the four specialised subsystems based on the requested
    policy operation.

    Public API:
      enforce()  - Initialise all commit subsystems and run enforcement
      validate() - Check git state and policy compliance
      report()   - Generate commit statistics and policy status report

    VERSION: 2.0.0
    """

    VERSION = "2.0.0"

    def __init__(self, workspace_path=None):
        """Initialise the unified policy.

        Args:
            workspace_path: Override workspace root for multi-repo operations.
        """
        self.workspace_path = workspace_path or str(DEFAULT_WORKSPACE)
        self._ai = GitAutoCommitAI()
        self._detector = AutoCommitDetector()
        self._engine = GitAutoCommitEngine()
        self._enforcer = AutoCommitEnforcer(engine=self._engine)

    # ------------------------------------------------------------------
    # Policy interface: enforce
    # ------------------------------------------------------------------

    def enforce(
        self,
        project_dir=None,
        push=False,
        dry_run=False,
        event="policy-enforce",
    ):
        """Initialise all commit subsystems and run enforcement.

        When *project_dir* is provided, enforces on that specific repository.
        Otherwise scans the entire workspace.

        Args:
            project_dir: Optional specific repository path to enforce on.
            push:        Push after each successful commit.
            dry_run:     Stage and generate messages without committing.
            event:       Label for the enforcement event in logs.

        Returns:
            dict: Enforcement result.
        """
        _write_policy_log("git-auto-commit-policy", "enforce-start", "event={}".format(event))

        if project_dir:
            result = self._engine.trigger_commit(
                project_dir=project_dir,
                event=event,
                push=push,
                dry_run=dry_run,
            )
        else:
            result = self._enforcer.enforce_auto_commit(
                workspace_path=self.workspace_path,
                dry_run=dry_run,
            )

        _write_policy_log(
            "git-auto-commit-policy",
            "enforce-complete",
            "success={}".format(result.get("success")),
        )
        return result

    # ------------------------------------------------------------------
    # Policy interface: validate
    # ------------------------------------------------------------------

    def validate(self, project_dir=None):
        """Check git state and policy compliance for a repository.

        Performs:
          - Repository existence check
          - Branch naming convention validation
          - Commit trigger evaluation
          - Pending changes summary
          - Sample commit message format validation

        Args:
            project_dir: Repository path to validate. Defaults to cwd.

        Returns:
            dict: Keys: valid (bool), checks (list of dict), path (str).
        """
        path = project_dir or os.getcwd()
        checks = []
        all_valid = True

        print("\n" + "=" * 70)
        print("GIT AUTO-COMMIT POLICY - VALIDATION")
        print("=" * 70 + "\n")
        print("Repository: {}\n".format(path))

        # Check 1: Is git repo?
        is_repo = _is_git_repo(path)
        c1 = {
            "check": "git_repository",
            "valid": is_repo,
            "message": "Directory is a git repository" if is_repo else "Not a git repository",
        }
        checks.append(c1)
        print("{} Git Repository: {}".format("[OK]" if is_repo else "[FAIL]", c1["message"]))
        if not is_repo:
            all_valid = False

        if is_repo:
            # Check 2: Branch naming
            branch = self._enforcer.get_current_branch(path)
            branch_result = self._enforcer.validate_branch_name(branch)
            c2 = {
                "check": "branch_naming",
                "valid": branch_result["valid"],
                "message": branch_result["message"],
                "branch": branch,
            }
            checks.append(c2)
            print(
                "{} Branch Naming: {}".format(
                    "[OK]" if branch_result["valid"] else "[WARN]",
                    branch_result["message"],
                )
            )
            if not branch_result["valid"]:
                all_valid = False

            # Check 3: Commit triggers (informational)
            trigger_result = self._detector.check_commit_triggers(path)
            gs = trigger_result.get("git_status", {})
            c3 = {
                "check": "commit_triggers",
                "valid": True,
                "should_commit": trigger_result["should_commit"],
                "trigger_count": trigger_result["trigger_count"],
                "triggers_met": trigger_result["triggers_met"],
                "git_status": gs,
                "message": (
                    "{} trigger(s) met".format(trigger_result["trigger_count"])
                    if trigger_result["should_commit"]
                    else "No commit triggers active"
                ),
            }
            checks.append(c3)
            print("[INFO] Commit Triggers: {}".format(c3["message"]))
            if gs:
                print(
                    "       Staged={}, Modified={}, Untracked={}".format(
                        gs.get("staged_count", 0),
                        gs.get("modified_count", 0),
                        gs.get("untracked_count", 0),
                    )
                )

            # Check 4: Sample commit message validation
            if trigger_result["should_commit"]:
                sample_msg = self._ai.generate_message_for_path(path)
                if sample_msg:
                    msg_check = self._enforcer.validate_commit_message(sample_msg)
                    c4 = {
                        "check": "commit_message_format",
                        "valid": msg_check["valid"],
                        "message": msg_check["message"],
                        "sample_message": sample_msg.splitlines()[0],
                    }
                    checks.append(c4)
                    print(
                        "{} Message Format: {}".format(
                            "[OK]" if msg_check["valid"] else "[WARN]",
                            msg_check["message"],
                        )
                    )
                    if not msg_check["valid"]:
                        all_valid = False

        _write_policy_log(
            "git-auto-commit-policy",
            "validate",
            "path={}, valid={}".format(path, all_valid),
        )

        print("\nOverall: {}".format("VALID" if all_valid else "ISSUES FOUND"))
        print("=" * 70 + "\n")

        return {"valid": all_valid, "checks": checks, "path": path}

    # ------------------------------------------------------------------
    # Policy interface: report
    # ------------------------------------------------------------------

    def report(self, project_dir=None):
        """Generate a commit statistics and policy status report.

        Reads from the commit log and policy-hits.log to produce a summary
        of recent commit activity, success rates, and policy enforcement events.

        Args:
            project_dir: Optional path (unused, kept for API consistency).

        Returns:
            dict: Keys: total_commits, successful_commits, failed_commits,
                  dry_runs, enforcement_events, last_commit_ts (str or None),
                  workspace_repos (int), repos_with_changes (int).
        """
        print("\n" + "=" * 70)
        print("GIT AUTO-COMMIT POLICY - STATISTICS REPORT")
        print("=" * 70 + "\n")
        print("Workspace: {}".format(self.workspace_path))
        print("Report generated: {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        # Parse commit log
        total_commits = 0
        successful = 0
        failed = 0
        dry_runs = 0
        last_ts = None

        if COMMIT_LOG.exists():
            try:
                with open(COMMIT_LOG, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        total_commits += 1
                        if entry.get("dry_run"):
                            dry_runs += 1
                        elif entry.get("success"):
                            successful += 1
                        else:
                            failed += 1
                        ts = entry.get("timestamp")
                        if ts and (last_ts is None or ts > last_ts):
                            last_ts = ts
            except OSError as exc:
                _logger.warning("Could not read commit log: %s", exc)

        # Count policy enforcement events
        enforcement_events = 0
        if POLICY_HIT_LOG.exists():
            try:
                with open(POLICY_HIT_LOG, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if "auto-commit" in line or "git-auto-commit" in line:
                            enforcement_events += 1
            except OSError:
                pass

        # Workspace repo discovery and status
        repos = self._detector.find_git_repos_in_workspace(self.workspace_path)
        repos_with_changes = 0

        print("Repositories in workspace: {}".format(len(repos)))
        for rp in repos:
            gs = self._detector.get_full_git_status(rp)
            if gs and (gs["staged_count"] > 0 or gs["modified_count"] > 0):
                repos_with_changes += 1
                print(
                    "   [CHANGES] {}: staged={}, modified={}, untracked={}".format(
                        Path(rp).name,
                        gs["staged_count"],
                        gs["modified_count"],
                        gs["untracked_count"],
                    )
                )

        print("\nCommit Log Statistics (all time):")
        print("   Total recorded commits:  {}".format(total_commits))
        print("   Successful commits:      {}".format(successful))
        print("   Failed commits:          {}".format(failed))
        print("   Dry runs:                {}".format(dry_runs))
        print("   Last commit recorded:    {}".format(last_ts or "N/A"))
        print("\nPolicy Enforcement Events: {}".format(enforcement_events))
        print("Repos with pending changes: {}/{}".format(repos_with_changes, len(repos)))

        _write_policy_log(
            "git-auto-commit-policy",
            "report-generated",
            "total_commits={}".format(total_commits),
        )

        print("\n" + "=" * 70 + "\n")

        return {
            "total_commits": total_commits,
            "successful_commits": successful,
            "failed_commits": failed,
            "dry_runs": dry_runs,
            "enforcement_events": enforcement_events,
            "last_commit_ts": last_ts,
            "workspace_repos": len(repos),
            "repos_with_changes": repos_with_changes,
        }

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def detect(self, project_dir=None):
        """Run trigger detection for *project_dir* and print the report.

        Args:
            project_dir: Repository path. Defaults to cwd.

        Returns:
            dict: Trigger detection result from check_commit_triggers().
        """
        path = project_dir or os.getcwd()
        result = self._detector.check_commit_triggers(path)
        self._detector.print_detection_report(result)
        return result

    def commit(
        self,
        project_dir=None,
        context=None,
        push=False,
        dry_run=False,
        auto_find=False,
    ):
        """Execute a commit for the given repository.

        When *auto_find* is True and *project_dir* is not a git repo,
        searches the workspace for repositories and commits them all.

        Args:
            project_dir: Repository path. Defaults to cwd.
            context:     Optional context for commit message generation.
            push:        Push after committing.
            dry_run:     Stage/generate without committing.
            auto_find:   Search workspace when cwd is not a git repo.

        Returns:
            dict: Commit result.
        """
        path = project_dir or os.getcwd()

        if not _is_git_repo(path):
            if auto_find:
                result = self._engine.commit_workspace(
                    workspace_path=self.workspace_path,
                    context=context,
                    push=push,
                    dry_run=dry_run,
                    require_triggers=False,
                )
            else:
                result = {
                    "success": False,
                    "error": "Not a git repository",
                    "suggestion": "Use --auto-find to search workspace, or cd to a git repo",
                }
        else:
            result = self._engine.commit_single_repo(
                path=path,
                context=context,
                push=push,
                dry_run=dry_run,
                require_triggers=False,
            )

        self._engine.print_commit_result(result)
        return result

    def generate_ai_message(self, project_dir=None, context=None):
        """Generate and print an AI commit message for the repository.

        Args:
            project_dir: Repository path. Defaults to cwd.
            context:     Optional context string.

        Returns:
            str: Generated commit message string, or None if no changes.
        """
        path = project_dir or os.getcwd()
        msg = self._ai.generate_message_for_path(path, context=context)
        print("\n" + "=" * 70)
        print("AI-Generated Commit Message")
        print("=" * 70 + "\n")
        if msg:
            print(msg)
        else:
            print("No changes detected - cannot generate commit message")
        print("\n" + "=" * 70 + "\n")
        return msg


# ===========================================================================
# Module-level backwards-compatible functions
# (Preserves the original git-auto-commit-policy.py function API)
# ===========================================================================

def run_git_command(args, timeout=30, cwd=None):
    """Run a git command and return the result.

    Backwards-compatible wrapper around _run_git.

    Args:
        args:    List of git sub-command arguments.
        timeout: Timeout in seconds.
        cwd:     Working directory.

    Returns:
        subprocess.CompletedProcess or error object with returncode/stdout/stderr.
    """
    return _run_git(args, cwd=cwd, timeout=timeout)


def log_policy_hit(action, context=""):
    """Log a policy hit entry to the central policy log.

    Args:
        action:  Short action label.
        context: Free-form context string.
    """
    _write_policy_log("git-auto-commit-policy", action, context)


def check_git_repo(project_dir):
    """Check if directory is a git repo.

    Args:
        project_dir: Directory path to check.

    Returns:
        bool: True if it is a git repository.
    """
    return _is_git_repo(project_dir)


def get_git_status(project_dir):
    """Get porcelain git status of a repo.

    Args:
        project_dir: Git repository root path.

    Returns:
        str: Status output, or None on failure.
    """
    result = _run_git(["status", "--porcelain"], cwd=project_dir, timeout=5)
    return result.stdout.strip() if result.returncode == 0 else None


def check_commit_triggers(project_dir):
    """Check if any commit triggers are met for *project_dir*.

    Returns a simple dict for backwards compatibility with the old script.

    Args:
        project_dir: Git repository root path.

    Returns:
        dict: Keys: has_changes (bool), milestone_detected (bool),
              phase_completion (bool), todo_completion (bool).
    """
    detector = AutoCommitDetector()
    full_result = detector.check_commit_triggers(project_dir)
    gs = full_result.get("git_status", {})
    return {
        "has_changes": bool(gs.get("staged_count", 0) or gs.get("modified_count", 0)),
        "milestone_detected": "milestone_signals" in full_result.get("triggers_met", []),
        "phase_completion": "phase_completion" in full_result.get("triggers_met", []),
        "todo_completion": "todo_completion" in full_result.get("triggers_met", []),
    }


def generate_commit_message(project_dir, git_status_raw):
    """Generate a smart commit message.

    Args:
        project_dir:    Git repository root path.
        git_status_raw: Raw porcelain git status string.

    Returns:
        str: Generated commit message.
    """
    ai = GitAutoCommitAI()
    changes = ai.parse_status(git_status_raw or "")
    return ai.generate_commit_message(changes)


def stage_files(project_dir, git_status_raw):
    """Stage all changed files.

    Args:
        project_dir:    Git repository root path.
        git_status_raw: Raw git status (unused, kept for API compat).

    Returns:
        bool: True if staging succeeded.
    """
    result = _run_git(["add", "-A"], cwd=project_dir, timeout=10)
    return result.returncode == 0


def create_commit(project_dir, message, dry_run=False):
    """Create a git commit.

    Args:
        project_dir: Git repository root path.
        message:     Commit message string.
        dry_run:     If True, print message without committing.

    Returns:
        bool: True on success.
    """
    if dry_run:
        log_policy_hit("DRY_RUN_COMMIT", "Would commit: {}".format(message[:50]))
        return True
    result = _run_git(["commit", "-m", message], cwd=project_dir, timeout=10)
    return result.returncode == 0


def push_changes(project_dir, dry_run=False):
    """Push changes to remote.

    Args:
        project_dir: Git repository root path.
        dry_run:     If True, skip the actual push.

    Returns:
        bool: True on success.
    """
    if dry_run:
        log_policy_hit("DRY_RUN_PUSH", "Would push to remote")
        return True
    result = _run_git(["push"], cwd=project_dir, timeout=30)
    return result.returncode == 0


def find_git_repos_with_changes():
    """Find all git repos in workspace with uncommitted changes.

    Returns:
        list: Repository path strings with uncommitted changes.
    """
    enforcer = AutoCommitEnforcer()
    return enforcer.find_git_repos_with_changes()


def trigger_commit_for_repo(repo_path, push=False, dry_run=False):
    """Trigger commit for a specific repo.

    Args:
        repo_path: Absolute path to the git repository.
        push:      Whether to push after committing.
        dry_run:   Whether to skip the actual commit.

    Returns:
        bool: True on success.
    """
    enforcer = AutoCommitEnforcer()
    return enforcer.trigger_commit_for_repo(repo_path, push=push, dry_run=dry_run)


def enforce_auto_commit(push=False, dry_run=False):
    """Enforce auto-commit policy across all repos.

    Args:
        push:    Whether to push after committing each repo.
        dry_run: Whether to skip actual commits.

    Returns:
        dict: Keys: total (int), committed (int), failed (int).
    """
    enforcer = AutoCommitEnforcer()
    result = enforcer.enforce_auto_commit(dry_run=dry_run)
    return {
        "total": result.get("total", 0),
        "committed": result.get("processed", 0),
        "failed": result.get("total", 0) - result.get("processed", 0),
    }


def validate():
    """Validate git auto-commit policy compliance (module-level function).

    Returns:
        bool: True if git is available and policy is valid.
    """
    try:
        log_policy_hit("VALIDATE", "git-auto-commit-ready")
        result = run_git_command(["--version"])
        if result.returncode != 0:
            return False
        log_policy_hit("VALIDATE_SUCCESS", "git-auto-commit-validated")
        return True
    except Exception as exc:
        log_policy_hit("VALIDATE_ERROR", str(exc))
        return False


def report():
    """Generate compliance report (module-level function).

    Returns:
        dict: Report dict with status and metrics.
    """
    try:
        policy = GitAutoCommitPolicy()
        metrics = policy.report()
        return {
            "status": "success",
            "policy": "git-auto-commit",
            "repos_checked": metrics.get("workspace_repos", 0),
            "commits_ready": metrics.get("repos_with_changes", 0),
            "total_commits": metrics.get("total_commits", 0),
            "successful_commits": metrics.get("successful_commits", 0),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def enforce():
    """Main policy enforcement function (module-level, backwards-compatible).

    Consolidates logic from 5 source scripts:
      - auto-commit.py:          Commit execution
      - auto-commit-enforcer.py: Policy enforcement
      - auto-commit-detector.py: Trigger detection
      - trigger-auto-commit.py:  Trigger management
      - git-auto-commit-ai.py:   Message generation

    Returns:
        dict: Status and results dict.
    """
    _track_start_time = datetime.now()
    _sub_operations = []
    try:
        log_policy_hit("ENFORCE_START", "git-auto-commit-enforcement")

        _op_start = datetime.now()
        results = enforce_auto_commit(push=False, dry_run=False)
        try:
            _sub_operations.append(record_sub_operation(
                "run_auto_commit", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"committed": results.get("committed", 0), "failed": results.get("failed", 0)}
            ))
        except Exception:
            pass

        log_policy_hit(
            "ENFORCE_COMPLETE",
            "Commits: {}, Failed: {}".format(results["committed"], results["failed"]),
        )
        print(
            "[git-auto-commit-policy] Policy enforced - {} commits created".format(
                results["committed"]
            )
        )
        result = {"status": "success", "results": results}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="git-auto-commit-policy",
                    policy_script="git-auto-commit-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results={"status": "success", "committed": results.get("committed", 0)},
                    decision=f"{results.get('committed', 0)} commits created",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return result
    except Exception as exc:
        log_policy_hit("ENFORCE_ERROR", str(exc))
        print("[git-auto-commit-policy] ERROR: {}".format(exc))
        error_result = {"status": "error", "message": str(exc)}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="git-auto-commit-policy",
                    policy_script="git-auto-commit-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results=error_result,
                    decision=f"error: {str(exc)}",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return error_result


# ===========================================================================
# CLI entry point
# ===========================================================================

def _build_cli_parser():
    """Build and return the argparse argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="git-auto-commit-policy",
        description=(
            "Unified Git Auto-Commit Policy System\n"
            "Consolidates AI message generation, trigger detection, "
            "enforcement, and commit execution."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
MODES:
  --detect        Check commit triggers for the repository
  --commit        Execute auto-commit (with optional --push / --dry-run)
  --ai-message    Generate and display an AI commit message
  --enforce       Scan workspace and enforce commits on all repos
  --enforce-now   Alias for --enforce (backwards compatibility)
  --validate      Validate git state and policy compliance
  --stats         Display commit statistics and policy report
  --report        Alias for --stats
  --check-task    Check if a task ID requires an auto-commit

EXAMPLES:
  python git-auto-commit-policy.py --detect
  python git-auto-commit-policy.py --commit --push
  python git-auto-commit-policy.py --commit --dry-run
  python git-auto-commit-policy.py --ai-message --context "fix login bug"
  python git-auto-commit-policy.py --enforce --dry-run
  python git-auto-commit-policy.py --validate
  python git-auto-commit-policy.py --stats
  python git-auto-commit-policy.py --check-task 42
""",
    )

    # Mode flags (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--detect",
        action="store_true",
        help="Check commit triggers for the repository",
    )
    mode_group.add_argument(
        "--commit",
        action="store_true",
        help="Execute auto-commit",
    )
    mode_group.add_argument(
        "--ai-message",
        action="store_true",
        help="Generate an AI commit message",
    )
    mode_group.add_argument(
        "--enforce",
        action="store_true",
        help="Enforce commits across all workspace repositories",
    )
    mode_group.add_argument(
        "--enforce-now",
        action="store_true",
        help="Alias for --enforce (backwards compatibility)",
    )
    mode_group.add_argument(
        "--validate",
        action="store_true",
        help="Validate git state and policy compliance",
    )
    mode_group.add_argument(
        "--stats",
        "--report",
        action="store_true",
        dest="stats",
        help="Display commit statistics report",
    )
    mode_group.add_argument(
        "--check-task",
        type=str,
        metavar="TASK_ID",
        help="Check whether a task requires an auto-commit",
    )

    # Shared options
    parser.add_argument(
        "--project-dir",
        "--path",
        type=str,
        default=None,
        dest="project_dir",
        help="Target git repository path (default: current directory)",
    )
    parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Context string for AI message generation",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push to remote after committing",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Do not push to remote (commit only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stage files and generate messages without creating a commit",
    )
    parser.add_argument(
        "--auto-find",
        action="store_true",
        help="Auto-discover git repositories in workspace when cwd is not a repo",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON (for --detect mode)",
    )
    parser.add_argument(
        "--event",
        type=str,
        default="policy-enforce",
        help="Event label for enforcement logging",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Override workspace root for multi-repo operations",
    )

    return parser


def main():
    """CLI entry point for git-auto-commit-policy."""
    parser = _build_cli_parser()
    args = parser.parse_args()

    policy = GitAutoCommitPolicy(workspace_path=args.workspace)
    project_dir = args.project_dir
    exit_code = 0

    # ------------------------------------------------------------------
    # Mode: --detect
    # ------------------------------------------------------------------
    if args.detect:
        path = project_dir or os.getcwd()
        result = policy._detector.check_commit_triggers(path)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            policy._detector.print_detection_report(result)
        exit_code = 0 if result["should_commit"] else 1

    # ------------------------------------------------------------------
    # Mode: --commit
    # ------------------------------------------------------------------
    elif args.commit:
        do_push = args.push and not args.no_push
        result = policy.commit(
            project_dir=project_dir,
            context=args.context,
            push=do_push,
            dry_run=args.dry_run,
            auto_find=args.auto_find,
        )
        exit_code = 0 if result.get("success") else 1

    # ------------------------------------------------------------------
    # Mode: --ai-message
    # ------------------------------------------------------------------
    elif args.ai_message:
        msg = policy.generate_ai_message(project_dir=project_dir, context=args.context)
        exit_code = 0 if msg else 1

    # ------------------------------------------------------------------
    # Mode: --enforce / --enforce-now
    # ------------------------------------------------------------------
    elif args.enforce or args.enforce_now:
        result = policy.enforce(
            project_dir=project_dir,
            push=args.push and not args.no_push,
            dry_run=args.dry_run,
            event=args.event,
        )
        exit_code = 0 if result.get("success") else 1

    # ------------------------------------------------------------------
    # Mode: --validate
    # ------------------------------------------------------------------
    elif args.validate:
        result = policy.validate(project_dir=project_dir)
        exit_code = 0 if result.get("valid") else 1

    # ------------------------------------------------------------------
    # Mode: --stats / --report
    # ------------------------------------------------------------------
    elif args.stats:
        policy.report(project_dir=project_dir)
        exit_code = 0

    # ------------------------------------------------------------------
    # Mode: --check-task
    # ------------------------------------------------------------------
    elif args.check_task:
        result = policy._enforcer.check_task_requires_commit(args.check_task)
        print(result["message"])
        exit_code = 0

    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# Legacy CLI shim (backwards compat with old if __name__ == "__main__" block)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # If called with old-style flags like --enforce, --validate, --report
    # delegate to the new full argparse main() if recognisable flags exist.
    _legacy_flags = {"--enforce", "--validate", "--report"}
    if len(sys.argv) > 1 and sys.argv[1] in _legacy_flags:
        if sys.argv[1] == "--enforce":
            _result = enforce()
            sys.exit(0 if _result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            _is_valid = validate()
            sys.exit(0 if _is_valid else 1)
        elif sys.argv[1] == "--report":
            _r = report()
            print(json.dumps(_r, indent=2))
            sys.exit(0 if _r.get("status") == "success" else 1)
    else:
        main()
