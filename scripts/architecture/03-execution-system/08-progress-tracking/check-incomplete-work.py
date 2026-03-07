#!/usr/bin/env python3
"""
Check for Incomplete Work - Session Resume Helper
Uses existing session memory to detect and resume incomplete tasks.

Integrates with:
- project-summary.md (cumulative context)
- session-*.md files (recent work)

Usage:
  python check-incomplete-work.py <project>     # Check for incomplete work
  python check-incomplete-work.py               # Use current directory
"""

# Fix encoding for Windows console
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


import os
import sys
import io
from datetime import datetime, timedelta
from pathlib import Path
import re

# Fix Windows console encoding

SESSIONS_DIR = Path.home() / ".claude" / "memory" / "sessions"


def get_current_project():
    """Get current project name from working directory."""
    cwd = Path.cwd()
    return cwd.name


def find_incomplete_markers(content):
    """Find markers of incomplete work in content."""
    incomplete_patterns = [
        r'(?:TODO|PENDING|IN PROGRESS|WIP|INCOMPLETE):\s*(.+)',
        r'Phase \d+/\d+.*(?:in progress|pending|not started)',
        r'Step \d+/\d+.*(?:in progress|pending|not started)',
        r'[PAUSE]️|[CYCLE]|[CROSS].*',
        r'\[ \].*',  # Unchecked checkboxes
        r'Next steps?:\s*(.+)',
        r'Remaining:\s*(.+)',
        r'Pending:\s*(.+)',
    ]

    incomplete_items = []

    for pattern in incomplete_patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            line = match.group(0).strip()
            if line and len(line) > 10:  # Avoid short matches
                incomplete_items.append(line)

    return incomplete_items


def check_project_summary(project):
    """Check project summary for incomplete work."""
    summary_file = SESSIONS_DIR / project / "project-summary.md"

    if not summary_file.exists():
        return None

    try:
        with open(summary_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Look for common incomplete work sections
        sections_to_check = [
            'Next Steps',
            'Pending Work',
            'TODO',
            'In Progress',
            'Remaining Tasks',
            'Current Work'
        ]

        incomplete_info = {
            'file': 'project-summary.md',
            'sections': [],
            'items': []
        }

        for section in sections_to_check:
            # Find section and extract content
            pattern = rf'#{1,3}\s*{section}.*?\n(.*?)(?=\n#{1,3}|\Z)'
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)

            if match:
                section_content = match.group(1).strip()
                if section_content and len(section_content) > 20:
                    incomplete_info['sections'].append({
                        'name': section,
                        'content': section_content[:500]  # First 500 chars
                    })

        # Also check for incomplete markers anywhere
        incomplete_info['items'] = find_incomplete_markers(content)

        # Only return if we found something significant
        if incomplete_info['sections'] or len(incomplete_info['items']) > 2:
            return incomplete_info

        return None

    except (IOError, UnicodeDecodeError):
        return None


def check_recent_session(project):
    """Check most recent session file for incomplete work."""
    project_dir = SESSIONS_DIR / project

    if not project_dir.exists():
        return None

    # Get most recent session file
    session_files = sorted(project_dir.glob('session-*.md'), reverse=True)

    if not session_files:
        return None

    recent_session = session_files[0]

    # Check if session is recent (within last 3 days)
    try:
        mtime = datetime.fromtimestamp(recent_session.stat().st_mtime)
        now = datetime.now()
        days_ago = (now - mtime).days

        if days_ago > 3:
            return None  # Too old

        # Read session content
        with open(recent_session, 'r', encoding='utf-8') as f:
            content = f.read()

        incomplete_items = find_incomplete_markers(content)

        if len(incomplete_items) >= 2:
            return {
                'file': recent_session.name,
                'age_days': days_ago,
                'items': incomplete_items[:10]  # Top 10
            }

    except (IOError, UnicodeDecodeError, OSError):
        pass

    return None


def show_resume_prompt(project):
    """Show resume prompt if incomplete work detected."""
    print("[SEARCH] Checking for incomplete work...")
    print()

    # Check project summary
    summary_incomplete = check_project_summary(project)

    # Check recent session
    session_incomplete = check_recent_session(project)

    if not summary_incomplete and not session_incomplete:
        print("[CHECK] No incomplete work detected")
        print("   You can start fresh or continue with new tasks!")
        return False

    # Found incomplete work!
    print("=" * 70)
    print("[U+1F44B] Welcome back!")
    print("=" * 70)
    print()
    print(f"[U+1F4C2] Project: {project}")
    print()

    if summary_incomplete:
        print("[CLIPBOARD] I found incomplete work in your project summary:")
        print()

        # Show sections
        for section in summary_incomplete.get('sections', []):
            print(f"  [U+1F4CC] {section['name']}:")
            # Show first few lines
            lines = section['content'].split('\n')[:7]
            for line in lines:
                if line.strip():
                    print(f"     {line.strip()}")
            if len(section['content'].split('\n')) > 7:
                print("     ...")
            print()

        # Show incomplete items (markers found)
        items = summary_incomplete.get('items', [])
        if items:
            unique_items = list(set(items))[:8]  # Remove duplicates, show top 8
            if unique_items:
                print("  [U+1F516] Incomplete markers detected:")
                for item in unique_items:
                    # Clean up the item
                    item_clean = item.replace('[PAUSE]️', '').replace('[CYCLE]', '').strip()
                    if len(item_clean) > 10:
                        print(f"     - {item_clean}")
                print()

    if session_incomplete:
        age = session_incomplete.get('age_days', 0)
        age_str = "today" if age == 0 else f"{age} day{'s' if age > 1 else ''} ago"

        print(f"[U+1F4DD] Last session ({age_str}) had incomplete items:")
        print()

        for item in session_incomplete.get('items', [])[:7]:
            print(f"     - {item}")

        print()

    print("=" * 70)
    print("[BULB] Do you want to:")
    print("   1. Resume from where we stopped")
    print("   2. Start something new")
    print("=" * 70)
    print()
    print("Tip: I have full context from previous sessions in my memory!")

    return True


def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    if len(sys.argv) < 2:
        project = get_current_project()
    else:
        project = sys.argv[1]

    print(f"Checking project: {project}")
    print()

    has_incomplete = show_resume_prompt(project)

    # Exit codes (standard Unix convention):
    # 0 = No incomplete work (all clear)
    # 1 = Incomplete work detected (NOT an error, just status indicator)
    if not has_incomplete:
        sys.exit(0)  # No incomplete work
    else:
        sys.exit(1)  # Has incomplete work (resume available)


if __name__ == "__main__":
    main()
