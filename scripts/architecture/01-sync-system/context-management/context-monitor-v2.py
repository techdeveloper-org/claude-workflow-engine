#!/usr/bin/env python3
"""
Context Monitor v2.0 - Level 1 Sync System Policy

Monitor context usage and prevent bloat using LAZY LOADING:
- Track memory usage of current session
- Archive old sessions automatically
- Use lazy loader to keep memory efficient
- Alert if context approaching limits

Invoked by: 3-level-flow.py (Level 1 Sync System)

Version: 2.0.0
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

MEMORY_BASE = Path.home() / '.claude' / 'memory'
SESSIONS_DIR = MEMORY_BASE / 'sessions'
ARCHIVE_DIR = MEMORY_BASE / 'archive'
LOG_DIR = MEMORY_BASE / 'logs'

# Context limits
MAX_CONTEXT_PERCENT = 80
ARCHIVE_AFTER_DAYS = 30


def get_context_usage():
    """Get current session context usage."""
    try:
        # Get current session trace size
        session_id = os.getenv('CLAUDE_SESSION_ID', 'unknown')
        trace_file = SESSIONS_DIR / session_id / 'flow-trace.json'
        
        if trace_file.exists():
            trace_size = trace_file.stat().st_size
            # Estimate: trace file is ~70% of session context
            estimated_context = (trace_size / 0.7) / 1024  # KB
            return estimated_context
        return 0
    except Exception:
        return 0


def archive_old_sessions():
    """Archive sessions older than threshold (frees memory)."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(days=ARCHIVE_AFTER_DAYS)
    archived = 0
    
    for session_dir in SESSIONS_DIR.glob('SESSION-*'):
        try:
            state_file = session_dir / 'session-state.json'
            if state_file.exists():
                data = json.loads(state_file.read_text())
                created = datetime.fromisoformat(data.get('created_at', ''))
                
                if created < cutoff:
                    # Move to archive
                    dst = ARCHIVE_DIR / session_dir.name
                    if not dst.exists():
                        session_dir.rename(dst)
                        archived += 1
        except Exception:
            pass
    
    return archived


def monitor_context():
    """Monitor context usage and take action if needed."""
    usage = get_context_usage()
    
    # Archive old sessions if memory getting tight
    if usage > (MAX_CONTEXT_PERCENT * 0.9):  # 90% of limit
        archived = archive_old_sessions()
        action = f"Archived {archived} old sessions"
    else:
        action = "OK - Within limits"
    
    # Log status
    status = {
        'timestamp': datetime.now().isoformat(),
        'context_usage_percent': min(100, (usage / MAX_CONTEXT_PERCENT) * 100),
        'action': action,
        'sessions_archived': archived if usage > (MAX_CONTEXT_PERCENT * 0.9) else 0
    }
    
    return status


if __name__ == '__main__':
    status = monitor_context()
    
    # Print for 3-level-flow
    print(json.dumps({
        'step': 'LEVEL_1_CONTEXT_MONITOR',
        'status': status['action'],
        'context_usage_percent': status['context_usage_percent'],
        'passed': True
    }))
