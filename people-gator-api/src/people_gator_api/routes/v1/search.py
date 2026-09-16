"""Search endpoints.

Cluster/version concepts have been removed; search returns entity and
annotation-level results.
"""

import uuid

from fastapi import (
    APIRouter,
    Query,
)
from people_gator_api.schemas.search import (
    ArchiveHitListResponse,
    FaceSearchQuery,
    FaceSearchResultListResponse,
    SearchArchiveQuery,
    SearchEntitiesQuery,
    SearchEntitiesResultListResponse,
)
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceEmbeddingModel,
    ScoreAggregation,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.crud_services.search_service import (
    search_archive_hits,
    search_entities,
    search_faces,
)
from people_gator_api.routes.v1.source_filters import SourceFilterDependency

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

@router.get("/search-archive", response_model=ArchiveHitListResponse)
async def search_archive_get(
    session: WeaviateSessionDependency,
    resolved_source_id: SourceFilterDependency,
    q: str = Query(
        min_length=1,
        description="Page/document ID, mention name, or linked entity alias.",
    ),
    limit: int = Query(default=20, ge=0),
) -> ArchiveHitListResponse:
    """Search pages and documents with one free-text or UUID query.

    The query matches page mentions, document mentions, linked entity names
    and aliases, or a bare Source/page/document UUID. Independent mention and
    entity rankings are fused with reciprocal-rank fusion inside Weaviate
    calls only, so no cross-service roundtrips occur.
    """
    return await search_archive_hits(
        session,
        SearchArchiveQuery(
            q=q,
            source_id=resolved_source_id,
            limit=limit,
        ),
    )