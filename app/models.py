"""SQLAlchemy database models."""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Experiment(Base):
    """Experiment model representing an A/B test."""

    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="draft")  # draft, running, stopped
    created_at = Column(DateTime, default=datetime.utcnow)

    variants = relationship("Variant", back_populates="experiment", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="experiment", cascade="all, delete-orphan")


class Variant(Base):
    """Variant model representing a variation in an experiment."""

    __tablename__ = "variants"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    name = Column(String, nullable=False)
    traffic_percentage = Column(Float, nullable=False)  # 0.0 to 100.0
    created_at = Column(DateTime, default=datetime.utcnow)

    experiment = relationship("Experiment", back_populates="variants")
    assignments = relationship("Assignment", back_populates="variant")


class Assignment(Base):
    """Assignment model representing a user's assignment to a variant."""

    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("variants.id"), nullable=False)
    user_id = Column(String, nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    experiment = relationship("Experiment", back_populates="assignments")
    variant = relationship("Variant", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("experiment_id", "user_id", name="uq_experiment_user"),
        Index("ix_assignment_user_experiment", "user_id", "experiment_id"),
    )


class Event(Base):
    """Event model representing a user action/conversion."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)  # click, purchase, signup, etc.
    timestamp = Column(DateTime, default=datetime.utcnow)
    properties = Column(JSON, nullable=True)  # Flexible JSON for additional context

    __table_args__ = (
        Index("ix_event_user_timestamp", "user_id", "timestamp"),
        Index("ix_event_type", "event_type"),
    )


class FeatureFlag(Base):
    """Feature flag model for simple on/off feature toggles."""

    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    enabled = Column(Integer, default=0)  # 0=disabled, 1=enabled globally
    rollout_percentage = Column(Float, default=0)  # 0-100, for gradual rollout
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_overrides = relationship("FeatureFlagOverride", back_populates="feature_flag", cascade="all, delete-orphan")


class FeatureFlagOverride(Base):
    """Per-user override for feature flags."""

    __tablename__ = "feature_flag_overrides"

    id = Column(Integer, primary_key=True, index=True)
    feature_flag_id = Column(Integer, ForeignKey("feature_flags.id"), nullable=False)
    user_id = Column(String, nullable=False)
    enabled = Column(Integer, nullable=False)  # 0=disabled, 1=enabled
    created_at = Column(DateTime, default=datetime.utcnow)

    feature_flag = relationship("FeatureFlag", back_populates="user_overrides")

    __table_args__ = (
        UniqueConstraint("feature_flag_id", "user_id", name="uq_flag_user"),
        Index("ix_override_user", "user_id"),
    )
