from fastapi import APIRouter
from people_gator_api.schemas.jwks import JwksResponse, TokenResponse
from people_gator_api.services.auth_service import TokenDependency
from people_gator_api.services.jwk_service import get_key_set

router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json", response_model=JwksResponse)
async def get_jwks() -> JwksResponse:
    """Return the public JSON Web Key Set used by this service."""
    key_set = await get_key_set()
    return JwksResponse.model_validate(key_set.as_dict(private=False))


@router.post("/token/login", response_model=TokenResponse)
async def get_token(token: TokenDependency) -> TokenResponse:
    """Return a signed JWT token for testing purposes."""
    return token
