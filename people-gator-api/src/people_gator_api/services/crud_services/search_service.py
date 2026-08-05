"""Entity search service powered by Weaviate BM25 helpers."""

from __future__ import annotations

import uuid
from typing import Protocol

from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.search import (
    SearchQuery,
    SearchResponse,
)
from people_gator_api.services.weaviate_service.search import search_entities_by_name_or_aliases


class SearchRequestLike(Protocol):
    query: SearchQuery
    limit: int
    after_id: uuid.UUID | None


async def search(
    session: WeaviateAsyncClient,
    query: SearchQuery,
) -> SearchResponse:
    """Run entity search using the configured Weaviate BM25 helper."""

    query_name = _resolve_query_name(query)
    if query_name is None:
        return SearchResponse(
            results=[],
            total=0,
            limit=20,
            next_after_id=None,
            query=query,
        )

    results = await search_entities_by_name_or_aliases(
        client=session,
        query_name=query_name,
        limit=100,
    )
    page = results
    next_after_id = page[-1].entity_id if page else None
    return SearchResponse(
        results=page,
        total=len(page),
        limit=20,
        next_after_id=next_after_id,
        query=query,
    )


def _resolve_query_name(query: SearchQuery) -> str | None:
    if query.name is None:
        return None
    cleaned = query.name.strip()
    if not cleaned:
        return None
    return cleaned
