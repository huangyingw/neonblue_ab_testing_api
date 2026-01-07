"""Experiment-related API endpoints."""

import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from scipy import stats

from app.database import get_db
from app.auth import verify_token
from app.models import Experiment, Variant, Assignment, Event
from app.schemas import (
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
    AssignmentResponse,
    ExperimentResults,
    VariantMetrics,
    StatisticalSignificance,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
def create_experiment(
    experiment: ExperimentCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """
    Create a new experiment with variants.

    The traffic percentages for all variants must sum to 100.
    """
    # Create experiment
    db_experiment = Experiment(
        name=experiment.name,
        description=experiment.description,
        status="draft",
    )
    db.add(db_experiment)
    db.flush()  # Get the experiment ID

    # Create variants
    for variant in experiment.variants:
        db_variant = Variant(
            experiment_id=db_experiment.id,
            name=variant.name,
            traffic_percentage=variant.traffic_percentage,
        )
        db.add(db_variant)

    db.commit()
    db.refresh(db_experiment)

    return db_experiment


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Get an experiment by ID."""
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    return experiment


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
def update_experiment(
    experiment_id: int,
    update: ExperimentUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Update an experiment's name, description, or status."""
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(experiment, field, value)

    db.commit()
    db.refresh(experiment)

    return experiment


@router.get("/{experiment_id}/assignment/{user_id}", response_model=AssignmentResponse)
def get_assignment(
    experiment_id: int,
    user_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """
    Get or create a user's variant assignment for an experiment.

    This endpoint is idempotent: once a user is assigned to a variant,
    subsequent calls will return the same assignment.
    """
    # Check if experiment exists
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    # Check for existing assignment
    existing_assignment = (
        db.query(Assignment)
        .filter(Assignment.experiment_id == experiment_id, Assignment.user_id == user_id)
        .first()
    )

    if existing_assignment:
        return AssignmentResponse(
            experiment_id=existing_assignment.experiment_id,
            variant_id=existing_assignment.variant_id,
            variant_name=existing_assignment.variant.name,
            user_id=existing_assignment.user_id,
            assigned_at=existing_assignment.assigned_at,
        )

    # Assign user to a variant based on traffic percentages
    variants = db.query(Variant).filter(Variant.experiment_id == experiment_id).all()

    if not variants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Experiment has no variants",
        )

    # Weighted random selection based on traffic percentages
    rand = random.uniform(0, 100)
    cumulative = 0
    selected_variant = variants[-1]  # Default to last variant

    for variant in variants:
        cumulative += variant.traffic_percentage
        if rand <= cumulative:
            selected_variant = variant
            break

    # Create assignment
    assignment = Assignment(
        experiment_id=experiment_id,
        variant_id=selected_variant.id,
        user_id=user_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return AssignmentResponse(
        experiment_id=assignment.experiment_id,
        variant_id=assignment.variant_id,
        variant_name=selected_variant.name,
        user_id=assignment.user_id,
        assigned_at=assignment.assigned_at,
    )


@router.get("/{experiment_id}/results", response_model=ExperimentResults)
def get_results(
    experiment_id: int,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Filter events after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events before this date"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """
    Get experiment performance results.

    Only counts events that occur after each user's assignment timestamp.
    Supports filtering by event type and date range.
    """
    # Check if experiment exists
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    # Get all variants for this experiment
    variants = db.query(Variant).filter(Variant.experiment_id == experiment_id).all()

    # Build variant metrics
    variant_metrics = []
    total_users = 0
    total_events = 0
    contingency_data = []  # For chi-square test

    for variant in variants:
        # Get assignments for this variant
        assignments = (
            db.query(Assignment)
            .filter(Assignment.variant_id == variant.id)
            .all()
        )
        user_count = len(assignments)
        total_users += user_count

        # Get events for users in this variant (only after assignment)
        event_count = 0
        events_by_type: dict[str, int] = {}

        for assignment in assignments:
            # Build event query
            query = db.query(Event).filter(
                Event.user_id == assignment.user_id,
                Event.timestamp > assignment.assigned_at,
            )

            if event_type:
                query = query.filter(Event.event_type == event_type)
            if start_date:
                query = query.filter(Event.timestamp >= start_date)
            if end_date:
                query = query.filter(Event.timestamp <= end_date)

            user_events = query.all()
            event_count += len(user_events)

            # Count events by type
            for event in user_events:
                events_by_type[event.event_type] = events_by_type.get(event.event_type, 0) + 1

        total_events += event_count

        # Calculate conversion rate
        conversion_rate = (event_count / user_count * 100) if user_count > 0 else 0

        variant_metrics.append(
            VariantMetrics(
                variant_id=variant.id,
                variant_name=variant.name,
                user_count=user_count,
                event_count=event_count,
                conversion_rate=round(conversion_rate, 2),
                events_by_type=events_by_type,
            )
        )

        # Store data for chi-square test (users with events, users without events)
        users_with_events = len(set(
            e.user_id for a in assignments
            for e in db.query(Event).filter(
                Event.user_id == a.user_id,
                Event.timestamp > a.assigned_at,
            ).all()
        ))
        contingency_data.append([users_with_events, user_count - users_with_events])

    # Calculate statistical significance using chi-square test
    statistical_significance = None
    if len(contingency_data) >= 2 and all(sum(row) > 0 for row in contingency_data):
        try:
            chi2, p_value, _, _ = stats.chi2_contingency(contingency_data)
            statistical_significance = StatisticalSignificance(
                chi_square=round(chi2, 4),
                p_value=round(p_value, 4),
                is_significant=p_value < 0.05,
                confidence_level=0.95,
            )
        except Exception:
            # Chi-square test may fail with certain data distributions
            pass

    # Build time range info
    time_range = None
    if start_date or end_date:
        time_range = {
            "start": start_date or experiment.created_at,
            "end": end_date or datetime.utcnow(),
        }

    return ExperimentResults(
        experiment_id=experiment.id,
        experiment_name=experiment.name,
        status=experiment.status,
        total_users=total_users,
        total_events=total_events,
        variants=variant_metrics,
        statistical_significance=statistical_significance,
        time_range=time_range,
    )
