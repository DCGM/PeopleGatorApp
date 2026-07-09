"""Search profile endpoints."""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.schemas.search_profiles import (
    SearchProfileCloneRequest,
    SearchProfileCreateRequest,
    SearchProfilePatchRequest,
    SearchProfileResponse,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.crud_services.profile_service import (
    clone_profile,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    update_profile,
)
from people_gator_api.services.database_service import get_session
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["search"])


@router.get("/search-profiles", response_model=list[SearchProfileResponse])
async def list_search_profiles(
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> list[SearchProfileResponse]:
    owner_id = auth.principal.principal_id if auth.principal is not None else None
    return await list_profiles(session, owner_id, include_system=True, include_public=True)


@router.get("/search-profiles/{profile_id}", response_model=SearchProfileResponse)
async def get_search_profile(
    profile_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> SearchProfileResponse:
    profile = await get_profile(session, profile_id)
    if profile is None:
        raise_api_error(404, "not_found", "Search profile not found")
    return profile


@router.post("/search-profiles", response_model=SearchProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_search_profile(
    payload: SearchProfileCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> SearchProfileResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    return await create_profile(session, auth.principal.principal_id, payload)


@router.patch("/search-profiles/{profile_id}", response_model=SearchProfileResponse)
async def patch_search_profile(
    profile_id: uuid.UUID,
    payload: SearchProfilePatchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> SearchProfileResponse:
    resolved = await update_profile(session, profile_id, payload)
    if resolved is None:
        raise_api_error(404, "not_found", "Search profile not found")
    return resolved


@router.delete("/search-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search_profile(
    profile_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    deleted = await delete_profile(session, profile_id)
    if not deleted:
        raise_api_error(404, "not_found", "Search profile not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search-profiles/{profile_id}/clone", response_model=SearchProfileResponse, status_code=status.HTTP_201_CREATED)
async def clone_search_profile(
    profile_id: uuid.UUID,
    payload: SearchProfileCloneRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> SearchProfileResponse:
    if _auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    cloned = await clone_profile(session, profile_id, _auth.principal.principal_id, payload)
    if cloned is None:
        raise_api_error(404, "not_found", "Search profile not found")
    return cloned