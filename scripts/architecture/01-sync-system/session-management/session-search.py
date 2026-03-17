#!/usr/bin/env python3
"""
Session Search
Search sessions by tags, project, file, date range
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


import json
import sys
import argparse
from pathlib import Path
from datetime import datetime


class SessionSearch:
    """Searches and filters session history across all projects.

    Provides keyword search, filtering by date/project/complexity, and session
    discovery capabilities. Helps users find and reuse previous work.

    Attributes:
        memory_dir (Path): Base memory directory for session storage.
        sessions_dir (Path): Directory containing all session files.
    """

    def __init__(self):
        self.memory_dir = Path.home() / ".claude" / "memory"
        self.sessions_dir = self.memory_dir / "sessions"
        self.index_file = self.sessions_dir / "session-index.json"

    def search(
        self,
        tags=None,
        project=None,
        file=None,
        date_from=None,
        date_to=None,
        purpose_keyword=None
    ):
        """Search sessions by various criteria"""

        if not self.index_file.exists():
            print("[CROSS] Session index not found")
            return []

        with open(self.index_file, 'r') as f:
            index = json.load(f)

        results = index['sessions']

        # Filter by tags
        if tags:
            results = [
                s for s in results
                if any(tag.lower() in [t.lower() for t in s.get('tags', [])] for tag in tags)
            ]

        # Filter by project
        if project:
            results = [s for s in results if project.lower() in s['project'].lower()]

        # Filter by purpose keyword
        if purpose_keyword:
            results = [
                s for s in results
                if purpose_keyword.lower() in s.get('purpose', '').lower()
            ]

        # Filter by file (requires reading session content)
        if file:
            filtered = []
            for session in results:
                session_file = self.memory_dir / session['file_path']
                if session_file.exists():
                    content = session_file.read_text()
                    if file in content:
                        filtered.append(session)
            results = filtered

        # Filter by date range
        if date_from or date_to:
            filtered = []
            for session in results:
                session_date = datetime.fromisoformat(session['timestamp'])

                if date_from:
                    from_date = datetime.fromisoformat(date_from)
                    if session_date < from_date:
                        continue

                if date_to:
                    to_date = datetime.fromisoformat(date_to)
                    if session_date > to_date:
                        continue

                filtered.append(session)
            results = filtered

        return results

    def display_results(self, results, query_desc):
        """Display search results"""

        print(f"\n{'='*70}")
        print(f"[SEARCH] SEARCH RESULTS")
        print(f"{'='*70}")
        print(f"Query: {query_desc}")
        print(f"Found: {len(results)} session(s)")
        print(f"{'='*70}\n")

        if not results:
            print("No sessions found matching criteria.")
            return

        for i, session in enumerate(results, 1):
            print(f"{i}. {session['session_id']}")
            print(f"   Date:    {session['timestamp']}")
            print(f"   Project: {session['project']}")
            print(f"   Purpose: {session['purpose']}")
            print(f"   Tags:    {', '.join(session.get('tags', []))}")
            print(f"   Files:   {session.get('files_modified', 0)} modified")
            print()

    def search_by_tags(self, tags):
        """Search sessions by tags"""
        query = f"Tags: {', '.join(tags)}"
        results = self.search(tags=tags)
        self.display_results(results, query)
        return results

    def search_by_project(self, project):
        """Search sessions by project"""
        query = f"Project: {project}"
        results = self.search(project=project)
        self.display_results(results, query)
        return results

    def search_by_file(self, file):
        """Search sessions that modified specific file"""
        query = f"File: {file}"
        results = self.search(file=file)
        self.display_results(results, query)
        return results

    def search_by_date_range(self, date_from, date_to):
        """Search sessions by date range"""
        query = f"Date Range: {date_from or 'start'} to {date_to or 'end'}"
        results = self.search(date_from=date_from, date_to=date_to)
        self.display_results(results, query)
        return results

    def search_by_purpose(self, keyword):
        """Search sessions by purpose keyword"""
        query = f"Purpose keyword: {keyword}"
        results = self.search(purpose_keyword=keyword)
        self.display_results(results, query)
        return results


def main():
    """CLI interface"""

    parser = argparse.ArgumentParser(
        description="Search Claude Code sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search by tags
  python session-search.py --tags authentication jwt

  # Search by project
  python session-search.py --project surgricalswale

  # Search by file
  python session-search.py --file AuthController.java

  # Search by date range
  python session-search.py --date-from 2026-02-01 --date-to 2026-02-16

  # Search by purpose keyword
  python session-search.py --purpose authentication

  # Combined search
  python session-search.py --tags jwt --project surgricalswale --date-from 2026-02-01
"""
    )

    parser.add_argument('--tags', nargs='+', help='Tags to search for')
    parser.add_argument('--project', help='Project name to search')
    parser.add_argument('--file', help='File name to search')
    parser.add_argument('--date-from', help='Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)')
    parser.add_argument('--date-to', help='End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)')
    parser.add_argument('--purpose', help='Keyword in session purpose')

    if len(sys.argv) < 2:
        sys.exit(0)
    args = parser.parse_args()

    # Check if any search criteria provided
    if not any([args.tags, args.project, args.file, args.date_from, args.date_to, args.purpose]):
        parser.print_help()
        sys.exit(1)

    searcher = SessionSearch()

    # Build query description
    query_parts = []
    if args.tags:
        query_parts.append(f"Tags: {', '.join(args.tags)}")
    if args.project:
        query_parts.append(f"Project: {args.project}")
    if args.file:
        query_parts.append(f"File: {args.file}")
    if args.date_from or args.date_to:
        query_parts.append(f"Date: {args.date_from or 'start'} to {args.date_to or 'end'}")
    if args.purpose:
        query_parts.append(f"Purpose: {args.purpose}")

    query_desc = " AND ".join(query_parts)

    # Execute search
    results = searcher.search(
        tags=args.tags,
        project=args.project,
        file=args.file,
        date_from=args.date_from,
        date_to=args.date_to,
        purpose_keyword=args.purpose
    )

    searcher.display_results(results, query_desc)

    # Suggest loading a session
    if results:
        print(f"[BULB] To load a session:")
        print(f"   python session-loader.py load SESSION_ID\n")


if __name__ == "__main__":
    main()
