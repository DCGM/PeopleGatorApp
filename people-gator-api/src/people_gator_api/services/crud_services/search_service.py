"""Entity search service powered by Weaviate BM25 helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.enums import AnnotationType
from people_gator_api.schemas.search import (
    SearchQuery,
    SearchResultListResponse,
)
from people_gator_api.services.weaviate_service.search import (
    search_entities_by_name_or_aliases,
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


def _resolve_query_entity_types(query: SearchQuery) -> list[AnnotationType] | None:
    if query.entity_types is None:
        return None
    raw = query.entity_types
    if isinstance(raw, AnnotationType):
        return [raw]

    deduplicated: list[AnnotationType] = []
    for item in raw:
        if item not in deduplicated:
            deduplicated.append(item)
    return deduplicated if deduplicated else None


def _entity_type_filters(
    entity_types: list[AnnotationType] | None,
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
