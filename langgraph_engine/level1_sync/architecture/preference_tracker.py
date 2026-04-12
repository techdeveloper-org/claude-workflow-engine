# -*- coding: utf-8 -*-
"""
preference_tracker.py - Level 1 Sync System: User Preference Tracker

Tracks user preferences from session history by looking for repeated patterns
(skills, agents, task types) across past session summaries. Generates a
preference profile that the pipeline can use to auto-apply consistent choices.

Policy Reference: policies/01-sync-system/user-preferences/user-preferences-policy.md

Usage:
    python preference_tracker.py                    # Track from default sessions dir
    python preference_tracker.py <sessions_dir>     # Track from specific sessions dir
    python preference_tracker.py --json             # Output as JSON
    python preference_tracker.py --update           # Update stored preferences file

Import usage:
    from preference_tracker import track_preferences
    prefs = track_preferences(sessions_dir)
    # prefs["preferred_skills"], prefs["preferred_agents"], prefs["common_task_types"]
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# CONSTANTS
# ============================================================================

# Minimum number of appearances across sessions to register as a preference
MIN_OCCURRENCES = 3

# Output file for storing learned preferences
PREFERENCES_FILE = Path.home() / ".claude" / "memory" / "user-preferences.json"

# Known skill names to search for in session text
KNOWN_SKILLS = [
    "python-core",
    "python-design-patterns-core",
    "clean-architecture",
    "error-handling-patterns",
    "logging-patterns",
    "performance-optimization",
    "rdbms-core",
    "nosql-core",
    "redis-core",
    "message-queues-core",
    "api-design-core",
    "graphql-core",
    "authentication-core",
    "testing-core",
    "json-core",
    "system-design",
    "langgraph-core",
    "langchain-core",
    "fastmcp-core",
    "react-core",
    "angular-core",
    "swiftui-core",
    "docker",
    "kubernetes",
    "jenkins-pipeline",
]

# Known agent names to search for in session text
KNOWN_AGENTS = [
    "python-backend-engineer",
    "spring-boot-microservices",
    "ui-ux-designer",
    "angular-engineer",
    "swiftui-designer",
    "devops-engineer",
    "qa-testing-agent",
    "python-system-scripting",
    "data-engineer",
    "ml-engineer",
]

# Task type keywords (maps keyword -> task type label)
TASK_TYPE_KEYWORDS = {
    "bug fix": "bug_fix",
    "bugfix": "bug_fix",
    "fix": "bug_fix",
    "feature": "feature",
    "new feature": "feature",
    "implement": "feature",
    "refactor": "refactor",
    "refactoring": "refactor",
    "test": "testing",
    "tests": "testing",
    "unit test": "testing",
    "documentation": "documentation",
    "docs": "documentation",
    "performance": "performance",
    "optimization": "performance",
    "security": "security",
    "deployment": "devops",
    "ci/cd": "devops",
    "docker": "devops",
    "kubernetes": "devops",
    "data migration": "data",
    "migration": "data",
    "api": "api_development",
    "rest api": "api_development",
    "graphql": "api_development",
}


# ============================================================================
# CORE FUNCTION
# ============================================================================


def track_preferences(
    sessions_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Track user preferences from session history.

    Reads all session summary files in sessions_dir, counts occurrences of
    known skills, agents, and task types, and returns a preference profile.

    Args:
        sessions_dir: Directory containing session files (or session subdirectories).
                      Defaults to ~/.claude/logs/sessions/.

    Returns:
        A dict with keys:
            - preferred_skills (list): Skills ranked by frequency [{name, count, score}].
            - preferred_agents (list): Agents ranked by frequency [{name, count, score}].
            - common_task_types (list): Task types ranked by frequency [{name, count, score}].
            - sessions_analysed (int): Number of session files read.
            - sessions_dir (str): Directory analysed.
            - timestamp (str): ISO timestamp.
            - learning_threshold (int): Min occurrences to register as preference.
    """
    if sessions_dir is None:
        sessions_dir = Path.home() / ".claude" / "logs" / "sessions"

    sessions_dir = Path(sessions_dir)

    # Collect all text content from session files
    session_texts = _collect_session_texts(sessions_dir)
    session_count = len(session_texts)

    # Count occurrences across all sessions
    skill_counts: Counter = Counter()
    agent_counts: Counter = Counter()
    task_counts: Counter = Counter()

    for text in session_texts:
        text_lower = text.lower()

        # Skills
        for skill in KNOWN_SKILLS:
            if skill.lower() in text_lower:
                skill_counts[skill] += 1

        # Agents
        for agent in KNOWN_AGENTS:
            if agent.lower() in text_lower:
                agent_counts[agent] += 1

        # Task types
        seen_task_types_this_session: set = set()
        for keyword, task_type in TASK_TYPE_KEYWORDS.items():
            if keyword.lower() in text_lower:
                seen_task_types_this_session.add(task_type)
        for task_type in seen_task_types_this_session:
            task_counts[task_type] += 1

    # Build ranked preference lists (filter by minimum occurrences)
    preferred_skills = _build_ranked_list(skill_counts, session_count)
    preferred_agents = _build_ranked_list(agent_counts, session_count)
    common_task_types = _build_ranked_list(task_counts, session_count)

    return {
        "preferred_skills": preferred_skills,
        "preferred_agents": preferred_agents,
        "common_task_types": common_task_types,
        "sessions_analysed": session_count,
        "sessions_dir": str(sessions_dir),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "learning_threshold": MIN_OCCURRENCES,
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _collect_session_texts(sessions_dir: Path) -> List[str]:
    """Collect text content from all session files under sessions_dir.

    Handles both flat layouts (session files directly in sessions_dir) and
    nested layouts (session files inside session subdirectories).
    """
    texts: List[str] = []
    if not sessions_dir.exists():
        return texts

    text_extensions = {".md", ".txt", ".json", ".log"}

    def _read_file(path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    for item in sessions_dir.iterdir():
        if item.is_file():
            if item.suffix.lower() in text_extensions:
                content = _read_file(item)
                if content:
                    texts.append(content)
        elif item.is_dir():
            # One level deeper (session subdirectory)
            for subitem in item.iterdir():
                if subitem.is_file() and subitem.suffix.lower() in text_extensions:
                    content = _read_file(subitem)
                    if content:
                        texts.append(content)

    return texts


def _build_ranked_list(
    counts: Counter,
    total_sessions: int,
) -> List[Dict[str, Any]]:
    """Build a ranked list of preferences from a Counter.

    Filters out items with fewer than MIN_OCCURRENCES appearances.
    Adds a confidence score (fraction of sessions that mentioned the item).

    Args:
        counts: Counter of {name: occurrence_count}.
        total_sessions: Total number of sessions analysed.

    Returns:
        List of {name, count, score} dicts sorted by count descending.
    """
    ranked = []
    for name, count in counts.most_common():
        if count < MIN_OCCURRENCES:
            break
        score = round(count / max(total_sessions, 1), 3)
        ranked.append({"name": name, "count": count, "score": score})
    return ranked


# ============================================================================
# PERSISTENCE
# ============================================================================


def load_stored_preferences(
    preferences_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Load previously stored preferences from disk.

    Args:
        preferences_file: Path to the JSON preferences file.
                          Defaults to ~/.claude/memory/user-preferences.json.

    Returns:
        Dict with stored preferences, or empty structure if file does not exist.
    """
    if preferences_file is None:
        preferences_file = PREFERENCES_FILE

    preferences_file = Path(preferences_file)
    if not preferences_file.exists():
        return _empty_preferences()

    try:
        data = json.loads(preferences_file.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return _empty_preferences()


def save_preferences(
    prefs: Dict[str, Any],
    preferences_file: Optional[Path] = None,
) -> bool:
    """Save preferences to disk.

    Args:
        prefs: Preference dict from track_preferences().
        preferences_file: Destination path.
                          Defaults to ~/.claude/memory/user-preferences.json.

    Returns:
        True on success, False on error.
    """
    if preferences_file is None:
        preferences_file = PREFERENCES_FILE

    preferences_file = Path(preferences_file)
    try:
        preferences_file.parent.mkdir(parents=True, exist_ok=True)
        preferences_file.write_text(
            json.dumps(prefs, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _empty_preferences() -> Dict[str, Any]:
    """Return an empty preferences structure."""
    return {
        "preferred_skills": [],
        "preferred_agents": [],
        "common_task_types": [],
        "sessions_analysed": 0,
        "sessions_dir": "",
        "timestamp": "",
        "learning_threshold": MIN_OCCURRENCES,
    }


def merge_preferences(
    existing: Dict[str, Any],
    new: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge newly computed preferences with previously stored ones.

    Combines counts from both sources and re-ranks. New data takes precedence
    for metadata fields (timestamp, sessions_dir, sessions_analysed).

    Args:
        existing: Previously stored preferences dict.
        new: Freshly computed preferences dict.

    Returns:
        Merged preferences dict.
    """
    merged = dict(new)  # Start from new

    for key in ("preferred_skills", "preferred_agents", "common_task_types"):
        existing_items = {item["name"]: item for item in existing.get(key, [])}
        new_items = {item["name"]: item for item in new.get(key, [])}

        combined: Dict[str, Dict[str, Any]] = {}
        for name, item in existing_items.items():
            combined[name] = item.copy()
        for name, item in new_items.items():
            if name in combined:
                combined[name]["count"] += item["count"]
                combined[name]["score"] = combined[name]["count"] / max(new.get("sessions_analysed", 1), 1)
            else:
                combined[name] = item.copy()

        # Filter and re-rank
        ranked = sorted(
            [v for v in combined.values() if v["count"] >= MIN_OCCURRENCES],
            key=lambda x: x["count"],
            reverse=True,
        )
        merged[key] = ranked

    return merged


# ============================================================================
# CLI ENTRY POINT
# ============================================================================


def _print_human(prefs: Dict[str, Any]) -> None:
    """Print a human-readable preferences report."""
    print("\nUser Preference Report")
    print("=" * 50)
    print(f"  Sessions dir:      {prefs['sessions_dir']}")
    print(f"  Sessions analysed: {prefs['sessions_analysed']}")
    print(f"  Timestamp:         {prefs['timestamp']}")
    print(f"  Min occurrences:   {prefs['learning_threshold']}\n")

    def _print_category(label: str, items: List[Dict[str, Any]]) -> None:
        print(f"  [{label}]")
        if not items:
            print("    (none above threshold)")
        else:
            for item in items:
                bar_len = int(item["score"] * 10)
                bar = "#" * bar_len + "." * (10 - bar_len)
                print(f"    {item['name']:<35} " f"[{bar}] {item['score'] * 100:.0f}%  " f"({item['count']} sessions)")
        print()

    _print_category("PREFERRED SKILLS", prefs["preferred_skills"])
    _print_category("PREFERRED AGENTS", prefs["preferred_agents"])
    _print_category("COMMON TASK TYPES", prefs["common_task_types"])


def main() -> int:
    """CLI entry point for preference_tracker.py."""
    parser = argparse.ArgumentParser(description="Track user preferences from Claude session history.")
    parser.add_argument(
        "sessions_dir",
        nargs="?",
        default=None,
        help="Sessions directory to analyse (default: ~/.claude/logs/sessions/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Merge and save computed preferences to ~/.claude/memory/user-preferences.json",
    )
    parser.add_argument(
        "--show-stored",
        action="store_true",
        help="Show currently stored preferences without re-analysing sessions",
    )
    args = parser.parse_args()

    if args.show_stored:
        stored = load_stored_preferences()
        if args.json:
            print(json.dumps(stored, indent=2))
        else:
            _print_human(stored)
        return 0

    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else None
    prefs = track_preferences(sessions_dir)

    if args.update:
        existing = load_stored_preferences()
        merged = merge_preferences(existing, prefs)
        ok = save_preferences(merged)
        if not ok:
            print("ERROR: Failed to save preferences.", file=sys.stderr)
            return 1
        print(f"Preferences saved to {PREFERENCES_FILE}")
        prefs = merged

    if args.json:
        print(json.dumps(prefs, indent=2))
    else:
        _print_human(prefs)

    return 0


if __name__ == "__main__":
    sys.exit(main())
