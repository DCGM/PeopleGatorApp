"""Pydantic schemas for entity and annotation endpoints."""

from __future__ import annotations

import uuid

from pydantic import (
    BaseModel,
    Field,
)

from people_gator_api.schemas.common import GenericListResponse

# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class EntityCreateRequest(BaseModel):
    """Request body for creating a new entity."""

    entity_type: str | None = None
    name: str | None = None
    description: str | None = None
    short_description: str | None = None
    aliases: list[str] | None = None
    wikidata_id: str | None = None
    nlcr_authority_id: str | None = None
    name_embedding: list[float] | None = None
    fulltext_embedding: list[float] | None = None
    model_identifier: str | None = None


class EntityResponse(BaseModel):
    """A single entity record."""

    entity_id: uuid.UUID
    entity_type: str | None
    name: str | None
    description: str | None
    short_description: str | None
    aliases: list[str] | None
    wikidata_id: str | None
    nlcr_authority_id: str | None
    principal_id: uuid.UUID


class EntityListResponse(GenericListResponse[EntityResponse]):
    """A paginated list of entities."""

    items: list[EntityResponse]


# ---------------------------------------------------------------------------
# Page mentions and spans
# ---------------------------------------------------------------------------


class PolygonPoint(BaseModel):
    """A polygon point in source-space coordinates."""

    x: float
    y: float


class Polygon(BaseModel):
    """One polygon represented by ordered points."""

    points: list[PolygonPoint] = Field(min_length=3)


class PageMentionCreateRequest(BaseModel):
    """Request body for ingesting a page-level mention aggregation."""

    name: str
    information: str
    aliases: list[str]
    polygons: list[Polygon]
    document_mention_id: uuid.UUID
    source_id: uuid.UUID


class PageMentionResponse(BaseModel):
    """A single page mention record."""

    page_mention_id: uuid.UUID
    name: str
    information: str
    aliases: list[str]
    polygons: list[Polygon]
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    principal_id: uuid.UUID


class PageMentionListResponse(GenericListResponse[PageMentionResponse]):
    """A paginated list of page mentions."""

    items: list[PageMentionResponse]


# ---------------------------------------------------------------------------
# Document mentions
# ---------------------------------------------------------------------------


class PageMentionInlineCreateRequest(BaseModel):
    """Page mention embedded directly inside a DocumentMentionCreateRequest.

    `document_mention_id` is omitted — it is assigned automatically from the
    owning document mention.
    """

    name: str
    information: str
    aliases: list[str]
    polygons: list[Polygon]
    source_id: uuid.UUID


class DocumentMentionCreateRequest(BaseModel):
    """Request body for creating a document-level mention aggregator."""

    name: str
    information: str
    aliases: list[str]
    source_id: uuid.UUID
    entity_id: uuid.UUID
    page_mentions: list[PageMentionInlineCreateRequest] = []


class DocumentMentionResponse(BaseModel):
    """A single document mention record."""

    document_mention_id: uuid.UUID
    name: str
    information: str
    aliases: list[str]
    principal_id: uuid.UUID
    source_id: uuid.UUID
    entity_id: uuid.UUID


class DocumentMentionListResponse(GenericListResponse[DocumentMentionResponse]):
    """A paginated list of document mentions."""

    items: list[DocumentMentionResponse]


class DocumentMentionEntityPatchRequest(BaseModel):
    """Patch body for reassigning a document mention to a different entity."""

    entity_id: uuid.UUID


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """Face detection bounding box."""

    x: int
    y: int
    width: int
    height: int


class FaceKeypoint(BaseModel):
    """One keypoint of a face detection."""

    type: str
    x: float
    y: float


class FaceCreateRequest(BaseModel):
    """Request body for ingesting a face detection."""

    source_id: uuid.UUID
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    embedding: list[float] | None = None
    model_identifier: str | None = None
    entity_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class FaceResponse(BaseModel):
    """A single face detection record."""

    detection_id: uuid.UUID
    source_id: uuid.UUID
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    principal_id: uuid.UUID
    entity_id: uuid.UUID | None = Field(default=None)
    confidence: float


class FaceListResponse(GenericListResponse[FaceResponse]):
    """A paginated list of face detections."""

    items: list[FaceResponse]


class FaceEntityPatchRequest(BaseModel):
    """Patch body for reassigning a face annotation to a different entity."""

    entity_id: uuid.UUID
