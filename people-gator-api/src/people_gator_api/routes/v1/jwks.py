from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from people_gator_api.schemas.jwks import JwksResponse, TokenResponse
from people_gator_api.services.auth_service import TokenDependency, refresh_access_token
from people_gator_api.services.jwk_service import get_key_set

router = APIRouter(tags=["jwks"])


class RefreshTokenRequest(BaseModel):
    """Request model for refresh token endpoint."""
    refresh_token: str


@router.get("/.well-known/jwks.json", response_model=JwksResponse)
async def get_jwks() -> JwksResponse:
    """Return the public JSON Web Key Set used by this service."""
    key_set = await get_key_set()
    return JwksResponse.model_validate(key_set.as_dict(private=False))


@router.post("/token/login", response_model=TokenResponse)
async def get_token(token: TokenDependency) -> TokenResponse:
    """Return a signed JWT token for testing purposes."""
    return token


@router.post("/token/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest) -> TokenResponse:
    """Refresh an access token using a valid refresh token.
    
    The refresh token must be valid and its session must still be active.
    Returns a new access token with the same scopes as the original.
    """
    return await refresh_access_token(request.refresh_token)
