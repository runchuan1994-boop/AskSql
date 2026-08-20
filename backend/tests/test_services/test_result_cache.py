"""ResultCache 单元测试."""
from __future__ import annotations

import time

import pytest

from app.services.result_cache import ResultCache


class TestResultCacheBasic:
    """基本功能测试."""

    def test_set_and_get(self):
        cache = ResultCache()
        cache.set("key1", {"data": "hello"})
        assert cache.get("key1") == {"data": "hello"}

    def test_get_missing_key_returns_none(self):
        cache = ResultCache()
        assert cache.get("nonexistent") is None

    def test_overwrite_existing_key(self):
        cache = ResultCache()
        cache.set("key1", {"data": "first"})
        cache.set("key1", {"data": "second"})
        assert cache.get("key1") == {"data": "second"}
        assert len(cache) == 1

    def test_delete(self):
        cache = ResultCache()
        cache.set("key1", {"data": "hello"})
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent_no_error(self):
        cache = ResultCache()
        cache.delete("nonexistent")  # should not raise

    def test_clear(self):
        cache = ResultCache()
        cache.set("key1", {"a": 1})
        cache.set("key2", {"b": 2})
        cache.clear()
        assert len(cache) == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_len(self):
        cache = ResultCache()
        assert len(cache) == 0
        cache.set("key1", {"a": 1})
        assert len(cache) == 1
        cache.set("key2", {"b": 2})
        assert len(cache) == 2
        cache.delete("key1")
        assert len(cache) == 1
        cache.clear()
        assert len(cache) == 0


class TestResultCacheLRU:
    """LRU 淘汰测试."""

    def test_max_size_eviction(self):
        cache = ResultCache(max_size=3)
        cache.set("key1", {"v": 1})
        cache.set("key2", {"v": 2})
        cache.set("key3", {"v": 3})
        assert len(cache) == 3

        # 插入第 4 个，应该淘汰最老的 key1
        cache.set("key4", {"v": 4})
        assert len(cache) == 3
        assert cache.get("key1") is None
        assert cache.get("key2") == {"v": 2}
        assert cache.get("key3") == {"v": 3}
        assert cache.get("key4") == {"v": 4}

    def test_get_updates_lru_order(self):
        cache = ResultCache(max_size=3)
        cache.set("key1", {"v": 1})
        cache.set("key2", {"v": 2})
        cache.set("key3", {"v": 3})

        # 访问 key1，使其变为最近使用
        assert cache.get("key1") == {"v": 1}

        # 插入 key4，应该淘汰 key2（现在最老）
        cache.set("key4", {"v": 4})
        assert cache.get("key2") is None
        assert cache.get("key1") == {"v": 1}
        assert cache.get("key3") == {"v": 3}
        assert cache.get("key4") == {"v": 4}

    def test_set_existing_key_updates_lru_order(self):
        cache = ResultCache(max_size=3)
        cache.set("key1", {"v": 1})
        cache.set("key2", {"v": 2})
        cache.set("key3", {"v": 3})

        # 重新 set key1，使其变为最近使用
        cache.set("key1", {"v": 10})

        # 插入 key4，应该淘汰 key2（现在最老）
        cache.set("key4", {"v": 4})
        assert cache.get("key2") is None
        assert cache.get("key1") == {"v": 10}
        assert cache.get("key3") == {"v": 3}
        assert cache.get("key4") == {"v": 4}


class TestResultCacheTTL:
    """TTL 过期测试."""

    def test_ttl_expiry(self):
        cache = ResultCache(ttl_seconds=1)
        cache.set("key1", {"data": "hello"})
        assert cache.get("key1") == {"data": "hello"}

        # 等待过期
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_ttl_expired_key_removed(self):
        cache = ResultCache(ttl_seconds=1)
        cache.set("key1", {"data": "hello"})
        time.sleep(1.1)

        # 过期后访问会被删除
        cache.get("key1")
        assert len(cache) == 0

    def test_no_ttl_for_new_cache(self):
        cache = ResultCache(ttl_seconds=3600)
        cache.set("key1", {"data": "hello"})
        # 刚设置的 key 不会立即过期
        assert cache.get("key1") is not None


class TestResultCacheThreadSafety:
    """线程安全基本测试."""

    def test_concurrent_set(self):
        import threading

        cache = ResultCache(max_size=1000)

        def worker(start: int, end: int):
            for i in range(start, end):
                cache.set(f"key_{i}", {"val": i})

        threads = [
            threading.Thread(target=worker, args=(0, 100)),
            threading.Thread(target=worker, args=(100, 200)),
            threading.Thread(target=worker, args=(200, 300)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(cache) == 300
        assert cache.get("key_0") == {"val": 0}
        assert cache.get("key_299") == {"val": 299}
