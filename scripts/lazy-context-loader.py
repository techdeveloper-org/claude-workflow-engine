#!/usr/bin/env python3
"""
Lazy Context Loader - Solve Context Bloat Without Vector DB

Instead of loading ALL sessions/traces into memory:
- Keep only INDEX in memory (small, fast)
- Lazy load individual sessions on demand
- Cache recent N sessions
- Archive old sessions to disk
- Use quick lookups to find what's needed

This solves context bloat IMMEDIATELY while Vector DB is being built.

Version: 1.0.0
Author: Claude Memory System
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import OrderedDict

MEMORY_BASE = Path.home() / '.claude' / 'memory'
SESSIONS_DIR = MEMORY_BASE / 'sessions'
ARCHIVE_DIR = MEMORY_BASE / 'archive'
INDEX_FILE = MEMORY_BASE / 'session-index.json'
CACHE_MAX_SIZE = 5  # Keep max 5 sessions in memory


class LazyContextLoader:
    """Load context on-demand, not all at once."""

    def __init__(self):
        """Initialize with index only (not full data)."""
        self.index = self._load_index()  # Small: just metadata
        self.memory_cache = OrderedDict()  # LRU cache for recent sessions
        self.cache_max = CACHE_MAX_SIZE

    def _load_index(self):
        """Load session index (metadata only, not full data)."""
        if INDEX_FILE.exists():
            return json.loads(INDEX_FILE.read_text(encoding='utf-8'))
        
        # Build index if missing
        index = {'sessions': {}, 'last_updated': datetime.now().isoformat()}
        for session_file in SESSIONS_DIR.glob('*/session-state.json'):
            session_id = session_file.parent.name
            try:
                data = json.loads(session_file.read_text(encoding='utf-8'))
                index['sessions'][session_id] = {
                    'created': data.get('created_at', ''),
                    'last_accessed': data.get('last_accessed_at', ''),
                    'size_bytes': session_file.stat().st_size,
                    'cached': False
                }
            except Exception:
                pass
        
        return index

    def get_session(self, session_id):
        """Lazy load a session (from cache or disk)."""
        # Check memory cache first
        if session_id in self.memory_cache:
            # Move to end (LRU)
            self.memory_cache.move_to_end(session_id)
            return self.memory_cache[session_id]
        
        # Load from disk
        session_path = SESSIONS_DIR / session_id / 'session-state.json'
        if not session_path.exists():
            return None
        
        try:
            data = json.loads(session_path.read_text(encoding='utf-8'))
            
            # Add to cache (evict oldest if needed)
            if len(self.memory_cache) >= self.cache_max:
                evicted_id, _ = self.memory_cache.popitem(last=False)
                self.index['sessions'][evicted_id]['cached'] = False
            
            # Cache this session
            self.memory_cache[session_id] = data
            self.index['sessions'][session_id]['cached'] = True
            
            return data
        except Exception:
            return None

    def archive_old_sessions(self, days=30):
        """Archive sessions older than N days (frees memory)."""
        cutoff = datetime.now() - timedelta(days=days)
        archived = []
        
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        
        for session_id, metadata in self.index['sessions'].items():
            created = datetime.fromisoformat(metadata.get('created', ''))
            
            if created < cutoff:
                # Move to archive
                src = SESSIONS_DIR / session_id
                dst = ARCHIVE_DIR / session_id
                
                if src.exists():
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        src.rename(dst)
                        archived.append(session_id)
                        
                        # Remove from index
                        del self.index['sessions'][session_id]
                    except Exception:
                        pass
        
        return archived

    def get_context_stats(self):
        """Get memory usage stats."""
        total_sessions = len(self.index['sessions'])
        cached_sessions = sum(1 for m in self.index['sessions'].values() if m.get('cached'))
        total_size = sum(m.get('size_bytes', 0) for m in self.index['sessions'].values())
        
        return {
            'total_sessions': total_sessions,
            'cached_sessions': cached_sessions,
            'cache_max': self.cache_max,
            'total_size_kb': total_size // 1024,
            'index_size_kb': len(json.dumps(self.index)) // 1024,
            'memory_usage_percent': (cached_sessions / self.cache_max * 100) if self.cache_max > 0 else 0
        }

    def save_index(self):
        """Persist index to disk (call periodically)."""
        self.index['last_updated'] = datetime.now().isoformat()
        INDEX_FILE.write_text(json.dumps(self.index, indent=2), encoding='utf-8')


def main():
    """Demo: Show lazy loading in action."""
    loader = LazyContextLoader()
    
    print("=" * 70)
    print("LAZY CONTEXT LOADER v1.0 - Context Bloat Solution")
    print("=" * 70)
    print()
    
    stats = loader.get_context_stats()
    print(f"[INDEX] Total sessions: {stats['total_sessions']}")
    print(f"[CACHE] Cached in memory: {stats['cached_sessions']}/{stats['cache_max']}")
    print(f"[DISK] Total size: {stats['total_size_kb']} KB")
    print(f"[INDEX] Index size: {stats['index_size_kb']} KB")
    print(f"[MEMORY] Usage: {stats['memory_usage_percent']:.1f}%")
    print()
    
    # Archive old sessions
    print("[ARCHIVE] Archiving sessions older than 30 days...")
    archived = loader.archive_old_sessions(days=30)
    print(f"  Archived: {len(archived)} sessions")
    print()
    
    # Save index
    loader.save_index()
    print("[INDEX] Saved to ~/.claude/memory/session-index.json")
    print()
    print("[OK] Lazy loading active! Context bloat prevented.")


if __name__ == '__main__':
    main()
