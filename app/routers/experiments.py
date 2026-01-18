"""Experiment-related API endpoints."""

import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from scipy import stats

from app.auth import verify_token
from app.dependencies import get_experiment_repository, get_event_repository
from app.repositories.interfaces import (
    ExperimentRepository,
    EventRepository,
    ExperimentInput,
    ExperimentUpdateInput,
    VariantInput,
)
from app.schemas import (
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
    AssignmentResponse,
    ExperimentResults,
    VariantMetrics,
    StatisticalSignificance,
    VariantResponse,
)
from app.cache import cache, CACHE_KEY_ASSIGNMENT

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _to_variant_response(entity) -> VariantResponse:
    """Convert VariantEntity to VariantResponse."""
    return VariantResponse(
        id=entity.id,
        name=entity.name,
        traffic_percentage=entity.traffic_percentage,
        created_at=entity.created_at,
    )


def _to_experiment_response(entity) -> ExperimentResponse:
    """Convert ExperimentEntity to ExperimentResponse."""
    return ExperimentResponse(
        id=entity.id,
        name=entity.name,
        description=entity.description,
        status=entity.status,
        created_at=entity.created_at,
        variants=[_to_variant_response(v) for v in entity.variants],
    )


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
def create_experiment(
    experiment: ExperimentCreate,
    repo: ExperimentRepository = Depends(get_experiment_repository),
    _: str = Depends(verify_token),
):
    """
    Create a new experiment with variants.

    The traffic percentages for all variants must sum to 100.
    """
    data = ExperimentInput(
        name=experiment.name,
        description=experiment.description,
        variants=[
            VariantInput(name=v.name, traffic_percentage=v.traffic_percentage)
            for v in experiment.variants
        ],
    )
    entity = repo.create(data)
    return _to_experiment_response(entity)


@router.get("", response_model=list[ExperimentResponse])
def list_experiments(
    repo: ExperimentRepository = Depends(get_experiment_repository),
    _: str = Depends(verify_token),
):
    """List all experiments."""
    entities = repo.list_all()
    return [_to_experiment_response(e) for e in entities]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: int,
    repo: ExperimentRepository = Depends(get_experiment_repository),
    _: str = Depends(verify_token),
):
    """Get an experiment by ID."""
    entity = repo.get_by_id(experiment_id)

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    return _to_experiment_response(entity)


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
def update_experiment(
    experiment_id: int,
    update: ExperimentUpdate,
    repo: ExperimentRepository = Depends(get_experiment_repository),
    _: str = Depends(verify_token),
):
    """Update an experiment's name, description, or status."""
    update_data = update.model_dump(exclude_unset=True)
    data = ExperimentUpdateInput(
        name=update_data.get("name"),
        description=update_data.get("description"),
        status=update_data.get("status"),
    )

    entity = repo.update(experiment_id, data)

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    return _to_experiment_response(entity)


@router.get("/{experiment_id}/assignment/{user_id}", response_model=AssignmentResponse)
def get_assignment(
    experiment_id: int,
    user_id: str,
    repo: ExperimentRepository = Depends(get_experiment_repository),
    _: str = Depends(verify_token),
):
    """
    Get or create a user's variant assignment for an experiment.

    This endpoint is idempotent: once a user is assigned to a variant,
    subsequent calls will return the same assignment.

    Results are cached for improved performance.
    """
    # Try cache first
    cache_key = CACHE_KEY_ASSIGNMENT.format(experiment_id=experiment_id, user_id=user_id)
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    # Check if experiment exists
    experiment = repo.get_by_id(experiment_id)
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    # Check for existing assignment
    existing_assignment = repo.get_assignment(experiment_id, user_id)

    if existing_assignment:
        response = AssignmentResponse(
            experiment_id=existing_assignment.experiment_id,
            variant_id=existing_assignment.variant_id,
            variant_name=existing_assignment.variant_name,
            user_id=existing_assignment.user_id,
            assigned_at=existing_assignment.assigned_at,
        )
        cache.set(cache_key, response, ttl=300)
        return response

    # Get variants for weighted random selection
    variants = repo.get_variants(experiment_id)

    if not variants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Experiment has no variants",
        )

    # Weighted random selection based on traffic percentages
    rand = random.uniform(0, 100)
    cumulative = 0
    selected_variant = variants[-1]

    for variant in variants:
        cumulative += variant.traffic_percentage
        if rand <= cumulative:
            selected_variant = variant
            break

    # Create assignment
    assignment = repo.create_assignment(experiment_id, selected_variant.id, user_id)

    response = AssignmentResponse(
        experiment_id=assignment.experiment_id,
        variant_id=assignment.variant_id,
        variant_name=assignment.variant_name,
        user_id=assignment.user_id,
        assigned_at=assignment.assigned_at,
    )
    cache.set(cache_key, response, ttl=300)
    return response


@router.get("/{experiment_id}/results", response_model=ExperimentResults)
def get_results(
    experiment_id: int,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Filter events after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events before this date"),
    experiment_repo: ExperimentRepository = Depends(get_experiment_repository),
    event_repo: EventRepository = Depends(get_event_repository),
    _: str = Depends(verify_token),
):
    """
    Get experiment performance results.

    Only counts events that occur after each user's assignment timestamp.
    Supports filtering by event type and date range.
    """
    # Check if experiment exists
    experiment = experiment_repo.get_by_id(experiment_id)
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment with id {experiment_id} not found",
        )

    # Get all variants for this experiment
    variants = experiment.variants

    # Build variant metrics
    variant_metrics = []
    total_users = 0
    total_events = 0
    contingency_data = []

    for variant in variants:
        # Get assignments for this variant
        assignments = experiment_repo.get_assignments_by_variant(variant.id)
        user_count = len(assignments)
        total_users += user_count

        # Get events for users in this variant (only after assignment)
        event_count = 0
        events_by_type: dict[str, int] = {}
        users_with_events = set()

        for assignment in assignments:
            user_events = event_repo.get_events_for_user_after(
                user_id=assignment.user_id,
                after=assignment.assigned_at,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            )
            event_count += len(user_events)

            if user_events:
                users_with_events.add(assignment.user_id)

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

        # Store data for chi-square test
        contingency_data.append([len(users_with_events), user_count - len(users_with_events)])

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
