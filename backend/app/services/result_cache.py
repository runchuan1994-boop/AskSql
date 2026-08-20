"""查询结果缓存服务.

用于支撑表格分页功能 — 全量结果存在内存缓存中，
前端通过分页接口逐页获取.

TTL: 默认 30 分钟.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock


class ResultCache:
    """带 TTL 的 LRU 结果缓存.

    线程安全，使用 OrderedDict 实现 LRU.
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 1800):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = Lock()

    def set(self, key: str, value: dict) -> None:
        """存入缓存."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + self._ttl,
            }
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def get(self, key: str) -> dict | None:
        """获取缓存，过期返回 None."""
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            if time.time() > item["expires_at"]:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return item["value"]

    def delete(self, key: str) -> None:
        """删除缓存."""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# 全局实例
result_cache = ResultCache(max_size=200, ttl_seconds=1800)
