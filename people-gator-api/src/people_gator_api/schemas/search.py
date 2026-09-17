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
    SourceKind,
)

# ---------------------------------------------------------------------------
# Search result type
# ---------------------------------------------------------------------------


class SearchEntitiesResult(BaseModel):
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


class SearchEntitiesResultListResponse(GenericListResponse[SearchEntitiesResult]):
    """A paginated list of search results."""

    items: list[SearchEntitiesResult]


# ---------------------------------------------------------------------------
# Search request and response
# ---------------------------------------------------------------------------


class SearchEntitiesQuery(BaseModel):
    """Typed query signals the caller wants to find matches for."""

    q: list[str] | None = Field(
        default=None,
        description="Name or alias text to search for.",
    )
    q_face_id: list[uuid.UUID] | None = Field(
        default=None,
        description="Reference face detection whose identity should rank nearby.",
    )
    entity_types: list[EntityType] | EntityType | None = Field(
        default=None,
        description="Optional entity type filter(s).",
    )
    source_id: uuid.UUID | None = Field(
        default=None,
        description="Only return entities occurring in this document or page Source.",
    )
    embedding_model: FaceEmbeddingModel = Field(
        default=FaceEmbeddingModel.gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3,
        description="Named face vector used for q_face_id search.",
    )
    aggregation: ScoreAggregation = Field(
        default=ScoreAggregation.max,
        description="How matching face scores are aggregated per entity.",
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

    face_id: uuid.UUID = Field(..., description="The matched face detection ID.")
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


# ---------------------------------------------------------------------------
# Page and document search
# ---------------------------------------------------------------------------


class ArchiveHit(BaseModel):
    """A page or document hit resolved back to its archive Source."""

    source_id: uuid.UUID = Field(
        ...,
        description="Source record describing the page or document.",
    )
    kind: SourceKind = Field(
        ...,
        description="Whether the hit is a page or a document.",
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        description="Archive document identity of the hit, when known.",
    )
    page_id: uuid.UUID | None = Field(
        default=None,
        description="Archive page identity of the hit, when known.",
    )
    matching_score: float = Field(
        ...,
        description="Fused BM25 relevance score of the hit.",
    )


class ArchiveHitListResponse(GenericListResponse[ArchiveHit]):
    """A paginated list of page and document hits."""

    items: list[ArchiveHit]


class SearchArchiveQuery(BaseModel):
    """Single-input search across pages and documents.

    The query input matches directly linked entity names and aliases, or
    archive UUIDs directly.
    """

    q: str = Field(
        ...,
        min_length=1,
        description="Free text name or alias to search for.",
    )
    source_id: uuid.UUID | None = Field(
        default=None,
        description="Only return hits inside this document or page Source.",
    )
    limit: int = Field(
        default=20,
        ge=0,
        description="The maximum number of results to return.",
    )


class FaceSearchQuery(BaseModel):
    """Query for faces similar to a set of reference faces."""

    q_face_id: list[uuid.UUID] = Field(
        default_factory=list[uuid.UUID],
        description="Reference face detection IDs the results should be similar to.",
    )
    embedding_model: FaceEmbeddingModel = Field(
        default=FaceEmbeddingModel.gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3,
        description="Named face vector to search by.",
    )
    limit: int = Field(
        default=20,
        ge=0,
        description="The maximum number of results to return.",
    )
