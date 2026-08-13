"""Small process-local cache for the demo.

The cache API is deliberately independent from LangGraph so it can later be
replaced by Redis without changing the tools or graph nodes.
"""

import threading
import time

_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_LOCK = threading.Lock()


def cache_get(namespace: str, key: str, ttl_seconds: int) -> str | None:
    with _LOCK:
        item = _CACHE.get((namespace, key))
        if not item:
            return None
        created_at, value = item
        if time.monotonic() - created_at > ttl_seconds:
            _CACHE.pop((namespace, key), None)
            return None
        return value


def cache_set(namespace: str, key: str, value: str) -> None:
    with _LOCK:
        _CACHE[(namespace, key)] = (time.monotonic(), value)


def cache_items(ttl_seconds: int = 900, namespace: str | None = None) -> list[dict[str, object]]:
    """Return a safe snapshot of live cache entries for the cache-index tool."""
    now = time.monotonic()
    items: list[dict[str, object]] = []
    with _LOCK:
        expired = []
        for (item_namespace, key), (created_at, value) in _CACHE.items():
            if now - created_at > ttl_seconds:
                expired.append((item_namespace, key))
                continue
            if namespace and item_namespace != namespace:
                continue
            items.append(
                {
                    "namespace": item_namespace,
                    "key": key,
                    "value": value,
                    "age_seconds": round(now - created_at, 3),
                }
            )
        for item_key in expired:
            _CACHE.pop(item_key, None)
    return items


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()
