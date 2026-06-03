import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.engine import get_session
from people_gator_api.schemas.search import (
    SearchFacetsResponse,
    SearchFilters,
    SearchProfileCloneRequest,
    SearchProfileCreateRequest,
    SearchProfileResponse,
    SearchProfileUpdateRequest,
    SearchQuery,
    SearchRequest,
    SearchResponse,
)
from people_gator_api.services.authz import AuthContext, require_scopes
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.search_service import (
    clone_profile,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    search,
    search_facets,
    update_profile,
)

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
    payload: SearchProfileUpdateRequest,
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


@router.get("/search", response_model=SearchResponse)
async def search_get(
    name: list[str] = Query(default_factory=list),
    text: list[str] = Query(default_factory=list),
    evidence_id: list[uuid.UUID] = Query(default_factory=list),
    reference_cluster_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    result_type: list[str] = Query(default_factory=lambda: ["cluster"]),
    cluster_role: list[str] = Query(default_factory=list),
    provider: list[str] = Query(default_factory=list),
    has_face: bool | None = None,
    has_authority_link: bool | None = None,
    language: list[str] = Query(default_factory=list),
    limit: int = 20,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    request = SearchRequest(
        query=SearchQuery(
            names=name or None,
            texts=text or None,
            evidence_ids=evidence_id or None,
            reference_cluster_id=reference_cluster_id,
        ),
        profile_id=profile_id,
        result_types=result_type,
        filters=SearchFilters(
            cluster_roles=[],
            provider=[],
            has_face=has_face,
            has_authority_link=has_authority_link,
            languages=language,
        ),
        limit=limit,
        after_id=after_id,
        save=False,
    )
    _ = cluster_role
    _ = provider
    return await search(session, request)


@router.post("/search", response_model=SearchResponse)
async def search_post(
    payload: SearchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    return await search(session, payload)


@router.get("/search/facets", response_model=SearchFacetsResponse)
async def search_facets_get(
    name: list[str] = Query(default_factory=list),
    text: list[str] = Query(default_factory=list),
    evidence_id: list[uuid.UUID] = Query(default_factory=list),
    reference_cluster_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> SearchFacetsResponse:
    return await search_facets(
        session,
        SearchQuery(
            names=name or None,
            texts=text or None,
            evidence_ids=evidence_id or None,
            reference_cluster_id=reference_cluster_id,
        ),
        SearchFilters(),
    )


@router.post("/search/facets", response_model=SearchFacetsResponse)
async def search_facets_post(
    payload: SearchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> SearchFacetsResponse:
    return await search_facets(session, payload.query, payload.filters)
