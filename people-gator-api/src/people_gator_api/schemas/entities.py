"""Pydantic schemas for entity and annotation endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class VectorInput(BaseModel):
    """Optional vector payload supplied for a single-vector annotation write."""

    embedding: list[float] | None = None
    model_identifier: str | None = None


class MultiVectorInput(BaseModel):
    """Optional vector payload supplied for dual-vector annotation writes."""

    name_embedding: list[float] | None = None
    fulltext_embedding: list[float] | None = None
    model_identifier: str | None = None


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class EntityCreateRequest(MultiVectorInput):
    """Request body for creating a new entity."""

    entity_type: str | None = None
    name: str | None = None
    description: str | None = None


class EntityResponse(BaseModel):
    """A single entity record."""

    entity_id: uuid.UUID
    principal_id: uuid.UUID
    entity_type: str | None
    name: str | None
    description: str | None
    wikidata_id: str | None
    nlcr_authority_id: str | None


class EntityListResponse(BaseModel):
    """A paginated list of entities."""

    items: list[EntityResponse]
    total: int
    next_after_id: uuid.UUID | None = None


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


class PageMentionCreateRequest(MultiVectorInput):
    """Request body for ingesting a page-level mention aggregation."""

    name: str
    information: str
    confidence: float = Field(ge=0.0, le=1.0)
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    model_agent_id: uuid.UUID


class PageMentionResponse(BaseModel):
    """A single page mention record."""

    page_mention_id: uuid.UUID
    name: str
    information: str
    confidence: float
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    model_agent_id: uuid.UUID


class SpanCreateRequest(VectorInput):
    """Request body for ingesting a span linked to a page mention."""

    text: str
    page_mention_id: uuid.UUID
    source_id: uuid.UUID
    polygons: list[Polygon]


class SpanResponse(BaseModel):
    """A single span record."""

    span_id: uuid.UUID
    text: str
    page_mention_id: uuid.UUID
    source_id: uuid.UUID
    entity_id: uuid.UUID
    polygons: list[Polygon]


# ---------------------------------------------------------------------------
# Document mentions
# ---------------------------------------------------------------------------


class DocumentMentionCreateRequest(MultiVectorInput):
    """Request body for creating a document-level mention aggregator."""

    name: str
    information: str
    model_agent_id: uuid.UUID
    source_id: uuid.UUID
    entity_id: uuid.UUID


class DocumentMentionResponse(BaseModel):
    """A single document mention record."""

    document_mention_id: uuid.UUID
    name: str
    information: str
    model_agent_id: uuid.UUID
    source_id: uuid.UUID
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


class FaceCreateRequest(VectorInput):
    """Request body for ingesting a face detection."""

    source_id: uuid.UUID
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    model_agent_id: uuid.UUID
    entity_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class FaceResponse(BaseModel):
    """A single face detection record."""

    detection_id: uuid.UUID
    source_id: uuid.UUID
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    model_agent_id: uuid.UUID
    entity_id: uuid.UUID
    confidence: float


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


class DescriptionCreateRequest(VectorInput):
    """Request body for adding a description."""

    text: str
    language: str
    source_id: uuid.UUID
    entity_id: uuid.UUID


class DescriptionResponse(BaseModel):
    """A single description record."""

    description_id: uuid.UUID
    text: str
    language: str
    source_id: uuid.UUID
    entity_id: uuid.UUID


# ---------------------------------------------------------------------------
# Entity names
# ---------------------------------------------------------------------------


class EntityNameCreateRequest(VectorInput):
    """Request body for adding a name."""

    name: str
    source_id: uuid.UUID
    entity_id: uuid.UUID


class EntityNameResponse(BaseModel):
    """A single entity-name record."""

    entity_name_id: uuid.UUID
    name: str
    source_id: uuid.UUID
    entity_id: uuid.UUID


# ---------------------------------------------------------------------------
# Entity View
# ---------------------------------------------------------------------------


class EntityViewResponse(BaseModel):
    """Current entity view grouped by attached entity IDs."""

    entity_id: uuid.UUID
    document_mention_ids: list[uuid.UUID]
    face_ids: list[uuid.UUID]
    description_ids: list[uuid.UUID]
    entity_name_ids: list[uuid.UUID]
