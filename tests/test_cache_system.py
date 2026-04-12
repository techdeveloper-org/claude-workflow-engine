"""
Tests for cache_system.py - Multi-tier persistent caching for the 3-level pipeline.

ASCII-safe, UTF-8 encoded - Windows cp1252 compatible.
"""

import importlib.util
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Pre-import stubs
# ---------------------------------------------------------------------------


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


_stub("loguru", logger=MagicMock())

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
for _p in [_REPO_ROOT, _SCRIPTS]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

_LE_ROOT = Path(_REPO_ROOT) / "langgraph_engine"

# Stub langgraph_engine as a bare namespace (skip __init__.py)
_le = types.ModuleType("langgraph_engine")
_le.__path__ = [str(_LE_ROOT)]
_le.__package__ = "langgraph_engine"
sys.modules["langgraph_engine"] = _le


def _load_module(name, rel_path):
    full_path = _LE_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(full_path))
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "langgraph_engine"
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_cs_mod = _load_module("langgraph_engine.cache_system", "cache_system.py")

_MemoryLayer = _cs_mod._MemoryLayer
CacheTier = _cs_mod.CacheTier
PipelineCache = _cs_mod.PipelineCache
get_pipeline_cache = _cs_mod.get_pipeline_cache
cached_llm_call = _cs_mod.cached_llm_call
cached_file_read = _cs_mod.cached_file_read


def _reset_singleton():
    """Reset the module-level pipeline cache singleton between tests."""
    _cs_mod._pipeline_cache = None


# ---------------------------------------------------------------------------
# _MemoryLayer tests
# ---------------------------------------------------------------------------


class TestMemoryLayerSetGet:
    """test_memory_layer_set_get - Store and retrieve value."""

    def test_set_get_value(self):
        layer = _MemoryLayer(max_entries=10)
        layer.set("key1", {"answer": 42}, ttl_seconds=3600)
        assert layer.get("key1") == {"answer": 42}

    def test_get_missing_key_returns_none(self):
        layer = _MemoryLayer(max_entries=10)
        assert layer.get("nonexistent") is None


class TestMemoryLayerTtlExpiry:
    """test_memory_layer_ttl_expiry - Value expires after TTL."""

    def test_ttl_expiry(self):
        layer = _MemoryLayer(max_entries=10)
        with patch.object(_cs_mod, "_now_ts") as mock_ts:
            mock_ts.return_value = 1000.0
            layer.set("expiring", "value", ttl_seconds=10)

            mock_ts.return_value = 1005.0
            assert layer.get("expiring") == "value"

            mock_ts.return_value = 1015.0
            assert layer.get("expiring") is None


class TestMemoryLayerLruEviction:
    """test_memory_layer_lru_eviction - Oldest evicted when at max_entries."""

    def test_evicts_soonest_expiring_when_full(self):
        layer = _MemoryLayer(max_entries=3)
        # Keep mock active for both set AND get so TTL expiry check is frozen
        with patch.object(_cs_mod, "_now_ts") as mock_ts:
            mock_ts.return_value = 1000.0
            layer.set("a", "v_a", ttl_seconds=10)  # expires at 1010
            layer.set("b", "v_b", ttl_seconds=100)  # expires at 1100
            layer.set("c", "v_c", ttl_seconds=50)  # expires at 1050
            # 4th entry triggers eviction of "a" (smallest expiry = 1010)
            layer.set("d", "v_d", ttl_seconds=200)

            # Assertions inside mock scope so _now_ts() still returns 1000.0
            assert layer.get("a") is None  # evicted
            assert layer.get("b") == "v_b"
            assert layer.get("d") == "v_d"


# ---------------------------------------------------------------------------
# CacheTier tests
# ---------------------------------------------------------------------------


