"""Abstract repository interfaces.

This module defines the contracts for data access.
Implementations should not expose database-specific details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


# =============================================================================
# Entity Classes (Database-agnostic data structures)
# =============================================================================


@dataclass
class VariantEntity:
    """Variant entity representing a variation in an experiment."""

    id: int
    experiment_id: int
    name: str
    traffic_percentage: float
    created_at: datetime


@dataclass
class ExperimentEntity:
    """Experiment entity representing an A/B test."""

    id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    variants: list[VariantEntity] = field(default_factory=list)


@dataclass
class AssignmentEntity:
    """Assignment entity representing a user's assignment to a variant."""

    id: int
    experiment_id: int
    variant_id: int
    user_id: str
    assigned_at: datetime
    variant_name: str  # Denormalized for convenience


@dataclass
class EventEntity:
    """Event entity representing a user action/conversion."""

    id: int
    user_id: str
    event_type: str
    timestamp: datetime
    properties: Optional[dict[str, Any]] = None


@dataclass
class FeatureFlagEntity:
    """Feature flag entity."""

    id: int
    key: str
    name: str
    description: Optional[str]
    enabled: bool
    rollout_percentage: float
    created_at: datetime
    updated_at: datetime


@dataclass
class FeatureFlagOverrideEntity:
    """Per-user override for feature flags."""

    id: int
    feature_flag_id: int
    user_id: str
    enabled: bool
    created_at: datetime


@dataclass
class ApiTokenEntity:
    """API Token entity for authentication."""

    id: int
    name: str
    token_hash: str
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]


# =============================================================================
# Input DTOs (for create/update operations)
# =============================================================================


@dataclass
class VariantInput:
    """Input for creating a variant."""

    name: str
    traffic_percentage: float


@dataclass
class ExperimentInput:
    """Input for creating an experiment."""

    name: str
    description: Optional[str]
    variants: list[VariantInput]


@dataclass
class ExperimentUpdateInput:
    """Input for updating an experiment."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


@dataclass
class EventInput:
    """Input for creating an event."""

    user_id: str
    event_type: str
    timestamp: Optional[datetime] = None
    properties: Optional[dict[str, Any]] = None


@dataclass
class FeatureFlagInput:
    """Input for creating a feature flag."""

    key: str
    name: str
    description: Optional[str] = None
    enabled: bool = False
    rollout_percentage: float = 0.0


@dataclass
class FeatureFlagUpdateInput:
    """Input for updating a feature flag."""

    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    rollout_percentage: Optional[float] = None


@dataclass
class EventFilter:
    """Filter criteria for listing events."""

    user_id: Optional[str] = None
    event_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


@dataclass
class ApiTokenInput:
    """Input for creating an API token."""

    name: str
    expires_at: Optional[datetime] = None


# =============================================================================
# Repository Interfaces
# =============================================================================


class ExperimentRepository(ABC):
    """Abstract interface for experiment data access."""

    @abstractmethod
    def create(self, data: ExperimentInput) -> ExperimentEntity:
        """Create a new experiment with variants."""
        pass

    @abstractmethod
    def get_by_id(self, experiment_id: int) -> Optional[ExperimentEntity]:
        """Get an experiment by ID."""
        pass

    @abstractmethod
    def update(
        self, experiment_id: int, data: ExperimentUpdateInput
    ) -> Optional[ExperimentEntity]:
        """Update an experiment."""
        pass

    @abstractmethod
    def get_variants(self, experiment_id: int) -> list[VariantEntity]:
        """Get all variants for an experiment."""
        pass

    @abstractmethod
    def get_assignment(
        self, experiment_id: int, user_id: str
    ) -> Optional[AssignmentEntity]:
        """Get existing assignment for a user in an experiment."""
        pass

    @abstractmethod
    def create_assignment(
        self, experiment_id: int, variant_id: int, user_id: str
    ) -> AssignmentEntity:
        """Create a new assignment."""
        pass

    @abstractmethod
    def get_assignments_by_variant(self, variant_id: int) -> list[AssignmentEntity]:
        """Get all assignments for a variant."""
        pass


class EventRepository(ABC):
    """Abstract interface for event data access."""

    @abstractmethod
    def create(self, data: EventInput) -> EventEntity:
        """Create a new event."""
        pass

    @abstractmethod
    def list(self, filter: EventFilter) -> list[EventEntity]:
        """List events with optional filters."""
        pass

    @abstractmethod
    def get_events_for_user_after(
        self,
        user_id: str,
        after: datetime,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[EventEntity]:
        """Get events for a user after a specific timestamp."""
        pass


class FeatureFlagRepository(ABC):
    """Abstract interface for feature flag data access."""

    @abstractmethod
    def create(self, data: FeatureFlagInput) -> FeatureFlagEntity:
        """Create a new feature flag."""
        pass

    @abstractmethod
    def get_by_key(self, key: str) -> Optional[FeatureFlagEntity]:
        """Get a feature flag by key."""
        pass

    @abstractmethod
    def list_all(self) -> list[FeatureFlagEntity]:
        """List all feature flags."""
        pass

    @abstractmethod
    def update(
        self, key: str, data: FeatureFlagUpdateInput
    ) -> Optional[FeatureFlagEntity]:
        """Update a feature flag."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a feature flag. Returns True if deleted."""
        pass

    @abstractmethod
    def get_user_override(
        self, flag_id: int, user_id: str
    ) -> Optional[FeatureFlagOverrideEntity]:
        """Get user-specific override for a flag."""
        pass

    @abstractmethod
    def set_user_override(self, flag_id: int, user_id: str, enabled: bool) -> None:
        """Create or update a user-specific override."""
        pass

    @abstractmethod
    def delete_user_override(self, flag_id: int, user_id: str) -> bool:
        """Delete a user-specific override. Returns True if deleted."""
        pass


class ApiTokenRepository(ABC):
    """Abstract interface for API token data access."""

    @abstractmethod
    def create(self, data: ApiTokenInput, token_hash: str) -> ApiTokenEntity:
        """Create a new API token."""
        pass

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> Optional[ApiTokenEntity]:
        """Get a token by its hash."""
        pass

    @abstractmethod
    def list_all(self) -> list[ApiTokenEntity]:
        """List all API tokens."""
        pass

    @abstractmethod
    def deactivate(self, token_id: int) -> bool:
        """Deactivate a token. Returns True if successful."""
        pass

    @abstractmethod
    def delete(self, token_id: int) -> bool:
        """Delete a token. Returns True if deleted."""
        pass

    @abstractmethod
    def update_last_used(self, token_id: int) -> None:
        """Update the last_used_at timestamp."""
        pass
