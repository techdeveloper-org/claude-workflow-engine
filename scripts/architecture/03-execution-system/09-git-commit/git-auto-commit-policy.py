#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git Auto-Commit Policy - Unified Git Automation System
=======================================================

Consolidates all git auto-commit functionality into a single comprehensive
enterprise-grade policy module covering:

  1. GitAutoCommitAI         - AI-powered semantic commit message generation
  2. AutoCommitDetector      - Detect files and triggers needing commits
  3. AutoCommitEnforcer      - Enforce commit policy requirements
  4. GitAutoCommitEngine     - Core auto-commit orchestration engine
  5. GitAutoCommitPolicy     - Unified policy interface (enforce/validate/report)
  6. TriggerAutoCommit       - Trigger commit automation on lifecycle events

USAGE (CLI):
  python git-auto-commit-policy.py --detect
  python git-auto-commit-policy.py --commit [--push] [--dry-run]
  python git-auto-commit-policy.py --ai-message [--context "task context"]
  python git-auto-commit-policy.py --enforce [--enforce-now]
  python git-auto-commit-policy.py --trigger [--event EVENT]
  python git-auto-commit-policy.py --stats
  python git-auto-commit-policy.py --validate
  python git-auto-commit-policy.py --report

PROGRAMMATIC:
  from git_auto_commit_policy import GitAutoCommitPolicy
  policy = GitAutoCommitPolicy()
  policy.enforce()
  policy.validate()
  policy.report()

CONSOLIDATED SOURCES:
  - git-auto-commit-ai.py     (AI-powered message generation)
  - auto-commit.py            (Core auto-commit engine)
  - auto-commit-detector.py   (Detect files needing commits)
  - auto-commit-enforcer.py   (Enforce commit requirements)
  - trigger-auto-commit.py    (Trigger commit automation)

VERSION: 2.5.0 (Consolidated)
LAST_UPDATED: 2026-03-06
"""

import os
import sys
import json
import logging
import subprocess
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ===================================================================
# POLICY TRACKING INTEGRATION
# ===================================================================
# Policy tracking - mandatory (find helper by walking up to scripts root)
_scripts_root = Path(__file__).resolve().parent
while _scripts_root != _scripts_root.parent:
    if (_scripts_root / 'policy_tracking_helper.py').exists():
        if str(_scripts_root) not in sys.path:
            sys.path.insert(0, str(_scripts_root))
        break
    _scripts_root = _scripts_root.parent
from policy_tracking_helper import record_policy_execution, record_sub_operation, get_session_id

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

# Workspace discovery root (auto-detect from CWD or env var)
DEFAULT_WORKSPACE = Path(os.environ.get("CLAUDE_WORKSPACE_ROOT",
                         str(Path.cwd().parent if Path.cwd().name == "scripts" else Path.cwd())))

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


def _run_command(cmd, timeout=30, shell=False):
    """Run a system command and return the result.

    Args:
        cmd:     Command to execute (str if shell=True, list if shell=False).
        timeout: Maximum execution time in seconds.
        shell:   If True, execute command through shell.

    Returns:
        subprocess.CompletedProcess, or error stub object on failure.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
        )
    except subprocess.TimeoutExpired:
        _logger.warning("Command timed out after %ds", timeout)

        class _Timeout:
            returncode = 1
            stdout = ""
            stderr = "Timed out after {}s".format(timeout)

        return _Timeout()
    except Exception as exc:

        class _Error:
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


