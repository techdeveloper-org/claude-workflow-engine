#!/usr/bin/env python3
"""
Version Sync - Single source of truth from VERSION file.

Reads VERSION file and updates all references across the project:
- README.md (line: **Version:** X.Y.Z + Last Updated)
- CLAUDE.md (line: **Version:** X.Y.Z + Last Updated)
- docs/SYSTEM_REQUIREMENTS_SPECIFICATION.md (title + Last Updated)
- setup.py (already reads VERSION dynamically)

Usage:
    python scripts/sync-version.py           # Sync current VERSION to all files
    python scripts/sync-version.py 7.4.0     # Set new version and sync

Windows-safe: ASCII only (cp1252 compatible).
"""

import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"
TODAY = datetime.now().strftime("%Y-%m-%d")

# Files to update with version
TARGETS = [
    {
        "file": PROJECT_ROOT / "README.md",
        "patterns": [
            (r"\*\*Version:\*\*\s*[\d.]+", "**Version:** {version}"),
            (r"\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}", f"**Last Updated:** {TODAY}"),
        ],
    },
    {
        "file": PROJECT_ROOT / "CLAUDE.md",
        "patterns": [
            (r"\*\*Version:\*\*\s*[\d.]+", "**Version:** {version}"),
            (r"\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}", f"**Last Updated:** {TODAY}"),
        ],
    },
    {
        "file": PROJECT_ROOT / "docs" / "SYSTEM_REQUIREMENTS_SPECIFICATION.md",
        "patterns": [
            # Title: # Claude Workflow Engine v7.3.0 - System Requirements Specification
            (r"# Claude Workflow Engine v[\d.]+ -", "# Claude Workflow Engine v{version} -"),
            (r"\*\*Last Updated:\*\*\s*\d{4}-\d{2}-\d{2}", f"**Last Updated:** {TODAY}"),
            (r"\*\*Release Date:\*\*\s*\d{4}-\d{2}-\d{2}", f"**Release Date:** {TODAY}"),
            # Version in key stats table: | **Version** | 7.3.0 |
            (r"(\| \*\*Version\*\* \| )[\d.]+", "\\g<1>{version}"),
        ],
    },
]


def read_version():
    """Read current version from VERSION file."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0.0.0"


def set_version(new_version):
    """Write new version to VERSION file."""
    VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")
    print(f"[VERSION] Set VERSION file to {new_version}")


def sync_file(filepath, patterns, version):
    """Update version references in a file."""
    if not filepath.exists():
        print(f"[SKIP] {filepath.name} not found")
        return False

    content = filepath.read_text(encoding="utf-8")
    original = content
    changes = 0

    for pattern, replacement in patterns:
        repl = replacement.replace("{version}", version)
        new_content = re.sub(pattern, repl, content)
        if new_content != content:
            changes += 1
        content = new_content

    if content != original:
        filepath.write_text(content, encoding="utf-8")
        print(f"[UPDATED] {filepath.name} ({changes} replacement(s))")
        return True
    else:
        print(f"[OK] {filepath.name} already up to date")
        return False


def main():
    # Set new version if provided
    if len(sys.argv) > 1:
        new_version = sys.argv[1].strip()
        set_version(new_version)

    version = read_version()
    print(f"\n=== Version Sync: {version} ({TODAY}) ===\n")

    updated = 0
    for target in TARGETS:
        if sync_file(target["file"], target["patterns"], version):
            updated += 1

    # Patch langgraph_engine/__init__.py __version__ string
    init_file = PROJECT_ROOT / "langgraph_engine" / "__init__.py"
    if init_file.exists():
        init_content = init_file.read_text(encoding="utf-8")
        init_original = init_content
        init_pattern = r'__version__\s*=\s*["\'][\d.]+["\']'
        init_replacement = f'__version__ = "{version}"'
        init_content = re.sub(init_pattern, init_replacement, init_content)
        if init_content != init_original:
            init_file.write_text(init_content, encoding="utf-8")
            print(f'[UPDATED] langgraph_engine/__init__.py (__version__ = "{version}")')
            updated += 1
        else:
            print(f"[OK] langgraph_engine/__init__.py already at version {version}")
    else:
        print("[SKIP] langgraph_engine/__init__.py not found")

    # setup.py reads VERSION dynamically - no update needed
    print("[OK] setup.py reads VERSION dynamically")

    print(f"\n=== Done: {updated} file(s) updated, version {version} ===\n")


if __name__ == "__main__":
    main()
