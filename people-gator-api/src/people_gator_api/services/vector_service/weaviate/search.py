"""Vector search interface over Weaviate.

VectorSearchService exposes three search operations that map to the
product-spec search requirements:

search_annotations_by_vector
    Nearest-neighbour lookup over AnnotationEmbedding.  Optionally filtered
    by annotation_type and identity_id.  Returns ranked
    AnnotationSearchResult objects with per-result distance and certainty
    scores.

search_identities_by_named_vector
    Nearest-neighbour lookup over IdentitySnapshot using a single named
    vector (face or name).  Returns IdentitySearchResult objects.

search_identities_weighted
    Multi-modal identity search that combines face and name signals with
    caller-supplied weights via Weaviate TargetVectors.manual_weights().
    This is the primary search path for weighted multi-modal identity
    resolution.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, MetadataQuery, TargetVectors

from people_gator_api.models.enums import AnnotationType
from people_gator_api.services.vector_service.schemas import (
    AnnotationSearchResult,
    IdentitySearchResult,
)
from people_gator_api.services.vector_service.weaviate.schema import (
    ANNOTATION_EMBEDDING_COLLECTION,
    FACE_VECTOR,
    IDENTITY_SNAPSHOT_COLLECTION,
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
        identity_id: UUID | None = None,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[AnnotationSearchResult]:
        """Return the nearest AnnotationEmbedding objects to *vector*.

        Args:
            vector: The query embedding vector.
            annotation_type: When supplied, only annotations of this type are returned.
            identity_id: When supplied, only annotations linked to this identity are returned.
            limit: Maximum number of results.
            certainty: Minimum similarity threshold in [0, 1].
            distance: Maximum cosine distance threshold.

        Returns:
            Ranked list of :class:`AnnotationSearchResult`, closest first.
        """
        collection = self._client.collections.get(ANNOTATION_EMBEDDING_COLLECTION)

        filters = _build_annotation_filters(
            annotation_type=annotation_type, identity_id=identity_id,
        )

        response = await collection.query.near_vector(
            near_vector=vector,
            limit=limit,
            certainty=certainty,
            distance=distance,
            filters=filters,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )

        results: list[AnnotationSearchResult] = []
        for obj in response.objects:
            props = obj.properties
            results.append(
                AnnotationSearchResult(
                    weaviate_id=obj.uuid,
                    annotation_type=AnnotationType(str(props.get("annotation_type"))),
                    annotation_id=UUID(str(props.get("annotation_id"))),
                    source_id=UUID(str(props.get("source_id"))),
                    model_agent_id=(
                        UUID(str(props["model_agent_id"]))
                        if props.get("model_agent_id")
                        else None
                    ),
                    confidence=cast(float | None, props.get("confidence")),
                    identity_id=(
                        UUID(str(props["identity_id"]))
                        if props.get("identity_id")
                        else None
                    ),
                    distance=cast(float | None, getattr(obj.metadata, "distance", None)) if obj.metadata else None,
                    certainty=cast(float | None, getattr(obj.metadata, "certainty", None)) if obj.metadata else None,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Identity-level search — single modality
    # ------------------------------------------------------------------

    async def search_identities_by_named_vector(
        self,
        vector: list[float],
        named_vector: str,
        *,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[IdentitySearchResult]:
        """Return nearest IdentitySnapshot objects using a single named vector.

        Args:
            vector: The query embedding vector.
            named_vector: Which named vector to search; use constants
                :data:`~people_gator_api.vector.schema.FACE_VECTOR` or
                :data:`~people_gator_api.vector.schema.NAME_VECTOR`.
            limit: Maximum number of results.
            certainty: Minimum similarity threshold.
            distance: Maximum cosine distance.

        Returns:
            Ranked list of :class:`IdentitySearchResult`, closest first.
        """
        collection = self._client.collections.get(IDENTITY_SNAPSHOT_COLLECTION)

        response = await collection.query.near_vector(
            near_vector={named_vector: vector},
            limit=limit,
            certainty=certainty,
            distance=distance,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )

        return [_object_to_identity_result(obj, named_vector) for obj in response.objects]

    async def search_identities_by_face(
        self,
        face_vector: list[float],
        *,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[IdentitySearchResult]:
        """Shorthand for a face-modality identity search."""
        return await self.search_identities_by_named_vector(
            vector=face_vector,
            named_vector=FACE_VECTOR,
            limit=limit,
            certainty=certainty,
            distance=distance,
        )

    async def search_identities_by_name(
        self,
        name_vector: list[float],
        *,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[IdentitySearchResult]:
        """Shorthand for a name-modality identity search."""
        return await self.search_identities_by_named_vector(
            vector=name_vector,
            named_vector=NAME_VECTOR,
            limit=limit,
            certainty=certainty,
            distance=distance,
        )

    # ------------------------------------------------------------------
    # Identity-level search — weighted multi-modal
    # ------------------------------------------------------------------

    async def search_identities_weighted(
        self,
        face_vector: list[float] | None = None,
        name_vector: list[float] | None = None,
        *,
        face_weight: float = _FACE_WEIGHT_DEFAULT,
        name_weight: float = _NAME_WEIGHT_DEFAULT,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[IdentitySearchResult]:
        """Multi-modal identity search with caller-supplied modality weights.

        At least one of *face_vector* or *name_vector* must be supplied.
        Weights do not need to sum to 1.0 — Weaviate applies them as
        relative multipliers on the per-modality cosine distances.

        This is the primary search path for weighted multi-modal identity
        resolution per the product specification.

        Args:
            face_vector: Query vector in the face embedding space.
            name_vector: Query vector in the name embedding space.
            face_weight: Relative weight for face-signal distance.
            name_weight: Relative weight for name-signal distance.
            limit: Maximum number of results.

        Returns:
            Ranked list of :class:`IdentitySearchResult`, best first.

        Raises:
            ValueError: If neither vector is provided.
        """
        if face_vector is None and name_vector is None:
            raise ValueError("At least one of face_vector or name_vector must be supplied.")

        collection = self._client.collections.get(IDENTITY_SNAPSHOT_COLLECTION)

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

        return [_object_to_identity_result(obj) for obj in response.objects]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_annotation_filters(
    *,
    annotation_type: AnnotationType | None,
    identity_id: UUID | None,
) -> Any:
    """Compose a Weaviate filter from optional annotation search constraints."""
    clauses: list[Any] = []
    if annotation_type is not None:
        clauses.append(Filter.by_property("annotation_type").equal(annotation_type.value))
    if identity_id is not None:
        clauses.append(Filter.by_property("identity_id").equal(str(identity_id)))
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return Filter.all_of(clauses)


def _object_to_identity_result(
    obj: Any,
    primary_named_vector: str | None = None,
) -> IdentitySearchResult:
    """Map a Weaviate query object to an IdentitySearchResult."""
    props = obj.properties
    meta = obj.metadata

    distance = meta.distance if meta else None

    return IdentitySearchResult(
        weaviate_id=obj.uuid,
        identity_id=UUID(str(props.get("identity_id"))),
        face_count=int(props.get("face_count", 0)),
        mention_count=int(props.get("mention_count", 0)),
        information_count=int(props.get("information_count", 0)),
        document_mention_count=int(props.get("document_mention_count", 0)),
        description_count=int(props.get("description_count", 0)),
        name_count=int(props.get("name_count", 0)),
        face_distance=distance if primary_named_vector == FACE_VECTOR else None,
        name_distance=distance if primary_named_vector == NAME_VECTOR else None,
        combined_distance=distance if primary_named_vector is None else None,
    )
