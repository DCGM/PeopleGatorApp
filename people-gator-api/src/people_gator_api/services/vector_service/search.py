"""Vector search primitives over Weaviate collections."""

from __future__ import annotations

import asyncio
from collections import (
    defaultdict,
)
from collections.abc import (
    Mapping,
    Sequence,
)
from dataclasses import (
    dataclass,
)
from typing import (
    TypeGuard,
)
from uuid import (
    UUID,
)

from weaviate import (
    WeaviateAsyncClient,
)
from weaviate.classes.query import (
    MetadataQuery,
)
from weaviate.collections.classes.filters import (
    FilterReturn,
)
from weaviate.collections.classes.types import (
    WeaviateField,
)

from people_gator_api.schemas.enums import (
    AnnotationType,
)
from people_gator_api.services.weaviate_utils import (
    WeaviateObjectLike,
    query_objects,
)
from people_gator_api.services.vector_service.schema import (
    ANNOTATION_COLLECTION_BY_TYPE,
)
from people_gator_api.services.vector_service.schemas import (
    AnnotationSearchResult,
)

_DEFAULT_LIMIT = 20


type AnnotationResultKey = tuple[AnnotationType, UUID]


@dataclass(slots=True, frozen=True)
class AnnotationSearchBatch:
    query_vector_index: int
    results: list[AnnotationSearchResult]


async def fetch_collection_objects(
    client: WeaviateAsyncClient,
    collection_name: str,
    *,
    filters: FilterReturn | None = None,
    include_vector: bool = False,
    limit: int = _DEFAULT_LIMIT,
) -> list[WeaviateObjectLike]:
    """Fetch objects from a collection with optional vector payloads."""

    response = await client.collections.get(collection_name).query.fetch_objects(
        filters=filters,
        include_vector=include_vector,
        limit=limit,
    )
    return query_objects(response)


async def query_collection_by_vector(
    client: WeaviateAsyncClient,
    collection_name: str,
    vector: list[float],
    target_named_vector: str,
    *,
    filters: FilterReturn | None = None,
    limit: int = _DEFAULT_LIMIT,
    certainty: float | None = None,
    distance: float | None = None,
) -> list[WeaviateObjectLike]:
    """Return raw Weaviate objects nearest to *vector* in *collection_name*."""

    response = await client.collections.get(collection_name).query.near_vector(
        near_vector=vector,
        target_vector=target_named_vector,
        limit=limit,
        certainty=certainty,
        distance=distance,
        filters=filters,
        return_metadata=MetadataQuery(distance=True, certainty=True),
    )
    return query_objects(response)


async def search_by_vector(
    client: WeaviateAsyncClient,
    vector: list[float],
    annotation_type: AnnotationType,
    target_named_vector: str,
    *,
    filters: FilterReturn | None = None,
    limit: int = _DEFAULT_LIMIT,
    certainty: float | None = None,
    distance: float | None = None,
) -> list[AnnotationSearchResult]:
    """Return the nearest annotation objects to *vector*."""
    objects = await query_collection_by_vector(
        client=client,
        collection_name=ANNOTATION_COLLECTION_BY_TYPE[annotation_type],
        vector=vector,
        target_named_vector=target_named_vector,
        filters=filters,
        limit=limit,
        certainty=certainty,
        distance=distance,
    )
    return _annotation_objects_to_results(objects, annotation_type)


async def search_by_vectors(
    client: WeaviateAsyncClient,
    vectors: Sequence[list[float]],
    annotation_type: AnnotationType,
    target_named_vector: str,
    *,
    filters: FilterReturn | None = None,
    limit: int = _DEFAULT_LIMIT,
    certainty: float | None = None,
    distance: float | None = None,
) -> list[AnnotationSearchBatch]:
    """Run independent vector searches and keep their result batches separate."""

    if not vectors:
        return []

    search_jobs = [
        search_by_vector(
            client=client,
            vector=vector,
            annotation_type=annotation_type,
            target_named_vector=target_named_vector,
            filters=filters,
            limit=limit,
            certainty=certainty,
            distance=distance,
        )
        for vector in vectors
    ]
    resolved_batches = await asyncio.gather(*search_jobs)
    return [
        AnnotationSearchBatch(query_vector_index=query_vector_index, results=results)
        for query_vector_index, results in enumerate(resolved_batches)
    ]


