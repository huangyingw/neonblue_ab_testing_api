"""Unit tests for the Cache module."""

import time
import pytest
from app.cache import Cache, cached


class TestCache:
    """Tests for Cache class."""

    def test_set_and_get(self):
        cache = Cache(default_ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        cache = Cache(default_ttl=60)
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        cache = Cache(default_ttl=60)
        cache.set("expire_key", "value", ttl=1)  # 1 second TTL
        assert cache.get("expire_key") == "value"
        time.sleep(1.1)  # Wait for expiration
        assert cache.get("expire_key") is None

    def test_delete_existing_key(self):
        cache = Cache(default_ttl=60)
        cache.set("delete_key", "value")
        assert cache.delete("delete_key") is True
        assert cache.get("delete_key") is None

    def test_delete_nonexistent_key(self):
        cache = Cache(default_ttl=60)
        assert cache.delete("nonexistent") is False

    def test_clear(self):
        cache = Cache(default_ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_invalidate_pattern(self):
        cache = Cache(default_ttl=60)
        cache.set("user:1:name", "Alice")
        cache.set("user:1:email", "alice@example.com")
        cache.set("user:2:name", "Bob")
        cache.set("product:1:name", "Widget")

        # Invalidate all keys starting with "user:1:"
        count = cache.invalidate_pattern("user:1:")
        assert count == 2
        assert cache.get("user:1:name") is None
        assert cache.get("user:1:email") is None
        assert cache.get("user:2:name") == "Bob"
        assert cache.get("product:1:name") == "Widget"

    def test_invalidate_pattern_no_matches(self):
        cache = Cache(default_ttl=60)
        cache.set("key1", "value1")
        count = cache.invalidate_pattern("nonexistent:")
        assert count == 0
        assert cache.get("key1") == "value1"

    def test_default_ttl(self):
        cache = Cache(default_ttl=1)
        cache.set("key", "value")  # Uses default TTL
        assert cache.get("key") == "value"
        time.sleep(1.1)
        assert cache.get("key") is None

    def test_overwrite_value(self):
        cache = Cache(default_ttl=60)
        cache.set("key", "value1")
        cache.set("key", "value2")
        assert cache.get("key") == "value2"

    def test_complex_value_types(self):
        cache = Cache(default_ttl=60)

        # Dict
        cache.set("dict_key", {"name": "test", "count": 42})
        assert cache.get("dict_key") == {"name": "test", "count": 42}

        # List
        cache.set("list_key", [1, 2, 3, "four"])
        assert cache.get("list_key") == [1, 2, 3, "four"]

        # Nested structure
        cache.set("nested_key", {"items": [{"id": 1}, {"id": 2}]})
        assert cache.get("nested_key")["items"][0]["id"] == 1


class TestCachedDecorator:
    """Tests for the @cached decorator."""

    def test_cached_decorator_basic(self):
        cache = Cache(default_ttl=60)
        # Replace global cache temporarily
        import app.cache as cache_module
        original_cache = cache_module.cache
        cache_module.cache = cache

        call_count = 0

        @cached("test_key", ttl=60)
        def expensive_function():
            nonlocal call_count
            call_count += 1
            return "result"

        # First call - should execute function
        result1 = expensive_function()
        assert result1 == "result"
        assert call_count == 1

        # Second call - should return cached result
        result2 = expensive_function()
        assert result2 == "result"
        assert call_count == 1  # Function not called again

        # Restore original cache
        cache_module.cache = original_cache

    def test_cached_decorator_with_kwargs(self):
        cache = Cache(default_ttl=60)
        import app.cache as cache_module
        original_cache = cache_module.cache
        cache_module.cache = cache

        call_count = 0

        @cached("user:{user_id}", ttl=60)
        def get_user(user_id=None):
            nonlocal call_count
            call_count += 1
            return f"User {user_id}"

        result1 = get_user(user_id="123")
        assert result1 == "User 123"
        assert call_count == 1

        result2 = get_user(user_id="123")
        assert result2 == "User 123"
        assert call_count == 1

        cache_module.cache = original_cache
