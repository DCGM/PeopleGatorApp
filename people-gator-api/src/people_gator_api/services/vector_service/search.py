"""Vector search interface over Weaviate.

VectorSearchService exposes three search operations that map to the
product-spec search requirements:

search_annotations_by_vector
    Nearest-neighbour lookup over AnnotationEmbedding.  Optionally filtered
    by annotation_type and entity_id.  Returns ranked
    AnnotationSearchResult objects with per-result distance and certainty
    scores.

search_entities_by_named_vector
    Nearest-neighbour lookup over Entity using a single named
    vector (face or name).  Returns EntitySearchResult objects.

search_entities_weighted
    Multi-modal entity search that combines face and name signals with
    caller-supplied weights via Weaviate TargetVectors.manual_weights().
    This is the primary search path for weighted multi-modal entity
    resolution.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, MetadataQuery, TargetVectors

from people_gator_api.schemas.enums import AnnotationType
from people_gator_api.services.vector_service.schemas import (
    AnnotationSearchResult,
    EntitySearchResult,
)
from people_gator_api.services.vector_service.schema import (
    ANNOTATION_COLLECTION_BY_TYPE,
    DESCRIPTION_VECTOR,
    ENTITY_COLLECTION,
    FACE_VECTOR,
    NAME_VECTOR,
)

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_FACE_WEIGHT_DEFAULT = 0.7
_NAME_WEIGHT_DEFAULT = 0.3


class VectorSearchService:
    """Async service for vector search over Weaviate collections.

    Instantiate with a connected :class:`~weaviate.WeaviateAsyncClient`.
    Use :func:`~people_gator_api.vector.client.get_weaviate_client` to
    obtain the application-scoped client instance.
    """

    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    # ------------------------------------------------------------------
    # Annotation-level search
    # ------------------------------------------------------------------

    async def search_annotations_by_vector(
        self,
        vector: list[float],
        *,
        annotation_type: AnnotationType | None = None,
        entity_id: UUID | None = None,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[AnnotationSearchResult]:
        """Return the nearest AnnotationEmbedding objects to *vector*.

        Args:
            vector: The query embedding vector.
            annotation_type: When supplied, only annotations of this type are returned.
            entity_id: When supplied, only annotations linked to this entity are returned.
            limit: Maximum number of results.
            certainty: Minimum similarity threshold in [0, 1].
            distance: Maximum cosine distance threshold.

        Returns:
            Ranked list of :class:`AnnotationSearchResult`, closest first.
        """
        results: list[AnnotationSearchResult] = []
        annotation_types: list[AnnotationType]
        if annotation_type is not None:
            annotation_types = [annotation_type]
        else:
            annotation_types = list(ANNOTATION_COLLECTION_BY_TYPE.keys())

        for candidate_type in annotation_types:
            collection = self._client.collections.get(
                ANNOTATION_COLLECTION_BY_TYPE[candidate_type]
            )
            filters = _build_annotation_filters(
                annotation_type=candidate_type,
                entity_id=entity_id,
            )

            response = await collection.query.near_vector(
                near_vector=vector,
                limit=limit,
                certainty=certainty,
                distance=distance,
                filters=filters,
                return_metadata=MetadataQuery(distance=True, certainty=True),
            )
            results.extend(
                _annotation_objects_to_results(response.objects, candidate_type)
            )

        return sorted(
            results,
            key=lambda item: item.distance if item.distance is not None else float("inf"),
        )[:limit]

    # ------------------------------------------------------------------
    # Identity-level search — single modality
    # ------------------------------------------------------------------

    async def search_entities_by_named_vector(
        self,
        vector: list[float],
        named_vector: str,
        *,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[EntitySearchResult]:
        """Return nearest Entity objects using a single named vector.

        Args:
            vector: The query embedding vector.
            named_vector: Which named vector to search; use constants
                :data:`~people_gator_api.vector.schema.FACE_VECTOR` or
                :data:`~people_gator_api.vector.schema.NAME_VECTOR`.
            limit: Maximum number of results.
            certainty: Minimum similarity threshold.
            distance: Maximum cosine distance.

        Returns:
            Ranked list of :class:`EntitySearchResult`, closest first.
        """
        collection = self._client.collections.get(ENTITY_COLLECTION)

        response = await collection.query.near_vector(
            near_vector={named_vector: vector},
            limit=limit,
            certainty=certainty,
            distance=distance,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )

        return [_object_to_entity_result(obj, named_vector) for obj in response.objects]

    async def search_entities_by_face(
        self,
        face_vector: list[float],
        *,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[EntitySearchResult]:
        """Shorthand for a face-modality entity search."""
        return await self.search_entities_by_named_vector(
            vector=face_vector,
            named_vector=FACE_VECTOR,
            limit=limit,
            certainty=certainty,
            distance=distance,
        )

    async def search_entities_by_name(
        self,
        name_vector: list[float],
        *,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[EntitySearchResult]:
        """Shorthand for a name-modality entity search."""
        return await self.search_entities_by_named_vector(
            vector=name_vector,
            named_vector=NAME_VECTOR,
            limit=limit,
            certainty=certainty,
            distance=distance,
        )

    # ------------------------------------------------------------------
    # Identity-level search — weighted multi-modal
    # ------------------------------------------------------------------

    async def search_entities_weighted(
        self,
        face_vector: list[float] | None = None,
        name_vector: list[float] | None = None,
        *,
        face_weight: float = _FACE_WEIGHT_DEFAULT,
        name_weight: float = _NAME_WEIGHT_DEFAULT,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[EntitySearchResult]:
        """Multi-modal entity search with caller-supplied modality weights.

        At least one of *face_vector* or *name_vector* must be supplied.
        Weights do not need to sum to 1.0 — Weaviate applies them as
        relative multipliers on the per-modality cosine distances.

        This is the primary search path for weighted multi-modal entity
        resolution per the product specification.

        Args:
            face_vector: Query vector in the face embedding space.
            name_vector: Query vector in the name embedding space.
            face_weight: Relative weight for face-signal distance.
            name_weight: Relative weight for name-signal distance.
            limit: Maximum number of results.

        Returns:
            Ranked list of :class:`EntitySearchResult`, best first.

        Raises:
            ValueError: If neither vector is provided.
        """
        if face_vector is None and name_vector is None:
            raise ValueError("At least one of face_vector or name_vector must be supplied.")

        collection = self._client.collections.get(ENTITY_COLLECTION)

        query_vector: dict[str, list[float]] = {}
        weights: dict[str, float | list[float]] = {}
        if face_vector is not None:
            query_vector[FACE_VECTOR] = face_vector
            weights[FACE_VECTOR] = face_weight
        if name_vector is not None:
            query_vector[NAME_VECTOR] = name_vector
            weights[NAME_VECTOR] = name_weight

        target = (
            TargetVectors.manual_weights(weights)
            if len(weights) > 1
            else list(weights.keys())[0]
        )

        response = await collection.query.near_vector(
            near_vector=query_vector,
            target_vector=target,
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
        )

        return [_object_to_entity_result(obj) for obj in response.objects]

    async def search_entities_by_name_description(
        self,
        name_vector: list[float] | None = None,
        description_vector: list[float] | None = None,
        *,
        name_weight: float = _NAME_WEIGHT_DEFAULT,
        description_weight: float = _FACE_WEIGHT_DEFAULT,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[EntitySearchResult]:
        """Search the dedicated Entity collection using name/description vectors."""
        if name_vector is None and description_vector is None:
            raise ValueError("At least one of name_vector or description_vector must be supplied.")

        query_vector: dict[str, list[float]] = {}
        weights: dict[str, float | list[float]] = {}
        if name_vector is not None:
            query_vector[NAME_VECTOR] = name_vector
            weights[NAME_VECTOR] = name_weight
        if description_vector is not None:
            query_vector[DESCRIPTION_VECTOR] = description_vector
            weights[DESCRIPTION_VECTOR] = description_weight

        target = (
            TargetVectors.manual_weights(weights)
            if len(weights) > 1
            else list(weights.keys())[0]
        )

        collection = self._client.collections.get(ENTITY_COLLECTION)
        response = await collection.query.near_vector(
            near_vector=query_vector,
            target_vector=target,
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
        )
        return [_object_to_entity_result(obj) for obj in response.objects]

    # Backward-compatible method names.
    search_identities_by_named_vector = search_entities_by_named_vector
    search_identities_by_face = search_entities_by_face
    search_identities_by_name = search_entities_by_name
    search_identities_weighted = search_entities_weighted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_annotation_filters(
    *,
    annotation_type: AnnotationType | None,
    entity_id: UUID | None,
) -> Any:
    """Compose a Weaviate filter from optional annotation search constraints."""
    clauses: list[Any] = []
    if entity_id is not None and annotation_type in {
        AnnotationType.person_name,
        AnnotationType.description,
        AnnotationType.face,
        AnnotationType.document_mention,
    }:
        clauses.append(Filter.by_property("entity_id").equal(str(entity_id)))
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return Filter.all_of(clauses)


def _object_to_entity_result(
    obj: Any,
    primary_named_vector: str | None = None,
) -> EntitySearchResult:
    """Map a Weaviate query object to an EntitySearchResult."""
    props = obj.properties
    meta = obj.metadata

    distance = meta.distance if meta else None

    return EntitySearchResult(
        weaviate_id=obj.uuid,
        entity_id=UUID(str(props.get("entity_id"))),
        face_count=int(props.get("face_count", 0)),
        mention_count=int(props.get("mention_count", 0)),
        information_count=int(props.get("information_count", 0)),
        document_mention_count=int(props.get("document_mention_count", 0)),
        description_count=int(props.get("description_count", 0)),
        name_count=int(props.get("name_count", 0)),
        face_distance=distance if primary_named_vector == FACE_VECTOR else None,
        name_distance=distance if primary_named_vector == NAME_VECTOR else None,
        description_distance=distance if primary_named_vector == DESCRIPTION_VECTOR else None,
        combined_distance=distance if primary_named_vector is None else None,
    )


def _annotation_id_property(annotation_type: AnnotationType) -> str:
    if annotation_type is AnnotationType.person_name:
        return "name_id"
    if annotation_type is AnnotationType.description:
        return "description_id"
    if annotation_type is AnnotationType.information:
        return "information_id"
    if annotation_type is AnnotationType.mention:
        return "mention_id"
    if annotation_type is AnnotationType.face:
        return "detection_id"
    return "document_mention_id"


def _annotation_objects_to_results(objects: list[Any], annotation_type: AnnotationType) -> list[AnnotationSearchResult]:
    id_property = _annotation_id_property(annotation_type)
    results: list[AnnotationSearchResult] = []

    for obj in objects:
        props = obj.properties
        source_id_value = props.get("source_id")
        model_agent_value = props.get("model_agent_id")
        confidence_value = props.get("confidence")
        entity_value = props.get("entity_id")

        if source_id_value is None:
            continue

        results.append(
            AnnotationSearchResult(
                weaviate_id=obj.uuid,
                annotation_type=annotation_type,
                annotation_id=UUID(str(props.get(id_property))),
                source_id=UUID(str(source_id_value)),
                model_agent_id=UUID(str(model_agent_value)) if model_agent_value else None,
                confidence=cast(float | None, confidence_value),
                entity_id=UUID(str(entity_value)) if entity_value else None,
                distance=cast(float | None, getattr(obj.metadata, "distance", None)) if obj.metadata else None,
                certainty=cast(float | None, getattr(obj.metadata, "certainty", None)) if obj.metadata else None,
            )
        )

    return results
