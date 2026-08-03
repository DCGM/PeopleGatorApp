"""Pydantic models returned by vector-search helpers."""

from uuid import (
    UUID,
)

from pydantic import (
    BaseModel,
    Field,
)

from people_gator_api.schemas.enums import (
    AnnotationType,
)


class AnnotationSearchResult(BaseModel):
    """A single result from a nearest-neighbour search over an annotation collection."""

    weaviate_id: UUID = Field(
        description="Weaviate object UUID for the annotation object.",
    )
    annotation_type: AnnotationType
    annotation_id: UUID
    source_id: UUID
    model_agent_id: UUID | None
    confidence: float | None
    entity_id: UUID | None
    distance: float | None = Field(
        default=None,
        description="Cosine distance from the query vector. Lower is more similar.",
    )
    certainty: float | None = Field(
        default=None,
        description="Certainty score in [0, 1]. Higher is more similar.",
    )
