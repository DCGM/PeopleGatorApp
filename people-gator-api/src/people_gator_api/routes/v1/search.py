"""Multimodal search endpoints backed only by persistence contracts."""

import uuid

from fastapi import APIRouter, Query

from people_gator_api.schemas.entities import EntityListFilter
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceEmbeddingModel,
    ScoreAggregation,
)
from people_gator_api.schemas.faces import FaceListFilter
from people_gator_api.schemas.search import (
    QueryBase,
    SearchDocumentsRequest,
    SearchDocumentsResultListResponse,
    SearchEntitiesRequest,
    SearchEntitiesResultListResponse,
    SearchFacesRequest,
    SearchFacesResultListResponse,
    SearchPagesRequest,
    SearchPagesResultListResponse,
)
from people_gator_api.schemas.sources import DocumentListFilter, PageListFilter
from people_gator_api.services.auth_service import BrowseUserDependency
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.services.http_errors import raise_api_error


router = APIRouter(tags=["search"])


def _query(
    text: list[str] | None,
    face_id: list[uuid.UUID] | None,
    face_embedding_model: FaceEmbeddingModel,
    exclude_reference_face_id: bool,
    score_aggregation: ScoreAggregation,
) -> QueryBase:
    values: dict[str, object] = {
        "face_embedding_model": face_embedding_model,
        "exclude_reference_face_id": exclude_reference_face_id,
        "score_aggregation": score_aggregation,
    }
    if text is not None:
        values["text"] = text
    if face_id is not None:
        values["face_id"] = face_id
    return QueryBase.model_validate(values)


@router.get("/search-entities", response_model=SearchEntitiesResultListResponse)
async def search_entities_get(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    text: list[str] | None = Query(default=None),
    face_id: list[uuid.UUID] | None = Query(default=None),
    entity_id: list[uuid.UUID] | None = Query(default=None),
    entity_type: list[EntityType] | None = Query(default=None),
    source_id: list[uuid.UUID] | None = Query(default=None),
    has_mentions: bool | None = None,
    has_detections: bool | None = None,
    face_embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    exclude_reference_face_id: bool = True,
    score_aggregation: ScoreAggregation = ScoreAggregation.min,
    limit: int = Query(default=20, ge=0),
    return_total_count: bool = False,
    cursor: str | None = None,
) -> SearchEntitiesResultListResponse:
    del user
    filter_values = {
        name: value
        for name, value in {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "source_id": source_id,
            "has_mentions": has_mentions,
            "has_detections": has_detections,
        }.items()
        if value is not None
    }
    try:
        request = SearchEntitiesRequest(
            query=_query(
                text,
                face_id,
                face_embedding_model,
                exclude_reference_face_id,
                score_aggregation,
            ),
            filter=(
                EntityListFilter.model_validate(filter_values)
                if filter_values
                else None
            ),
            limit=limit,
            return_total_count=return_total_count,
            cursor=cursor,
        )
        return await database.entities.search(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))


@router.get("/search-faces", response_model=SearchFacesResultListResponse)
async def search_faces_get(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    text: list[str] | None = Query(default=None),
    face_id: list[uuid.UUID] | None = Query(default=None),
    detection_id: list[uuid.UUID] | None = Query(default=None),
    source_id: list[uuid.UUID] | None = Query(default=None),
    entity_id: list[uuid.UUID] | None = Query(default=None),
    face_embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    exclude_reference_face_id: bool = True,
    score_aggregation: ScoreAggregation = ScoreAggregation.min,
    limit: int = Query(default=20, ge=0),
    return_total_count: bool = False,
    cursor: str | None = None,
) -> SearchFacesResultListResponse:
    del user
    filter_values = {
        name: value
        for name, value in {
            "detection_id": detection_id,
            "source_id": source_id,
            "entity_id": entity_id,
        }.items()
        if value is not None
    }
    try:
        request = SearchFacesRequest(
            query=_query(
                text,
                face_id,
                face_embedding_model,
                exclude_reference_face_id,
                score_aggregation,
            ),
            filter=(
                FaceListFilter.model_validate(filter_values)
                if filter_values
                else None
            ),
            limit=limit,
            return_total_count=return_total_count,
            cursor=cursor,
        )
        return await database.faces.search(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))


@router.get("/search-pages", response_model=SearchPagesResultListResponse)
async def search_pages_get(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    text: list[str] | None = Query(default=None),
    face_id: list[uuid.UUID] | None = Query(default=None),
    source_id: list[uuid.UUID] | None = Query(default=None),
    library: list[str] | None = Query(default=None),
    document_id: list[uuid.UUID] | None = Query(default=None),
    page_id: list[uuid.UUID] | None = Query(default=None),
    face_embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    exclude_reference_face_id: bool = True,
    score_aggregation: ScoreAggregation = ScoreAggregation.min,
    limit: int = Query(default=20, ge=0),
    return_total_count: bool = False,
    cursor: str | None = None,
) -> SearchPagesResultListResponse:
    del user
    filter_values = {
        name: value
        for name, value in {
            "source_id": source_id,
            "library": library,
            "document_id": document_id,
            "page_id": page_id,
        }.items()
        if value is not None
    }
    try:
        request = SearchPagesRequest(
            query=_query(
                text,
                face_id,
                face_embedding_model,
                exclude_reference_face_id,
                score_aggregation,
            ),
            filter=(
                PageListFilter.model_validate(filter_values)
                if filter_values
                else None
            ),
            limit=limit,
            return_total_count=return_total_count,
            cursor=cursor,
        )
        return await database.sources.search_pages(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))


@router.get("/search-documents", response_model=SearchDocumentsResultListResponse)
async def search_documents_get(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    text: list[str] | None = Query(default=None),
    face_id: list[uuid.UUID] | None = Query(default=None),
    source_id: list[uuid.UUID] | None = Query(default=None),
    library: list[str] | None = Query(default=None),
    document_id: list[uuid.UUID] | None = Query(default=None),
    face_embedding_model: FaceEmbeddingModel = Query(
        default=DEFAULT_FACE_EMBEDDING_MODEL,
        alias="model",
    ),
    exclude_reference_face_id: bool = True,
    score_aggregation: ScoreAggregation = ScoreAggregation.min,
    limit: int = Query(default=20, ge=0),
    return_total_count: bool = False,
    cursor: str | None = None,
) -> SearchDocumentsResultListResponse:
    del user
    filter_values = {
        name: value
        for name, value in {
            "source_id": source_id,
            "library": library,
            "document_id": document_id,
        }.items()
        if value is not None
    }
    try:
        request = SearchDocumentsRequest(
            query=_query(
                text,
                face_id,
                face_embedding_model,
                exclude_reference_face_id,
                score_aggregation,
            ),
            filter=(
                DocumentListFilter.model_validate(filter_values)
                if filter_values
                else None
            ),
            limit=limit,
            return_total_count=return_total_count,
            cursor=cursor,
        )
        return await database.sources.search_documents(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))
