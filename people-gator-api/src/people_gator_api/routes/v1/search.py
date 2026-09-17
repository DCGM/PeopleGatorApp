"""Search endpoints.

Cluster/version concepts have been removed; search returns entity and
annotation-level results.
"""

import uuid

from fastapi import APIRouter, Query

from people_gator_api.routes.v1.source_filters import SourceFilterDependency
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceEmbeddingModel,
    ScoreAggregation,
)
from people_gator_api.schemas.search import (
    DocumentSearchResultListResponse,
    FaceSearchQuery,
    FaceSearchResultListResponse,
    PageSearchResultListResponse,
    SearchDocumentsQuery,
    SearchEntitiesQuery,
    SearchEntitiesResultListResponse,
    SearchPagesQuery,
)
from people_gator_api.services.crud_services.search_service import (
    search_documents,
    search_entities,
    search_faces,
    search_pages,
)
from people_gator_api.services.database_service import WeaviateSessionDependency

router = APIRouter(tags=["search"])


@router.get("/search-entities", response_model=SearchEntitiesResultListResponse)
async def search_entities_get(
    session: WeaviateSessionDependency,
    resolved_source_id: SourceFilterDependency,
    q: list[str] | None = Query(default=None),
    q_face_id: list[uuid.UUID] | None = Query(default=None),
    entity_type: list[EntityType] | None = Query(default=None),
    embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    aggregation: ScoreAggregation = Query(default=ScoreAggregation.max),
    limit: int = Query(default=20, ge=0),
    after_id: uuid.UUID | None = None,
) -> SearchEntitiesResultListResponse:
    return await search_entities(
        session,
        SearchEntitiesQuery(
            q=q,
            q_face_id=q_face_id,
            entity_types=entity_type,
            source_id=resolved_source_id,
            embedding_model=embedding_model,
            aggregation=aggregation,
            limit=limit,
            after_id=after_id,
        ),
    )


@router.get("/search-faces", response_model=FaceSearchResultListResponse)
async def search_faces_get(
    session: WeaviateSessionDependency,
    q_face_id: list[uuid.UUID] = Query(default_factory=list),
    embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    limit: int = Query(default=20, ge=0),
) -> FaceSearchResultListResponse:
    return await search_faces(
        session,
        FaceSearchQuery(
            q_face_id=q_face_id,
            embedding_model=embedding_model,
            limit=limit,
        ),
    )


@router.get("/search-pages", response_model=PageSearchResultListResponse)
async def search_pages_get(
    session: WeaviateSessionDependency,
    resolved_source_id: SourceFilterDependency,
    q: str = Query(
        min_length=1,
        description="Page Source UUID or directly linked entity name/alias.",
    ),
    limit: int = Query(default=20, ge=0),
) -> PageSearchResultListResponse:
    """Search pages with one free-text or UUID query."""
    return await search_pages(
        session,
        SearchPagesQuery(
            q=q,
            source_id=resolved_source_id,
            limit=limit,
        ),
    )


@router.get("/search-documents", response_model=DocumentSearchResultListResponse)
async def search_documents_get(
    session: WeaviateSessionDependency,
    resolved_source_id: SourceFilterDependency,
    q: str = Query(
        min_length=1,
        description="Document Source UUID or directly linked entity name/alias.",
    ),
    limit: int = Query(default=20, ge=0),
) -> DocumentSearchResultListResponse:
    """Search documents with one free-text or UUID query."""
    return await search_documents(
        session,
        SearchDocumentsQuery(
            q=q,
            source_id=resolved_source_id,
            limit=limit,
        ),
    )
