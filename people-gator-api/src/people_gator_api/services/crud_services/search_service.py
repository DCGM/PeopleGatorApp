"""Entity search service powered by Weaviate BM25 helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.search import (
    FoundDocument,
    SearchDocumentsResultListResponse,
    SearchFacesRequest,
    FoundFace,
    SearchFacesResultListResponse,
    FoundPage,
    SearchPagesResultListResponse,
    SearchDocumentsQuery,
    SearchEntitiesRequest,
    FoundEntity,
    SearchEntitiesResultListResponse,
    SearchPagesQuery,
)
from people_gator_api.services.weaviate_service.archive_search import search_archive
from people_gator_api.services.weaviate_service.assignments import (
    assigned_reference_ids,
)
from people_gator_api.weaviate_schema import FACE_VECTOR_BY_MODEL
from people_gator_api.services.weaviate_service.search import (
    fetch_face_vectors,
    search_entities_by_faces_vectors,
    search_entities_by_names_or_aliases,
    search_faces_by_vectors,
)
from people_gator_api.utils.opentelemetry import trace

logger = logging.getLogger(__name__)

_RRF_RANK_CONSTANT = 60


class SearchEntitiesRequestLike(Protocol):
    query: SearchEntitiesRequest
    limit: int
    after_id: uuid.UUID | None


@trace()
async def search_entities(
    session: WeaviateAsyncClient,
    query: SearchEntitiesRequest,
) -> SearchEntitiesResultListResponse:
    """Search entities by name/alias text, a positive face, or both."""
    if query.q is None and query.q_face_id is None:
        return _empty_entity_search_response(limit=query.limit)

    assigned_entity_ids = (
        await assigned_reference_ids(session, query.assignment, "entity")
        if query.assignment is not None
        else None
    )
    if assigned_entity_ids is not None and not assigned_entity_ids:
        return _empty_entity_search_response(limit=query.limit)

    q_entities: list[FoundEntity] = []
    if query.q is not None:
        text_filter_kwargs: dict[str, object] = {}
        if query.entity_types is not None:
            text_filter_kwargs["entity_types"] = (
                query.entity_types
                if isinstance(query.entity_types, list)
                else [query.entity_types]
            )
        if assigned_entity_ids is not None:
            text_filter_kwargs["entity_ids"] = assigned_entity_ids
        q_entities = await search_entities_by_names_or_aliases(
            session,
            query.q,
            limit=query.limit,
            **text_filter_kwargs,  # pyright: ignore[reportArgumentType]
        )
    q_face_entities: list[FoundEntity] = []
    if query.q_face_id is not None:
        face_query_vectors = await fetch_face_vectors(
            session,
            query.q_face_id,
            vector_name=FACE_VECTOR_BY_MODEL[query.embedding_model],
        )
        face_filter_kwargs: dict[str, object] = {}
        if query.entity_types is not None:
            face_filter_kwargs["entity_types"] = (
                query.entity_types
                if isinstance(query.entity_types, list)
                else [query.entity_types]
            )
        if assigned_entity_ids is not None:
            face_filter_kwargs["entity_ids"] = assigned_entity_ids
        q_face_entities = await search_entities_by_faces_vectors(
            session,
            query_vectors=face_query_vectors,
            vector_name=FACE_VECTOR_BY_MODEL[query.embedding_model],
            excluded_face_ids=query.q_face_id,
            number_of_groups=query.limit,
            **face_filter_kwargs,  # pyright: ignore[reportArgumentType]
        )
    fused_entities = _fuse_entity_results(
        [q_entities, q_face_entities],
    )
    items = fused_entities[: query.limit]
    return SearchEntitiesResultListResponse(
        items=items,
        total_count=len(fused_entities),
        limit=query.limit,
        cursor=items[-1].entity_id if items else None,
    )


@trace()
async def search_faces(
    session: WeaviateAsyncClient,
    query: SearchFacesRequest,
) -> SearchFacesResultListResponse:
    """Find faces similar to any of the supplied reference faces."""
    logger.debug("search_faces called", extra={"face_ids": query.q_face_id})
    vector_name = FACE_VECTOR_BY_MODEL[query.embedding_model]
    query_vectors = await fetch_face_vectors(
        session,
        query.q_face_id,
        vector_name=vector_name,
    )
    if not query_vectors:
        logger.info(
            "face search skipped missing reference vectors",
            extra={"face_ids": query.q_face_id, "vector_name": vector_name},
        )
        return _empty_face_search_response(limit=query.limit)
    faces: list[FoundFace] = await search_faces_by_vectors(
        session,
        query_vectors,
        vector_name=vector_name,
        excluded_face_ids=query.q_face_id,
        limit=query.limit,
    )
    logger.info("search_faces completed", extra={"total": len(faces)})
    return SearchFacesResultListResponse(
        items=faces,
        total_count=len(faces),
        limit=query.limit,
        cursor=faces[-1].face_id if faces else None,
    )


def _empty_entity_search_response(limit: int) -> SearchEntitiesResultListResponse:
    return SearchEntitiesResultListResponse(
        items=[],
        total_count=0,
        limit=limit,
        cursor=None,
    )


def _empty_face_search_response(limit: int) -> SearchFacesResultListResponse:
    return SearchFacesResultListResponse(
        items=[],
        total_count=0,
        limit=limit,
        cursor=None,
    )


def _fuse_entity_results(
    ranked_lists: list[list[FoundEntity]],
) -> list[FoundEntity]:
    """Fuse heterogeneous BM25 and cosine rankings without mixing raw scores."""
    non_empty_lists = [items for items in ranked_lists if items]
    if not non_empty_lists:
        return []
    if len(non_empty_lists) == 1:
        return non_empty_lists[0]

    fused_scores: dict[uuid.UUID, float] = {}
    best_items: dict[uuid.UUID, FoundEntity] = {}
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
    fused.sort(key=lambda item: (-item.score, item.entity_id))
    return fused


@trace()
async def search_pages(
    session: WeaviateAsyncClient,
    query: SearchPagesQuery,
) -> SearchPagesResultListResponse:
    """Search page sources by source UUID or directly linked entity text."""
    archive_filter_kwargs = (
        {"assignment": query.assignment} if query.assignment is not None else {}
    )
    candidates = await search_archive(
        session,
        query.q,
        source_id=query.source_id,
        source_kind=SourceKind.page,
        limit=query.limit,
        **archive_filter_kwargs,
    )
    items = [
        FoundPage(
            source_id=candidate.source_id,
            document_id=candidate.document_id,
            page_id=candidate.page_id,
            matching_score=candidate.matching_score,
        )
        for candidate in candidates
        if candidate.document_id is not None and candidate.page_id is not None
    ]
    logger.info("search_pages completed", extra={"total": len(items)})
    return SearchPagesResultListResponse(
        items=items,
        total_count=len(items),
        limit=query.limit,
        cursor=items[-1].source_id if items else None,
    )


@trace()
async def search_documents(
    session: WeaviateAsyncClient,
    query: SearchDocumentsQuery,
) -> SearchDocumentsResultListResponse:
    """Search document sources by source UUID or directly linked entity text."""
    candidates = await search_archive(
        session,
        query.q,
        source_id=query.source_id,
        source_kind=SourceKind.document,
        limit=query.limit,
    )
    items = [
        FoundDocument(
            source_id=candidate.source_id,
            document_id=candidate.document_id,
            score_text=candidate.matching_score,
        )
        for candidate in candidates
        if candidate.document_id is not None
    ]
    logger.info("search_documents completed", extra={"total": len(items)})
    return SearchDocumentsResultListResponse(
        items=items,
        total_count=len(items),
        limit=query.limit,
        cursor=items[-1].source_id if items else None,
    )
