"""Weaviate helpers for entity name and reference-face search."""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)
from statistics import fmean
from typing import cast
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import (
    Filter,
    GroupBy,
    MetadataQuery,
    NearVector,
    QueryReference,
    TargetVectors,
)
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.grpc import NearVectorInputType
from weaviate.collections.classes.internal import CrossReferences
from weaviate.collections.classes.types import WeaviateField

from people_gator_api.schemas.entities import BoundingBox
from people_gator_api.schemas.enums import EntityType, ScoreAggregation
from people_gator_api.schemas.search import FoundEntity, FoundFace
from people_gator_api.weaviate_schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    empty_reference_queries,
    optional_str,
)

_DEFAULT_LIMIT = 20
_DEFAULT_OBJECTS_PER_GROUP = 10
_ENTITY_REFERENCE_PROPERTIES = [
    "entity_type",
    "name",
    "description",
    "short_description",
    "aliases",
]


async def search_entities_by_names_or_aliases(
    client: WeaviateAsyncClient,
    query_name: list[str],
    *,
    entity_types: Sequence[EntityType] = (),
    entity_ids: Sequence[UUID] | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[FoundEntity]:
    """Search Entity documents with BM25 across name and aliases."""
    cleaned_name = ", ".join(query_name).strip()
    if not cleaned_name or limit <= 0:
        return []
    filters = _parse_entity_filters(entity_types, entity_ids)
    response = await client.collections.get(ENTITY_COLLECTION).query.bm25(
        query=cleaned_name,
        query_properties=["name", "aliases"],
        filters=filters,
        limit=limit,
        return_metadata=MetadataQuery(score=True),
    )
    return [_entity_object_to_result(obj) for obj in response.objects]


async def search_entities_by_faces_vectors(
    client: WeaviateAsyncClient,
    query_vectors: Sequence[Sequence[float]],
    *,
    vector_name: str,
    aggregation: ScoreAggregation = ScoreAggregation.max,
    excluded_face_ids: Sequence[UUID] = (),
    entity_types: Sequence[EntityType] = (),
    entity_ids: Sequence[UUID] | None = None,
    number_of_groups: int = _DEFAULT_LIMIT,
    objects_per_group: int = _DEFAULT_OBJECTS_PER_GROUP,
) -> list[FoundEntity]:
    """Multi-vector face search with Weaviate-side grouping on the entity reference.

    Per-face similarities inside a group are reduced with ``aggregation``.
    Filter out unassigned faces *before* nearest-neighbour grouping, otherwise
    their empty-reference group can crowd out every assigned entity.
    """
    if not query_vectors or number_of_groups <= 0 or objects_per_group <= 0:
        return []
    assigned_faces = Filter.by_ref_count(link_on="entity").greater_than(0)
    other_filters = _parse_face_filters(excluded_face_ids, entity_types, entity_ids)
    filters = (
        Filter.all_of([assigned_faces, other_filters])
        if other_filters is not None
        else assigned_faces
    )
    response = await client.collections.get(FACE_COLLECTION).query.near_vector(
        near_vector=_multi_vector_query(vector_name, query_vectors),
        target_vector=TargetVectors.minimum([vector_name]),
        filters=filters,
        group_by=GroupBy(
            prop="entity",
            number_of_groups=number_of_groups,
            objects_per_group=objects_per_group,
        ),
        return_metadata=MetadataQuery(distance=True),
        return_references=QueryReference(
            link_on="entity",
            return_properties=_ENTITY_REFERENCE_PROPERTIES,
        ),
    )
    results: list[FoundEntity] = []
    for group_name, group in response.groups.items():
        entity_id = _group_name_to_uuid(group_name)
        if entity_id is None or not group.objects:
            continue
        scores = [
            _metadata_similarity(face_object.metadata) for face_object in group.objects
        ]
        results.append(
            _grouped_entity_result(
                entity_id,
                _linked_entity_properties(group.objects[0].references),
                _aggregate_scores(scores, aggregation),
            )
        )
    return results

async def search_faces_by_vectors(
    client: WeaviateAsyncClient,
    query_vectors: Sequence[Sequence[float]],
    *,
    vector_name: str,
    excluded_face_ids: Sequence[UUID] = (),
    limit: int = _DEFAULT_LIMIT,
) -> list[FoundFace]:
    """Search the Face collection with several query vectors against one named vector.

    Weaviate scores each candidate against every query vector and keeps the
    smallest distance, so a face matching any reference face ranks highly.
    """
    if not query_vectors or limit <= 0:
        return []
    response = await client.collections.get(FACE_COLLECTION).query.near_vector(
        near_vector=_multi_vector_query(vector_name, query_vectors),
        target_vector=TargetVectors.minimum([vector_name]),
        filters=_parse_face_filters(excluded_face_ids, None),
        limit=limit,
        return_metadata=MetadataQuery(distance=True),
        return_references=empty_reference_queries(["entity", "source"]),
    )
    return [
        FoundFace(
            face_id=face_object.uuid,
            source_id=_optional_reference_uuid(face_object.references, "source"),
            entity_id=_optional_reference_uuid(face_object.references, "entity"),
            bounding_box=_optional_bounding_box(face_object.properties),
            matching_score=_metadata_similarity(face_object.metadata),
        )
        for face_object in response.objects
    ]

async def fetch_face_vectors(
    client: WeaviateAsyncClient,
    face_ids: Sequence[UUID],
    *,
    vector_name: str,
) -> list[list[float]]:
    """Load the named embedding of each reference face detection."""
    if not face_ids:
        return []

    response = await client.collections.get(FACE_COLLECTION).query.fetch_objects_by_ids(
        ids=[str(face_id) for face_id in face_ids],
        include_vector=[vector_name],
        return_properties=[],
    )
    vectors: list[list[float]] = []
    for face_object in response.objects:
        raw_vector = face_object.vector.get(vector_name)
        if raw_vector is None:
            continue
        vectors.append(_as_flat_vector(raw_vector))
    return vectors


def _aggregate_scores(scores: list[float], aggregation: ScoreAggregation) -> float:
    match aggregation:
        case ScoreAggregation.min:
            return min(scores)
        case ScoreAggregation.max:
            return max(scores)
        case ScoreAggregation.average:
            return fmean(scores)

def _parse_face_filters(
    excluded_face_ids: Sequence[UUID] | None,
    entity_types: Sequence[EntityType] | None,
    entity_ids: Sequence[UUID] | None = None,
) -> FilterReturn | None:
    if not entity_types and not excluded_face_ids and entity_ids is None:
        return None
    filters: list[FilterReturn] = []
    if entity_types:
        for entity_type in entity_types:
            filters.append(Filter.by_ref("entity_type").by_property("entity_type").equal(entity_type.value))
    if excluded_face_ids:
        filters.append(
            Filter.by_id().contains_none([str(face_id) for face_id in excluded_face_ids])
        )
    if entity_ids is not None:
        filters.append(Filter.by_ref("entity").by_id().contains_any(sorted(entity_ids)))
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return Filter.all_of(filters)

def _parse_entity_filters(
    entity_types: Sequence[EntityType] | None,
    entity_ids: Sequence[UUID] | None = None,
) -> FilterReturn | None:
    filters: list[FilterReturn] = []
    entity_type_values = [entity_type.value for entity_type in (entity_types or [])]
    if len(entity_type_values) == 1:
        filters.append(Filter.by_property("entity_type").equal(entity_type_values[0]))
    elif entity_type_values:
        filters.append(
            Filter.any_of(
                [
                    Filter.by_property("entity_type").equal(entity_type_value)
                    for entity_type_value in entity_type_values
                ]
            )
        )
    if entity_ids is not None:
        filters.append(Filter.by_id().contains_any(sorted(entity_ids)))
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return Filter.all_of(filters)


def _linked_entity_properties(
    references: CrossReferences | None,
) -> dict[str, WeaviateField]:
    if references is None or "entity" not in references:
        return {}
    linked_objects = references["entity"].objects
    if not linked_objects:
        return {}
    return _as_weaviate_properties(linked_objects[0].properties)


def _grouped_entity_result(
    entity_id: UUID,
    properties: Mapping[str, WeaviateField],
    matching_score: float,
) -> FoundEntity:
    return FoundEntity(
        entity_id=entity_id,
        entity_type=_optional_entity_type(properties),
        name=optional_str(properties, "name") or "",
        description=optional_str(properties, "description") or "",
        short_description=optional_str(properties, "short_description") or "",
        aliases=_optional_alias_text_array(properties),
        score=matching_score,
    )


def _multi_vector_query(
    vector_name: str,
    query_vectors: Sequence[Sequence[float]],
) -> NearVectorInputType:
    return {
        vector_name: NearVector.list_of_vectors(
            *[list(vector) for vector in query_vectors]
        )
    }


def _group_name_to_uuid(group_name: str) -> UUID | None:
    """Group names for reference properties are beacons ending with the target UUID."""
    candidate = group_name.rsplit("/", 1)[-1]
    try:
        return UUID(candidate)
    except ValueError:
        return None


def _as_flat_vector(raw_vector: object) -> list[float]:
    if not isinstance(raw_vector, Sequence) or isinstance(raw_vector, (str, bytes)):
        raise TypeError("Expected a numeric sequence for the named face vector.")
    values = cast(Sequence[object], raw_vector)
    flat: list[float] = []
    for item in values:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise TypeError("Face vectors must be one-dimensional numeric sequences.")
        flat.append(float(item))
    return flat


def _optional_reference_uuid(
    references: CrossReferences | None,
    key: str,
) -> UUID | None:
    if references is None or key not in references:
        return None
    linked_objects = references[key].objects
    if not linked_objects:
        return None
    return linked_objects[0].uuid


def _optional_bounding_box(raw_properties: object) -> BoundingBox | None:
    if not isinstance(raw_properties, Mapping):
        return None
    raw_box = cast(Mapping[str, object], raw_properties).get("bounding_box")
    if not isinstance(raw_box, Mapping):
        return None
    box = cast(Mapping[str, object], raw_box)
    coordinates: dict[str, int] = {}
    for key in ("x", "y", "width", "height"):
        item = box.get(key)
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            return None
        coordinates[key] = int(item)
    return BoundingBox(**coordinates)


def _entity_object_to_result(
    entity_object: object,
) -> FoundEntity:
    object_uuid = getattr(entity_object, "uuid")
    raw_properties = getattr(entity_object, "properties")
    metadata = getattr(entity_object, "metadata", None)

    properties = _as_weaviate_properties(raw_properties)

    return FoundEntity(
        entity_id=_field_to_uuid(object_uuid),
        entity_type=_optional_entity_type(properties),
        name=optional_str(properties, "name") or "",
        description=optional_str(properties, "description") or "",
        short_description=optional_str(properties, "short_description") or "",
        aliases=_optional_alias_text_array(properties),
        score=_metadata_score(metadata),
    )


def _as_weaviate_properties(raw_properties: object) -> dict[str, WeaviateField]:
    if not isinstance(raw_properties, Mapping):
        raise TypeError("Expected mapping-like properties from Weaviate object.")

    # We validated Mapping at runtime; values come from Weaviate property payloads.
    mapping = cast(Mapping[object, WeaviateField], raw_properties)
    properties: dict[str, WeaviateField] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise TypeError("Weaviate property names must be strings.")
        properties[key] = value
    return properties


def _optional_entity_type(
    properties: Mapping[str, WeaviateField],
) -> EntityType | None:
    raw_value = optional_str(properties, "entity_type")
    if raw_value is None:
        return None
    return EntityType(raw_value)


def _optional_alias_text_array(properties: Mapping[str, WeaviateField]) -> list[str]:
    raw_value = properties.get("aliases")
    if raw_value is None:
        return []
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise TypeError("Property 'aliases' is not a text array.")

    aliases: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            raise TypeError("Property 'aliases' contains a non-string alias item.")
        aliases.append(item)
    return aliases


def _field_to_uuid(value: WeaviateField | None) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise TypeError("Expected UUID-compatible field value.")


def _metadata_score(metadata: object | None) -> float:
    if metadata is None:
        return 0.0
    score_value = getattr(metadata, "score", None)
    if isinstance(score_value, (int, float)):
        return float(score_value)
    return 0.0


def _metadata_similarity(metadata: object | None) -> float:
    """Convert the reported cosine distance into a cosine similarity score."""
    if metadata is None:
        return 0.0
    distance = getattr(metadata, "distance", None)
    if isinstance(distance, (int, float)) and not isinstance(distance, bool):
        return 1.0 - float(distance)
    return 0.0
