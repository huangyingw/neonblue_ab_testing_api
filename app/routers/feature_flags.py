"""Feature flag API endpoints."""

import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import verify_token
from app.models import FeatureFlag, FeatureFlagOverride
from app.schemas import (
    FeatureFlagCreate,
    FeatureFlagUpdate,
    FeatureFlagResponse,
    FeatureFlagEvaluation,
    FeatureFlagOverrideCreate,
)
from app.cache import cache, CACHE_KEY_FEATURE_FLAG, CACHE_KEY_FLAG_EVALUATION

router = APIRouter(prefix="/flags", tags=["feature-flags"])


def _flag_to_response(flag: FeatureFlag) -> FeatureFlagResponse:
    """Convert FeatureFlag model to response schema."""
    return FeatureFlagResponse(
        id=flag.id,
        key=flag.key,
        name=flag.name,
        description=flag.description,
        enabled=bool(flag.enabled),
        rollout_percentage=flag.rollout_percentage,
        created_at=flag.created_at,
        updated_at=flag.updated_at,
    )


@router.post("", response_model=FeatureFlagResponse, status_code=status.HTTP_201_CREATED)
def create_feature_flag(
    flag: FeatureFlagCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Create a new feature flag."""
    # Check if key already exists
    existing = db.query(FeatureFlag).filter(FeatureFlag.key == flag.key).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feature flag with key '{flag.key}' already exists",
        )

    db_flag = FeatureFlag(
        key=flag.key,
        name=flag.name,
        description=flag.description,
        enabled=1 if flag.enabled else 0,
        rollout_percentage=flag.rollout_percentage,
    )
    db.add(db_flag)
    db.commit()
    db.refresh(db_flag)

    return _flag_to_response(db_flag)


@router.get("", response_model=list[FeatureFlagResponse])
def list_feature_flags(
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """List all feature flags."""
    flags = db.query(FeatureFlag).order_by(FeatureFlag.key).all()
    return [_flag_to_response(f) for f in flags]


@router.get("/{key}", response_model=FeatureFlagResponse)
def get_feature_flag(
    key: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Get a feature flag by key."""
    # Try cache first
    cache_key = CACHE_KEY_FEATURE_FLAG.format(key=key)
    cached = cache.get(cache_key)
    if cached:
        return cached

    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    response = _flag_to_response(flag)
    cache.set(cache_key, response, ttl=60)
    return response


@router.patch("/{key}", response_model=FeatureFlagResponse)
def update_feature_flag(
    key: str,
    update: FeatureFlagUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Update a feature flag."""
    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    update_data = update.model_dump(exclude_unset=True)
    if "enabled" in update_data:
        update_data["enabled"] = 1 if update_data["enabled"] else 0

    for field, value in update_data.items():
        setattr(flag, field, value)

    db.commit()
    db.refresh(flag)

    # Invalidate cache
    cache.invalidate_pattern(f"feature_flag:{key}")
    cache.invalidate_pattern(f"flag_eval:{key}:")

    return _flag_to_response(flag)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feature_flag(
    key: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Delete a feature flag."""
    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    db.delete(flag)
    db.commit()

    # Invalidate cache
    cache.invalidate_pattern(f"feature_flag:{key}")
    cache.invalidate_pattern(f"flag_eval:{key}:")


@router.get("/{key}/evaluate/{user_id}", response_model=FeatureFlagEvaluation)
def evaluate_feature_flag(
    key: str,
    user_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """
    Evaluate a feature flag for a specific user.

    Evaluation order:
    1. Check for user-specific override
    2. If globally enabled, return enabled
    3. If rollout percentage > 0, use deterministic hash to decide
    4. Otherwise, return disabled
    """
    # Try cache first
    cache_key = CACHE_KEY_FLAG_EVALUATION.format(key=key, user_id=user_id)
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    # Check for user override
    override = (
        db.query(FeatureFlagOverride)
        .filter(
            FeatureFlagOverride.feature_flag_id == flag.id,
            FeatureFlagOverride.user_id == user_id,
        )
        .first()
    )

    if override:
        result = FeatureFlagEvaluation(
            key=key,
            enabled=bool(override.enabled),
            reason="user_override",
        )
        cache.set(cache_key, result, ttl=60)
        return result

    # Check if globally enabled
    if flag.enabled:
        result = FeatureFlagEvaluation(
            key=key,
            enabled=True,
            reason="global",
        )
        cache.set(cache_key, result, ttl=60)
        return result

    # Check rollout percentage using deterministic hash
    if flag.rollout_percentage > 0:
        # Create deterministic hash from flag key and user_id
        hash_input = f"{key}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        bucket = hash_value % 100

        if bucket < flag.rollout_percentage:
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


@router.post("/{key}/overrides", status_code=status.HTTP_201_CREATED)
def create_user_override(
    key: str,
    override: FeatureFlagOverrideCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Create or update a user-specific override for a feature flag."""
    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    # Check for existing override
    existing = (
        db.query(FeatureFlagOverride)
        .filter(
            FeatureFlagOverride.feature_flag_id == flag.id,
            FeatureFlagOverride.user_id == override.user_id,
        )
        .first()
    )

    if existing:
        existing.enabled = 1 if override.enabled else 0
    else:
        db_override = FeatureFlagOverride(
            feature_flag_id=flag.id,
            user_id=override.user_id,
            enabled=1 if override.enabled else 0,
        )
        db.add(db_override)

    db.commit()

    # Invalidate cache for this evaluation
    cache.delete(CACHE_KEY_FLAG_EVALUATION.format(key=key, user_id=override.user_id))

    return {"message": f"Override set for user '{override.user_id}' on flag '{key}'"}


@router.delete("/{key}/overrides/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_override(
    key: str,
    user_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_token),
):
    """Delete a user-specific override for a feature flag."""
    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{key}' not found",
        )

    override = (
        db.query(FeatureFlagOverride)
        .filter(
            FeatureFlagOverride.feature_flag_id == flag.id,
            FeatureFlagOverride.user_id == user_id,
        )
        .first()
    )

    if override:
        db.delete(override)
        db.commit()

    # Invalidate cache
    cache.delete(CACHE_KEY_FLAG_EVALUATION.format(key=key, user_id=user_id))
