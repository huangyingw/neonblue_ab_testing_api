"""Authentication middleware for Bearer token validation."""

import hashlib
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.interfaces import ApiTokenRepository, ApiTokenEntity
from app.repositories.sqlalchemy import SQLAlchemyApiTokenRepository

security = HTTPBearer()


def hash_token(token: str) -> str:
    """Hash a token using SHA256."""
    return hashlib.sha256(token.encode()).hexdigest()


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

    repo = SQLAlchemyApiTokenRepository(db)
    token_entity = repo.get_by_hash(token_hash)

    _validate_token(token_entity)

    # Update last used timestamp
    repo.update_last_used(token_entity.id)

    return token_entity
