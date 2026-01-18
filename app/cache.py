"""Simple in-memory cache with TTL support."""

import time
from typing import Any, Optional
from functools import wraps
from threading import Lock


class Cache:
    """Thread-safe in-memory cache with TTL (time-to-live) support."""

    def __init__(self, default_ttl: int = 300):
        """
        Initialize cache.

        Args:
            default_ttl: Default time-to-live in seconds (default: 5 minutes)
        """
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = Lock()
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        with self._lock:
            if key not in self._cache:
                return None

            value, expires_at = self._cache[key]
            if time.time() > expires_at:
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern prefix.

        Args:
            pattern: Key prefix to match

        Returns:
            Number of keys invalidated
        """
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)


# Global cache instance
cache = Cache(default_ttl=300)


# Cache keys
CACHE_KEY_ASSIGNMENT = "assignment:{experiment_id}:{user_id}"
CACHE_KEY_FEATURE_FLAG = "feature_flag:{key}"
CACHE_KEY_FLAG_EVALUATION = "flag_eval:{key}:{user_id}"


def get_flag_cache_pattern(key: str) -> str:
    """Get cache invalidation pattern for a feature flag."""
    return f"feature_flag:{key}"


def get_flag_eval_cache_pattern(key: str) -> str:
    """Get cache invalidation pattern for all evaluations of a feature flag."""
    return f"flag_eval:{key}:"


def cached(key_template: str, ttl: int = 300):
    """
    Decorator for caching function results.

    Args:
        key_template: Cache key template with placeholders for function arguments
        ttl: Time-to-live in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from template and arguments
            # This is a simple implementation - in production, use proper key building
            cache_key = key_template.format(**kwargs) if kwargs else key_template

            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        return wrapper
    return decorator
