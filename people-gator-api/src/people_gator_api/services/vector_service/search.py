"""Vector search helpers over Weaviate annotation collections."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import WeaviateField

from people_gator_api.schemas.enums import AnnotationType
from people_gator_api.services.weaviate_utils import WeaviateObjectLike
from people_gator_api.services.weaviate_utils import query_objects
from people_gator_api.services.vector_service.schema import (
    ANNOTATION_COLLECTION_BY_TYPE,
)
from people_gator_api.services.vector_service.schemas import AnnotationSearchResult

_DEFAULT_LIMIT = 20


async def search_by_vector(
    client: WeaviateAsyncClient,
    vector: list[float],
    annotation_type: AnnotationType,
    target_named_vector: str,
    *,
    entity_id: UUID | None = None,
    limit: int = _DEFAULT_LIMIT,
    certainty: float | None = None,
    distance: float | None = None,
    min_confidence: float | None = None,
) -> list[AnnotationSearchResult]:
    """Return the nearest annotation objects to *vector*."""

    collection = client.collections.get(ANNOTATION_COLLECTION_BY_TYPE[annotation_type])
    filters = _build_annotation_filters(
        annotation_type=annotation_type,
        entity_id=entity_id,
        min_confidence=min_confidence,
    )

    response = cast(
        object,
        await collection.query.near_vector(
            near_vector=vector,
            target_vector=target_named_vector,
            limit=limit,
            certainty=certainty,
            distance=distance,
            filters=filters,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        ),
    )
    return _annotation_objects_to_results(query_objects(response), annotation_type)


def _build_annotation_filters(
    *,
    annotation_type: AnnotationType,
    entity_id: UUID | None,
    min_confidence: float | None,
) -> FilterReturn | None:
    clauses: list[FilterReturn] = []
    if entity_id is not None and annotation_type in {
        AnnotationType.entity,
        AnnotationType.document_mention,
        AnnotationType.span,
        AnnotationType.face,
        AnnotationType.description,
        AnnotationType.entity_name,
    }:
        clauses.append(Filter.by_property("entity_id").equal(str(entity_id)))
    if min_confidence is not None and annotation_type in {
        AnnotationType.page_mention,
        AnnotationType.face,
    }:
        clauses.append(Filter.by_property("confidence").greater_or_equal(min_confidence))
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return Filter.all_of(clauses)


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
