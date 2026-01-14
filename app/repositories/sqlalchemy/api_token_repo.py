"""SQLAlchemy implementation of ApiTokenRepository."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ApiToken
from app.repositories.interfaces import (
    ApiTokenRepository,
    ApiTokenEntity,
    ApiTokenInput,
)


class SQLAlchemyApiTokenRepository(ApiTokenRepository):
    """SQLAlchemy implementation of ApiTokenRepository."""

    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: ApiToken) -> ApiTokenEntity:
        """Convert SQLAlchemy model to entity."""
        return ApiTokenEntity(
            id=model.id,
            name=model.name,
            token_hash=model.token_hash,
            is_active=model.is_active,
            created_at=model.created_at,
            expires_at=model.expires_at,
            last_used_at=model.last_used_at,
        )

    def create(self, data: ApiTokenInput, token_hash: str) -> ApiTokenEntity:
        """Create a new API token."""
        db_token = ApiToken(
            name=data.name,
            token_hash=token_hash,
            expires_at=data.expires_at,
        )
        self.db.add(db_token)
        self.db.commit()
        self.db.refresh(db_token)
        return self._to_entity(db_token)

    def get_by_hash(self, token_hash: str) -> Optional[ApiTokenEntity]:
        """Get a token by its hash."""
        token = (
            self.db.query(ApiToken)
            .filter(ApiToken.token_hash == token_hash)
            .first()
        )
        return self._to_entity(token) if token else None

    def list_all(self) -> list[ApiTokenEntity]:
        """List all API tokens."""
        tokens = self.db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()
        return [self._to_entity(t) for t in tokens]

    def deactivate(self, token_id: int) -> bool:
        """Deactivate a token."""
        token = self.db.query(ApiToken).filter(ApiToken.id == token_id).first()
        if not token:
            return False
        token.is_active = False
        self.db.commit()
        return True

    def delete(self, token_id: int) -> bool:
        """Delete a token."""
        token = self.db.query(ApiToken).filter(ApiToken.id == token_id).first()
        if not token:
            return False
        self.db.delete(token)
        self.db.commit()
        return True

    def update_last_used(self, token_id: int) -> None:
        """Update the last_used_at timestamp."""
        token = self.db.query(ApiToken).filter(ApiToken.id == token_id).first()
        if token:
            token.last_used_at = datetime.utcnow()
            self.db.commit()
