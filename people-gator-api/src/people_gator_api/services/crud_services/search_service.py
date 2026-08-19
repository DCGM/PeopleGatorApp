"""Entity search service powered by Weaviate BM25 helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.enums import EntityType, ScoreAggregation
from people_gator_api.schemas.search import (
    EntityFaceSearchQuery,
    EntitySearchResult,
    FaceSearchQuery,
    FaceSearchResult,
    FaceSearchResultListResponse,
    SearchQuery,
    SearchResultListResponse,
)
from people_gator_api.services.weaviate_service.db_schema import FACE_VECTOR_BY_MODEL
from people_gator_api.services.weaviate_service.search import (
    fetch_face_vectors,
    search_entities_by_name_or_aliases,
    search_faces_by_vectors,
    search_faces_by_vectors_grouped_by_entity,
)
from people_gator_api.services.weaviate_service.utils import combine_filters
from people_gator_api.utils.opentelemetry import trace


logger = logging.getLogger(__name__)


class SearchRequestLike(Protocol):
    query: SearchQuery
    limit: int
    after_id: uuid.UUID | None


@trace()
async def search(
    session: WeaviateAsyncClient,
    query: SearchQuery,
) -> SearchResultListResponse:
    """Run entity search using the configured Weaviate BM25 helper."""
    logger.debug("search called", extra={"query_name": query.name})

    query_name = _resolve_query_name(query)
    entity_types = _resolve_query_entity_types(query)
    if query_name is None:
        logger.info("search skipped empty query")
        return SearchResultListResponse(
            items=[],
            total_count=0,
            limit=query.limit,
            after_id=None,
        )

    results = await search_entities_by_name_or_aliases(
        client=session,
        query_name=query_name,
        filters=combine_filters(_entity_type_filters(entity_types)),
        limit=query.limit,
    )
    page = results
    next_after_id = page[-1].entity_id if page else None
    logger.info(
        "search completed", extra={"query_name": query_name, "total": len(page)}
    )
    return SearchResultListResponse(
        items=page,
        total_count=len(page),
        limit=query.limit,
        after_id=next_after_id,
    )


@trace()
async def search_faces(
    session: WeaviateAsyncClient,
    query: FaceSearchQuery,
) -> FaceSearchResultListResponse:
    """Find faces similar to any of the supplied reference faces."""
    logger.debug("search_faces called", extra={"face_ids": query.face_ids})
    results = await _matching_faces(session, query, limit=query.limit)
    logger.info("search_faces completed", extra={"total": len(results)})
    return FaceSearchResultListResponse(
        items=results,
        total_count=len(results),
        limit=query.limit,
        after_id=results[-1].detection_id if results else None,
    )


@trace()
async def search_entities_by_faces(
    session: WeaviateAsyncClient,
    query: EntityFaceSearchQuery,
) -> SearchResultListResponse:
    """Find faces similar to the reference faces and aggregate scores per entity."""
    logger.debug(
        "search_entities_by_faces called",
        extra={"face_ids": query.face_ids, "aggregation": query.aggregation},
    )
    entities = await _matching_faces_group_by_entity(
        session, query, aggregation=query.aggregation
    )
    logger.info("search_entities_by_faces completed", extra={"total": len(entities)})
    return SearchResultListResponse(
        items=entities,
        total_count=len(entities),
        limit=query.limit,
        after_id=entities[-1].entity_id if entities else None,
    )


async def _matching_faces(
    session: WeaviateAsyncClient,
    query: FaceSearchQuery,
    *,
    limit: int,
) -> list[FaceSearchResult]:
    if not query.face_ids or limit <= 0:
        return []

    vector_name = FACE_VECTOR_BY_MODEL[query.embedding_model]
    query_vectors = await fetch_face_vectors(
        session,
        query.face_ids,
        vector_name=vector_name,
    )
    if not query_vectors:
        logger.info(
            "face search skipped missing reference vectors",
            extra={"face_ids": query.face_ids, "vector_name": vector_name},
        )
        return []

    return await search_faces_by_vectors(
        session,
        query_vectors,
        vector_name=vector_name,
        excluded_face_ids=query.face_ids,
        limit=limit,
    )


async def _matching_faces_group_by_entity(
    session: WeaviateAsyncClient,
    query: FaceSearchQuery,
    aggregation: ScoreAggregation,
) -> list[EntitySearchResult]:
    if not query.face_ids or query.limit <= 0:
        return []

    vector_name = FACE_VECTOR_BY_MODEL[query.embedding_model]
    query_vectors = await fetch_face_vectors(
        session,
        query.face_ids,
        vector_name=vector_name,
    )
    if not query_vectors:
        logger.info(
            "face search skipped missing reference vectors",
            extra={"face_ids": query.face_ids, "vector_name": vector_name},
        )
        return []

    return await search_faces_by_vectors_grouped_by_entity(
        session,
        query_vectors,
        vector_name=vector_name,
        aggregation=aggregation,
        excluded_face_ids=query.face_ids,
        number_of_groups=query.limit,
    )


def _resolve_query_name(query: SearchQuery) -> list[str] | None:
    if query.name is None:
        return None
    raw = query.name
    cleaned: list[str] | None = None
    if isinstance(raw, list):
        cleaned = [name.strip() for name in raw if name.strip()]
        cleaned = cleaned if cleaned else None
    if isinstance(raw, str):
        cleaned = [raw.strip()] if raw.strip() else None
    return cleaned


def _resolve_query_entity_types(query: SearchQuery) -> list[EntityType] | None:
    if query.entity_types is None:
        return None
    raw = query.entity_types
    if isinstance(raw, EntityType):
        return [raw]

    deduplicated: list[EntityType] = []
    for item in raw:
        if item not in deduplicated:
            deduplicated.append(item)
    return deduplicated if deduplicated else None


def _entity_type_filters(
    entity_types: list[EntityType] | None,
) -> list[FilterReturn]:
    if entity_types is None:
        return []

    entity_type_values = [entity_type.value for entity_type in entity_types]
    if len(entity_type_values) == 1:
        return [Filter.by_property("entity_type").equal(entity_type_values[0])]

    return [
        Filter.any_of(
            [
                Filter.by_property("entity_type").equal(entity_type_value)
                for entity_type_value in entity_type_values
            ]
        )
    ]
