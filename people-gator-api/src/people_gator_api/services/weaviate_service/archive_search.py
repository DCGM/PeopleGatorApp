"""Pure-Weaviate archive search through direct entity-to-source links."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.internal import CrossReferences

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.services.weaviate_service.db_schema import (
    ENTITY_COLLECTION,
    SOURCE_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import fetch_collection_object
from people_gator_api.utils.opentelemetry import trace

_ENTITY_QUERY_PROPERTIES = ["name", "aliases"]
_SOURCE_PROPERTIES = ["source_type", "library", "document", "page"]
_RRF_RANK_CONSTANT = 60
_ENTITY_MATCH_LIMIT = 100


@dataclass(frozen=True, slots=True)
class ArchiveCandidate:
    """One deduplicated page or document hit resolved to its Source."""

    source_id: uuid.UUID
    kind: SourceKind
    document_id: uuid.UUID | None
    page_id: uuid.UUID | None
    matching_score: float

    def with_matching_score(self, matching_score: float) -> ArchiveCandidate:
        """Copy this candidate with the relevance score attached."""
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
    """Resolve an entity name, alias, or Source UUID to archive sources."""
    cleaned = query.strip()
    if not cleaned or limit <= 0:
        return []
    if (direct_source_id := _as_uuid(cleaned)) is not None:
        direct = await _source_candidate(client, direct_source_id)
        return [direct] if direct is not None else []

    source_ranking = await _entity_source_ranking(client, cleaned, source_id)
    ranked = [
        (linked_source_id, 1.0 / (_RRF_RANK_CONSTANT + rank))
        for rank, linked_source_id in enumerate(source_ranking[:limit], start=1)
    ]
    if not ranked:
        return []
    return await _resolve_source_candidates(client, ranked)


def _as_uuid(query: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(query)
    except ValueError:
        return None


@trace()
async def _entity_source_ranking(
    client: WeaviateAsyncClient,
    query: str,
    source_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Rank sources by the matching entities that link to them directly."""
    response = await client.collections.get(ENTITY_COLLECTION).query.bm25(
        query=query,
        query_properties=_ENTITY_QUERY_PROPERTIES,
        filters=_source_scope_filter(source_id),
        limit=_ENTITY_MATCH_LIMIT,
        return_properties=[],
        return_references=QueryReference(
            link_on="mentioned_in",
            return_properties=[],
        ),
    )
    linked_sources: list[uuid.UUID] = []
    for entity_object in response.objects:
        for linked_source_id in _reference_uuids(
            entity_object.references,
            "mentioned_in",
        ):
            if source_id is None or linked_source_id == source_id:
                linked_sources.append(linked_source_id)
    return _deduplicate(linked_sources)


def _source_scope_filter(source_id: uuid.UUID | None) -> FilterReturn | None:
    if source_id is None:
        return None
    return Filter.by_ref("mentioned_in").by_id().equal(source_id)


def _reference_uuids(
    references: CrossReferences | None,
    key: str,
) -> list[uuid.UUID]:
    if references is None or key not in references:
        return []
    return [linked.uuid for linked in references[key].objects]


def _deduplicate(values: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    ordered: list[uuid.UUID] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


@trace()
async def _resolve_source_candidates(
    client: WeaviateAsyncClient,
    ranked: Sequence[tuple[uuid.UUID, float]],
) -> list[ArchiveCandidate]:
    """Batch-fetch Source records while preserving their ranking."""
    source_ids = [source_id for source_id, _score in ranked]
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
        for source_id, score in ranked
        if source_id in candidates_by_id
    ]


async def _source_candidate(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
) -> ArchiveCandidate | None:
    """Fetch one Source by UUID and interpret it as a page or document hit."""
    response = await fetch_collection_object(
        client,
        SOURCE_COLLECTION,
        source_id,
    )
    if response is None:
        return None
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
