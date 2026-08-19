"""Readable BM25 search helpers for Entity records."""

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
from people_gator_api.schemas.search import EntitySearchResult, FaceSearchResult
from people_gator_api.services.weaviate_service.db_schema import (
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


async def search_entities_by_name_or_aliases(
    client: WeaviateAsyncClient,
    query_name: list[str],
    *,
    filters: FilterReturn | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[EntitySearchResult]:
    """Search Entity documents with BM25 across name and aliases."""
    cleaned_name = ", ".join(query_name).strip()
    if not cleaned_name:
        return []

    response = await client.collections.get(ENTITY_COLLECTION).query.bm25(
        query=cleaned_name,
        query_properties=["name", "aliases"],
        filters=filters,
        limit=limit,
        return_metadata=MetadataQuery(score=True),
    )
    return [_entity_object_to_result(obj) for obj in response.objects]


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


async def search_faces_by_vectors(
    client: WeaviateAsyncClient,
    query_vectors: Sequence[Sequence[float]],
    *,
    vector_name: str,
    excluded_face_ids: Sequence[UUID] = (),
    filters: FilterReturn | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[FaceSearchResult]:
    """Search the Face collection with several query vectors against one named vector.

    Weaviate scores each candidate against every query vector and keeps the
    smallest distance, so a face matching any reference face ranks highly.
    """
    if not query_vectors or limit <= 0:
        return []

    response = await client.collections.get(FACE_COLLECTION).query.near_vector(
        near_vector=_multi_vector_query(vector_name, query_vectors),
        target_vector=TargetVectors.minimum([vector_name]),
        filters=_with_excluded_faces(filters, excluded_face_ids),
        limit=limit,
        return_metadata=MetadataQuery(distance=True),
        return_references=empty_reference_queries(["entity", "source"]),
    )
    return [
        FaceSearchResult(
            detection_id=face_object.uuid,
            source_id=_optional_reference_uuid(face_object.references, "source"),
            entity_id=_optional_reference_uuid(face_object.references, "entity"),
            bounding_box=_optional_bounding_box(face_object.properties),
            matching_score=_metadata_similarity(face_object.metadata),
        )
        for face_object in response.objects
    ]


async def search_faces_by_vectors_grouped_by_entity(
    client: WeaviateAsyncClient,
    query_vectors: Sequence[Sequence[float]],
    *,
    vector_name: str,
    aggregation: ScoreAggregation = ScoreAggregation.max,
    excluded_face_ids: Sequence[UUID] = (),
    filters: FilterReturn | None = None,
    number_of_groups: int = _DEFAULT_LIMIT,
    objects_per_group: int = _DEFAULT_OBJECTS_PER_GROUP,
) -> list[EntitySearchResult]:
    """Multi-vector face search with Weaviate-side grouping on the entity reference.

    Per-face similarities inside a group are reduced with ``aggregation``; faces
    without an entity reference are dropped by the grouping.
    """
    if not query_vectors or number_of_groups <= 0 or objects_per_group <= 0:
        return []

    response = await client.collections.get(FACE_COLLECTION).query.near_vector(
        near_vector=_multi_vector_query(vector_name, query_vectors),
        target_vector=TargetVectors.minimum([vector_name]),
        filters=_with_excluded_faces(filters, excluded_face_ids),
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

    results: list[EntitySearchResult] = []
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
    results.sort(key=lambda item: (-item.matching_score, item.entity_id))
    return results


def _aggregate_scores(scores: list[float], aggregation: ScoreAggregation) -> float:
    match aggregation:
        case ScoreAggregation.min:
            return min(scores)
        case ScoreAggregation.max:
            return max(scores)
        case ScoreAggregation.average:
            return fmean(scores)


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
) -> EntitySearchResult:
    return EntitySearchResult(
        entity_id=entity_id,
        entity_type=_optional_entity_type(properties),
        name=optional_str(properties, "name") or "",
        description=optional_str(properties, "description") or "",
        short_description=optional_str(properties, "short_description") or "",
        aliases=_optional_alias_text_array(properties),
        matching_score=matching_score,
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


def _with_excluded_faces(
    filters: FilterReturn | None,
    excluded_face_ids: Sequence[UUID],
) -> FilterReturn | None:
    if not excluded_face_ids:
        return filters
    exclusion = Filter.by_id().contains_none(
        [str(face_id) for face_id in excluded_face_ids]
    )
    if filters is None:
        return exclusion
    return Filter.all_of([filters, exclusion])


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
) -> EntitySearchResult:
    object_uuid = getattr(entity_object, "uuid")
    raw_properties = getattr(entity_object, "properties")
    metadata = getattr(entity_object, "metadata", None)

    properties = _as_weaviate_properties(raw_properties)

    return EntitySearchResult(
        entity_id=_field_to_uuid(object_uuid),
        entity_type=_optional_entity_type(properties),
        name=optional_str(properties, "name") or "",
        description=optional_str(properties, "description") or "",
        short_description=optional_str(properties, "short_description") or "",
        aliases=_optional_alias_text_array(properties),
        matching_score=_metadata_score(metadata),
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