class TestCacheTierGetMiss:
    """test_cache_tier_get_miss - Returns None on cache miss."""

    def test_get_miss_returns_none(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        assert tier.get("nonexistent_key_xyz") is None

    def test_miss_increments_miss_counter(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        tier.get("miss1")
        tier.get("miss2")
        assert tier._misses == 2


class TestCacheTierSetGetHit:
    """test_cache_tier_set_get_hit - Store then retrieve = hit."""

    def test_set_then_get_returns_value(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        tier.set("key1", {"response": "hello"})
        assert tier.get("key1") == {"response": "hello"}

    def test_hit_increments_hit_counter(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        tier.set("k", "v")
        tier.get("k")
        assert tier._hits >= 1


class TestCacheTierDiskPersistence:
    """test_cache_tier_disk_persistence - Value survives memory clear (on disk)."""

    def test_disk_persistence_after_memory_clear(self, tmp_path):
        tier = CacheTier("file_analysis", ttl_seconds=86400, cache_base_dir=str(tmp_path))
        tier.set("persist_key", "persisted_value")
        tier._mem.clear()

        assert tier._mem.get("persist_key") is None
        assert tier.get("persist_key") == "persisted_value"


class TestCacheTierInvalidate:
    """test_cache_tier_invalidate - Removes from both memory and disk."""

    def test_invalidate_removes_entry(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        tier.set("to_remove", "some_value")
        tier.invalidate("to_remove")
        tier._mem.clear()
        assert tier.get("to_remove") is None


class TestCacheTierClearExpired:
    """test_cache_tier_clear_expired - Removes old entries from disk."""

    def test_clear_expired_removes_stale_files(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=10, cache_base_dir=str(tmp_path))
        from datetime import datetime, timedelta

        stale = {
            "key": "stale",
            "saved_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "ttl_seconds": 10,
            "value": "old",
        }
        stale_path = tier._disk_dir / "stale.json"
        stale_path.write_text(json.dumps(stale), encoding="utf-8")
        removed = tier.clear_expired()
        assert removed >= 1
        assert not stale_path.exists()

    def test_clear_expired_keeps_fresh_entries(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        tier.set("fresh", "fresh_value")
        assert tier.clear_expired() == 0
        assert tier.get("fresh") == "fresh_value"


class TestCacheTierHitRate:
    """test_cache_tier_hit_rate - Tracks hits/misses correctly."""

    def test_hit_rate_calculation(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        tier.set("key", "value")
        tier.get("key")  # hit
        tier.get("miss1")  # miss
        tier.get("miss2")  # miss
        tier.get("key")  # hit
        assert tier.hit_rate() == 0.5

    def test_hit_rate_zero_when_no_operations(self, tmp_path):
        tier = CacheTier("llm", ttl_seconds=3600, cache_base_dir=str(tmp_path))
        assert tier.hit_rate() == 0.0


class TestCacheTierStats:
    """test_cache_tier_stats - Returns complete stats dict."""

    def test_stats_returns_required_keys(self, tmp_path):
        tier = CacheTier("skill_defs", ttl_seconds=604800, cache_base_dir=str(tmp_path))
        tier.set("k", "v")
        tier.get("k")
        stats = tier.stats()
        assert stats["name"] == "skill_defs"
        assert stats["ttl_seconds"] == 604800
        for key in ("hits", "misses", "sets", "hit_rate", "memory"):
            assert key in stats


# ---------------------------------------------------------------------------
# Key derivation tests
# ---------------------------------------------------------------------------


class TestMakeLlmKeyDeterministic:
    """test_make_llm_key_deterministic - Same input = same key."""

    def test_same_input_same_key(self):
        messages = [{"role": "user", "content": "hello"}]
        key1 = CacheTier.make_llm_key("gpt-4", messages)
        key2 = CacheTier.make_llm_key("gpt-4", messages)
        assert key1 == key2

    def test_different_model_different_key(self):
        messages = [{"role": "user", "content": "hello"}]
        assert CacheTier.make_llm_key("gpt-4", messages) != CacheTier.make_llm_key("claude-3", messages)


class TestMakeFileKeyIncludesMtime:
    """test_make_file_key_includes_mtime - Key changes when file modified."""

    def test_key_changes_after_file_modification(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("# initial", encoding="utf-8")
        key1 = CacheTier.make_file_key(str(f))
        time.sleep(0.05)
        f.write_text("# modified with more data now", encoding="utf-8")
        key2 = CacheTier.make_file_key(str(f))
        assert key1 != key2

    def test_nonexistent_file_returns_string(self):
        key = CacheTier.make_file_key("/nonexistent/path/file.py")
        assert isinstance(key, str) and len(key) > 0


# ---------------------------------------------------------------------------
# PipelineCache tests
# ---------------------------------------------------------------------------


class TestPipelineCacheThreeTiers:
    """test_pipeline_cache_three_tiers - Has llm, file_analysis, skill_defs tiers."""

    def test_has_all_three_tiers(self, tmp_path):
        cache = PipelineCache(cache_base_dir=str(tmp_path))
        assert isinstance(cache.llm, CacheTier)
        assert isinstance(cache.file_analysis, CacheTier)
        assert isinstance(cache.skill_defs, CacheTier)

    def test_tier_names_correct(self, tmp_path):
        cache = PipelineCache(cache_base_dir=str(tmp_path))
        assert cache.llm.name == "llm"
        assert cache.file_analysis.name == "file_analysis"
        assert cache.skill_defs.name == "skill_defs"


class TestGetPipelineCacheSingleton:
    """test_get_pipeline_cache_singleton - Returns same instance."""

    def test_singleton_returns_same_instance(self, tmp_path):
        _reset_singleton()
        cache1 = get_pipeline_cache(cache_base_dir=str(tmp_path))
        cache2 = get_pipeline_cache(cache_base_dir=str(tmp_path))
        assert cache1 is cache2
        _reset_singleton()


# ---------------------------------------------------------------------------
# Integration helper tests
# ---------------------------------------------------------------------------


class TestCachedLlmCallUsesCache:
    """test_cached_llm_call_uses_cache - Cached call skips LLM on second call."""

    def test_second_call_skips_llm(self, tmp_path):
        _reset_singleton()
        cache = PipelineCache(cache_base_dir=str(tmp_path))
        call_count = 0

        def _fake_llm(model, messages):
            nonlocal call_count
            call_count += 1
            return {"message": {"content": "LLM response"}}

        messages = [{"role": "user", "content": "test prompt"}]
        result1 = cached_llm_call("test-model", messages, _fake_llm, cache=cache)
        result2 = cached_llm_call("test-model", messages, _fake_llm, cache=cache)
        assert call_count == 1
        assert result1 == result2
        _reset_singleton()

    def test_cache_miss_calls_llm(self, tmp_path):
        _reset_singleton()
        cache = PipelineCache(cache_base_dir=str(tmp_path))
        call_count = 0

        def _fake_llm(model, messages):
            nonlocal call_count
            call_count += 1
            return {"message": {"content": "fresh"}}

        cached_llm_call("model-x", [{"role": "user", "content": "new"}], _fake_llm, cache=cache)
        assert call_count == 1
        _reset_singleton()


class TestCachedFileRead:
    """test_cached_file_read - File read cached by path+mtime."""

    def test_second_read_uses_cache(self, tmp_path):
        _reset_singleton()
        cache = PipelineCache(cache_base_dir=str(tmp_path))
        f = tmp_path / "read_me.py"
        f.write_text("# some code", encoding="utf-8")
        read_count = 0

        def _fake_read(path):
            nonlocal read_count
            read_count += 1
            return "# some code"

        r1 = cached_file_read(str(f), _fake_read, cache=cache)
        r2 = cached_file_read(str(f), _fake_read, cache=cache)
        assert read_count == 1
        assert r1 == r2
        _reset_singleton()
