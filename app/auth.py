"""Authentication middleware for Bearer token validation."""

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Verify the Bearer token from the request.

    Args:
        credentials: The HTTP authorization credentials containing the token.

    Returns:
        The validated token string.

    Raises:
        HTTPException: If the token is invalid or missing.
    """
    token = credentials.credentials

    if token not in settings.api_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
