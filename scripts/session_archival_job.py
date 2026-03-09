#!/usr/bin/env python3
"""Session Archival Job - Clean up old sessions to maintain bounded storage.

Phase 2: Run periodically to:
- Archive sessions older than 7 days
- Cleanup project summary files
- Remove stale session metadata
"""

import sys
from pathlib import Path

try:
    from ide_paths import MEMORY_BASE
except ImportError:
    MEMORY_BASE = Path.home() / '.claude' / 'memory'

try:
    from session_api import SessionAPI
    HAS_API = True
except ImportError:
    HAS_API = False


def run_archival():
    """Run session archival job."""
    if not HAS_API:
        return 0

    try:
        api = SessionAPI()
        
        # Archive sessions older than 7 days
        archived = api.archive_old_sessions(days=7)
        if archived > 0:
            sys.stderr.write(f"[ARCHIVAL] Archived {archived} old sessions\n")
        
        # Cleanup project summaries
        cleaned = api.cleanup_project_summaries(max_lines=100)
        if cleaned > 0:
            sys.stderr.write(f"[ARCHIVAL] Cleaned {cleaned} project summaries\n")
        
        # Rebuild session index
        api.index._build_index()
        
        return archived + cleaned
    except Exception as e:
        sys.stderr.write(f"[ARCHIVAL-ERROR] {str(e)[:100]}\n")
        return 0


if __name__ == '__main__':
    count = run_archival()
    sys.exit(0)  # Always exit 0, don't block anything
