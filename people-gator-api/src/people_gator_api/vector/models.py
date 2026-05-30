"""Pydantic result models returned by VectorSearchService.

All models use uuid.UUID for identifier fields and expose per-modality
distance/score information so callers can implement their own re-ranking
or provenance logging.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from people_gator_api.db.models.enums import ClusterRole, RecordType


class RecordSearchResult(BaseModel):
    """A single result from a nearest-neighbour search over RecordEmbedding."""

    weaviate_id: UUID = Field(description="Weaviate object UUID (same as embedding_id on RECORD).")
    record_id: UUID
    record_version_id: UUID
    record_type: RecordType
    source_id: UUID
    cluster_id: UUID | None
    confidence: float | None
    model_version: str | None
    membership_weight: float | None
    membership_reason: str | None
    distance: float | None = Field(
        default=None,
        description="Cosine distance from the query vector.  Lower is more similar.",
    )
    certainty: float | None = Field(
        default=None,
        description="Certainty score in [0, 1].  Higher is more similar.",
    )


class ClusterSearchResult(BaseModel):
    """A single result from a nearest-neighbour search over ClusterSnapshot."""

    weaviate_id: UUID = Field(description="Weaviate object UUID for this cluster snapshot.")
    cluster_id: UUID
    cluster_role: ClusterRole
    as_of_version_id: UUID | None
    face_count: int
    named_entity_count: int
    text_region_count: int
    face_distance: float | None = Field(
        default=None,
        description="Cosine distance from the query in the face named-vector space.",
    )
    name_distance: float | None = Field(
        default=None,
        description="Cosine distance from the query in the name named-vector space.",
    )
    combined_distance: float | None = Field(
        default=None,
        description=(
            "Weighted combined distance used to rank this result.  "
            "Computed by Weaviate using the caller-supplied TargetVectors weights."
        ),
    )
