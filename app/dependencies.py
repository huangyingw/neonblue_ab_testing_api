"""FastAPI dependency injection for repositories."""

from __future__ import annotations

from typing import Generator
from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.interfaces import (
    ExperimentRepository,
    EventRepository,
    FeatureFlagRepository,
    ApiTokenRepository,
)
from app.repositories.sqlalchemy import (
    SQLAlchemyExperimentRepository,
    SQLAlchemyEventRepository,
    SQLAlchemyFeatureFlagRepository,
    SQLAlchemyApiTokenRepository,
)


def get_experiment_repository(
    db: Session = Depends(get_db),
) -> Generator[ExperimentRepository, None, None]:
    """Provide ExperimentRepository instance."""
    yield SQLAlchemyExperimentRepository(db)


def get_event_repository(
    db: Session = Depends(get_db),
) -> Generator[EventRepository, None, None]:
    """Provide EventRepository instance."""
    yield SQLAlchemyEventRepository(db)


def get_feature_flag_repository(
    db: Session = Depends(get_db),
) -> Generator[FeatureFlagRepository, None, None]:
    """Provide FeatureFlagRepository instance."""
    yield SQLAlchemyFeatureFlagRepository(db)


def get_api_token_repository(
    db: Session = Depends(get_db),
) -> Generator[ApiTokenRepository, None, None]:
    """Provide ApiTokenRepository instance."""
    yield SQLAlchemyApiTokenRepository(db)
