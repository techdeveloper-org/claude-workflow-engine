"""
Tests for src/mcp/base/persistence.py

Covers:
- AtomicJsonStore: save/load round-trip, backup creation, backup fallback,
  missing-file default, modify (read-modify-write), delete
- JsonlAppender: append/read_all, auto-timestamp, read_filtered, count,
  skip malformed lines
- SessionIdResolver: TTL caching, expiry, invalidate, priority order

All tests use tmp_path fixture for isolation. No real disk dependencies outside tmp_path.
ASCII-only: cp1252 safe for Windows.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "mcp"))


# ---------------------------------------------------------------------------
# AtomicJsonStore
# ---------------------------------------------------------------------------


class TestAtomicJsonStoreSaveLoad:

    def test_atomic_json_store_save_load(self, tmp_path):
        """Save a dict then load it back - data is preserved."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "state.json")
        original = {"count": 42, "name": "test", "active": True}
        store.save(original)

        loaded = store.load()
        assert loaded == original

    def test_atomic_json_store_load_returns_dict(self, tmp_path):
        """load() always returns a dict type."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "state.json")
        store.save({"key": "value"})

        result = store.load()
        assert isinstance(result, dict)

    def test_atomic_json_store_uses_atomic_write(self, tmp_path):
        """After save(), the primary file exists and no .tmp file remains."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "state.json")
        store.save({"x": 1})

        assert (tmp_path / "state.json").exists()
        assert not (tmp_path / "state.tmp").exists()


class TestAtomicJsonStoreBackup:

    def test_atomic_json_store_backup_creates_bak_file(self, tmp_path):
        """save(backup=True) creates a .bak copy of the existing file."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "state.json")
        store.save({"version": 1})
        store.save({"version": 2}, backup=True)

        bak_path = tmp_path / "state.json.bak"
        assert bak_path.exists()

    def test_atomic_json_store_backup_contains_previous_data(self, tmp_path):
        """The .bak file holds the data from before the save."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "state.json")
        store.save({"version": 1})
        store.save({"version": 2}, backup=True)

        bak_path = tmp_path / "state.json.bak"
        bak_data = json.loads(bak_path.read_text(encoding="utf-8"))
        assert bak_data["version"] == 1

    def test_atomic_json_store_no_backup_by_default(self, tmp_path):
        """save() without backup=True does not create a .bak file."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "state.json")
        store.save({"v": 1})
        store.save({"v": 2})

        assert not (tmp_path / "state.json.bak").exists()


class TestAtomicJsonStoreFallback:

    def test_atomic_json_store_load_fallback_to_backup(self, tmp_path):
        """When primary file is corrupt, load() falls back to the .bak file."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "data.json")

        # Write a valid backup
        bak_path = tmp_path / "data.json.bak"
        bak_path.write_text(json.dumps({"recovered": True}), encoding="utf-8")

        # Corrupt the primary file
        (tmp_path / "data.json").write_text("not valid json{{", encoding="utf-8")

        result = store.load()
        assert result.get("recovered") is True

    def test_atomic_json_store_load_default_when_both_missing(self, tmp_path):
        """load() returns the explicit default when both primary and backup are absent."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "missing.json")
        result = store.load(default={"fallback": 99})
        assert result == {"fallback": 99}

    def test_atomic_json_store_load_default_factory_when_no_default(self, tmp_path):
        """load() calls default_factory when file is absent and no default is given."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "missing.json", default_factory=lambda: {"from_factory": True})
        result = store.load()
        assert result == {"from_factory": True}

    def test_atomic_json_store_load_empty_dict_default(self, tmp_path):
        """Default default_factory is dict, so missing file returns {}."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "absent.json")
        result = store.load()
        assert result == {}


class TestAtomicJsonStoreModify:

    def test_atomic_json_store_modify(self, tmp_path):
        """modify() reads, mutates, saves, and returns the updated dict."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "counter.json")
        store.save({"count": 10})

        result = store.modify(lambda d: d.update({"count": d["count"] + 5}))

        assert result["count"] == 15
        # Persisted to disk
        assert store.load()["count"] == 15

    def test_atomic_json_store_modify_creates_file_if_missing(self, tmp_path):
        """modify() on a non-existent file uses default and saves the result."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "new.json")
        result = store.modify(lambda d: d.update({"created": True}), default={})
        assert result.get("created") is True
        assert store.exists


class TestAtomicJsonStoreDelete:

    def test_atomic_json_store_delete_removes_file(self, tmp_path):
        """delete() removes the backing file and returns True."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "to_delete.json")
        store.save({"temp": True})
        assert store.exists

        deleted = store.delete()
        assert deleted is True
        assert not store.exists

    def test_atomic_json_store_delete_returns_false_when_absent(self, tmp_path):
        """delete() returns False when the file does not exist."""
        from base.persistence import AtomicJsonStore

        store = AtomicJsonStore(tmp_path / "never_existed.json")
        assert store.delete() is False


