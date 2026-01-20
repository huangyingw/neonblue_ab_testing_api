"""SQLAlchemy implementation of FeatureFlagRepository."""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import FeatureFlag, FeatureFlagOverride, FeatureFlagRolloutAssignment
from app.repositories.interfaces import (
    FeatureFlagRepository,
    FeatureFlagEntity,
    FeatureFlagInput,
    FeatureFlagUpdateInput,
    FeatureFlagOverrideEntity,
    FeatureFlagRolloutAssignmentEntity,
)


class SQLAlchemyFeatureFlagRepository(FeatureFlagRepository):
    """SQLAlchemy implementation of feature flag repository."""

    def __init__(self, session: Session):
        self._session = session

    def _to_entity(self, model: FeatureFlag) -> FeatureFlagEntity:
        """Convert SQLAlchemy model to entity."""
        return FeatureFlagEntity(
            id=model.id,
            key=model.key,
            name=model.name,
            description=model.description,
            enabled=model.enabled,
            rollout_percentage=model.rollout_percentage,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_override_entity(self, model: FeatureFlagOverride) -> FeatureFlagOverrideEntity:
        """Convert SQLAlchemy model to entity."""
        return FeatureFlagOverrideEntity(
            id=model.id,
            feature_flag_id=model.feature_flag_id,
            user_id=model.user_id,
            enabled=model.enabled,
            created_at=model.created_at,
        )

    def create(self, data: FeatureFlagInput) -> FeatureFlagEntity:
        """Create a new feature flag."""
        model = FeatureFlag(
            key=data.key,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
            rollout_percentage=data.rollout_percentage,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)

        return self._to_entity(model)

    def get_by_key(self, key: str) -> Optional[FeatureFlagEntity]:
        """Get a feature flag by key."""
        model = (
            self._session.query(FeatureFlag)
            .filter(FeatureFlag.key == key)
            .first()
        )
        if not model:
            return None
        return self._to_entity(model)

    def list_all(self) -> list[FeatureFlagEntity]:
        """List all feature flags."""
        models = (
            self._session.query(FeatureFlag)
            .order_by(FeatureFlag.key)
            .all()
        )
        return [self._to_entity(m) for m in models]

    def update(
        self, key: str, data: FeatureFlagUpdateInput
    ) -> Optional[FeatureFlagEntity]:
        """Update a feature flag."""
        model = (
            self._session.query(FeatureFlag)
            .filter(FeatureFlag.key == key)
            .first()
        )
        if not model:
            return None

        if data.name is not None:
            model.name = data.name
        if data.description is not None:
            model.description = data.description
        if data.enabled is not None:
            model.enabled = data.enabled
        if data.rollout_percentage is not None:
            model.rollout_percentage = data.rollout_percentage

        self._session.commit()
        self._session.refresh(model)

        return self._to_entity(model)

    def delete(self, key: str) -> bool:
        """Delete a feature flag. Returns True if deleted."""
        model = (
            self._session.query(FeatureFlag)
            .filter(FeatureFlag.key == key)
            .first()
        )
        if not model:
            return False

        self._session.delete(model)
        self._session.commit()
        return True

    def get_user_override(
        self, flag_id: int, user_id: str
    ) -> Optional[FeatureFlagOverrideEntity]:
        """Get user-specific override for a flag."""
        model = (
            self._session.query(FeatureFlagOverride)
            .filter(
                FeatureFlagOverride.feature_flag_id == flag_id,
                FeatureFlagOverride.user_id == user_id,
            )
            .first()
        )
        if not model:
            return None
        return self._to_override_entity(model)

    def set_user_override(self, flag_id: int, user_id: str, enabled: bool) -> None:
        """Create or update a user-specific override."""
        existing = (
            self._session.query(FeatureFlagOverride)
            .filter(
                FeatureFlagOverride.feature_flag_id == flag_id,
                FeatureFlagOverride.user_id == user_id,
            )
            .first()
        )

        if existing:
            existing.enabled = enabled
        else:
            model = FeatureFlagOverride(
                feature_flag_id=flag_id,
                user_id=user_id,
                enabled=enabled,
            )
            self._session.add(model)

        self._session.commit()

    def delete_user_override(self, flag_id: int, user_id: str) -> bool:
        """Delete a user-specific override. Returns True if deleted."""
        model = (
            self._session.query(FeatureFlagOverride)
            .filter(
                FeatureFlagOverride.feature_flag_id == flag_id,
                FeatureFlagOverride.user_id == user_id,
            )
            .first()
        )

        if model:
            self._session.delete(model)
            self._session.commit()
            return True
        return False

    def _to_rollout_assignment_entity(
        self, model: FeatureFlagRolloutAssignment
    ) -> FeatureFlagRolloutAssignmentEntity:
        """Convert SQLAlchemy model to entity."""
        return FeatureFlagRolloutAssignmentEntity(
            id=model.id,
            feature_flag_id=model.feature_flag_id,
            user_id=model.user_id,
            enabled=model.enabled,
            assigned_at=model.assigned_at,
        )

    def get_rollout_assignment(
        self, flag_id: int, user_id: str
    ) -> Optional[FeatureFlagRolloutAssignmentEntity]:
        """Get existing rollout assignment for a user."""
        model = (
            self._session.query(FeatureFlagRolloutAssignment)
            .filter(
                FeatureFlagRolloutAssignment.feature_flag_id == flag_id,
                FeatureFlagRolloutAssignment.user_id == user_id,
            )
            .first()
        )
        if not model:
            return None
        return self._to_rollout_assignment_entity(model)

    def create_rollout_assignment(
        self, flag_id: int, user_id: str, enabled: bool
    ) -> FeatureFlagRolloutAssignmentEntity:
        """Create a new rollout assignment using INSERT ... ON CONFLICT.

        Uses PostgreSQL UPSERT to atomically handle concurrent requests.
        If assignment already exists, the INSERT is silently ignored.
        Returns the assignment (newly created or existing).
        """
        stmt = insert(FeatureFlagRolloutAssignment).values(
            feature_flag_id=flag_id,
            user_id=user_id,
            enabled=enabled,
        ).on_conflict_do_nothing(
            index_elements=["feature_flag_id", "user_id"]
        )
        self._session.execute(stmt)
        self._session.commit()

        # Return the assignment (either newly created or existing)
        existing = self.get_rollout_assignment(flag_id, user_id)
        if existing:
            return existing
        # Should not happen with proper constraints
        raise RuntimeError("Rollout assignment not found after insert")
