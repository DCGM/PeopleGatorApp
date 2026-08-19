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
    EntityFaceSearchQuery,
    FaceSearchQuery,
    FaceSearchResultListResponse,
    SearchQuery,
    SearchResultListResponse,
)
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceEmbeddingModel,
    ScoreAggregation,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.crud_services.search_service import (
    search,
    search_entities_by_faces,
    search_faces,
)

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResultListResponse)
async def search_get(
    session: WeaviateSessionDependency,
    name: list[str] | None = Query(default=None, alias="query_name"),
    entity_type: list[EntityType] | None = Query(
        default=None,
        alias="query_entity_type",
    ),
    limit: int = Query(default=20, ge=0),
    after_id: uuid.UUID | None = None,
) -> SearchResultListResponse:
    return await search(
        session,
        SearchQuery(
            name=name,
            entity_types=entity_type,
            limit=limit,
            after_id=after_id,
        ),
    )


@router.post("/search", response_model=SearchResultListResponse)
async def search_post(
    request: SearchQuery,
    session: WeaviateSessionDependency,
) -> SearchResultListResponse:
    return await search(session, request)


@router.get("/search-faces", response_model=FaceSearchResultListResponse)
async def search_faces_get(
    session: WeaviateSessionDependency,
    face_id: list[uuid.UUID] = Query(default_factory=list),
    embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    limit: int = Query(default=20, ge=0),
) -> FaceSearchResultListResponse:
    return await search_faces(
        session,
        FaceSearchQuery(
            face_ids=face_id,
            embedding_model=embedding_model,
            limit=limit,
        ),
    )


@router.get("/search-entities", response_model=SearchResultListResponse)
async def search_entities_by_faces_get(
    session: WeaviateSessionDependency,
    face_id: list[uuid.UUID] = Query(default_factory=list),
    embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    aggregation: ScoreAggregation = Query(default=ScoreAggregation.max),
    limit: int = Query(default=20, ge=0),
) -> SearchResultListResponse:
    return await search_entities_by_faces(
        session,
        EntityFaceSearchQuery(
            face_ids=face_id,
            embedding_model=embedding_model,
            aggregation=aggregation,
            limit=limit,
        ),
    )
