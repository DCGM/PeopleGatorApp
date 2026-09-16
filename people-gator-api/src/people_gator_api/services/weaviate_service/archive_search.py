"""Pure-Weaviate searches resolving pages and documents from archive queries.

Every lookup below stays inside Weaviate: BM25 over mention collections with
reference grouping, BM25 over entity names/aliases with a two-hop mention
follow-up for alias-only matches, and UUID fetches against the Source
collection. The three independent rankings are fused client-side with
reciprocal-rank fusion so raw BM25 scores are never mixed.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import (
    Filter,
    GroupBy,
    MetadataQuery,
    QueryReference,
)
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.internal import CrossReferences

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.services.weaviate_service.db_schema import (
    DOCUMENT_MENTION_COLLECTION,
    ENTITY_COLLECTION,
    PAGE_MENTION_COLLECTION,
    SOURCE_COLLECTION,
)
from people_gator_api.utils.opentelemetry import trace

_MENTION_QUERY_PROPERTIES = ["name", "aliases"]
_ENTITY_QUERY_PROPERTIES = ["name", "aliases"]
_SOURCE_PROPERTIES = ["source_type", "library", "document", "page"]
_RRF_RANK_CONSTANT = 60
_MENTION_GROUP_SIZE = 5
_ENTITY_MATCH_LIMIT = 10
_LINKED_MENTION_LIMIT = 100


@dataclass(frozen=True, slots=True)
class ArchiveCandidate:
    """One deduplicated page or document hit resolved to its Source."""

    source_id: uuid.UUID
    kind: SourceKind
    document_id: uuid.UUID | None
    page_id: uuid.UUID | None
    matching_score: float

    def with_matching_score(self, matching_score: float) -> ArchiveCandidate:
        """Copy this candidate with the fused relevance score attached."""
        return ArchiveCandidate(
            self.source_id,
            self.kind,
            self.document_id,
            self.page_id,
            matching_score,
        )


@trace()
async def search_archive(
    client: WeaviateAsyncClient,
    query: str,
    *,
    source_id: uuid.UUID | None,
    limit: int,
) -> list[ArchiveCandidate]:
    """Resolve one free-text or UUID query into fused page/document candidates.

    A bare UUID shortcuts to a direct Source fetch. Otherwise the page-mention,
    document-mention, and entity BM25 arms run as independent grouped queries
    and their rankings are fused with reciprocal-rank fusion.
    """
    cleaned = query.strip()
    if not cleaned or limit <= 0:
        return []
    if (direct_source_id := _as_uuid(cleaned)) is not None:
        direct = await _source_candidate(client, direct_source_id)
        return [direct] if direct is not None else []

    mention_filters = _source_scope_filters(source_id)
    page_ranking, document_ranking = await _mention_rankings(
        client,
        cleaned,
        mention_filters,
    )
    entity_ranking = await _entity_ranking(client, cleaned, source_id)
    fused = _fuse_rankings(
        [page_ranking, document_ranking, entity_ranking],
    )[:limit]
    if not fused:
        return []
    return await _resolve_source_candidates(client, fused)


def _as_uuid(query: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(query)
    except ValueError:
        return None


@trace()
async def _mention_rankings(
    client: WeaviateAsyncClient,
    query: str,
    mention_filters: FilterReturn | None,
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """BM25 page and document mentions grouped on their source reference."""
    number_of_groups = _group_count(query)
    page_response = await client.collections.get(PAGE_MENTION_COLLECTION).query.bm25(
        query=query,
        query_properties=_MENTION_QUERY_PROPERTIES,
        filters=mention_filters,
        group_by=GroupBy(
            prop="source",
            number_of_groups=number_of_groups,
            objects_per_group=_MENTION_GROUP_SIZE,
        ),
        return_metadata=MetadataQuery(score=True),
        return_properties=[],
    )
    document_response = await client.collections.get(
        DOCUMENT_MENTION_COLLECTION
    ).query.bm25(
        query=query,
        query_properties=_MENTION_QUERY_PROPERTIES,
        filters=mention_filters,
        group_by=GroupBy(
            prop="source",
            number_of_groups=number_of_groups,
            objects_per_group=_MENTION_GROUP_SIZE,
        ),
        return_metadata=MetadataQuery(score=True),
        return_properties=[],
    )
    return (
        _grouped_source_ids(page_response.groups),
        _grouped_source_ids(document_response.groups),
    )


def _group_count(query: str) -> int:
    """Scale the group count with query length to keep short queries broad."""
    return max(5, min(20, len(query)))


def _grouped_source_ids(groups: Mapping[str, object]) -> list[uuid.UUID]:
    """Extract source UUIDs from grouped-by-reference group names."""
    source_ids: list[uuid.UUID] = []
    for group_name in groups:
        source_id = _group_name_to_uuid(str(group_name))
        if source_id is not None:
            source_ids.append(source_id)
    return source_ids


def _group_name_to_uuid(group_name: str) -> uuid.UUID | None:
    """Group names for reference properties are beacons ending with the UUID."""
    candidate = group_name.rsplit("/", 1)[-1]
    try:
        return uuid.UUID(candidate)
    except ValueError:
        return None


@trace()
async def _entity_ranking(
    client: WeaviateAsyncClient,
    query: str,
    source_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Rank sources holding mentions whose linked entity matches the query.

    Entity BM25 finds name and alias matches; a two-hop filter
    (page_mention→document_mention→entity) then collects the page mentions
    pointing at those entities so alias-only matches — recorded on the entity
    but absent from mention text — still resolve to sources.
    """
    entity_ids = await _entity_ids_matching_query(client, query)
    if not entity_ids:
        return []
    filters = _linked_mention_filters(entity_ids, _source_scope_filters(source_id))
    response = await client.collections.get(PAGE_MENTION_COLLECTION).query.fetch_objects(
        filters=filters,
        limit=_LINKED_MENTION_LIMIT,
        return_properties=[],
        return_references=QueryReference(link_on="source", return_properties=[]),
    )
    source_ids: list[uuid.UUID] = []
    for mention_object in response.objects:
        linked_source_id = _reference_uuid(mention_object.references, "source")
        if linked_source_id is not None:
            source_ids.append(linked_source_id)
    return _deduplicate(source_ids)


