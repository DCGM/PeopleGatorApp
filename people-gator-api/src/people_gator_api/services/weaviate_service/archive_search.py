"""Pure-Weaviate archive search through direct entity-to-source links."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.internal import CrossReferences
from weaviate.collections.classes.types import WeaviateProperties

from people_gator_api.schemas.enums import AssignmentType, SourceKind
from people_gator_api.services.weaviate_service.assignments import source_has_assignment
from people_gator_api.weaviate_schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
    SOURCE_COLLECTION,
    TEXT_MENTION_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    reference_id_filter,
)
from people_gator_api.utils.opentelemetry import trace

_ENTITY_QUERY_PROPERTIES = ["name", "aliases"]
_SOURCE_PROPERTIES = ["source_type", "library", "document", "page"]
_RRF_RANK_CONSTANT = 60
_ENTITY_MATCH_LIMIT = 100
_APPEARANCE_PAGE_SIZE = 100


class _AppearanceObject(Protocol):
    uuid: uuid.UUID
    properties: WeaviateProperties
    references: CrossReferences


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
    source_kind: SourceKind,
    limit: int,
    assignment: AssignmentType | None = None,
) -> list[ArchiveCandidate]:
    """Resolve an entity name, alias, or Source UUID to one source kind."""
    cleaned = query.strip()
    if not cleaned or limit <= 0:
        return []
    if (direct_source_id := _as_uuid(cleaned)) is not None:
        direct = await _source_candidate(client, direct_source_id)
        if direct is None or direct.kind is not source_kind:
            return []
        if assignment is not None and not await source_has_assignment(
            client, direct_source_id, assignment
        ):
            return []
        return [direct]

    source_ranking = (
        await _entity_source_ranking(client, cleaned, source_id, assignment)
        if assignment is not None
        else await _entity_source_ranking(client, cleaned, source_id)
    )
    ranked = [
        (linked_source_id, 1.0 / (_RRF_RANK_CONSTANT + rank))
        for rank, linked_source_id in enumerate(source_ranking, start=1)
    ]
    if not ranked:
        return []
    candidates = await _resolve_source_candidates(client, ranked)
    return [candidate for candidate in candidates if candidate.kind is source_kind][
        :limit
    ]


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
    assignment: AssignmentType | None = None,
) -> list[uuid.UUID]:
    """Rank sources reached through faces and text mentions of matching entities."""
    response = await client.collections.get(ENTITY_COLLECTION).query.bm25(
        query=query,
        query_properties=_ENTITY_QUERY_PROPERTIES,
        limit=_ENTITY_MATCH_LIMIT,
        return_properties=[],
    )
    entity_ids = [entity_object.uuid for entity_object in response.objects]
    if not entity_ids:
        return []

    collection_names = {
        None: (FACE_COLLECTION, TEXT_MENTION_COLLECTION),
        AssignmentType.face: (FACE_COLLECTION,),
        AssignmentType.text_mention: (TEXT_MENTION_COLLECTION,),
    }[assignment]
    appearances_by_collection = await asyncio.gather(
        *(
            _fetch_appearances(
                client,
                collection_name,
                entity_ids=entity_ids,
                source_id=source_id,
            )
            for collection_name in collection_names
        )
    )
    entity_rank = {entity_id: rank for rank, entity_id in enumerate(entity_ids)}
    ranked_sources: list[tuple[int, uuid.UUID]] = []
    for appearance in (
        appearance
        for collection_appearances in appearances_by_collection
        for appearance in collection_appearances
    ):
        linked_entities = _reference_uuids(appearance.references, "entity")
        linked_sources = _reference_uuids(appearance.references, "source")
        if not linked_entities or not linked_sources:
            continue
        rank = entity_rank.get(linked_entities[0])
        if rank is not None:
            ranked_sources.append((rank, linked_sources[0]))
    ranked_sources.sort(key=lambda item: (item[0], item[1]))
    return _deduplicate([source for _rank, source in ranked_sources])


async def _fetch_appearances(
    client: WeaviateAsyncClient,
    collection_name: str,
    *,
    entity_ids: Sequence[uuid.UUID],
    source_id: uuid.UUID | None,
) -> list[_AppearanceObject]:
    filters: list[FilterReturn] = [
        Filter.by_ref("entity").by_id().contains_any(sorted(entity_ids))
    ]
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))

    collection = client.collections.get(collection_name)
    appearances: list[_AppearanceObject] = []
    after_id: uuid.UUID | None = None
    while True:
        response = await collection.query.fetch_objects(
            filters=combine_filters(filters),
            limit=_APPEARANCE_PAGE_SIZE,
            after=after_id,
            return_properties=[],
            return_references=empty_reference_queries(["entity", "source"]),
        )
        page = cast(list[_AppearanceObject], list(response.objects))
        if not page:
            break
        appearances.extend(page)
        if len(page) < _APPEARANCE_PAGE_SIZE:
            break
        next_after_id = page[-1].uuid
        if next_after_id == after_id:
            raise RuntimeError("Weaviate appearance pagination did not advance")
        after_id = next_after_id
    return appearances


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
