"""API Token management endpoints."""

import secrets
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_token, hash_token
from app.dependencies import get_api_token_repository
from app.repositories.interfaces import ApiTokenRepository, ApiTokenInput, ApiTokenEntity
from app.schemas import ApiTokenCreate, ApiTokenResponse, ApiTokenCreatedResponse

router = APIRouter(prefix="/tokens", tags=["api-tokens"])


def _entity_to_response(entity: ApiTokenEntity) -> ApiTokenResponse:
    """Convert entity to response schema."""
    return ApiTokenResponse(
        id=entity.id,
        name=entity.name,
        is_active=entity.is_active,
        created_at=entity.created_at,
        expires_at=entity.expires_at,
        last_used_at=entity.last_used_at,
    )


@router.post("", response_model=ApiTokenCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_token(
    data: ApiTokenCreate,
    repo: ApiTokenRepository = Depends(get_api_token_repository),
    _: ApiTokenEntity = Depends(verify_token),
):
    """
    Create a new API token.

    The actual token value is only returned once at creation time.
    Store it securely - it cannot be retrieved later.
    """
    # Generate a secure random token
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)

    token_input = ApiTokenInput(
        name=data.name,
        expires_at=data.expires_at,
    )

    entity = repo.create(token_input, token_hash)

    return ApiTokenCreatedResponse(
        id=entity.id,
        name=entity.name,
        token=token,  # Only returned once!
        is_active=entity.is_active,
        created_at=entity.created_at,
        expires_at=entity.expires_at,
    )


@router.get("", response_model=list[ApiTokenResponse])
def list_tokens(
    repo: ApiTokenRepository = Depends(get_api_token_repository),
    _: ApiTokenEntity = Depends(verify_token),
):
    """List all API tokens."""
    entities = repo.list_all()
    return [_entity_to_response(e) for e in entities]


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_token(
    token_id: int,
    repo: ApiTokenRepository = Depends(get_api_token_repository),
    current_token: ApiTokenEntity = Depends(verify_token),
):
    """Delete an API token."""
    if token_id == current_token.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the token currently being used for authentication",
        )

    if not repo.delete(token_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token with id {token_id} not found",
        )


@router.post("/{token_id}/deactivate", response_model=ApiTokenResponse)
def deactivate_token(
    token_id: int,
    repo: ApiTokenRepository = Depends(get_api_token_repository),
    current_token: ApiTokenEntity = Depends(verify_token),
):
    """Deactivate an API token (soft delete)."""
    if token_id == current_token.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate the token currently being used for authentication",
        )

    if not repo.deactivate(token_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token with id {token_id} not found",
        )

    # Fetch updated entity
    # Note: We need to get by id, but we only have get_by_hash
    # For simplicity, return a minimal response
    tokens = repo.list_all()
    for t in tokens:
        if t.id == token_id:
            return _entity_to_response(t)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Token with id {token_id} not found",
    )