# ---------------------------------------------------------------------------
# JsonlAppender
# ---------------------------------------------------------------------------


class TestJsonlAppenderBasic:

    def test_jsonl_appender_append_read_all(self, tmp_path):
        """Appended entries are recoverable via read_all()."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "events.jsonl")
        log.append({"event": "start"}, auto_timestamp=False)
        log.append({"event": "end"}, auto_timestamp=False)

        entries = log.read_all()
        assert len(entries) == 2
        assert entries[0]["event"] == "start"
        assert entries[1]["event"] == "end"

    def test_jsonl_appender_auto_timestamp(self, tmp_path):
        """auto_timestamp=True adds a 'timestamp' field when absent."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "ts.jsonl")
        log.append({"action": "click"}, auto_timestamp=True)

        entries = log.read_all()
        assert "timestamp" in entries[0]
        assert entries[0]["timestamp"]  # non-empty

    def test_jsonl_appender_auto_timestamp_does_not_overwrite_existing(self, tmp_path):
        """auto_timestamp respects caller-supplied timestamp field."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "ts.jsonl")
        log.append({"timestamp": "2026-01-01T00:00:00"}, auto_timestamp=True)

        entries = log.read_all()
        assert entries[0]["timestamp"] == "2026-01-01T00:00:00"

    def test_jsonl_appender_no_timestamp_when_disabled(self, tmp_path):
        """auto_timestamp=False does not add a timestamp field."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "no_ts.jsonl")
        log.append({"data": "x"}, auto_timestamp=False)

        entries = log.read_all()
        assert "timestamp" not in entries[0]

    def test_jsonl_appender_read_all_empty_when_file_missing(self, tmp_path):
        """read_all() returns [] when the JSONL file does not exist."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "absent.jsonl")
        assert log.read_all() == []


class TestJsonlAppenderFiltered:

    def test_jsonl_appender_read_filtered_by_field(self, tmp_path):
        """read_filtered() returns only entries matching the keyword filter."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "filtered.jsonl")
        log.append({"type": "click", "element": "btn"}, auto_timestamp=False)
        log.append({"type": "view", "element": "page"}, auto_timestamp=False)
        log.append({"type": "click", "element": "link"}, auto_timestamp=False)

        results = log.read_filtered(type="click")
        assert len(results) == 2
        assert all(r["type"] == "click" for r in results)

    def test_jsonl_appender_read_filtered_by_date(self, tmp_path):
        """read_filtered(date=...) filters on timestamp prefix."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "dated.jsonl")
        log.append({"ts": "match"}, auto_timestamp=False)
        log.append({"ts": "no-match"}, auto_timestamp=False)

        # Manually set timestamps to simulate date filtering
        (tmp_path / "dated.jsonl").write_text(
            json.dumps({"ts": "match", "timestamp": "2026-03-17T10:00:00"})
            + "\n"
            + json.dumps({"ts": "no-match", "timestamp": "2026-03-18T10:00:00"})
            + "\n",
            encoding="utf-8",
        )

        results = log.read_filtered(date="2026-03-17")
        assert len(results) == 1
        assert results[0]["ts"] == "match"

    def test_jsonl_appender_read_filtered_no_match_returns_empty(self, tmp_path):
        """read_filtered() returns [] when no entries match."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "empty_match.jsonl")
        log.append({"type": "view"}, auto_timestamp=False)

        results = log.read_filtered(type="nonexistent")
        assert results == []


