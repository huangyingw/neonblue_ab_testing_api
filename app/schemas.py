"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator


# --- Variant Schemas ---


class VariantCreate(BaseModel):
    """Schema for creating a variant."""

    name: str = Field(..., min_length=1, max_length=100)
    traffic_percentage: float = Field(..., ge=0, le=100)


class VariantResponse(BaseModel):
    """Schema for variant response."""

    id: int
    name: str
    traffic_percentage: float
    created_at: datetime

    class Config:
        from_attributes = True


# --- Experiment Schemas ---


class ExperimentCreate(BaseModel):
    """Schema for creating an experiment."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    variants: list[VariantCreate] = Field(..., min_length=2)

    @field_validator("variants")
    @classmethod
    def validate_traffic_percentage(cls, variants: list[VariantCreate]) -> list[VariantCreate]:
        """Ensure traffic percentages sum to 100."""
        total = sum(v.traffic_percentage for v in variants)
        if abs(total - 100) > 0.01:
            raise ValueError(f"Traffic percentages must sum to 100, got {total}")
        return variants


class ExperimentResponse(BaseModel):
    """Schema for experiment response."""

    id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    variants: list[VariantResponse]

    class Config:
        from_attributes = True


class ExperimentUpdate(BaseModel):
    """Schema for updating an experiment."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate status value."""
        if v is not None and v not in ["draft", "running", "stopped", "completed"]:
            raise ValueError("Status must be one of: draft, running, stopped, completed")
        return v


# --- Assignment Schemas ---


class AssignmentResponse(BaseModel):
    """Schema for assignment response."""

    experiment_id: int
    variant_id: int
    variant_name: str
    user_id: str
    assigned_at: datetime


# --- Event Schemas ---


class EventCreate(BaseModel):
    """Schema for creating an event."""

    user_id: str = Field(..., min_length=1, max_length=100)
    event_type: str = Field(..., min_length=1, max_length=50)
    timestamp: Optional[datetime] = None
    properties: Optional[dict[str, Any]] = None


class EventResponse(BaseModel):
    """Schema for event response."""

    id: int
    user_id: str
    event_type: str
    timestamp: datetime
    properties: Optional[dict[str, Any]]

    class Config:
        from_attributes = True


# --- Results Schemas ---


class VariantMetrics(BaseModel):
    """Metrics for a single variant."""

    variant_id: int
    variant_name: str
    user_count: int
    event_count: int
    conversion_rate: float
    events_by_type: dict[str, int]


class StatisticalSignificance(BaseModel):
    """Statistical significance results."""

    chi_square: float
    p_value: float
    is_significant: bool
    confidence_level: float = 0.95


class ExperimentResults(BaseModel):
    """Schema for experiment results response."""

    experiment_id: int
    experiment_name: str
    status: str
    total_users: int
    total_events: int
    variants: list[VariantMetrics]
    statistical_significance: Optional[StatisticalSignificance] = None
    time_range: Optional[dict[str, datetime]] = None


# --- Feature Flag Schemas ---


class FeatureFlagCreate(BaseModel):
    """Schema for creating a feature flag."""

    key: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    enabled: bool = False
    rollout_percentage: float = Field(default=0, ge=0, le=100)


class FeatureFlagUpdate(BaseModel):
    """Schema for updating a feature flag."""

    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    rollout_percentage: Optional[float] = Field(default=None, ge=0, le=100)


class FeatureFlagResponse(BaseModel):
    """Schema for feature flag response."""

    id: int
    key: str
    name: str
    description: Optional[str]
    enabled: bool
    rollout_percentage: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FeatureFlagEvaluation(BaseModel):
    """Schema for feature flag evaluation result."""

    key: str
    enabled: bool
    reason: str  # "global", "rollout", "user_override", "disabled"


class FeatureFlagOverrideCreate(BaseModel):
    """Schema for creating a user override."""

    user_id: str = Field(..., min_length=1, max_length=100)
    enabled: bool


class FeatureFlagOverrideResponse(BaseModel):
    """Schema for feature flag override response."""

    feature_flag_key: str
    user_id: str
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- API Token Schemas ---


class ApiTokenCreate(BaseModel):
    """Schema for creating an API token."""

    name: str = Field(..., min_length=1, max_length=200, description="Description of token usage")
    expires_at: Optional[datetime] = Field(None, description="Expiration time (None = never expires)")


class ApiTokenResponse(BaseModel):
    """Schema for API token response (without the actual token)."""

    id: int
    name: str
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApiTokenCreatedResponse(BaseModel):
    """Schema for response when a new token is created (includes the actual token)."""

    id: int
    name: str
    token: str  # Only returned once at creation time
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
