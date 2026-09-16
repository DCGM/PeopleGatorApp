"""Entity search service powered by Weaviate BM25 helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from weaviate import WeaviateAsyncClient
from people_gator_api.schemas.search import (
    SearchEntitiesResult,
    FaceSearchQuery,
    FaceSearchResult,
    FaceSearchResultListResponse,
    SearchEntitiesQuery,
    SearchEntitiesResultListResponse,
)
from people_gator_api.services.weaviate_service.db_schema import FACE_VECTOR_BY_MODEL
from people_gator_api.services.weaviate_service.search import (
    fetch_face_vectors,
    search_entities_by_names_or_aliases,
    search_faces_by_vectors,
    search_entities_by_faces_vectors,
)
from people_gator_api.utils.opentelemetry import trace


logger = logging.getLogger(__name__)

_RRF_RANK_CONSTANT = 60


class SearchEntitiesRequestLike(Protocol):
    query: SearchEntitiesQuery
    limit: int
    after_id: uuid.UUID | None


@trace()
async def search_entities(
    session: WeaviateAsyncClient,
    query: SearchEntitiesQuery,
) -> SearchEntitiesResultListResponse:
    """Search entities by name/alias text, a positive face, or both."""
    if query.q is None and query.q_face_id is None:
        return _empty_entity_search_response(limit=query.limit)
    
    q_entities: list[SearchEntitiesResult] = []
    if query.q is not None:
        q_entities = await search_entities_by_names_or_aliases(
            session,
            query.q,
            limit=query.limit,
        )
    q_face_entities: list[SearchEntitiesResult] = []
    if query.q_face_id is not None:
        face_query_vectors = await fetch_face_vectors(
            session,
            query.q_face_id,
            vector_name=FACE_VECTOR_BY_MODEL[query.embedding_model],
        )
        q_face_entities = await search_entities_by_faces_vectors(
            session,
            query_vectors=face_query_vectors,
            vector_name=FACE_VECTOR_BY_MODEL[query.embedding_model],
            excluded_face_ids=query.q_face_id,
            number_of_groups=query.limit,
        )
    fused_entities = _fuse_entity_results(
        [q_entities, q_face_entities],
    )
    items = fused_entities[: query.limit]
    return SearchEntitiesResultListResponse(
        items=items,
        total_count=len(fused_entities),
        limit=query.limit,
        after_id=items[-1].entity_id if items else None,
    )
    

@trace()
async def search_faces(
    session: WeaviateAsyncClient,
    query: FaceSearchQuery,
) -> FaceSearchResultListResponse:
    """Find faces similar to any of the supplied reference faces."""
    logger.debug("search_faces called", extra={"face_ids": query.face_ids})
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
        return _empty_face_search_response(limit=query.limit)
    faces: list[FaceSearchResult] = await search_faces_by_vectors(
        session,
        query_vectors,
        vector_name=vector_name,
        excluded_face_ids=query.face_ids,
        limit=query.limit,
    )
    logger.info("search_faces completed", extra={"total": len(faces)})
    return FaceSearchResultListResponse(
        items=faces,
        total_count=len(faces),
        limit=query.limit,
        after_id=faces[-1].face_id if faces else None,
    )


def _empty_entity_search_response(limit: int) -> SearchEntitiesResultListResponse:
    return SearchEntitiesResultListResponse(
        items=[],
        total_count=0,
        limit=limit,
        after_id=None,
    )


def _empty_face_search_response(limit: int) -> FaceSearchResultListResponse:
    return FaceSearchResultListResponse(
        items=[],
        total_count=0,
        limit=limit,
        after_id=None,
    )

def _fuse_entity_results(
    ranked_lists: list[list[SearchEntitiesResult]],
) -> list[SearchEntitiesResult]:
    """Fuse heterogeneous BM25 and cosine rankings without mixing raw scores."""
    non_empty_lists = [items for items in ranked_lists if items]
    if not non_empty_lists:
        return []
    if len(non_empty_lists) == 1:
        return non_empty_lists[0]
    
    fused_scores: dict[uuid.UUID, float] = {}
    best_items: dict[uuid.UUID, SearchEntitiesResult] = {}
    for items in non_empty_lists:
        for rank, item in enumerate(items, start=1):
            contribution = 1.0 / (_RRF_RANK_CONSTANT + rank)
            fused_scores[item.entity_id] = (
                fused_scores.get(item.entity_id, 0.0) + contribution
            )
            # Keep the highest-ranked occurrence as the representative payload.
            if item.entity_id not in best_items:
                best_items[item.entity_id] = item
    fused = [
        item.model_copy(update={"matching_score": fused_scores[item.entity_id]})
        for item in best_items.values()
    ]
    fused.sort(key=lambda item: (-item.matching_score, item.entity_id))
    return fused
