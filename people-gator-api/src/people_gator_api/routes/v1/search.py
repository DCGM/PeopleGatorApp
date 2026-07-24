"""Search endpoints.

Cluster/version concepts have been removed; search returns entity and
annotation-level results.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.enums import AnnotationType
from people_gator_api.schemas.search import (
    SearchFilters,
    SearchQuery,
    SearchRequest,
    SearchResponse,
)
from people_gator_api.settings import settings
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.database_service import get_session
from people_gator_api.services.crud_services.search_service import search

router = APIRouter(tags=["search"])


def _build_search_request(
    *,
    annotation_id: list[uuid.UUID],
    reference_entity_id: uuid.UUID | None,
    result_type: list[str],
    annotation_type: list[AnnotationType],
    entity_type: list[str],
    source_kind: list[str],
    has_face: bool | None,
    has_authority_link: bool | None,
    language: list[str],
    limit: int,
    after_id: uuid.UUID | None,
) -> SearchRequest:
    return SearchRequest(
        query=SearchQuery(
            annotation_ids=annotation_id or None,
            reference_entity_id=reference_entity_id,
        ),
        result_types=result_type,
        filters=SearchFilters(
            annotation_types=annotation_type,
            entity_types=entity_type,
            source_kinds=source_kind,
            has_face=has_face,
            has_authority_link=has_authority_link,
            languages=language,
        ),
        limit=limit,
        after_id=after_id,
    )


@router.get("/search", response_model=SearchResponse)
async def search_get(
    annotation_id: list[uuid.UUID] = Query(default_factory=list),
    reference_entity_id: uuid.UUID | None = None,
    result_type: list[str] = Query(default_factory=lambda: ["entity"]),
    annotation_type: list[AnnotationType] = Query(default_factory=list),
    entity_type: list[str] = Query(default_factory=list),
    source_kind: list[str] = Query(default_factory=list),
    has_face: bool | None = None,
    has_authority_link: bool | None = None,
    language: list[str] = Query(default_factory=list),
    limit: int = 20,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchResponse:
    request = _build_search_request(
        annotation_id=annotation_id,
        reference_entity_id=reference_entity_id,
        result_type=result_type,
        annotation_type=annotation_type,
        entity_type=entity_type,
        source_kind=source_kind,
        has_face=has_face,
        has_authority_link=has_authority_link,
        language=language,
        limit=limit,
        after_id=after_id,
    )
    return await search(session, request, settings.search.profile)


@router.post("/search", response_model=SearchResponse)
async def search_post(
    request: SearchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchResponse:
    return await search(session, request, settings.search.profile)
