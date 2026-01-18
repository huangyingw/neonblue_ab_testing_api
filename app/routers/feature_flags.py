"""Feature flag API endpoints."""

import random

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_token
from app.dependencies import get_feature_flag_repository
from app.repositories.interfaces import (
    FeatureFlagRepository,
    FeatureFlagInput,
    FeatureFlagUpdateInput,
)
from app.schemas import (
    FeatureFlagCreate,
    FeatureFlagUpdate,
    FeatureFlagResponse,
    FeatureFlagEvaluation,
    FeatureFlagOverrideCreate,
    FeatureFlagOverrideResponse,
)
from app.cache import (
    cache,
    CACHE_KEY_FEATURE_FLAG,
    CACHE_KEY_FLAG_EVALUATION,
    get_flag_cache_pattern,
    get_flag_eval_cache_pattern,
)

router = APIRouter(prefix="/flags", tags=["feature-flags"])


def _to_flag_response(entity) -> FeatureFlagResponse:
    """Convert FeatureFlagEntity to FeatureFlagResponse."""
    return FeatureFlagResponse(
        id=entity.id,
        key=entity.key,
        name=entity.name,
        description=entity.description,
        enabled=entity.enabled,
        rollout_percentage=entity.rollout_percentage,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.post("", response_model=FeatureFlagResponse, status_code=status.HTTP_201_CREATED)
def create_feature_flag(
    flag: FeatureFlagCreate,
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """Create a new feature flag."""
    # Check if key already exists
    existing = repo.get_by_key(flag.key)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feature flag with key '{flag.key}' already exists",
        )

    data = FeatureFlagInput(
        key=flag.key,
        name=flag.name,
        description=flag.description,
        enabled=flag.enabled,
        rollout_percentage=flag.rollout_percentage,
    )
    entity = repo.create(data)
    return _to_flag_response(entity)


@router.get("", response_model=list[FeatureFlagResponse])
def list_feature_flags(
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """List all feature flags."""
    entities = repo.list_all()
    return [_to_flag_response(e) for e in entities]


@router.get("/{key}", response_model=FeatureFlagResponse)
def get_feature_flag(
    key: str,
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """Get a feature flag by key."""
    # Try cache first
    cache_key = CACHE_KEY_FEATURE_FLAG.format(key=key)
    cached = cache.get(cache_key)
    if cached:
        return cached

    entity = repo.get_by_key(key)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    response = _to_flag_response(entity)
    cache.set(cache_key, response, ttl=60)
    return response


@router.patch("/{key}", response_model=FeatureFlagResponse)
def update_feature_flag(
    key: str,
    update: FeatureFlagUpdate,
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """Update a feature flag."""
    update_data = update.model_dump(exclude_unset=True)
    data = FeatureFlagUpdateInput(
        name=update_data.get("name"),
        description=update_data.get("description"),
        enabled=update_data.get("enabled"),
        rollout_percentage=update_data.get("rollout_percentage"),
    )

    entity = repo.update(key, data)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    # Invalidate cache
    cache.invalidate_pattern(get_flag_cache_pattern(key))
    cache.invalidate_pattern(get_flag_eval_cache_pattern(key))

    return _to_flag_response(entity)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feature_flag(
    key: str,
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """Delete a feature flag."""
    deleted = repo.delete(key)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    # Invalidate cache
    cache.invalidate_pattern(get_flag_cache_pattern(key))
    cache.invalidate_pattern(get_flag_eval_cache_pattern(key))


@router.get("/{key}/evaluate/{user_id}", response_model=FeatureFlagEvaluation)
def evaluate_feature_flag(
    key: str,
    user_id: str,
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """
    Evaluate a feature flag for a specific user.

    Evaluation order:
    1. Check for user-specific override
    2. If globally enabled, return enabled
    3. If rollout percentage > 0, use stored assignment (idempotent)
    4. Otherwise, return disabled

    Results are cached for 60 seconds. Rollout assignments are stored
    in database for consistency across servers.
    """
    # Try cache first
    cache_key = CACHE_KEY_FLAG_EVALUATION.format(key=key, user_id=user_id)
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    entity = repo.get_by_key(key)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    # Check for user override
    override = repo.get_user_override(entity.id, user_id)

    if override:
        result = FeatureFlagEvaluation(
            key=key,
            enabled=override.enabled,
            reason="user_override",
        )
        cache.set(cache_key, result, ttl=60)
        return result

    # Check if globally enabled
    if entity.enabled:
        result = FeatureFlagEvaluation(
            key=key,
            enabled=True,
            reason="global",
        )
        cache.set(cache_key, result, ttl=60)
        return result

    # Check rollout percentage using stored assignment (idempotent like experiments)
    if entity.rollout_percentage > 0:
        # Check for existing rollout assignment
        rollout_assignment = repo.get_rollout_assignment(entity.id, user_id)

        if rollout_assignment:
            # Use stored assignment
            enabled = rollout_assignment.enabled
        else:
            # First time: make random decision and store it
            enabled = random.uniform(0, 100) < entity.rollout_percentage
            repo.create_rollout_assignment(entity.id, user_id, enabled)

        if enabled:
            result = FeatureFlagEvaluation(
                key=key,
                enabled=True,
                reason="rollout",
            )
            cache.set(cache_key, result, ttl=60)
            return result

    # Default: disabled
    result = FeatureFlagEvaluation(
        key=key,
        enabled=False,
        reason="disabled",
    )
    cache.set(cache_key, result, ttl=60)
    return result


@router.post("/{key}/overrides", response_model=FeatureFlagOverrideResponse, status_code=status.HTTP_201_CREATED)
def create_user_override(
    key: str,
    override: FeatureFlagOverrideCreate,
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """Create or update a user-specific override for a feature flag."""
    entity = repo.get_by_key(key)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    repo.set_user_override(entity.id, override.user_id, override.enabled)

    # Invalidate cache for this evaluation
    cache.delete(CACHE_KEY_FLAG_EVALUATION.format(key=key, user_id=override.user_id))

    # Get the created/updated override to return
    override_entity = repo.get_user_override(entity.id, override.user_id)
    return FeatureFlagOverrideResponse(
        feature_flag_key=key,
        user_id=override_entity.user_id,
        enabled=override_entity.enabled,
        created_at=override_entity.created_at,
    )


@router.delete("/{key}/overrides/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_override(
    key: str,
    user_id: str,
    repo: FeatureFlagRepository = Depends(get_feature_flag_repository),
    _: str = Depends(verify_token),
):
    """Delete a user-specific override for a feature flag."""
    entity = repo.get_by_key(key)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    repo.delete_user_override(entity.id, user_id)

    # Invalidate cache
    cache.delete(CACHE_KEY_FLAG_EVALUATION.format(key=key, user_id=user_id))
