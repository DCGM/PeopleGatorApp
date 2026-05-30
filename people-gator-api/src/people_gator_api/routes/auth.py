import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from people_gator_api.auth import get_current_principal
from people_gator_api.db.models.principal import Principal

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class MeResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: str
    display_name: str
    is_active: bool


@router.get("/me", response_model=MeResponse)
async def me(principal: Principal = Depends(get_current_principal)) -> MeResponse:
    """Return the identity of the caller resolved from the Bearer token.

    Use this endpoint to verify that authentication is working — a valid
    Keycloak access token must be supplied as ``Authorization: Bearer <token>``.
    """
    return MeResponse(
        principal_id=principal.principal_id,
        principal_type=principal.principal_type.value,
        display_name=principal.display_name,
        is_active=principal.is_active,
    )
