"""Mock repository implementations for testing.

These implementations use in-memory storage and do not depend on any database.
They are completely isolated and do not pollute any real environment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from app.repositories.interfaces import (
    ExperimentRepository,
    EventRepository,
    FeatureFlagRepository,
    ApiTokenRepository,
    ExperimentEntity,
    VariantEntity,
    AssignmentEntity,
    EventEntity,
    FeatureFlagEntity,
    FeatureFlagOverrideEntity,
    ApiTokenEntity,
    ExperimentInput,
    ExperimentUpdateInput,
    EventInput,
    EventFilter,
    FeatureFlagInput,
    FeatureFlagUpdateInput,
    ApiTokenInput,
)


class MockExperimentRepository(ExperimentRepository):
    """In-memory mock implementation of ExperimentRepository."""

    def __init__(self):
        self._experiments: dict[int, ExperimentEntity] = {}
        self._variants: dict[int, VariantEntity] = {}
        self._assignments: dict[int, AssignmentEntity] = {}
        self._next_experiment_id = 1
        self._next_variant_id = 1
        self._next_assignment_id = 1

    def reset(self):
        """Reset all data. Call this between tests."""
        self._experiments.clear()
        self._variants.clear()
        self._assignments.clear()
        self._next_experiment_id = 1
        self._next_variant_id = 1
        self._next_assignment_id = 1

    def create(self, data: ExperimentInput) -> ExperimentEntity:
        """Create a new experiment with variants."""
        now = datetime.utcnow()
        experiment_id = self._next_experiment_id
        self._next_experiment_id += 1

        # Create variants
        variants = []
        for v in data.variants:
            variant = VariantEntity(
                id=self._next_variant_id,
                experiment_id=experiment_id,
                name=v.name,
                traffic_percentage=v.traffic_percentage,
                created_at=now,
            )
            self._variants[variant.id] = variant
            variants.append(variant)
            self._next_variant_id += 1

        experiment = ExperimentEntity(
            id=experiment_id,
            name=data.name,
            description=data.description,
            status="draft",
            created_at=now,
            variants=variants,
        )
        self._experiments[experiment_id] = experiment
        return experiment

    def get_by_id(self, experiment_id: int) -> Optional[ExperimentEntity]:
        """Get an experiment by ID."""
        experiment = self._experiments.get(experiment_id)
        if experiment:
            # Attach current variants
            experiment.variants = [
                v for v in self._variants.values()
                if v.experiment_id == experiment_id
            ]
        return experiment

    def update(
        self, experiment_id: int, data: ExperimentUpdateInput
    ) -> Optional[ExperimentEntity]:
        """Update an experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return None

        if data.name is not None:
            experiment.name = data.name
        if data.description is not None:
            experiment.description = data.description
        if data.status is not None:
            experiment.status = data.status

        return self.get_by_id(experiment_id)

    def get_variants(self, experiment_id: int) -> list[VariantEntity]:
        """Get all variants for an experiment."""
        return [
            v for v in self._variants.values()
            if v.experiment_id == experiment_id
        ]

    def get_assignment(
        self, experiment_id: int, user_id: str
    ) -> Optional[AssignmentEntity]:
        """Get existing assignment for a user in an experiment."""
        for assignment in self._assignments.values():
            if (
                assignment.experiment_id == experiment_id
                and assignment.user_id == user_id
            ):
                return assignment
        return None

    def create_assignment(
        self, experiment_id: int, variant_id: int, user_id: str
    ) -> AssignmentEntity:
        """Create a new assignment."""
        variant = self._variants.get(variant_id)
        variant_name = variant.name if variant else "Unknown"

        assignment = AssignmentEntity(
            id=self._next_assignment_id,
            experiment_id=experiment_id,
            variant_id=variant_id,
            user_id=user_id,
            assigned_at=datetime.utcnow(),
            variant_name=variant_name,
        )
        self._assignments[assignment.id] = assignment
        self._next_assignment_id += 1
        return assignment

    def get_assignments_by_variant(self, variant_id: int) -> list[AssignmentEntity]:
        """Get all assignments for a variant."""
        return [
            a for a in self._assignments.values()
            if a.variant_id == variant_id
        ]