def _load_task_context():
    """Load actual task context from session data.

    Loads from flow-trace.json, session-progress.json, and tool-tracker.jsonl
    to get task information for intelligent commit messages.

    Returns:
        dict: Context dict with keys:
            - task_subject: Task title/name
            - task_description: Task description
            - task_type: Type of task (feat, fix, refactor, etc)
            - edits_summary: List of recently edited file paths
    """
    ctx = {
        "task_subject": "",
        "task_description": "",
        "task_type": "",
        "edits_summary": []
    }

    try:
        # 1. Get session ID from session-progress
        progress_file = LOGS_DIR / "session-progress.json"
        session_id = ""
        if progress_file.exists():
            with open(progress_file, "r", encoding="utf-8") as f:
                prog = json.load(f)
            session_id = prog.get("session_id", "")

        # 2. Get task type + complexity from flow-trace
        if session_id:
            trace_file = SESSIONS_DIR / session_id / "flow-trace.json"
            if trace_file.exists():
                with open(trace_file, "r", encoding="utf-8") as f:
                    trace = json.load(f)
                fd = trace.get("final_decision", {})
                ctx["task_type"] = fd.get("task_type", "")

        # 3. Get last task subject + edits from tool-tracker.jsonl
        tracker_file = LOGS_DIR / "tool-tracker.jsonl"
        if tracker_file.exists():
            with open(tracker_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Scan from end: find latest TaskCreate, collect recent edits
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                tool = entry.get("tool", "")
                if tool == "TaskCreate" and not ctx["task_subject"]:
                    ctx["task_subject"] = entry.get("task_subject", "")
                if tool == "Edit" and len(ctx["edits_summary"]) < 5:
                    f_path = entry.get("file", "")
                    if f_path:
                        ctx["edits_summary"].append(f_path)
                if tool == "Write" and len(ctx["edits_summary"]) < 5:
                    f_path = entry.get("file", "")
                    if f_path:
                        ctx["edits_summary"].append(f_path)

    except Exception as exc:
        _logger.debug("Could not load task context: %s", exc)

    return ctx


# ===========================================================================
# Class 1: GitAutoCommitAI - AI-powered semantic commit message generator
# ===========================================================================

class GitAutoCommitAI:
    """AI-powered semantic commit message generator.

    Analyzes the git diff and status of a repository to produce a structured,
    semantic commit message that follows conventional-commit conventions.

    Commit type precedence:
      1. Task context (session flow-trace / tool-tracker data)
      2. File-type heuristics (test files, doc files, source files)
      3. Change category (added > deleted > modified)

    Attributes:
        SOURCE_EXTENSIONS (tuple): File extensions considered source code.
        TEST_MARKERS (tuple): Markers for test files.
        DOC_EXTENSIONS (tuple): File extensions for documentation.
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
        """Analyze recent commits to match style.

        Examines the last 10 commits to detect:
          - Type prefix style (feat:, fix:, etc.)
          - Emoji usage
          - Average line length

        Args:
            path: Git repository root path.

        Returns:
            dict with keys:
                - type_prefix (bool): True if commits use type: prefix
                - emoji (bool): True if commits contain emoji
                - length (str): 'short', 'medium', or 'long'
            Or None if analysis fails.
        """
        result = _run_git(["log", "-10", "--pretty=format:%s"], cwd=path, timeout=5)

        if result.returncode == 0 and result.stdout.strip():
            messages = result.stdout.strip().split("\n")

            # Detect style patterns
            has_type_prefix = any(":" in msg[:20] for msg in messages)
            has_emoji = any(any(ord(c) > 127 for c in msg[:10]) for msg in messages)
            avg_length = sum(len(msg) for msg in messages) / len(messages)

            return {
                "type_prefix": has_type_prefix,
                "emoji": has_emoji,
                "length": (
                    "short"
                    if avg_length < 50
                    else "medium"
                    if avg_length < 80
                    else "long"
                ),
            }

        return None

    # ------------------------------------------------------------------
    # Analysis and generation
    # ------------------------------------------------------------------

    def analyze_changes(self, status, diff=None):
        """Analyze git status to categorize changes.

        Args:
            status: Output from `git status --porcelain`.
            diff:   Optional output from `git diff --stat`.

        Returns:
            dict with keys:
                - added: List of added file paths
                - modified: List of modified file paths
                - deleted: List of deleted file paths
                - renamed: List of renamed file paths
        """
        if not status:
            return None

        changes = {
            "added": [],
            "modified": [],
            "deleted": [],
            "renamed": [],
        }

        # Parse porcelain status
        for line in status.split("\n"):
            if not line:
                continue

            status_code = line[0:2].strip()
            filename = line[3:].strip()

            if status_code in ["A", "??"]:
                changes["added"].append(filename)
            elif status_code == "M":
                changes["modified"].append(filename)
            elif status_code == "D":
                changes["deleted"].append(filename)
            elif status_code == "R":
                changes["renamed"].append(filename)

        return changes

    def _llm_classify_commit(self, changes, context=None):
        """Use local LLM to classify commit type from changes and context.

        Calls Ollama (qwen2.5:7b or best available) to analyze the actual
        changes and determine the semantic commit type intelligently.

        Args:
            changes: Dict with added/modified/deleted/renamed file lists.
            context: Optional task context string.

        Returns:
            str or None: Commit type from LLM, or None if LLM unavailable.
        """
        try:
            from urllib import request as _urllib_request
            import json as _json

            # Build a concise summary of changes for the LLM
            parts = []
            if changes.get('added'):
                parts.append(f"Added: {', '.join(changes['added'][:10])}")
            if changes.get('modified'):
                parts.append(f"Modified: {', '.join(changes['modified'][:10])}")
            if changes.get('deleted'):
                parts.append(f"Deleted: {', '.join(changes['deleted'][:10])}")
            if changes.get('renamed'):
                parts.append(f"Renamed: {', '.join(changes['renamed'][:5])}")
            if context:
                parts.append(f"Context: {context[:200]}")

            if not parts:
                return None

            prompt = (
                "Classify this git commit. Return ONLY a JSON object: "
                "{\"type\":\"string\",\"reason\":\"string\"}\n"
                "type MUST be one of: feat, fix, refactor, docs, test, chore, style, perf\n"
                "Rules:\n"
                "- feat: new functionality, new files with business logic\n"
                "- fix: bug fixes, error corrections, broken behavior repair\n"
                "- refactor: restructuring without behavior change, cleanup, deletions\n"
                "- docs: documentation, README, comments only\n"
                "- test: test files added/modified\n"
                "- chore: config, dependencies, build, CI/CD\n"
                "- style: formatting, whitespace, linting\n"
                "- perf: performance improvements\n\n"
                "Changes:\n" + "\n".join(parts)
            )

            # Auto-detect Ollama model
            model = 'qwen2.5:7b'
            try:
                req = _urllib_request.Request('http://127.0.0.1:11434/api/tags')
                with _urllib_request.urlopen(req, timeout=2) as resp:
                    data = _json.loads(resp.read().decode('utf-8'))
                    installed = [m['name'] for m in data.get('models', [])]
                    for preferred in ['qwen3:4b', 'qwen2.5:7b', 'qwen2.5:3b', 'granite4:3b']:
                        if preferred in installed:
                            model = preferred
                            break
            except Exception:
                pass

            payload = _json.dumps({
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'You classify git commits. Return ONLY valid JSON.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 100,
                'temperature': 0.1,
                'response_format': {'type': 'json_object'},
            }).encode('utf-8')

            req = _urllib_request.Request(
                'http://127.0.0.1:11434/v1/chat/completions',
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with _urllib_request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read().decode('utf-8'))
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                parsed = _json.loads(content)
                commit_type = parsed.get('type', '').lower().strip()
                valid_types = ('feat', 'fix', 'refactor', 'docs', 'test', 'chore', 'style', 'perf')
                if commit_type in valid_types:
                    return commit_type
        except Exception:
            pass
        return None

    def determine_commit_type(self, changes, context=None):
        """Determine semantic commit type from changes and context.

        Uses LLM classification first (via local Ollama), falls back to
        heuristic-based detection if LLM is unavailable.

        Args:
            changes: Dict from analyze_changes().
            context: Optional task context string.

        Returns:
            str: One of 'feat', 'fix', 'refactor', 'docs', 'test', 'chore', 'style', 'perf'.
        """
        if not changes:
            return "chore"

        # Try LLM classification first (more accurate)
        llm_type = self._llm_classify_commit(changes, context)
        if llm_type:
            return llm_type

        # Fallback: heuristic-based classification
        # Check for new features (new files with source extension)
        if changes.get("added"):
            source_files = [
                f for f in changes["added"]
                if f.endswith(self.SOURCE_EXTENSIONS)
            ]
            if source_files:
                return "feat"

        # Check for deletions/cleanup
        if changes.get("deleted"):
            return "refactor"

        # Check for modifications
        if changes.get("modified"):
            # Check context for clues
            if context:
                context_lower = context.lower()
                if any(w in context_lower for w in ["fix", "bug", "error", "broken"]):
                    return "fix"
                elif "test" in context_lower:
                    return "test"
                elif any(w in context_lower for w in ["doc", "readme", "documentation"]):
                    return "docs"
                elif "refactor" in context_lower:
                    return "refactor"

            # Check file types
            test_files = [f for f in changes["modified"] if any(m in f.lower() for m in self.TEST_MARKERS)]
            if test_files:
                return "test"

            doc_files = [f for f in changes["modified"] if f.endswith(self.DOC_EXTENSIONS)]
            if doc_files:
                return "docs"

        return "chore"

    def _describe_files(self, file_list, max_names=3):
        """Build a readable description of changed files.

        Args:
            file_list: List of file paths.
            max_names: Max number of file names to include.

        Returns:
            str: e.g. "stop-notifier, git_operations" or "3 langgraph_engine modules"
        """
        if not file_list:
            return "files"
        stems = [Path(f).stem for f in file_list]
        # If all files share a common directory, mention it
        dirs = set(str(Path(f).parent) for f in file_list)
        if len(file_list) <= max_names:
            return ", ".join(stems)
        if len(dirs) == 1:
            dirname = Path(list(dirs)[0]).name
            return f"{len(file_list)} {dirname} modules"
        return f"{len(file_list)} files"

    def generate_summary(self, changes, commit_type):
        """Generate first line of commit message with meaningful file context.

        Args:
            changes:      Dict from analyze_changes().
            commit_type:  Type from determine_commit_type().

        Returns:
            str: Summary text (first line of commit message).
        """
        if not changes:
            return "update files"

        if commit_type == "feat":
            desc = self._describe_files(changes.get("added", []))
            return f"add {desc}"

        elif commit_type == "fix":
            desc = self._describe_files(changes.get("modified", []))
            return f"fix {desc}"

        elif commit_type == "refactor":
            if changes.get("deleted"):
                desc = self._describe_files(changes.get("deleted", []))
                return f"remove {desc}"
            else:
                desc = self._describe_files(changes.get("modified", []))
                return f"refactor {desc}"

        elif commit_type == "test":
            desc = self._describe_files(
                changes.get("added", []) + changes.get("modified", [])
            )
            return f"update tests in {desc}"

        elif commit_type == "docs":
            desc = self._describe_files(
                changes.get("added", []) + changes.get("modified", [])
            )
            return f"update docs: {desc}"

        else:
            all_files = (
                changes.get("added", [])
                + changes.get("modified", [])
                + changes.get("deleted", [])
            )
            desc = self._describe_files(all_files)
            return f"update {desc}"

    def generate_details(self, changes):
        """Generate detailed description for commit body.

        Args:
            changes: Dict from analyze_changes().

        Returns:
            list: Detail lines to include in commit body.
        """
        details = []

        if changes.get("added"):
            details.append(f"Added files ({len(changes['added'])}):")
            for f in changes["added"][:5]:
                details.append(f"  - {f}")
            if len(changes["added"]) > 5:
                details.append(f"  - ... and {len(changes['added']) - 5} more")

        if changes.get("modified"):
            if details:
                details.append("")
            details.append(f"Modified files ({len(changes['modified'])}):")
            for f in changes["modified"][:5]:
                details.append(f"  - {f}")
            if len(changes["modified"]) > 5:
                details.append(f"  - ... and {len(changes['modified']) - 5} more")

        if changes.get("deleted"):
            if details:
                details.append("")
            details.append(f"Deleted files ({len(changes['deleted'])}):")
            for f in changes["deleted"][:5]:
                details.append(f"  - {f}")
            if len(changes["deleted"]) > 5:
                details.append(f"  - ... and {len(changes['deleted']) - 5} more")

        return details

    def generate_commit_message(self, changes, context=None, style=None):
        """Generate complete semantic commit message.

        Combines type, summary, and details into a structured message.

        Args:
            changes:  Dict from analyze_changes().
            context:  Optional task context for better type detection.
            style:    Optional style dict from get_recent_commit_style().

        Returns:
            str: Complete commit message with type, summary, details, and co-author tag.
        """
        if not changes:
            return "chore: update files\n\nCo-Authored-By: Claude <noreply@anthropic.com>"

        # Determine commit type
        commit_type = self.determine_commit_type(changes, context)

        # Generate summary
        summary = self.generate_summary(changes, commit_type)

        # Generate detailed description
        details = self.generate_details(changes)

        # Build message
        message_parts = []

        # First line with type prefix (if style suggests it)
        if style and style.get("type_prefix"):
            message_parts.append(f"{commit_type}: {summary}")
        else:
            message_parts.append(summary.capitalize() if summary else "Update implementation")

        # Add body if there are details
        if details:
            message_parts.append("")  # Blank line
            message_parts.extend(details)

        # Add co-author
        message_parts.append("")
        message_parts.append("Co-Authored-By: Claude <noreply@anthropic.com>")

        return "\n".join(message_parts)

    def find_git_repos(self, base_path):
        """Find all git repositories in base path.

        Useful when running from non-git directory like .claude.

        Args:
            base_path: Directory to search from.

        Returns:
            list: Paths to discovered git repositories (1-2 levels deep).
        """
        git_repos = []

        try:
            base = Path(base_path)
            if not base.exists():
                return []

            # Check immediate subdirectories (1 level deep)
            for item in base.iterdir():
                if item.is_dir():
                    # Check if it has .git
                    if (item / ".git").exists():
                        git_repos.append(str(item))

                    # Check one level deeper (for nested structure)
                    try:
                        for subitem in item.iterdir():
                            if subitem.is_dir() and (subitem / ".git").exists():
                                git_repos.append(str(subitem))
                    except Exception:
                        pass

        except Exception as exc:
            _logger.debug("Error finding git repos: %s", exc)

        return git_repos

    def log_commit(self, result):
        """Log commit operation to git-auto-commit.log.

        Args:
            result: Dict with commit operation result data.
        """
        try:
            self.logs_path.mkdir(parents=True, exist_ok=True)

            log_entry = {
                "timestamp": result.get("timestamp", datetime.now().isoformat()),
                "path": result.get("path", ""),
                "success": result.get("success", False),
                "dry_run": result.get("dry_run", False),
                "file_count": sum(
                    len(v) for v in result.get("changes", {}).values()
                ),
            }

            with open(self.commit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as exc:
            _logger.warning("Could not log commit: %s", exc)

    def auto_commit(self, path=".", context=None, push=False, dry_run=False, auto_find=True):
        """Main entry point - auto commit with AI message.

        Args:
            path:      Git repo path (or base path to search).
            context:   Task context for better messages.
            push:      Auto-push after commit.
            dry_run:   Don't actually commit if True.
            auto_find: Auto-find git repos if current dir is not a repo.

        Returns:
            dict: Result with keys:
                - success (bool)
                - multi_repo (bool): True if multiple repos were committed
                - repos (list): List of individual repo results (if multi_repo)
                - error (str): Error message if unsuccessful
                - skipped (bool): True if no changes to commit
                - committed (bool): True if commit was created
                - pushed (bool): True if changes were pushed
        """
        # Check if current path is a git repo
        if not self.check_git_repo(path):
            # If auto_find enabled and we're in .claude or similar
            if auto_find and (".claude" in str(Path(path).resolve()) or path == "."):
                # Try to find git repos in workspace
                workspace_path = DEFAULT_WORKSPACE

                if workspace_path.exists():
                    git_repos = self.find_git_repos(workspace_path)

                    if git_repos:
                        # Commit to all found repos
                        results = []
                        for repo_path in git_repos:
                            result = self._commit_single_repo(repo_path, context, push, dry_run)
                            results.append(result)

                        return {
                            "success": True,
                            "multi_repo": True,
                            "repos": results,
                            "total_repos": len(git_repos),
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"No git repositories found in {workspace_path}",
                            "path": path,
                            "suggestion": "Run this script from a project directory with .git",
                        }
                else:
                    return {
                        "success": False,
                        "error": f"Workspace not found: {workspace_path}",
                        "path": path,
                        "suggestion": "Run this script from a project directory with .git",
                    }

            return {
                "success": False,
                "error": "Not a git repository",
                "path": path,
                "suggestion": "Run from git repo or use --auto-find",
            }

        # Single repo commit
        return self._commit_single_repo(path, context, push, dry_run)

    def _commit_single_repo(self, path, context, push, dry_run):
        """Commit to a single repository.

        Args:
            path:    Repository root path.
            context: Optional task context.
            push:    Whether to push after commit.
            dry_run: If True, don't actually commit.

        Returns:
            dict: Result with success, changes, commit_message, etc.
        """
        # Get status
        status = self.get_git_status(path)
        if not status:
            return {
                "success": True,
                "skipped": True,
                "reason": "No changes to commit",
                "path": path,
            }

        # Get diff
        diff = self.get_git_diff(path, staged=False)

        # Analyze changes
        changes = self.analyze_changes(status, diff)

        # Get commit message style
        style = self.get_recent_commit_style(path)

        # Generate commit message
        commit_message = self.generate_commit_message(changes, context, style)

        result = {
            "path": path,
            "changes": changes,
            "commit_message": commit_message,
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat(),
        }

        # Commit (if not dry run)
        if not dry_run:
            # Stage all changes
            try:
                _run_git(["add", "."], cwd=path, timeout=10)
            except Exception as exc:
                result["success"] = False
                result["error"] = f"Failed to stage changes: {exc}"
                return result

            # Commit
            try:
                res = _run_git(["commit", "-m", commit_message], cwd=path, timeout=10)
                if res.returncode != 0:
                    result["success"] = False
                    result["error"] = f"Commit failed: {res.stderr}"
                    return result

                result["success"] = True
                result["committed"] = True

            except Exception as exc:
                result["success"] = False
                result["error"] = f"Failed to commit: {exc}"
                return result

            # Push (if requested)
            if push:
                try:
                    res = _run_git(["push"], cwd=path, timeout=60)
                    if res.returncode == 0:
                        result["pushed"] = True
                    else:
                        result["push_error"] = res.stderr

                except Exception as exc:
                    result["push_error"] = str(exc)

        else:
            result["success"] = True

        # Log commit
        self.log_commit(result)

        return result


# ===========================================================================
# Class 2: AutoCommitDetector - Detect when to automatically commit changes
# ===========================================================================

class AutoCommitDetector:
    """Detects when to automatically commit changes.

    Monitors multiple triggers:
      1. File modifications (staged/unstaged)
      2. Time since last commit
      3. Phase completion
      4. Todo completion
      5. Milestone signals

    Attributes:
        THRESHOLDS (dict): Trigger configuration thresholds.
        MILESTONE_KEYWORDS (list): Keywords that signal completion.
    """

    def __init__(self):
        """Initialize AutoCommitDetector."""
        pass

    def check_git_repo(self, project_dir):
        """Check if directory is a git repo.

        Args:
            project_dir: Path to check.

        Returns:
            bool: True if valid git repository.
        """
        return _is_git_repo(project_dir)

    def get_git_status(self, project_dir):
        """Get git status - staged files, modified files, etc.

        Args:
            project_dir: Git repository root path.

        Returns:
            dict with keys:
                - staged: List of staged file paths
                - modified: List of modified (unstaged) file paths
                - untracked: List of untracked file paths
                - staged_count: Number of staged files
                - modified_count: Number of modified files
                - untracked_count: Number of untracked files
            Or None on failure.
        """
        try:
            # Get staged files
            result = _run_git(["diff", "--cached", "--name-only"], cwd=project_dir)
            staged_files = (
                [f for f in result.stdout.strip().split("\n") if f]
                if result.returncode == 0
                else []
            )

            # Get modified but not staged
            result = _run_git(["diff", "--name-only"], cwd=project_dir)
            modified_files = (
                [f for f in result.stdout.strip().split("\n") if f]
                if result.returncode == 0
                else []
            )

            # Get untracked files
            result = _run_git(
                ["ls-files", "--others", "--exclude-standard"], cwd=project_dir
            )
            untracked_files = (
                [f for f in result.stdout.strip().split("\n") if f]
                if result.returncode == 0
                else []
            )

            return {
                "staged": staged_files,
                "modified": modified_files,
                "untracked": untracked_files,
                "staged_count": len(staged_files),
                "modified_count": len(modified_files),
                "untracked_count": len(untracked_files),
            }

        except Exception as exc:
            _logger.warning("Could not get git status: %s", exc)
            return None

    def get_last_commit_time(self, project_dir):
        """Get time of last commit.

        Args:
            project_dir: Git repository root path.

        Returns:
            datetime: Timestamp of last commit, or None if not available.
        """
        try:
            result = _run_git(["log", "-1", "--format=%ct"], cwd=project_dir)

            if result.returncode == 0 and result.stdout.strip():
                timestamp = int(result.stdout.strip())
                return datetime.fromtimestamp(timestamp)
            else:
                return None

        except Exception as exc:
            _logger.debug("Could not get last commit time: %s", exc)
            return None

    def detect_milestone_signals(self):
        """Detect milestone completion signals from logs.

        Scans recent policy-hits.log entries for milestone keywords.

        Returns:
            list: Unique milestone keywords found in recent logs.
        """
        log_file = POLICY_HIT_LOG

        if not log_file.exists():
            return []

        signals = []
        cutoff_time = datetime.now() - timedelta(minutes=15)

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

                for line in lines[-100:]:
                    try:
                        if line.startswith("["):
                            timestamp_str = line[1:20]
                            timestamp = datetime.strptime(
                                timestamp_str, "%Y-%m-%d %H:%M:%S"
                            )

                            if timestamp > cutoff_time:
                                line_lower = line.lower()
                                for keyword in MILESTONE_KEYWORDS:
                                    if keyword in line_lower:
                                        signals.append(keyword)
                                        break

                    except Exception:
                        continue

        except Exception as exc:
            _logger.debug("Could not detect signals: %s", exc)

        return list(set(signals))

    def detect_phase_completion(self):
        """Detect phase completion from logs.

        Returns:
            bool: True if phase completion detected in recent logs.
        """
        log_file = POLICY_HIT_LOG

        if not log_file.exists():
            return False

        cutoff_time = datetime.now() - timedelta(minutes=15)

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

                for line in lines[-50:]:
                    try:
                        if line.startswith("["):
                            timestamp_str = line[1:20]
                            timestamp = datetime.strptime(
                                timestamp_str, "%Y-%m-%d %H:%M:%S"
                            )

                            if timestamp > cutoff_time:
                                if "phase-complete" in line.lower() or "phase completed" in line.lower():
                                    return True

                    except Exception:
                        continue

        except Exception:
            pass

        return False

    def detect_todo_completion(self):
        """Detect todo completion from logs.

        Returns:
            bool: True if todo completion detected in recent logs.
        """
        log_file = POLICY_HIT_LOG

        if not log_file.exists():
            return False

        cutoff_time = datetime.now() - timedelta(minutes=15)

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

                for line in lines[-50:]:
                    try:
                        if line.startswith("["):
                            timestamp_str = line[1:20]
                            timestamp = datetime.strptime(
                                timestamp_str, "%Y-%m-%d %H:%M:%S"
                            )

                            if timestamp > cutoff_time:
                                if "todo-complete" in line.lower() or "task completed" in line.lower():
                                    return True

                    except Exception:
                        continue

        except Exception:
            pass

        return False

    def check_commit_triggers(self, project_dir):
        """Check all commit triggers.

        Args:
            project_dir: Git repository root path.

        Returns:
            dict with keys:
                - should_commit (bool): True if any trigger met
                - triggers_met (list): Names of triggers that fired
                - trigger_count (int): Number of triggers met
                - details (dict): Details for each trigger
                - git_status (dict): Git status info
                - reason (str): Reason if should_commit is False
        """
        triggers_met = []
        trigger_details = {}

        # Check if git repo
        if not self.check_git_repo(project_dir):
            return {
                "should_commit": False,
                "reason": "Not a git repository",
                "triggers_met": [],
                "trigger_count": 0,
                "details": {},
            }

        # Get git status
        git_status = self.get_git_status(project_dir)

        if not git_status:
            return {
                "should_commit": False,
                "reason": "Could not get git status",
                "triggers_met": [],
                "trigger_count": 0,
                "details": {},
            }

        # No changes to commit
        if git_status["staged_count"] == 0 and git_status["modified_count"] == 0:
            return {
                "should_commit": False,
                "reason": "No changes to commit",
                "triggers_met": [],
                "trigger_count": 0,
                "details": {},
                "git_status": git_status,
            }

        # 1a. Modified files threshold (unstaged changes)
        if git_status["modified_count"] >= THRESHOLDS["modified_files"]:
            triggers_met.append("modified_files")
            trigger_details["modified_files"] = {
                "count": git_status["modified_count"],
                "threshold": THRESHOLDS["modified_files"],
                "reason": f"{git_status['modified_count']} modified files",
            }

        # 1b. Staged files threshold
        if git_status["staged_count"] >= THRESHOLDS["staged_files"]:
            triggers_met.append("staged_files")
            trigger_details["staged_files"] = {
                "count": git_status["staged_count"],
                "threshold": THRESHOLDS["staged_files"],
                "reason": f"{git_status['staged_count']} files staged",
            }

        # 2. Time since last commit
        last_commit = self.get_last_commit_time(project_dir)
        if last_commit:
            time_diff = (datetime.now() - last_commit).total_seconds() / 60

            if time_diff >= THRESHOLDS["time_since_last_commit_min"]:
                triggers_met.append("time_since_commit")
                trigger_details["time_since_commit"] = {
                    "minutes": round(time_diff, 1),
                    "threshold": THRESHOLDS["time_since_last_commit_min"],
                    "reason": f"{time_diff:.1f} minutes since last commit",
                }

        # 3. Phase completion
        if THRESHOLDS["phase_completion"] and self.detect_phase_completion():
            triggers_met.append("phase_completion")
            trigger_details["phase_completion"] = {
                "reason": "Phase completion detected"
            }

        # 4. Todo completion
        if THRESHOLDS["todo_completion"] and self.detect_todo_completion():
            triggers_met.append("todo_completion")
            trigger_details["todo_completion"] = {
                "reason": "Todo completion detected"
            }

        # 5. Milestone signals
        milestone_signals = self.detect_milestone_signals()
        if milestone_signals:
            triggers_met.append("milestone_signals")
            trigger_details["milestone_signals"] = {
                "signals": milestone_signals,
                "reason": f"Milestone signals: {', '.join(milestone_signals)}",
            }

        return {
            "should_commit": len(triggers_met) > 0,
            "triggers_met": triggers_met,
            "trigger_count": len(triggers_met),
            "details": trigger_details,
            "git_status": git_status,
            "project_dir": project_dir,
            "timestamp": datetime.now().isoformat(),
        }


# ===========================================================================
# Class 3: AutoCommitEnforcer - Enforce commit policy requirements
# ===========================================================================

class AutoCommitEnforcer:
    """Enforces auto-commit policy requirements.

    Finds git repositories with uncommitted changes and triggers
    the commit automation for each.

    Attributes:
        None
    """

    def __init__(self):
        """Initialize AutoCommitEnforcer."""
        pass

    def find_git_repos_with_changes(self, workspace_dir=None):
        """Find all git repos in workspace with uncommitted changes.

        Args:
            workspace_dir: Base directory to search. Defaults to DEFAULT_WORKSPACE.

        Returns:
            list: Paths to git repositories with changes.
        """
        repos_with_changes = []

        # Detect workspace from environment or default
        workspace = workspace_dir or os.environ.get(
            "CLAUDE_WORKSPACE_DIR", str(DEFAULT_WORKSPACE)
        )

        if not os.path.exists(workspace):
            return repos_with_changes

        # Walk through workspace
        for root, dirs, files in os.walk(workspace):
            # Skip .git internals
            if ".git" in root.split(os.sep):
                continue

            # Check if this is a git repo
            if ".git" in dirs:
                try:
                    # Check git status
                    result = _run_git(["status", "--porcelain"], cwd=root)

                    if result.returncode == 0 and result.stdout.strip():
                        repos_with_changes.append(root)

                except Exception:
                    pass

        return repos_with_changes

    def trigger_commit_for_repo(self, repo_path, engine):
        """Trigger auto-commit for a specific repo.

        Args:
            repo_path: Path to git repository.
            engine:    GitAutoCommitEngine instance for committing.

        Returns:
            bool: True if successful or skipped, False on error.
        """
        _logger.info(f"Processing repository: {os.path.basename(repo_path)}")

        try:
            # Run auto-commit
            result = engine.auto_commit(repo_path, push=True)

            if result.get("success"):
                _write_policy_log(
                    "auto-commit-enforcer",
                    "commit-triggered",
                    f"repo={os.path.basename(repo_path)}",
                )
                return True
            else:
                error = result.get("error", "Unknown error")
                _write_policy_log(
                    "auto-commit-enforcer",
                    "commit-failed",
                    f"repo={os.path.basename(repo_path)}, error={error}",
                )
                return False

        except Exception as exc:
            _write_policy_log(
                "auto-commit-enforcer",
                "commit-error",
                f"repo={os.path.basename(repo_path)}, error={str(exc)}",
            )
            return False

    def enforce_auto_commit(self, workspace_dir=None, engine=None):
        """Enforce auto-commit on all repos with changes.

        Args:
            workspace_dir: Base directory to search for repos.
            engine:        GitAutoCommitEngine instance. Creates if None.

        Returns:
            bool: True if enforcement successful or no changes found.
        """
        if engine is None:
            engine = GitAutoCommitEngine()

        _logger.info("Starting auto-commit enforcement scan")

        # Find repos with changes
        repos = self.find_git_repos_with_changes(workspace_dir)

        if not repos:
            _logger.info("No repositories with changes found")
            _write_policy_log("auto-commit-enforcer", "no-changes", "scan-complete")
            return True

        _logger.info(f"Found {len(repos)} repository(ies) with changes")

        # Trigger commit for each repo
        success_count = 0
        for repo in repos:
            if self.trigger_commit_for_repo(repo, engine):
                success_count += 1

        _logger.info(f"Processed {success_count}/{len(repos)} repositories")

        return True  # Always return True - enforcement is best-effort


# ===========================================================================
# Class 4: GitAutoCommitEngine - Core auto-commit orchestration
# ===========================================================================

class GitAutoCommitEngine:
    """Core auto-commit orchestration engine.

    Orchestrates detection, message generation, staging, and commit creation.

    Attributes:
        detector: AutoCommitDetector instance.
        ai:       GitAutoCommitAI instance.
    """

    def __init__(self):
        """Initialize GitAutoCommitEngine with detector and AI components."""
        self.detector = AutoCommitDetector()
        self.ai = GitAutoCommitAI()

    def auto_commit(self, project_dir, push=False, dry_run=False):
        """Execute auto-commit process.

        Args:
            project_dir: Git repository root path.
            push:        If True, push after commit.
            dry_run:     If True, don't actually commit.

        Returns:
            dict with keys:
                - success (bool)
                - reason (str): Description of result
                - committed (bool): True if commit was created
                - pushed (bool): True if changes were pushed
        """
        _logger.info(f"Starting auto-commit for {project_dir}")

        # Check if git repo
        if not self.detector.check_git_repo(project_dir):
            _logger.error("Not a git repository")
            return {"success": False, "reason": "Not a git repository"}

        # Check triggers
        detection = self.detector.check_commit_triggers(project_dir)

        if not detection.get("should_commit"):
            _logger.info("No commit triggers met")
            return {"success": True, "reason": "No triggers met"}

        _logger.info(f"{detection['trigger_count']} triggers met")

        # Get task context for better commit message
        context_task = _load_task_context()
        task_context = context_task.get("task_subject", "")

        # Generate and commit
        result = self.ai.auto_commit(
            project_dir, context=task_context, push=push, dry_run=dry_run
        )

        if not dry_run and result.get("success"):
            _write_policy_log(
                "auto-commit-engine",
                "commit-created",
                f"triggers={detection['trigger_count']}, files={detection['git_status'].get('staged_count', 0)}",
            )

        return result


# ===========================================================================
# Class 5: TriggerAutoCommit - Trigger commit automation on lifecycle events
# ===========================================================================

class TriggerAutoCommit:
    """Trigger auto-commit automation on lifecycle events.

    Responds to events like task completion, phase completion, etc.

    Attributes:
        engine: GitAutoCommitEngine instance.
    """

    def __init__(self):
        """Initialize TriggerAutoCommit with an engine."""
        self.engine = GitAutoCommitEngine()

    def find_git_root(self, start_dir, max_levels=5):
        """Find git root directory by walking up.

        Args:
            start_dir:  Starting directory.
            max_levels: Maximum parent levels to traverse.

        Returns:
            str: Path to git root, or None if not found.
        """
        return _find_git_root(start_dir, max_levels)

    def trigger_auto_commit(self, project_dir, event="manual", push=True):
        """Trigger auto-commit process.

        Args:
            project_dir: Project directory (will search for git root).
            event:       Event name that triggered this (e.g., 'task-completed').
            push:        If True, push after commit.

        Returns:
            bool: True if successful, False otherwise.
        """
        # Find git root
        git_root = self.find_git_root(project_dir)

        if not git_root:
            _logger.error(f"No git repository found from {project_dir}")
            _write_policy_log(
                "auto-commit-trigger",
                "no-git-repo",
                f"event={event}, dir={project_dir}",
            )
            return False

        _logger.info(f"Found git repository: {git_root}")
        _write_policy_log(
            "auto-commit-trigger",
            "triggered",
            f"event={event}, repo={os.path.basename(git_root)}",
        )

        # Run auto-commit
        try:
            result = self.engine.auto_commit(git_root, push=push, dry_run=False)

            if result.get("success"):
                _logger.info("Auto-commit successful")
                _write_policy_log(
                    "auto-commit-trigger",
                    "success",
                    f"event={event}, repo={os.path.basename(git_root)}, push={push}",
                )
                return True
            else:
                _logger.warning(f"Auto-commit failed: {result.get('reason')}")
                _write_policy_log(
                    "auto-commit-trigger",
                    "failed",
                    f"event={event}, repo={os.path.basename(git_root)}",
                )
                return False

        except Exception as exc:
            _logger.error(f"Error during auto-commit: {exc}")
            _write_policy_log(
                "auto-commit-trigger",
                "error",
                f"event={event}, error={str(exc)}",
            )
            return False


# ===========================================================================
# Class 6: GitAutoCommitPolicy - Main unified policy orchestrator
# ===========================================================================

class GitAutoCommitPolicy:
    """Unified git auto-commit policy interface.

    Orchestrates all components and provides main entry points for:
      - Detection of uncommitted changes
      - Message generation
      - Enforcement of commit policy
      - Validation and reporting

    Attributes:
        detector: AutoCommitDetector instance.
        ai:       GitAutoCommitAI instance.
        enforcer: AutoCommitEnforcer instance.
        engine:   GitAutoCommitEngine instance.
        trigger:  TriggerAutoCommit instance.
    """

    def __init__(self):
        """Initialize GitAutoCommitPolicy with all components."""
        self.detector = AutoCommitDetector()
        self.ai = GitAutoCommitAI()
        self.enforcer = AutoCommitEnforcer()
        self.engine = GitAutoCommitEngine()
        self.trigger = TriggerAutoCommit()

    def detect(self, project_dir=None):
        """Detect when to commit changes.

        Args:
            project_dir: Git repository root. Defaults to current directory.

        Returns:
            dict: Detection result with triggers_met, details, etc.
        """
        if not project_dir:
            project_dir = os.getcwd()

        return self.detector.check_commit_triggers(project_dir)

    def commit(self, project_dir=None, push=False, dry_run=False):
        """Execute auto-commit.

        Args:
            project_dir: Git repository root. Defaults to current directory.
            push:        If True, push after commit.
            dry_run:     If True, don't actually commit.

        Returns:
            dict: Commit result with success, committed, pushed, etc.
        """
        if not project_dir:
            project_dir = os.getcwd()

        return self.ai.auto_commit(project_dir, push=push, dry_run=dry_run)

    def ai_message(self, project_dir=None, context=None):
        """Generate AI commit message without committing.

        Args:
            project_dir: Git repository root. Defaults to current directory.
            context:     Optional task context for better messages.

        Returns:
            dict: Message generation result with commit_message, changes, etc.
        """
        if not project_dir:
            project_dir = os.getcwd()

        if not self.ai.check_git_repo(project_dir):
            return {"success": False, "error": "Not a git repository"}

        status = self.ai.get_git_status(project_dir)
        if not status:
            return {"success": False, "error": "Could not get git status"}

        diff = self.ai.get_git_diff(project_dir)
        changes = self.ai.analyze_changes(status, diff)
        style = self.ai.get_recent_commit_style(project_dir)

        message = self.ai.generate_commit_message(changes, context, style)

        return {
            "success": True,
            "commit_message": message,
            "changes": changes,
            "path": project_dir,
        }

    def enforce(self, workspace_dir=None):
        """Enforce auto-commit policy on all repositories.

        Args:
            workspace_dir: Base directory to search. Defaults to DEFAULT_WORKSPACE.

        Returns:
            bool: True if enforcement successful.
        """
        return self.enforcer.enforce_auto_commit(workspace_dir, self.engine)

    def trigger(self, project_dir=None, event="manual", push=True):
        """Trigger auto-commit on lifecycle event.

        Args:
            project_dir: Project directory (will search for git root).
            event:       Event name (e.g., 'task-completed', 'phase-complete').
            push:        If True, push after commit.

        Returns:
            bool: True if successful.
        """
        if not project_dir:
            project_dir = os.getcwd()

        return self.trigger.trigger_auto_commit(project_dir, event, push)

    def validate(self):
        """Validate policy configuration and environment.

        Returns:
            dict: Validation result with status, checks, errors, etc.
        """
        checks = {
            "memory_dir_exists": MEMORY_DIR.exists(),
            "logs_dir_exists": LOGS_DIR.exists(),
            "policy_log_accessible": self._check_log_accessible(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "platform": sys.platform,
        }

        errors = []
        if not checks["memory_dir_exists"]:
            errors.append(f"Memory directory not found: {MEMORY_DIR}")
        if not checks["logs_dir_exists"]:
            errors.append(f"Logs directory not found: {LOGS_DIR}")
        if not checks["policy_log_accessible"]:
            errors.append(f"Policy log not accessible: {POLICY_HIT_LOG}")

        return {
            "success": len(errors) == 0,
            "checks": checks,
            "errors": errors,
        }

    def report(self):
        """Generate policy execution report.

        Returns:
            dict: Report with statistics, recent commits, etc.
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "memory_dir": str(MEMORY_DIR),
            "logs_dir": str(LOGS_DIR),
            "commit_log": str(COMMIT_LOG),
        }

        # Count recent commits
        if COMMIT_LOG.exists():
            try:
                with open(COMMIT_LOG, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                report["total_commits_logged"] = len(lines)
                if lines:
                    report["last_commit"] = lines[-1].strip()

            except Exception as exc:
                report["commit_log_error"] = str(exc)

        # Count policy hits
        if POLICY_HIT_LOG.exists():
            try:
                with open(POLICY_HIT_LOG, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                report["total_policy_hits"] = len(lines)

            except Exception as exc:
                report["policy_log_error"] = str(exc)

        return report

    def _check_log_accessible(self):
        """Check if policy log file is accessible.

        Returns:
            bool: True if log is readable and writable.
        """
        try:
            POLICY_HIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            # Try to write a test entry
            test_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] test\n"
            with open(POLICY_HIT_LOG, "a", encoding="utf-8") as f:
                f.write(test_entry)
            # Read it back
            with open(POLICY_HIT_LOG, "r", encoding="utf-8") as f:
                _ = f.read()
            return True

        except Exception:
            return False


# ===========================================================================
# CLI Entry Point
# ===========================================================================

def main():
    """Main CLI entry point.

    Parses arguments and executes the corresponding policy operation.
    """
    parser = argparse.ArgumentParser(
        description="Git Auto-Commit Policy - Unified Git Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Detect commit triggers
  python git-auto-commit-policy.py --detect

  # Generate AI commit message
  python git-auto-commit-policy.py --ai-message --context "fix bug in parser"

  # Execute auto-commit (dry run)
  python git-auto-commit-policy.py --commit --dry-run

  # Enforce policy on all repos
  python git-auto-commit-policy.py --enforce

  # Trigger on lifecycle event
  python git-auto-commit-policy.py --trigger --event task-completed --push

  # Validate and report
  python git-auto-commit-policy.py --validate
  python git-auto-commit-policy.py --report
        """,
    )

    # Action selection
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--detect",
        action="store_true",
        help="Detect commit triggers in current or specified repo",
    )
    action_group.add_argument(
        "--commit",
        action="store_true",
        help="Execute auto-commit in current or specified repo",
    )
    action_group.add_argument(
        "--ai-message",
        action="store_true",
        help="Generate AI commit message without committing",
    )
    action_group.add_argument(
        "--enforce",
        action="store_true",
        help="Enforce auto-commit on all repos with changes",
    )
    action_group.add_argument(
        "--trigger",
        action="store_true",
        help="Trigger auto-commit on lifecycle event",
    )
    action_group.add_argument(
        "--validate",
        action="store_true",
        help="Validate policy configuration and environment",
    )
    action_group.add_argument(
        "--report",
        action="store_true",
        help="Generate policy execution report",
    )
    action_group.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics (alias for --report)",
    )

    # Options
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Git repository or project directory (default: current directory)",
    )
    parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Task context for better commit messages",
    )
    parser.add_argument(
        "--event",
        type=str,
        default="manual",
        help="Event name for trigger (e.g., task-completed, phase-complete)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push to remote after commit (for --commit and --trigger)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Do not push to remote",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - show what would happen without making changes",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (for programmatic parsing)",
    )

    args = parser.parse_args()

    # Initialize policy
    policy = GitAutoCommitPolicy()

    # Handle actions
    try:
        if args.detect:
            project_dir = args.project_dir or os.getcwd()
            result = policy.detect(project_dir)

            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                _print_detection_result(result)

            sys.exit(0 if result.get("should_commit") else 1)

        elif args.ai_message:
            project_dir = args.project_dir or os.getcwd()
            result = policy.ai_message(project_dir, args.context)

            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                _print_ai_message_result(result)

            sys.exit(0 if result.get("success") else 1)

        elif args.commit:
            project_dir = args.project_dir or os.getcwd()
            push = args.push and not args.no_push
            result = policy.commit(project_dir, push, args.dry_run)

            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                _print_commit_result(result, args.dry_run)

            sys.exit(0 if result.get("success") else 1)

        elif args.enforce:
            result = policy.enforce()

            if args.json:
                print(json.dumps({"success": result}, indent=2))
            else:
                print("[OK] Auto-commit enforcement complete" if result else "[FAIL] Enforcement failed")

            sys.exit(0 if result else 1)

        elif args.trigger:
            project_dir = args.project_dir or os.getcwd()
            push = args.push and not args.no_push
            result = policy.trigger(project_dir, args.event, push)

            if args.json:
                print(json.dumps({"success": result}, indent=2))
            else:
                print("[OK] Auto-commit triggered" if result else "[FAIL] Trigger failed")

            sys.exit(0 if result else 1)

        elif args.validate:
            result = policy.validate()

            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                _print_validation_result(result)

            sys.exit(0 if result.get("success") else 1)

        elif args.report or args.stats:
            result = policy.report()

            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                _print_report_result(result)

            sys.exit(0)

    except Exception as exc:
        _logger.error(f"Error: {exc}", exc_info=True)
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        else:
            print(f"[FAIL] Error: {exc}")
        sys.exit(1)


def _print_detection_result(result):
    """Pretty-print detection result."""
    print("\n" + "=" * 70)
    print("[CHART] AUTO-COMMIT TRIGGER DETECTION")
    print("=" * 70)
    print(f"\nProject: {result.get('project_dir', 'N/A')}")
    print(f"Timestamp: {result.get('timestamp', 'N/A')}")

    if result["should_commit"]:
        print(f"\n[CHECK] AUTO-COMMIT RECOMMENDED ({result['trigger_count']} triggers met)")

        if "git_status" in result:
            git = result["git_status"]
            print(f"\n[FOLDER] Git Status:")
            print(f"   Staged: {git['staged_count']} files")
            print(f"   Modified: {git['modified_count']} files")
            print(f"   Untracked: {git['untracked_count']} files")

        print("\n[TARGET] Triggers Met:")
        for trigger in result["triggers_met"]:
            details = result["details"].get(trigger, {})
            reason = details.get("reason", "N/A")
            print(f"   [CHECK] {trigger.replace('_', ' ').title()}: {reason}")

    else:
        reason = result.get("reason", "No triggers met")
        print(f"\n[PAUSE] NO COMMIT NEEDED")
        print(f"   Reason: {reason}")

    print("\n" + "=" * 70 + "\n")


def _print_ai_message_result(result):
    """Pretty-print AI message generation result."""
    print("\n" + "=" * 70)
    print("[LIGHTBULB] AI COMMIT MESSAGE GENERATION")
    print("=" * 70)

    if not result.get("success"):
        print(f"\n[FAIL] {result.get('error', 'Unknown error')}")
        print("=" * 70 + "\n")
        return

    print(f"\nRepository: {result.get('path', 'N/A')}")

    changes = result.get("changes", {})
    print(f"\n[STATS] Changes Summary:")
    print(f"   Added: {len(changes.get('added', []))}")
    print(f"   Modified: {len(changes.get('modified', []))}")
    print(f"   Deleted: {len(changes.get('deleted', []))}")

    print(f"\n[MEMO] Generated Commit Message:")
    print("─" * 70)
    print(result.get("commit_message", "N/A"))
    print("─" * 70)

    print("\n" + "=" * 70 + "\n")


def _print_commit_result(result, dry_run):
    """Pretty-print commit result."""
    print("\n" + "=" * 70)
    print("[FLOPPY] AUTO-COMMIT EXECUTION")
    print("=" * 70)

    if result.get("skipped"):
        print(f"\n[PAUSE] Skipped: {result.get('reason', 'No changes')}")
        print("=" * 70 + "\n")
        return

    if not result.get("success"):
        print(f"\n[FAIL] Error: {result.get('error', 'Unknown error')}")
        print("=" * 70 + "\n")
        return

    print(f"\nRepository: {result.get('path', 'N/A')}")

    changes = result.get("changes", {})
    print(f"\n[STATS] Changes Summary:")
    print(f"   Added: {len(changes.get('added', []))}")
    print(f"   Modified: {len(changes.get('modified', []))}")
    print(f"   Deleted: {len(changes.get('deleted', []))}")

    print(f"\n[MEMO] Commit Message:")
    print("─" * 70)
    print(result.get("commit_message", "N/A"))
    print("─" * 70)

    if dry_run:
        print("\n[WARNING] DRY RUN - No actual commit")
    else:
        if result.get("committed"):
            print("\n[CHECK] Changes committed successfully!")

        if result.get("pushed"):
            print("[CHECK] Changes pushed to remote!")
        elif result.get("push_error"):
            print(f"[WARNING] Push failed: {result['push_error']}")

    print("\n" + "=" * 70 + "\n")


def _print_validation_result(result):
    """Pretty-print validation result."""
    print("\n" + "=" * 70)
    print("[CLIPBOARD] POLICY VALIDATION")
    print("=" * 70)

    checks = result.get("checks", {})
    print(f"\n[CHECKS] Configuration:")
    print(f"   Memory dir: {'✓' if checks.get('memory_dir_exists') else '✗'}")
    print(f"   Logs dir: {'✓' if checks.get('logs_dir_exists') else '✗'}")
    print(f"   Policy log: {'✓' if checks.get('policy_log_accessible') else '✗'}")
    print(f"   Python: {checks.get('python_version', 'N/A')}")
    print(f"   Platform: {checks.get('platform', 'N/A')}")

    errors = result.get("errors", [])
    if errors:
        print(f"\n[ERRORS] Issues Found:")
        for error in errors:
            print(f"   [FAIL] {error}")
    else:
        print(f"\n[OK] All checks passed!")

    print("\n" + "=" * 70 + "\n")


def _print_report_result(result):
    """Pretty-print report result."""
    print("\n" + "=" * 70)
    print("[CHART] POLICY EXECUTION REPORT")
    print("=" * 70)

    print(f"\nReport Generated: {result.get('timestamp', 'N/A')}")
    print(f"Memory Directory: {result.get('memory_dir', 'N/A')}")
    print(f"Logs Directory: {result.get('logs_dir', 'N/A')}")

    print(f"\n[STATISTICS]")
    print(f"   Total commits logged: {result.get('total_commits_logged', 'N/A')}")
    print(f"   Total policy hits: {result.get('total_policy_hits', 'N/A')}")

    last_commit = result.get("last_commit")
    if last_commit:
        print(f"\n[LAST COMMIT]")
        print(f"   {last_commit}")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
