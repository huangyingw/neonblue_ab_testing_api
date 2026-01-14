"""Unit tests for token caching behavior.

These tests verify that:
1. Token verification uses cache when available (cache hit)
2. Token verification queries database on cache miss
3. Cache is invalidated when token is deactivated/deleted
4. Expired cache entries are refreshed from database
"""

import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.auth import (
    hash_token,
    verify_token,
    get_token_cache_key,
    invalidate_token_cache,
    TOKEN_CACHE_TTL,
)
from app.cache import cache
from app.repositories.interfaces import ApiTokenEntity


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


class TestTokenCacheKey:
    """Tests for cache key generation."""

    def test_cache_key_format(self):
        """Test that cache key is generated correctly."""
        token_hash = "abc123"
        key = get_token_cache_key(token_hash)
        assert key == "token:abc123"

    def test_different_hashes_produce_different_keys(self):
        """Test that different token hashes produce different cache keys."""
        key1 = get_token_cache_key("hash1")
        key2 = get_token_cache_key("hash2")
        assert key1 != key2


class TestTokenCacheInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_removes_cached_token(self):
        """Test that invalidate_token_cache removes the token from cache."""
        token_hash = "test_hash"
        cache_key = get_token_cache_key(token_hash)

        # Add token to cache
        mock_entity = ApiTokenEntity(
            id=1,
            name="Test",
            token_hash=token_hash,
            is_active=True,
            created_at=datetime.utcnow(),
            expires_at=None,
            last_used_at=None,
        )
        cache.set(cache_key, mock_entity, TOKEN_CACHE_TTL)

        # Verify it's in cache
        assert cache.get(cache_key) is not None

        # Invalidate
        invalidate_token_cache(token_hash)

        # Verify it's removed
        assert cache.get(cache_key) is None

    def test_invalidate_nonexistent_token_does_not_error(self):
        """Test that invalidating a non-cached token doesn't raise an error."""
        # Should not raise any exception
        invalidate_token_cache("nonexistent_hash")


