"""Authentication middleware for Bearer token validation."""

import hashlib
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.cache import cache
from app.database import get_db
from app.repositories.interfaces import ApiTokenEntity
from app.repositories.sqlalchemy import SQLAlchemyApiTokenRepository

security = HTTPBearer()

# Cache key template and TTL for token entities
CACHE_KEY_TOKEN = "token:{token_hash}"
TOKEN_CACHE_TTL = 300  # 5 minutes


def hash_token(token: str) -> str:
    """Hash a token using SHA256."""
    return hashlib.sha256(token.encode()).hexdigest()


def get_token_cache_key(token_hash: str) -> str:
    """Generate cache key for a token hash."""
    return CACHE_KEY_TOKEN.format(token_hash=token_hash)


def invalidate_token_cache(token_hash: str) -> None:
    """Invalidate cache for a specific token hash."""
    cache_key = get_token_cache_key(token_hash)
    cache.delete(cache_key)


def _validate_token(token_entity: Optional[ApiTokenEntity]) -> None:
    """Validate token entity (active, not expired)."""
    if not token_entity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not token_entity.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_entity.expires_at and token_entity.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db),
) -> ApiTokenEntity:
    """
    Verify the Bearer token from the request.

    Uses cache to avoid database queries on every request.
    Cache is invalidated when token is deactivated or deleted.

    Args:
        credentials: The HTTP authorization credentials containing the token.
        db: Database session.

    Returns:
        The validated ApiTokenEntity.

    Raises:
        HTTPException: If the token is invalid, inactive, or expired.
    """
    token = credentials.credentials
    token_hash = hash_token(token)
    cache_key = get_token_cache_key(token_hash)

    # Try to get from cache first
    token_entity: Optional[ApiTokenEntity] = cache.get(cache_key)

    if token_entity is None:
        # Cache miss - query database
        repo = SQLAlchemyApiTokenRepository(db)
        token_entity = repo.get_by_hash(token_hash)

        if token_entity:
            # Cache the token entity
            cache.set(cache_key, token_entity, TOKEN_CACHE_TTL)
            # Update last used timestamp (only on cache miss to reduce DB writes)
            repo.update_last_used(token_entity.id)

    # Always validate (expiration check is time-sensitive)
    _validate_token(token_entity)

    return token_entity
