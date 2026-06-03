"""Vector search interface over Weaviate.

VectorSearchService exposes three search operations that map to the
product-spec search requirements:

search_records_by_vector
    Nearest-neighbour lookup over RecordEmbedding.  Optionally filtered
    by record_type and cluster_id.  Returns ranked RecordSearchResult
    objects with per-result distance and certainty scores.

search_clusters_by_named_vector
    Nearest-neighbour lookup over ClusterSnapshot using a single named
    vector (face or name).  Returns ClusterSearchResult objects.

search_clusters_weighted
    Multi-modal cluster search that combines face and name signals with
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

from people_gator_api.db.models.enums import ClusterRole, EvidenceType
from people_gator_api.vector.models import ClusterSearchResult, EvidenceSearchResult
from people_gator_api.vector.schema import (
    CLUSTER_SNAPSHOT_COLLECTION,
    FACE_VECTOR,
    NAME_VECTOR,
    RECORD_EMBEDDING_COLLECTION,
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
    # Record-level search
    # ------------------------------------------------------------------

    async def search_records_by_vector(
        self,
        vector: list[float],
        *,
        evidence_type: EvidenceType | None = None,
        cluster_id: UUID | None = None,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[EvidenceSearchResult]:
        """Return the nearest EvidenceEmbedding objects to *vector*.

        Args:
            vector: The query embedding vector.
            evidence_type: When supplied, only evidence of this type is returned.
            cluster_id: When supplied, only evidence in this cluster is returned.
            limit: Maximum number of results.
            certainty: Minimum similarity threshold in [0, 1].
            distance: Maximum cosine distance threshold.

        Returns:
            Ranked list of :class:`EvidenceSearchResult`, closest first.
        """
        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)

        filters = _build_evidence_filters(evidence_type=evidence_type, cluster_id=cluster_id)

        response = await collection.query.near_vector(
            near_vector=vector,
            limit=limit,
            certainty=certainty,
            distance=distance,
            filters=filters,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )

        results: list[EvidenceSearchResult] = []
        for obj in response.objects:
            props = obj.properties
            results.append(
                EvidenceSearchResult(
                    weaviate_id=obj.uuid,
                    evidence_id=UUID(str(props.get("evidence_id"))),
                    evidence_version_id=UUID(str(props.get("evidence_version_id"))),
                    evidence_type=EvidenceType(str(props.get("evidence_type"))),
                    source_id=UUID(str(props.get("source_id"))),
                    producer_id=UUID(str(props["producer_id"])) if props.get("producer_id") else None,
                    cluster_id=UUID(str(props["cluster_id"])) if props.get("cluster_id") else None,
                    confidence=cast(float | None, props.get("confidence")),
                    model_version=cast(str | None, props.get("model_version")),
                    membership_weight=cast(float | None, props.get("membership_weight")),
                    distance=cast(float | None, getattr(obj.metadata, "distance", None)) if obj.metadata else None,
                    certainty=cast(float | None, getattr(obj.metadata, "certainty", None)) if obj.metadata else None,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Cluster-level search — single modality
    # ------------------------------------------------------------------

    async def search_clusters_by_named_vector(
        self,
        vector: list[float],
        named_vector: str,
        *,
        cluster_role: ClusterRole | None = None,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[ClusterSearchResult]:
        """Return nearest ClusterSnapshot objects using a single named vector.

        Args:
            vector: The query embedding vector.
            named_vector: Which named vector to search; use constants
                :data:`~people_gator_api.vector.schema.FACE_VECTOR` or
                :data:`~people_gator_api.vector.schema.NAME_VECTOR`.
            cluster_role: Optional cluster_role filter.
            limit: Maximum number of results.
            certainty: Minimum similarity threshold.
            distance: Maximum cosine distance.

        Returns:
            Ranked list of :class:`ClusterSearchResult`, closest first.
        """
        collection = self._client.collections.get(CLUSTER_SNAPSHOT_COLLECTION)
        filters = _build_cluster_filters(cluster_role=cluster_role)

        response = await collection.query.near_vector(
            near_vector={named_vector: vector},
            limit=limit,
            certainty=certainty,
            distance=distance,
            filters=filters,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )

        return [_object_to_cluster_result(obj, named_vector) for obj in response.objects]

    async def search_clusters_by_face(
        self,
        face_vector: list[float],
        *,
        cluster_role: ClusterRole | None = None,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[ClusterSearchResult]:
        """Shorthand for a face-modality cluster search."""
        return await self.search_clusters_by_named_vector(
            vector=face_vector,
            named_vector=FACE_VECTOR,
            cluster_role=cluster_role,
            limit=limit,
            certainty=certainty,
            distance=distance,
        )

    async def search_clusters_by_name(
        self,
        name_vector: list[float],
        *,
        cluster_role: ClusterRole | None = None,
        limit: int = _DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[ClusterSearchResult]:
        """Shorthand for a name-modality cluster search."""
        return await self.search_clusters_by_named_vector(
            vector=name_vector,
            named_vector=NAME_VECTOR,
            cluster_role=cluster_role,
            limit=limit,
            certainty=certainty,
            distance=distance,
        )

    # ------------------------------------------------------------------
    # Cluster-level search — weighted multi-modal
    # ------------------------------------------------------------------

    async def search_clusters_weighted(
        self,
        face_vector: list[float] | None = None,
        name_vector: list[float] | None = None,
        *,
        face_weight: float = _FACE_WEIGHT_DEFAULT,
        name_weight: float = _NAME_WEIGHT_DEFAULT,
        cluster_role: ClusterRole | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[ClusterSearchResult]:
        """Multi-modal cluster search with caller-supplied modality weights.

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
            cluster_role: Optional cluster_role filter.
            limit: Maximum number of results.

        Returns:
            Ranked list of :class:`ClusterSearchResult`, best first.

        Raises:
            ValueError: If neither vector is provided.
        """
        if face_vector is None and name_vector is None:
            raise ValueError("At least one of face_vector or name_vector must be supplied.")

        collection = self._client.collections.get(CLUSTER_SNAPSHOT_COLLECTION)
        filters = _build_cluster_filters(cluster_role=cluster_role)

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
            filters=filters,
            return_metadata=MetadataQuery(distance=True),
        )

        return [_object_to_cluster_result(obj) for obj in response.objects]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_evidence_filters(
    *,
    evidence_type: EvidenceType | None,
    cluster_id: UUID | None,
) -> Any:
    """Compose a Weaviate filter from optional evidence search constraints."""
    clauses: list[Any] = []
    if evidence_type is not None:
        clauses.append(Filter.by_property("evidence_type").equal(evidence_type.value))
    if cluster_id is not None:
        clauses.append(Filter.by_property("cluster_id").equal(str(cluster_id)))
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return Filter.all_of(clauses)


def _build_cluster_filters(*, cluster_role: ClusterRole | None) -> Any:
    """Compose a Weaviate filter from optional cluster search constraints."""
    if cluster_role is None:
        return None
    return Filter.by_property("cluster_role").equal(cluster_role.value)


def _object_to_cluster_result(
    obj: Any,
    primary_named_vector: str | None = None,
) -> ClusterSearchResult:
    """Map a Weaviate query object to a ClusterSearchResult."""
    props = obj.properties
    meta = obj.metadata

    distance = meta.distance if meta else None

    return ClusterSearchResult(
        weaviate_id=obj.uuid,
        cluster_id=UUID(str(props.get("cluster_id"))),
        cluster_role=ClusterRole(str(props.get("cluster_role"))),
        as_of_version_id=(
            UUID(str(props["as_of_version_id"])) if props.get("as_of_version_id") else None
        ),
        face_count=int(props.get("face_count", 0)),
        named_entity_count=int(props.get("named_entity_count", 0)),
        text_region_count=int(props.get("text_region_count", 0)),
        face_distance=distance if primary_named_vector == FACE_VECTOR else None,
        name_distance=distance if primary_named_vector == NAME_VECTOR else None,
        combined_distance=distance if primary_named_vector is None else None,
    )