class MockEventRepository(EventRepository):
    """In-memory mock implementation of EventRepository."""

    def __init__(self):
        self._events: dict[int, EventEntity] = {}
        self._next_id = 1

    def reset(self):
        """Reset all data. Call this between tests."""
        self._events.clear()
        self._next_id = 1

    def create(self, data: EventInput) -> EventEntity:
        """Create a new event."""
        event = EventEntity(
            id=self._next_id,
            user_id=data.user_id,
            event_type=data.event_type,
            timestamp=data.timestamp or datetime.utcnow(),
            properties=data.properties,
        )
        self._events[event.id] = event
        self._next_id += 1
        return event

    def list(self, filter: EventFilter) -> list[EventEntity]:
        """List events with optional filters."""
        events = list(self._events.values())

        # Apply filters
        if filter.user_id:
            events = [e for e in events if e.user_id == filter.user_id]
        if filter.event_type:
            events = [e for e in events if e.event_type == filter.event_type]
        if filter.start_date:
            events = [e for e in events if e.timestamp >= filter.start_date]
        if filter.end_date:
            events = [e for e in events if e.timestamp <= filter.end_date]

        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        return events[filter.offset : filter.offset + filter.limit]

    def get_events_for_user_after(
        self,
        user_id: str,
        after: datetime,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[EventEntity]:
        """Get events for a user after a specific timestamp."""
        events = [
            e for e in self._events.values()
            if e.user_id == user_id and e.timestamp >= after
        ]

        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if start_date:
            events = [e for e in events if e.timestamp >= start_date]
        if end_date:
            events = [e for e in events if e.timestamp <= end_date]

        return events


class MockFeatureFlagRepository(FeatureFlagRepository):
    """In-memory mock implementation of FeatureFlagRepository."""

    def __init__(self):
        self._flags: dict[str, FeatureFlagEntity] = {}
        self._overrides: dict[tuple[int, str], FeatureFlagOverrideEntity] = {}
        self._next_flag_id = 1
        self._next_override_id = 1

    def reset(self):
        """Reset all data. Call this between tests."""
        self._flags.clear()
        self._overrides.clear()
        self._next_flag_id = 1
        self._next_override_id = 1

    def create(self, data: FeatureFlagInput) -> FeatureFlagEntity:
        """Create a new feature flag."""
        now = datetime.utcnow()
        flag = FeatureFlagEntity(
            id=self._next_flag_id,
            key=data.key,
            name=data.name,
            description=data.description,
            enabled=data.enabled,
            rollout_percentage=data.rollout_percentage,
            created_at=now,
            updated_at=now,
        )
        self._flags[data.key] = flag
        self._next_flag_id += 1
        return flag

    def get_by_key(self, key: str) -> Optional[FeatureFlagEntity]:
        """Get a feature flag by key."""
        return self._flags.get(key)

    def list_all(self) -> list[FeatureFlagEntity]:
        """List all feature flags."""
        return sorted(self._flags.values(), key=lambda f: f.key)

    def update(
        self, key: str, data: FeatureFlagUpdateInput
    ) -> Optional[FeatureFlagEntity]:
        """Update a feature flag."""
        flag = self._flags.get(key)
        if not flag:
            return None

        if data.name is not None:
            flag.name = data.name
        if data.description is not None:
            flag.description = data.description
        if data.enabled is not None:
            flag.enabled = data.enabled
        if data.rollout_percentage is not None:
            flag.rollout_percentage = data.rollout_percentage

        flag.updated_at = datetime.utcnow()
        return flag

    def delete(self, key: str) -> bool:
        """Delete a feature flag. Returns True if deleted."""
        if key in self._flags:
            flag_id = self._flags[key].id
            # Delete associated overrides
            keys_to_delete = [
                k for k in self._overrides.keys()
                if k[0] == flag_id
            ]
            for k in keys_to_delete:
                del self._overrides[k]
            del self._flags[key]
            return True
        return False

    def get_user_override(
        self, flag_id: int, user_id: str
    ) -> Optional[FeatureFlagOverrideEntity]:
        """Get user-specific override for a flag."""
        return self._overrides.get((flag_id, user_id))

    def set_user_override(self, flag_id: int, user_id: str, enabled: bool) -> None:
        """Create or update a user-specific override."""
        key = (flag_id, user_id)
        existing = self._overrides.get(key)

        if existing:
            existing.enabled = enabled
        else:
            override = FeatureFlagOverrideEntity(
                id=self._next_override_id,
                feature_flag_id=flag_id,
                user_id=user_id,
                enabled=enabled,
                created_at=datetime.utcnow(),
            )
            self._overrides[key] = override
            self._next_override_id += 1

    def delete_user_override(self, flag_id: int, user_id: str) -> bool:
        """Delete a user-specific override. Returns True if deleted."""
        key = (flag_id, user_id)
        if key in self._overrides:
            del self._overrides[key]
            return True
        return False


class MockApiTokenRepository(ApiTokenRepository):
    """In-memory mock implementation of ApiTokenRepository."""

    def __init__(self):
        self._tokens: dict[int, ApiTokenEntity] = {}
        self._hash_index: dict[str, int] = {}  # token_hash -> token_id
        self._next_id = 1

    def reset(self):
        """Reset all data. Call this between tests."""
        self._tokens.clear()
        self._hash_index.clear()
        self._next_id = 1

    def create(self, data: ApiTokenInput, token_hash: str) -> ApiTokenEntity:
        """Create a new API token."""
        token = ApiTokenEntity(
            id=self._next_id,
            name=data.name,
            token_hash=token_hash,
            is_active=True,
            created_at=datetime.utcnow(),
            expires_at=data.expires_at,
            last_used_at=None,
        )
        self._tokens[token.id] = token
        self._hash_index[token_hash] = token.id
        self._next_id += 1
        return token

    def get_by_hash(self, token_hash: str) -> Optional[ApiTokenEntity]:
        """Get a token by its hash."""
        token_id = self._hash_index.get(token_hash)
        if token_id:
            return self._tokens.get(token_id)
        return None

    def get_by_id(self, token_id: int) -> Optional[ApiTokenEntity]:
        """Get a token by its ID."""
        return self._tokens.get(token_id)

    def list_all(self) -> list[ApiTokenEntity]:
        """List all API tokens."""
        return sorted(self._tokens.values(), key=lambda t: t.created_at, reverse=True)

    def deactivate(self, token_id: int) -> bool:
        """Deactivate a token."""
        token = self._tokens.get(token_id)
        if not token:
            return False
        token.is_active = False
        return True

    def delete(self, token_id: int) -> bool:
        """Delete a token."""
        token = self._tokens.get(token_id)
        if not token:
            return False
        del self._hash_index[token.token_hash]
        del self._tokens[token_id]
        return True

    def update_last_used(self, token_id: int) -> None:
        """Update the last_used_at timestamp."""
        token = self._tokens.get(token_id)
        if token:
            token.last_used_at = datetime.utcnow()
