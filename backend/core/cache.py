"""
Simple in-memory cache with TTL support.

Provides a dict-based cache that auto-expires entries.
Thread-safe for basic concurrent access.
"""

import time
import threading
from typing import Any, Optional


class SimpleCache:
    """Dict-based cache with per-key TTL expiration."""

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Return cached value, or None if missing/expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() > entry["expires"]:
                del self._cache[key]
                return None
            return entry["value"]

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Store value with a TTL in seconds (default 300)."""
        with self._lock:
            self._cache[key] = {
                "value": value,
                "expires": time.time() + ttl,
            }

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._cache.clear()


# Module-level singleton for convenience
request_cache = SimpleCache()
