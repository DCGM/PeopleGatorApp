"""Entity search service powered by Weaviate BM25 helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.search import (
    SearchQuery,
    SearchResultListResponse,
)
from people_gator_api.services.weaviate_service.search import (
    search_entities_by_name_or_aliases,
)
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
