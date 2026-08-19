"""Pydantic schemas for search and search endpoints."""

import uuid

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
)
from people_gator_api.schemas.common import GenericListResponse
from people_gator_api.schemas.entities import BoundingBox
from people_gator_api.schemas.enums import (
    EntityType,
    FaceEmbeddingModel,
    ScoreAggregation,
)

# ---------------------------------------------------------------------------
# Search result type
# ---------------------------------------------------------------------------


class EntitySearchResult(BaseModel):
    """A single result from a nearest-neighbour search over an annotation collection."""

    entity_id: uuid.UUID = Field(..., description="The entity ID of the annotation.")
    entity_type: EntityType | None = Field(
        ..., description="The entity type of the annotation."
    )
    name: str = Field(..., description="The name of the annotation.")
    description: str = Field(..., description="The description of the annotation.")
    short_description: str = Field(
        ..., description="The short description of the annotation."
    )
    aliases: list[str] = Field(..., description="The aliases of the annotation.")
    matching_score: float = Field(
        ..., description="The matching score of the annotation."
    )


class SearchResultListResponse(GenericListResponse[EntitySearchResult]):
    """A paginated list of search results."""

    items: list[EntitySearchResult]


# ---------------------------------------------------------------------------
# Search request and response
# ---------------------------------------------------------------------------


class SearchQuery(BaseModel):
    """Typed query signals the caller wants to find matches for."""

    name: list[str] | str | None = Field(
        default=None,
        validation_alias=AliasChoices("name", "query_name", "query_names"),
        description="The name to search for.",
    )
    entity_types: list[EntityType] | EntityType | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "entity_types",
            "entity_type",
            "types",
            "query_entity_types",
            "query_entity_type",
            "query_types",
        ),
        description="Optional entity type filter(s).",
    )
    limit: int = Field(
        default=20,
        ge=0,
        validation_alias=AliasChoices("limit", "query_limit"),
        description="The maximum number of results to return.",
    )
    after_id: uuid.UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("after_id", "query_after_id"),
        description="The ID of the last result from the previous page of results.",
    )


# ---------------------------------------------------------------------------
# Face similarity search
# ---------------------------------------------------------------------------


class FaceSearchResult(BaseModel):
    """A single face detection matched against the supplied query faces."""

    detection_id: uuid.UUID = Field(..., description="The matched face detection ID.")
    source_id: uuid.UUID | None = Field(
        default=None, description="Source containing the matched face."
    )
    entity_id: uuid.UUID | None = Field(
        default=None, description="Entity the matched face is assigned to."
    )
    bounding_box: BoundingBox | None = Field(
        default=None, description="Bounding box of the matched face."
    )
    matching_score: float = Field(
        ...,
        description="Cosine similarity to the closest supplied query face.",
    )


class FaceSearchResultListResponse(GenericListResponse[FaceSearchResult]):
    """A paginated list of face similarity results."""

    items: list[FaceSearchResult]


class FaceSearchQuery(BaseModel):
    """Query for faces similar to a set of reference faces."""

    face_ids: list[uuid.UUID] = Field(
        default_factory=list[uuid.UUID],
        validation_alias=AliasChoices("face_ids", "face_id"),
        description="Reference face detection IDs the results should be similar to.",
    )
    embedding_model: FaceEmbeddingModel = Field(
        default=FaceEmbeddingModel.gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3,
        validation_alias=AliasChoices("embedding_model", "model"),
        description="Named face vector to search by.",
    )
    limit: int = Field(
        default=20,
        ge=0,
        description="The maximum number of results to return.",
    )


class EntityFaceSearchQuery(FaceSearchQuery):
    """Face similarity query whose results are aggregated per entity."""

    aggregation: ScoreAggregation = Field(
        default=ScoreAggregation.max,
        description="How per-face scores are aggregated into an entity score.",
    )