async def _entity_ids_matching_query(
    client: WeaviateAsyncClient,
    query: str,
) -> list[uuid.UUID]:
    """BM25 entity name and alias matches."""
    response = await client.collections.get(ENTITY_COLLECTION).query.bm25(
        query=query,
        query_properties=_ENTITY_QUERY_PROPERTIES,
        limit=_ENTITY_MATCH_LIMIT,
        return_properties=[],
    )
    return [entity_object.uuid for entity_object in response.objects]


def _linked_mention_filters(
    entity_ids: list[uuid.UUID],
    mention_filters: FilterReturn | None,
) -> FilterReturn | None:
    """Match page mentions whose document mention links to any matched entity."""
    filters: list[FilterReturn] = [
        Filter.by_ref("document_mention")
        .by_ref("entity")
        .by_id()
        .contains_any([str(entity_id) for entity_id in entity_ids])
    ]
    if mention_filters is not None:
        filters.append(mention_filters)
    if len(filters) == 1:
        return filters[0]
    return Filter.all_of(filters)


def _source_scope_filters(source_id: uuid.UUID | None) -> FilterReturn | None:
    """Restrict mention searches to one source when requested."""
    if source_id is None:
        return None
    return Filter.by_ref("source").by_id().equal(source_id)


def _reference_uuid(
    references: CrossReferences | None,
    key: str,
) -> uuid.UUID | None:
    if references is None or key not in references:
        return None
    linked = references[key].objects
    if not linked:
        return None
    return linked[0].uuid


def _deduplicate(values: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    ordered: list[uuid.UUID] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _fuse_rankings(
    rankings: Sequence[Sequence[uuid.UUID]],
) -> list[tuple[uuid.UUID, float]]:
    """Fuse independent source rankings with reciprocal-rank fusion.

    Each ranking contributes ``1 / (60 + rank)`` per hit; ties are broken by
    source UUID so pagination stays deterministic.
    """
    fused_scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, source_id in enumerate(ranking, start=1):
            contribution = 1.0 / (_RRF_RANK_CONSTANT + rank)
            fused_scores[source_id] = fused_scores.get(source_id, 0.0) + contribution
    return sorted(
        fused_scores.items(),
        key=lambda item: (-item[1], item[0]),
    )


@trace()
async def _resolve_source_candidates(
    client: WeaviateAsyncClient,
    fused: Sequence[tuple[uuid.UUID, float]],
) -> list[ArchiveCandidate]:
    """Batch-fetch the Source records backing fused hits, preserving order."""
    source_ids = [source_id for source_id, _score in fused]
    response = await client.collections.get(
        SOURCE_COLLECTION
    ).query.fetch_objects_by_ids(
        ids=[str(source_id) for source_id in source_ids],
        return_properties=_SOURCE_PROPERTIES,
    )
    candidates_by_id: dict[uuid.UUID, ArchiveCandidate] = {}
    for source_object in response.objects:
        candidate = _source_candidate_from_properties(
            source_object.uuid,
            source_object.properties,
        )
        if candidate is not None:
            candidates_by_id[source_object.uuid] = candidate
    return [
        candidates_by_id[source_id].with_matching_score(score)
        for source_id, score in fused
        if source_id in candidates_by_id
    ]


async def _source_candidate(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
) -> ArchiveCandidate | None:
    """Fetch one Source by UUID and interpret it as a page or document hit."""
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_object_by_id(
        source_id,
        return_properties=_SOURCE_PROPERTIES,
    )
    return _source_candidate_from_properties(source_id, response.properties)


def _source_candidate_from_properties(
    source_id: uuid.UUID,
    raw_properties: object,
) -> ArchiveCandidate | None:
    """Interpret a Source property payload as a page or document candidate."""
    if not isinstance(raw_properties, Mapping):
        return None
    properties = cast(Mapping[str, object], raw_properties)
    raw_source_type = properties.get("source_type")
    if not isinstance(raw_source_type, str):
        return None
    kind = SourceKind(raw_source_type)
    if kind not in (SourceKind.page, SourceKind.document):
        return None
    document_id = _optional_uuid(properties, "document")
    if kind is SourceKind.page:
        return ArchiveCandidate(
            source_id,
            kind,
            document_id,
            _optional_uuid(properties, "page"),
            0.0,
        )
    return ArchiveCandidate(source_id, kind, document_id, None, 0.0)


def _optional_uuid(
    properties: Mapping[str, object],
    key: str,
) -> uuid.UUID | None:
    raw_value = properties.get(key)
    if isinstance(raw_value, uuid.UUID):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return uuid.UUID(raw_value)
        except ValueError:
            return None
    return None
