"""Identity endpoints (spec §2.1)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.schemas.identities import (
    IdentityCreateRequest,
    IdentityListResponse,
    IdentityResponse,
    IdentityViewResponse,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.database_service import get_session
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.crud_services.identity_service import (
    create_identity,
    delete_identity,
    get_identity,
    get_identity_view,
    list_identities,
)

router = APIRouter(tags=["identities"])


@router.get("/identities", response_model=IdentityListResponse)
async def list_identities_route(
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> IdentityListResponse:
    return await list_identities(session, after_id, limit)


@router.get("/identities/{identity_id}", response_model=IdentityResponse)
async def get_identity_route(
    identity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> IdentityResponse:
    identity = await get_identity(session, identity_id)
    if identity is None:
        raise_api_error(404, "not_found", "Identity not found")
    return identity


@router.get("/identities/{identity_id}/view", response_model=IdentityViewResponse)
async def get_identity_view_route(
    identity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> IdentityViewResponse:
    view = await get_identity_view(session, identity_id)
    if view is None:
        raise_api_error(404, "not_found", "Identity not found")
    return view


@router.post("/identities", response_model=IdentityResponse, status_code=status.HTTP_201_CREATED)
async def create_identity_route(
    payload: IdentityCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> IdentityResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    return await create_identity(session, payload, auth.principal.principal_id)


@router.delete("/identities/{identity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_identity_route(
    identity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    deleted = await delete_identity(session, identity_id)
    if not deleted:
        raise_api_error(404, "not_found", "Identity not found")
