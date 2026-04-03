"""GitHub label definitions and label-building helpers.

Provides LABEL_DEFINITIONS, _build_issue_labels(), _detect_issue_type(),
_detect_scope_labels(), _get_priority_labels(), _get_repo_labels(), and
_ensure_labels_exist().
"""

import json
import subprocess

from .client import GH_TIMEOUT

# All labels the system uses, with colors and descriptions.
# These get auto-created in the repo if they don't exist yet.
LABEL_DEFINITIONS = {
    # Type labels
    "bug": {"color": "d73a4a", "description": "Something isn't working"},
    "enhancement": {"color": "a2eeef", "description": "New feature or request"},
    "refactor": {"color": "D4C5F9", "description": "Code restructuring without behavior change"},
    "documentation": {"color": "0075ca", "description": "Improvements or additions to documentation"},
    "test": {"color": "BFD4F2", "description": "Test coverage or test infrastructure"},
    # Priority labels
    "critical-priority": {"color": "8B0000", "description": "CRITICAL - blocks other work"},
    "high-priority": {"color": "FF0000", "description": "High priority - should be done soon"},
    "medium-priority": {"color": "FFA500", "description": "Medium priority - can wait"},
    "low-priority": {"color": "FBCA04", "description": "Low priority - nice to have"},
    # Complexity labels
    "complexity-high": {"color": "B60205", "description": "High complexity (10+ score)"},
    "complexity-medium": {"color": "D93F0B", "description": "Medium complexity (4-9 score)"},
    "complexity-low": {"color": "0E8A16", "description": "Low complexity (1-3 score)"},
    # Scope labels
    "backend": {"color": "1D76DB", "description": "Backend / server-side changes"},
    "frontend": {"color": "C5DEF5", "description": "Frontend / UI changes"},
    "devops": {"color": "EDEDED", "description": "CI/CD, deployment, infrastructure"},
    "config": {"color": "F9D0C4", "description": "Configuration or settings changes"},
    "scripts": {"color": "E99695", "description": "Hook scripts or automation"},
    "policy": {"color": "D4C5F9", "description": "Policy or architecture changes"},
    # Auto-management labels
    "auto-created": {"color": "C2E0C6", "description": "Auto-created by Claude Memory System"},
}

# Cache for labels known to exist in the repo (avoids repeated gh calls)
_repo_labels_cache = None


def _detect_issue_type(subject, description=""):
    """Classify the issue type from the subject and description text.

    Keyword matching selects the most appropriate semantic type label.
    The result drives both GitHub label assignment and branch naming
    (e.g. bugfix/42, feature/123).

    Args:
        subject (str): Issue title or task subject line.
        description (str): Optional longer description. Defaults to ''.

    Returns:
        str: One of 'bugfix', 'feature', 'refactor', 'docs', 'enhancement',
            'perf', 'test', or 'chore'. Defaults to 'feature' when no
            keywords match.
    """
    combined = (subject + " " + (description or "")).lower()
    if any(w in combined for w in ["fix", "bug", "error", "broken", "crash", "issue", "resolve"]):
        return "bugfix"
    if any(w in combined for w in ["refactor", "cleanup", "reorganize", "simplify", "restructure"]):
        return "refactor"
    if any(w in combined for w in ["doc", "readme", "comment", "documentation", "javadoc"]):
        return "docs"
    if any(w in combined for w in ["test", "spec", "coverage", "unit test", "integration test"]):
        return "test"
    if any(w in combined for w in ["performance", "perf", "optimize", "speed", "faster"]):
        return "perf"
    if any(w in combined for w in ["update", "enhance", "improve", "upgrade"]):
        return "enhancement"
    if any(w in combined for w in ["chore", "maintenance", "dependency", "dependencies"]):
        return "chore"
    return "feature"


def _detect_scope_labels(subject, description=""):
    """Detect applicable scope/technology labels from the subject and description.

    Checks for keywords associated with backend, frontend, devops, config,
    scripts, and policy scopes.

    Args:
        subject (str): Issue title or task subject line.
        description (str): Optional longer description. Defaults to ''.

    Returns:
        list[str]: Scope label name strings that matched (may be empty).
    """
    labels = []
    combined = (subject + " " + (description or "")).lower()

    if any(
        w in combined
        for w in ["api", "endpoint", "server", "service", "database", "backend", "spring", "flask", "rest", "query"]
    ):
        labels.append("backend")
    if any(
        w in combined
        for w in ["ui", "frontend", "template", "css", "html", "component", "dashboard", "page", "layout", "view"]
    ):
        labels.append("frontend")
    if any(
        w in combined for w in ["deploy", "ci", "cd", "docker", "kubernetes", "pipeline", "build", "release", "version"]
    ):
        labels.append("devops")
    if any(w in combined for w in ["config", "setting", "environment", "properties", "json config"]):
        labels.append("config")
    if any(
        w in combined
        for w in ["script", "hook", "automation", "daemon", "enforcer", "tracker", "notifier", "policy script"]
    ):
        labels.append("scripts")
    if any(
        w in combined for w in ["policy", "architecture", "level-1", "level-2", "level-3", "enforcement", "standard"]
    ):
        labels.append("policy")

    return labels


