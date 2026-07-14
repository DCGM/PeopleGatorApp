"""Search endpoints.

Cluster/version concepts have been removed; search returns entity and
annotation-level results.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from weaviate import WeaviateAsyncClient

from people_gator_api.models.enums import AnnotationType
from people_gator_api.schemas.search import (
    SearchFacetsResponse,
    SearchFilters,
    SearchQuery,
    SearchRequest,
    SearchResponse,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.database_service import get_session
from people_gator_api.services.crud_services.search_service import search, search_facets

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_get(
    annotation_id: list[uuid.UUID] = Query(default_factory=list),
    reference_entity_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    result_type: list[str] = Query(default_factory=lambda: ["entity"]),
    annotation_type: list[AnnotationType] = Query(default_factory=list),
    source_kind: list[str] = Query(default_factory=list),
    has_face: bool | None = None,
    has_authority_link: bool | None = None,
    language: list[str] = Query(default_factory=list),
    limit: int = 20,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchResponse:
    request = SearchRequest(
        query=SearchQuery(
            annotation_ids=annotation_id or None,
            reference_entity_id=reference_entity_id,
        ),
        profile_id=profile_id,
        result_types=result_type,
        filters=SearchFilters(
            annotation_types=annotation_type,
            source_kinds=source_kind,
            has_face=has_face,
            has_authority_link=has_authority_link,
            languages=language,
        ),
        limit=limit,
        after_id=after_id,
    )
    return await search(session, request)


@router.post("/search", response_model=SearchResponse)
async def search_post(
    payload: SearchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchResponse:
    return await search(session, payload)


@router.get("/search/facets", response_model=SearchFacetsResponse)
async def search_facets_get(
    annotation_id: list[uuid.UUID] = Query(default_factory=list),
    reference_entity_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchFacetsResponse:
    return await search_facets(
        session,
        SearchQuery(
            annotation_ids=annotation_id or None,
            reference_entity_id=reference_entity_id,
        ),
        SearchFilters(),
    )


@router.post("/search/facets", response_model=SearchFacetsResponse)
async def search_facets_post(
    payload: SearchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchFacetsResponse:
    return await search_facets(session, payload.query, payload.filters)