def flatten_annotation_search_batches(
    batches: Sequence[AnnotationSearchBatch],
) -> list[AnnotationSearchResult]:
    """Flatten independent vector-search batches into a single hit list."""

    return [result for batch in batches for result in batch.results]


def group_annotation_results_by_entity(
    results: Sequence[AnnotationSearchResult],
) -> dict[UUID, list[AnnotationSearchResult]]:
    """Group annotation hits by linked entity identifier."""

    grouped: dict[UUID, list[AnnotationSearchResult]] = defaultdict(list)
    for result in results:
        if result.entity_id is None:
            continue
        grouped[result.entity_id].append(result)
    return dict(grouped)


def group_annotation_results_by_annotation(
    results: Sequence[AnnotationSearchResult],
) -> dict[AnnotationResultKey, list[AnnotationSearchResult]]:
    """Group hits by annotation identifier within an annotation type."""

    grouped: dict[AnnotationResultKey, list[AnnotationSearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.annotation_type, result.annotation_id].append(result)
    return dict(grouped)


def extract_named_vectors(
    objects: Sequence[WeaviateObjectLike],
    vector_name: str,
) -> list[list[float]]:
    """Extract all vectors named *vector_name* from fetched objects."""

    vectors: list[list[float]] = []
    for obj in objects:
        vector = extract_named_vector(obj.vector, vector_name)
        if vector is not None:
            vectors.append(vector)
    return vectors


def extract_named_vector(
    raw_vector: list[float] | Mapping[str, object] | None,
    vector_name: str,
) -> list[float] | None:
    """Extract a single named vector from a Weaviate vector payload."""

    if raw_vector is None:
        return None
    if _is_float_vector(raw_vector):
        return list(raw_vector)
    if not isinstance(raw_vector, Mapping):
        return None
    named_vector: object | None = raw_vector.get(vector_name)
    if _is_float_vector(named_vector):
        return list(named_vector)
    return None


def _annotation_id_property(annotation_type: AnnotationType) -> str:
    if annotation_type is AnnotationType.entity:
        return "entity_id"
    if annotation_type is AnnotationType.page_mention:
        return "page_mention_id"
    if annotation_type is AnnotationType.span:
        return "span_id"
    if annotation_type is AnnotationType.face:
        return "detection_id"
    if annotation_type is AnnotationType.description:
        return "description_id"
    if annotation_type is AnnotationType.entity_name:
        return "entity_name_id"
    return "document_mention_id"


def _annotation_objects_to_results(
    objects: Sequence[WeaviateObjectLike],
    annotation_type: AnnotationType,
) -> list[AnnotationSearchResult]:
    id_property = _annotation_id_property(annotation_type)
    results: list[AnnotationSearchResult] = []

    for obj in objects:
        properties = obj.properties
        source_id_value = properties.get("source_id")
        if source_id_value is None:
            continue

        annotation_id_value = properties.get(id_property)
        if annotation_id_value is None:
            continue

        model_agent_value = properties.get("model_agent_id")
        confidence_value = properties.get("confidence")
        entity_value = properties.get("entity_id")
        metadata = getattr(obj, "metadata", None)

        results.append(
            AnnotationSearchResult(
                weaviate_id=obj.uuid,
                annotation_type=annotation_type,
                annotation_id=_field_to_uuid(annotation_id_value),
                source_id=_field_to_uuid(source_id_value),
                model_agent_id=_field_to_uuid(model_agent_value)
                if model_agent_value is not None
                else None,
                confidence=_field_to_float(confidence_value),
                entity_id=_field_to_uuid(entity_value) if entity_value is not None else None,
                distance=getattr(metadata, "distance", None) if metadata is not None else None,
                certainty=getattr(metadata, "certainty", None) if metadata is not None else None,
            )
        )

    return results


def _field_to_uuid(value: WeaviateField) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise TypeError("Expected UUID-compatible Weaviate field.")


def _field_to_float(value: WeaviateField | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, float):
        return value
    raise TypeError("Expected numeric Weaviate field.")


def _is_float_vector(value: object) -> TypeGuard[list[float]]:
    if not isinstance(value, list) or not value:
        return False
    return isinstance(value[0], float)
