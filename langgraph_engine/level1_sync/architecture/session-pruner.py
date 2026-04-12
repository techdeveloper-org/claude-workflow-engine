# -*- coding: utf-8 -*-
"""
session-pruner.py - Level 1 Sync System: Session Pruning Script

Archives sessions older than 30 days from ~/.claude/sessions/
while keeping the last 10 active sessions minimum.
Moves archived sessions to ~/.claude/sessions/archive/<YYYY-MM>/

Policy Reference: policies/01-sync-system/session-management/session-pruning-policy.md

Usage:
    python session-pruner.py                  # Archive all eligible sessions
    python session-pruner.py --dry-run        # Preview without archiving
    python session-pruner.py --stats          # Show statistics only
    python session-pruner.py <session_dir>    # Archive specific sessions directory

Import usage:
    from session_pruner import prune_sessions
    result = prune_sessions(sessions_dir, max_age_days=30, keep_min=10)
"""

import argparse
import shutil
import sys
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_KEEP_MIN = 10
NEVER_ARCHIVE_FILES = {"project-summary.md", "SUMMARY.md", "README.md"}
SESSION_FILE_PATTERNS = ("session-", "session_")
ARCHIVE_SUBDIR = "archive"
LOG_DIR = Path.home() / ".claude" / "memory" / "logs"
LOG_FILE = LOG_DIR / "policy-hits.log"


# ============================================================================
# CORE FUNCTION
# ============================================================================