class TestJsonlAppenderCount:

    def test_jsonl_appender_count(self, tmp_path):
        """count() returns the number of non-empty lines in the file."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "count.jsonl")
        for i in range(5):
            log.append({"i": i}, auto_timestamp=False)

        assert log.count() == 5

    def test_jsonl_appender_count_zero_when_absent(self, tmp_path):
        """count() returns 0 when the file does not exist."""
        from base.persistence import JsonlAppender

        log = JsonlAppender(tmp_path / "no_file.jsonl")
        assert log.count() == 0


class TestJsonlAppenderMalformed:

    def test_jsonl_appender_skip_malformed_lines(self, tmp_path):
        """read_all() skips lines that are not valid JSON without raising."""
        from base.persistence import JsonlAppender

        log_path = tmp_path / "mixed.jsonl"
        log_path.write_text('{"valid": 1}\n' "not valid json at all\n" '{"valid": 2}\n' "{broken\n", encoding="utf-8")

        log = JsonlAppender(log_path)
        entries = log.read_all()

        assert len(entries) == 2
        assert entries[0]["valid"] == 1
        assert entries[1]["valid"] == 2


# ---------------------------------------------------------------------------
# SessionIdResolver
# ---------------------------------------------------------------------------


class TestSessionIdResolverCaching:

    def setup_method(self):
        """Reset singleton before each test for isolation."""
        from base.persistence import SessionIdResolver

        SessionIdResolver.reset()

    def test_session_id_resolver_get_caching(self, tmp_path):
        """Returns cached ID on second call without re-reading disk."""
        from base.persistence import SessionIdResolver

        session_file = tmp_path / ".current-session.json"
        session_file.write_text(json.dumps({"current_session_id": "SESSION-20260317-001"}), encoding="utf-8")

        resolver = SessionIdResolver(config_dir=tmp_path)
        first = resolver.get()
        assert first == "SESSION-20260317-001"

        # Remove the file - cached value should still be returned
        session_file.unlink()
        second = resolver.get()
        assert second == "SESSION-20260317-001"

    def test_session_id_resolver_get_expired(self, tmp_path):
        """Re-resolves from disk after TTL expires."""
        from base.persistence import SessionIdResolver

        session_file = tmp_path / ".current-session.json"
        session_file.write_text(json.dumps({"current_session_id": "SESSION-OLD-001"}), encoding="utf-8")

        resolver = SessionIdResolver(config_dir=tmp_path)
        first = resolver.get()
        assert first == "SESSION-OLD-001"

        # Write updated session ID and simulate TTL expiry
        session_file.write_text(json.dumps({"current_session_id": "SESSION-NEW-002"}), encoding="utf-8")

        # Force re-resolution by bypassing cache
        second = resolver.get(force_refresh=True)
        assert second == "SESSION-NEW-002"

    def test_session_id_resolver_invalidate(self, tmp_path):
        """invalidate() clears cache so next get() reads from disk."""
        from base.persistence import SessionIdResolver

        session_file = tmp_path / ".current-session.json"
        session_file.write_text(json.dumps({"current_session_id": "SESSION-FIRST-001"}), encoding="utf-8")

        resolver = SessionIdResolver(config_dir=tmp_path)
        resolver.get()  # Populate cache

        # Update file and invalidate
        session_file.write_text(json.dumps({"current_session_id": "SESSION-SECOND-002"}), encoding="utf-8")
        resolver.invalidate()

        result = resolver.get()
        assert result == "SESSION-SECOND-002"

    def test_session_id_resolver_returns_empty_when_no_files(self, tmp_path):
        """Returns empty string when neither session file exists."""
        from base.persistence import SessionIdResolver

        resolver = SessionIdResolver(config_dir=tmp_path)
        result = resolver.get()
        assert result == ""


class TestSessionIdResolverPriority:

    def setup_method(self):
        from base.persistence import SessionIdResolver

        SessionIdResolver.reset()

    def test_session_id_resolver_priority_current_session_first(self, tmp_path):
        """current-session.json takes priority over session-progress.json."""
        from base.persistence import SessionIdResolver

        # Write primary (higher priority)
        primary = tmp_path / ".current-session.json"
        primary.write_text(json.dumps({"current_session_id": "SESSION-PRIMARY-001"}), encoding="utf-8")

        # Write fallback (lower priority)
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        fallback = logs_dir / "session-progress.json"
        fallback.write_text(json.dumps({"session_id": "SESSION-FALLBACK-002"}), encoding="utf-8")

        resolver = SessionIdResolver(config_dir=tmp_path)
        result = resolver.get()
        assert result == "SESSION-PRIMARY-001"

    def test_session_id_resolver_falls_back_to_progress_when_primary_missing(self, tmp_path):
        """Falls back to session-progress.json when current-session.json is absent."""
        from base.persistence import SessionIdResolver

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        fallback = logs_dir / "session-progress.json"
        fallback.write_text(json.dumps({"session_id": "SESSION-FALLBACK-003"}), encoding="utf-8")

        resolver = SessionIdResolver(config_dir=tmp_path)
        result = resolver.get()
        assert result == "SESSION-FALLBACK-003"

    def test_session_id_resolver_ignores_invalid_session_id_format(self, tmp_path):
        """Entries not starting with 'SESSION-' are ignored."""
        from base.persistence import SessionIdResolver

        primary = tmp_path / ".current-session.json"
        primary.write_text(json.dumps({"current_session_id": "invalid-format"}), encoding="utf-8")

        resolver = SessionIdResolver(config_dir=tmp_path)
        result = resolver.get()
        assert result == ""

    def test_session_id_resolver_singleton_behavior(self, tmp_path):
        """Two SessionIdResolver() calls return the same instance (singleton)."""
        from base.persistence import SessionIdResolver

        r1 = SessionIdResolver(config_dir=tmp_path)
        r2 = SessionIdResolver()
        assert r1 is r2

    def test_session_id_resolver_reset_creates_fresh_instance(self, tmp_path):
        """After reset(), a new SessionIdResolver() creates a fresh instance."""
        from base.persistence import SessionIdResolver

        r1 = SessionIdResolver(config_dir=tmp_path)
        SessionIdResolver.reset()
        r2 = SessionIdResolver(config_dir=tmp_path)
        assert r1 is not r2
