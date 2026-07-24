"""Pydantic result models returned by VectorSearchService.

All models use uuid.UUID for identifier fields and expose per-modality
distance/score information so callers can implement their own re-ranking
or provenance logging.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from people_gator_api.schemas.enums import AnnotationType


class AnnotationSearchResult(BaseModel):
    """A single result from a nearest-neighbour search over AnnotationEmbedding."""

    weaviate_id: UUID = Field(
        description="Weaviate object UUID (deterministic: uuid5 of annotation_type + annotation_id)."
    )
    annotation_type: AnnotationType
    annotation_id: UUID
    source_id: UUID
    model_agent_id: UUID | None
    confidence: float | None
    entity_id: UUID | None
    distance: float | None = Field(
        default=None,
        description="Cosine distance from the query vector.  Lower is more similar.",
    )
    certainty: float | None = Field(
        default=None,
        description="Certainty score in [0, 1].  Higher is more similar.",
    )


class EntitySearchResult(BaseModel):
    """A single result from a nearest-neighbour search over entity collections."""

    weaviate_id: UUID = Field(
        description="Weaviate object UUID for this identity snapshot."
    )
    entity_id: UUID
    face_count: int
    mention_count: int
    information_count: int
    document_mention_count: int
    description_count: int
    name_count: int
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
        description="Weighted combined distance used to rank this result.",
    )
    description_distance: float | None = Field(
        default=None,
        description="Cosine distance from the query in the description named-vector space.",
    )
