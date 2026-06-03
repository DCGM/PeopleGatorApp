"""Pydantic result models returned by VectorSearchService.

All models use uuid.UUID for identifier fields and expose per-modality
distance/score information so callers can implement their own re-ranking
or provenance logging.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from people_gator_api.db.models.enums import ClusterRole, EvidenceType


class EvidenceSearchResult(BaseModel):
    """A single result from a nearest-neighbour search over EvidenceEmbedding."""

    weaviate_id: UUID = Field(description="Weaviate object UUID (deterministic: uuid5 of evidence_id + evidence_version_id).")
    evidence_id: UUID
    evidence_version_id: UUID
    evidence_type: EvidenceType
    source_id: UUID
    producer_id: UUID | None
    cluster_id: UUID | None
    confidence: float | None
    model_version: str | None
    membership_weight: float | None
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
        description="Weighted combined distance used to rank this result. Computed by Weaviate using the caller-supplied TargetVectors weights.",
    )