def prune_sessions(
    sessions_dir: Path,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    keep_min: int = DEFAULT_KEEP_MIN,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Archive sessions older than max_age_days while keeping keep_min recent sessions.

    Args:
        sessions_dir: Path to the sessions directory to prune.
        max_age_days: Sessions older than this many days are eligible for archival.
        keep_min: Always keep at least this many recent sessions active.
        dry_run: If True, report what would happen but do not archive anything.

    Returns:
        A dict with keys:
            - total_sessions (int): Total session files found.
            - kept_active (int): Sessions kept as active.
            - archived (int): Sessions archived (or would be archived in dry_run).
            - skipped (int): Sessions skipped (protected files, etc.).
            - archive_paths (list): Paths of archives created.
            - errors (list): Any errors encountered.
    """
    sessions_dir = Path(sessions_dir)
    result: Dict[str, Any] = {
        "total_sessions": 0,
        "kept_active": 0,
        "archived": 0,
        "skipped": 0,
        "archive_paths": [],
        "errors": [],
    }

    if not sessions_dir.exists():
        result["errors"].append(f"Sessions directory does not exist: {sessions_dir}")
        return result

    # Collect all session files (not directories, not protected names)
    all_session_files = _collect_session_files(sessions_dir)
    result["total_sessions"] = len(all_session_files)

    if not all_session_files:
        return result

    # Sort by modification time, newest first
    all_session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Always keep the most recent keep_min sessions
    keep_set = set(all_session_files[:keep_min])
    candidates = all_session_files[keep_min:]

    # Mark those kept as active
    result["kept_active"] = len(keep_set)

    # Filter candidates by age
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    to_archive: List[Path] = []
    for session_file in candidates:
        mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
        if mtime < cutoff_date:
            to_archive.append(session_file)
        else:
            # Not old enough; keep active
            result["kept_active"] += 1

    if not to_archive:
        return result

    # Group by month (YYYY-MM) for archival
    by_month: Dict[str, List[Path]] = {}
    for session_file in to_archive:
        mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
        month_key = mtime.strftime("%Y-%m")
        by_month.setdefault(month_key, []).append(session_file)

    # Archive each month group
    archive_base = sessions_dir / ARCHIVE_SUBDIR
    for month_key, files in sorted(by_month.items()):
        archive_dir = archive_base / month_key
        archive_path = archive_dir / "sessions.tar.gz"

        if dry_run:
            print(f"  [DRY RUN] Would archive {len(files)} session(s) -> {archive_path}")
            for f in files:
                age_days = (datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).days
                print(f"    - {f.name} (age: {age_days} days)")
            result["archived"] += len(files)
            continue

        try:
            archive_dir.mkdir(parents=True, exist_ok=True)
            _append_to_tar(archive_path, files)

            # Only delete originals after successful archive
            for session_file in files:
                try:
                    session_file.unlink()
                    result["archived"] += 1
                except OSError as e:
                    result["errors"].append(f"Failed to delete {session_file}: {e}")

            result["archive_paths"].append(str(archive_path))
            _log_action("session-pruner", "archived", f"{month_key}: {len(files)} sessions")

        except Exception as e:
            result["errors"].append(f"Failed to archive month {month_key}: {e}")

    return result


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _collect_session_files(sessions_dir: Path) -> List[Path]:
    """Return all session files in the directory (not subdirs, not protected files)."""
    files = []
    for item in sessions_dir.iterdir():
        if item.is_dir():
            continue
        if item.name in NEVER_ARCHIVE_FILES:
            continue
        # Match session file patterns
        if any(item.name.startswith(pat) for pat in SESSION_FILE_PATTERNS):
            files.append(item)
    return files


def _append_to_tar(archive_path: Path, files: List[Path]) -> None:
    """Add files to a tar.gz archive, creating it if it does not exist."""
    mode = "a:gz" if archive_path.exists() else "w:gz"
    # tarfile does not support "a:gz" on compressed archives;
    # we must read existing content and rewrite.
    if archive_path.exists() and mode == "a:gz":
        _merge_into_tar(archive_path, files)
    else:
        with tarfile.open(archive_path, "w:gz") as tar:
            for f in files:
                tar.add(f, arcname=f.name)


def _merge_into_tar(archive_path: Path, new_files: List[Path]) -> None:
    """Merge new files into an existing tar.gz by rewriting it."""

    tmp_path = archive_path.with_suffix(".tmp.tar.gz")
    try:
        with tarfile.open(archive_path, "r:gz") as old_tar:
            with tarfile.open(tmp_path, "w:gz") as new_tar:
                # Copy existing members
                for member in old_tar.getmembers():
                    fileobj = old_tar.extractfile(member)
                    if fileobj is not None:
                        new_tar.addfile(member, fileobj)
                # Add new files
                for f in new_files:
                    new_tar.add(f, arcname=f.name)
        # Replace the original
        shutil.move(str(tmp_path), str(archive_path))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _log_action(source: str, action: str, detail: str) -> None:
    """Append a line to the policy-hits log."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {source} | {action} | {detail}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # Logging failure must not break the main operation


def _get_stats(sessions_dir: Path) -> Dict[str, Any]:
    """Collect statistics about active and archived sessions."""
    sessions_dir = Path(sessions_dir)
    stats: Dict[str, Any] = {
        "directory": str(sessions_dir),
        "active_sessions": 0,
        "archivable_sessions": 0,
        "archived_sessions": 0,
        "archive_size_bytes": 0,
    }

    if not sessions_dir.exists():
        return stats

    all_files = _collect_session_files(sessions_dir)
    all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    cutoff_date = datetime.now() - timedelta(days=DEFAULT_MAX_AGE_DAYS)

    active_count = 0
    archivable_count = 0
    for i, f in enumerate(all_files):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if i < DEFAULT_KEEP_MIN:
            active_count += 1
        elif mtime < cutoff_date:
            archivable_count += 1
        else:
            active_count += 1

    stats["active_sessions"] = active_count
    stats["archivable_sessions"] = archivable_count

    # Count archived
    archive_base = sessions_dir / ARCHIVE_SUBDIR
    if archive_base.exists():
        for tar_file in archive_base.rglob("sessions.tar.gz"):
            try:
                with tarfile.open(tar_file, "r:gz") as tar:
                    stats["archived_sessions"] += len(tar.getmembers())
                stats["archive_size_bytes"] += tar_file.stat().st_size
            except Exception:
                pass

    return stats


# ============================================================================
# MULTI-PROJECT PRUNING
# ============================================================================


def prune_all_projects(
    sessions_root: Optional[Path] = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    keep_min: int = DEFAULT_KEEP_MIN,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Prune sessions across all projects under sessions_root.

    Args:
        sessions_root: Root directory containing project session folders.
                       Defaults to ~/.claude/sessions/.
        max_age_days: Maximum session age before archival.
        keep_min: Minimum recent sessions to keep per project.
        dry_run: Preview mode - no files modified.

    Returns:
        Combined results across all projects.
    """
    if sessions_root is None:
        sessions_root = Path.home() / ".claude" / "sessions"

    sessions_root = Path(sessions_root)
    combined: Dict[str, Any] = {
        "projects_processed": 0,
        "total_archived": 0,
        "total_kept": 0,
        "errors": [],
        "per_project": {},
    }

    if not sessions_root.exists():
        combined["errors"].append(f"Sessions root does not exist: {sessions_root}")
        return combined

    # Each subdirectory is a project
    for project_dir in sorted(sessions_root.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_dir.name == ARCHIVE_SUBDIR:
            continue

        result = prune_sessions(project_dir, max_age_days, keep_min, dry_run)
        combined["projects_processed"] += 1
        combined["total_archived"] += result["archived"]
        combined["total_kept"] += result["kept_active"]
        combined["errors"].extend(result["errors"])
        combined["per_project"][project_dir.name] = result

    return combined


# ============================================================================
# CLI ENTRY POINT
# ============================================================================


def _print_stats(sessions_root: Path) -> None:
    """Print statistics for all project session directories."""
    print("\nSession Memory Statistics")
    print("=" * 60)
    total_active = 0
    total_archivable = 0
    total_archived = 0

    if not sessions_root.exists():
        print(f"Directory not found: {sessions_root}")
        return

    for project_dir in sorted(sessions_root.iterdir()):
        if not project_dir.is_dir() or project_dir.name == ARCHIVE_SUBDIR:
            continue
        s = _get_stats(project_dir)
        total_active += s["active_sessions"]
        total_archivable += s["archivable_sessions"]
        total_archived += s["archived_sessions"]
        archive_mb = s["archive_size_bytes"] / (1024 * 1024)
        print(f"\n  {project_dir.name}")
        print(f"    Active sessions:     {s['active_sessions']}")
        print(f"    Archivable (>{DEFAULT_MAX_AGE_DAYS}d, beyond last {DEFAULT_KEEP_MIN}): {s['archivable_sessions']}")
        print(f"    Already archived:    {s['archived_sessions']} ({archive_mb:.2f} MB)")

    print("\n" + "=" * 60)
    print("Total:")
    print(f"  Active sessions:   {total_active}")
    print(f"  Archivable:        {total_archivable}")
    print(f"  Archived sessions: {total_archived}")


def main() -> int:
    """CLI entry point for session-pruner.py."""
    parser = argparse.ArgumentParser(description="Archive old Claude sessions per session-pruning-policy.")
    parser.add_argument(
        "sessions_dir",
        nargs="?",
        default=None,
        help="Specific sessions directory to prune (default: ~/.claude/sessions/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be archived without making changes",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help=f"Archive sessions older than this many days (default: {DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument(
        "--keep-min",
        type=int,
        default=DEFAULT_KEEP_MIN,
        help=f"Always keep this many recent sessions (default: {DEFAULT_KEEP_MIN})",
    )
    args = parser.parse_args()

    default_root = Path.home() / ".claude" / "sessions"

    if args.stats:
        root = Path(args.sessions_dir) if args.sessions_dir else default_root
        _print_stats(root)
        return 0

    if args.sessions_dir:
        # Prune a single directory
        target = Path(args.sessions_dir)
        if args.dry_run:
            print(f"[DRY RUN] Pruning sessions in: {target}")
        else:
            print(f"Pruning sessions in: {target}")

        result = prune_sessions(target, args.max_age_days, args.keep_min, dry_run=args.dry_run)
        print(f"  Total found:   {result['total_sessions']}")
        print(f"  Kept active:   {result['kept_active']}")
        print(f"  Archived:      {result['archived']}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"  ERROR: {err}", file=sys.stderr)
            return 1
    else:
        # Prune all projects
        label = "[DRY RUN] " if args.dry_run else ""
        print(f"{label}Archiving sessions across all projects...")
        print(f"  Rules: Keep last {args.keep_min} sessions, archive older than {args.max_age_days} days\n")

        result = prune_all_projects(default_root, args.max_age_days, args.keep_min, dry_run=args.dry_run)
        print(f"Projects processed: {result['projects_processed']}")
        print(f"Total kept active:  {result['total_kept']}")
        print(f"Total archived:     {result['total_archived']}")

        if result["errors"]:
            for err in result["errors"]:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1

        if not args.dry_run:
            print(f"\nArchived {result['total_archived']} sessions successfully.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