def _build_issue_labels(issue_type, complexity, subject, description=""):
    """Build the complete set of labels to attach to a new GitHub issue.

    Assigns one type label (semantic format matching branch naming), one
    priority label based on complexity score, a status label ('in-progress'),
    and any relevant scope labels detected from the subject/description.

    Args:
        issue_type (str): Semantic type string from _detect_issue_type
            (e.g. 'bugfix', 'feature', 'refactor').
        complexity (int or float): Task complexity score (0-25).
        subject (str): Issue title or task subject line.
        description (str): Optional longer description. Defaults to ''.

    Returns:
        list[str]: Label name strings to assign to the issue.
    """
    labels = []

    # 1. Type label (semantic format - matches branch naming!)
    # Supported types: bugfix, feature, refactor, docs, enhancement, perf, test, chore
    # These also match branch naming: bugfix/42, feature/123, etc.
    type_map = {
        "bugfix": "bugfix",
        "fix": "bugfix",  # backward compatibility
        "feature": "feature",
        "refactor": "refactor",
        "docs": "docs",
        "enhancement": "enhancement",
        "perf": "perf",
        "test": "test",
        "chore": "chore",
    }
    labels.append(type_map.get(issue_type, "feature"))

    # 2. Priority label (CHANGED v3.0: semantic naming)
    # p0-critical (>=18), p1-high (12-17), p2-medium (6-11), p3-low (0-5)
    if complexity and isinstance(complexity, (int, float)):
        c = int(complexity)
        if c >= 18:
            labels.append("p0-critical")
        elif c >= 12:
            labels.append("p1-high")
        elif c >= 6:
            labels.append("p2-medium")
        else:
            labels.append("p3-low")

    # 3. Status label (always in-progress for new issues)
    labels.append("in-progress")

    # 4. Scope/technology labels (optional - only if relevant)
    labels.extend(_detect_scope_labels(subject, description))

    return labels


def _get_priority_labels(complexity):
    """Return priority and complexity labels for a given complexity score.

    .. deprecated::
        Use _build_issue_labels() instead. Retained for backward compatibility.

    Args:
        complexity (int or float or None): Task complexity score (0-25).

    Returns:
        list[str]: Priority label and complexity label strings, or an empty
            list if complexity is falsy or not numeric.
    """
    labels = []
    if not complexity or not isinstance(complexity, (int, float)):
        return labels

    complexity = int(complexity)

    if complexity >= 15:
        labels.append("critical-priority")
    elif complexity >= 10:
        labels.append("high-priority")
    elif complexity >= 5:
        labels.append("medium-priority")
    else:
        labels.append("low-priority")

    if complexity >= 10:
        labels.append("complexity-high")
    elif complexity >= 4:
        labels.append("complexity-medium")
    else:
        labels.append("complexity-low")

    return labels


def _get_repo_labels(repo_root):
    """Fetch all label names currently defined in the GitHub repository.

    The result is cached in the module-level ``_repo_labels_cache`` set so
    that subsequent calls within the same invocation do not make additional
    ``gh`` CLI requests.

    Args:
        repo_root (str): Absolute path to the git repository root, passed as
            the working directory for the ``gh`` CLI call.

    Returns:
        set: Label name strings present in the repo, or an empty set if the
            ``gh label list`` call fails or returns no data.
    """
    global _repo_labels_cache
    if _repo_labels_cache is not None:
        return _repo_labels_cache

    try:
        result = subprocess.run(
            ["gh", "label", "list", "--limit", "100", "--json", "name"],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            cwd=repo_root,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            _repo_labels_cache = {item["name"] for item in data}
            return _repo_labels_cache
    except Exception:
        pass
    _repo_labels_cache = set()
    return _repo_labels_cache


def _ensure_labels_exist(labels, repo_root):
    """Create any of the given labels that do not already exist in the repository.

    Only creates labels that are defined in LABEL_DEFINITIONS. Uses
    ``gh label create --force`` so re-creation of an existing label is
    idempotent. Failures for individual labels are silently ignored.

    Args:
        labels (list[str]): Label names to ensure exist.
        repo_root (str): Absolute path to the git repository root.
    """
    existing = _get_repo_labels(repo_root)
    for label_name in labels:
        if label_name in existing:
            continue
        defn = LABEL_DEFINITIONS.get(label_name)
        if not defn:
            continue
        try:
            subprocess.run(
                [
                    "gh",
                    "label",
                    "create",
                    label_name,
                    "--color",
                    defn["color"],
                    "--description",
                    defn["description"],
                    "--force",
                ],
                capture_output=True,
                text=True,
                timeout=GH_TIMEOUT,
                cwd=repo_root,
            )
            existing.add(label_name)
        except Exception:
            pass