class TestTokenCacheBehavior:
    """Tests for token caching in verify_token function."""

    def _create_mock_token_entity(
        self,
        token_id: int = 1,
        is_active: bool = True,
        expires_at: datetime = None,
    ) -> ApiTokenEntity:
        """Helper to create a mock token entity."""
        return ApiTokenEntity(
            id=token_id,
            name="Test Token",
            token_hash=hash_token("test-token"),
            is_active=is_active,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            last_used_at=None,
        )

    @patch("app.auth.SQLAlchemyApiTokenRepository")
    def test_cache_miss_queries_database(self, mock_repo_class):
        """Test that cache miss triggers database query."""
        token = "test-token"
        token_hash = hash_token(token)
        mock_entity = self._create_mock_token_entity()

        # Setup mock repository
        mock_repo = Mock()
        mock_repo.get_by_hash.return_value = mock_entity
        mock_repo_class.return_value = mock_repo

        # Create mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Create mock db session
        mock_db = Mock()

        # Call verify_token
        result = verify_token(mock_credentials, mock_db)

        # Verify database was queried
        mock_repo.get_by_hash.assert_called_once_with(token_hash)
        mock_repo.update_last_used.assert_called_once()
        assert result.id == mock_entity.id

    @patch("app.auth.SQLAlchemyApiTokenRepository")
    def test_cache_hit_skips_database(self, mock_repo_class):
        """Test that cache hit skips database query."""
        token = "test-token"
        token_hash = hash_token(token)
        cache_key = get_token_cache_key(token_hash)
        mock_entity = self._create_mock_token_entity()

        # Pre-populate cache
        cache.set(cache_key, mock_entity, TOKEN_CACHE_TTL)

        # Setup mock repository (should not be called)
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        # Create mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Create mock db session
        mock_db = Mock()

        # Call verify_token
        result = verify_token(mock_credentials, mock_db)

        # Verify database was NOT queried
        mock_repo.get_by_hash.assert_not_called()
        mock_repo.update_last_used.assert_not_called()
        assert result.id == mock_entity.id

    @patch("app.auth.SQLAlchemyApiTokenRepository")
    def test_cache_stores_token_after_db_query(self, mock_repo_class):
        """Test that token is cached after database query."""
        token = "test-token"
        token_hash = hash_token(token)
        cache_key = get_token_cache_key(token_hash)
        mock_entity = self._create_mock_token_entity()

        # Setup mock repository
        mock_repo = Mock()
        mock_repo.get_by_hash.return_value = mock_entity
        mock_repo_class.return_value = mock_repo

        # Create mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Create mock db session
        mock_db = Mock()

        # Verify cache is empty
        assert cache.get(cache_key) is None

        # Call verify_token
        verify_token(mock_credentials, mock_db)

        # Verify token is now cached
        cached_entity = cache.get(cache_key)
        assert cached_entity is not None
        assert cached_entity.id == mock_entity.id

    @patch("app.auth.SQLAlchemyApiTokenRepository")
    def test_second_request_uses_cache(self, mock_repo_class):
        """Test that second request with same token uses cache."""
        token = "test-token"
        mock_entity = self._create_mock_token_entity()

        # Setup mock repository
        mock_repo = Mock()
        mock_repo.get_by_hash.return_value = mock_entity
        mock_repo_class.return_value = mock_repo

        # Create mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Create mock db session
        mock_db = Mock()

        # First request - should query database
        verify_token(mock_credentials, mock_db)
        assert mock_repo.get_by_hash.call_count == 1

        # Second request - should use cache
        verify_token(mock_credentials, mock_db)
        assert mock_repo.get_by_hash.call_count == 1  # Still 1, not 2

        # Third request - should still use cache
        verify_token(mock_credentials, mock_db)
        assert mock_repo.get_by_hash.call_count == 1  # Still 1

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL."""
        token_hash = "test_hash"
        cache_key = get_token_cache_key(token_hash)
        mock_entity = ApiTokenEntity(
            id=1,
            name="Test",
            token_hash=token_hash,
            is_active=True,
            created_at=datetime.utcnow(),
            expires_at=None,
            last_used_at=None,
        )

        # Set with very short TTL
        cache.set(cache_key, mock_entity, ttl=1)

        # Immediately should be in cache
        assert cache.get(cache_key) is not None

        # Wait for TTL to expire
        time.sleep(1.1)

        # Should be expired now
        assert cache.get(cache_key) is None

    @patch("app.auth.SQLAlchemyApiTokenRepository")
    def test_expired_cache_triggers_db_query(self, mock_repo_class):
        """Test that expired cache entry triggers new database query."""
        token = "test-token"
        token_hash = hash_token(token)
        cache_key = get_token_cache_key(token_hash)
        mock_entity = self._create_mock_token_entity()

        # Pre-populate cache with very short TTL
        cache.set(cache_key, mock_entity, ttl=1)

        # Setup mock repository
        mock_repo = Mock()
        mock_repo.get_by_hash.return_value = mock_entity
        mock_repo_class.return_value = mock_repo

        # Create mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Create mock db session
        mock_db = Mock()

        # First request - should use cache
        verify_token(mock_credentials, mock_db)
        assert mock_repo.get_by_hash.call_count == 0  # Cache hit

        # Wait for cache to expire
        time.sleep(1.1)

        # Second request - should query database
        verify_token(mock_credentials, mock_db)
        assert mock_repo.get_by_hash.call_count == 1  # Cache miss, DB query


class TestTokenCacheWithDeactivation:
    """Tests for cache behavior when tokens are deactivated."""

    @patch("app.auth.SQLAlchemyApiTokenRepository")
    def test_deactivated_token_in_cache_is_rejected(self, mock_repo_class):
        """Test that a deactivated token in cache is still rejected."""
        token = "test-token"
        token_hash = hash_token(token)
        cache_key = get_token_cache_key(token_hash)

        # Create a deactivated token entity
        deactivated_entity = ApiTokenEntity(
            id=1,
            name="Deactivated Token",
            token_hash=token_hash,
            is_active=False,  # Deactivated
            created_at=datetime.utcnow(),
            expires_at=None,
            last_used_at=None,
        )

        # Pre-populate cache with deactivated token
        cache.set(cache_key, deactivated_entity, TOKEN_CACHE_TTL)

        # Create mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Create mock db session
        mock_db = Mock()

        # Should raise HTTPException for deactivated token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_token(mock_credentials, mock_db)

        assert exc_info.value.status_code == 401
        assert "deactivated" in exc_info.value.detail.lower()

    @patch("app.auth.SQLAlchemyApiTokenRepository")
    def test_expired_token_in_cache_is_rejected(self, mock_repo_class):
        """Test that an expired token in cache is still rejected."""
        token = "test-token"
        token_hash = hash_token(token)
        cache_key = get_token_cache_key(token_hash)

        # Create an expired token entity
        expired_entity = ApiTokenEntity(
            id=1,
            name="Expired Token",
            token_hash=token_hash,
            is_active=True,
            created_at=datetime.utcnow() - timedelta(days=30),
            expires_at=datetime.utcnow() - timedelta(days=1),  # Expired
            last_used_at=None,
        )

        # Pre-populate cache with expired token
        cache.set(cache_key, expired_entity, TOKEN_CACHE_TTL)

        # Create mock credentials
        mock_credentials = Mock()
        mock_credentials.credentials = token

        # Create mock db session
        mock_db = Mock()

        # Should raise HTTPException for expired token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_token(mock_credentials, mock_db)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()
