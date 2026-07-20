"""Pydantic schemas for entity and annotation endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ModificationMetadata(BaseModel):
    """Optional model metadata attached to mutable evidence records."""

    embedding: list[float] | None = None
    model_identifier: str | None = None


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class EntityCreateRequest(BaseModel):
    """Request body for creating a new entity."""

    name: str | None = None
    description: str | None = None


class EntityResponse(BaseModel):
    """A single entity record."""

    entity_id: uuid.UUID
    principal_id: uuid.UUID
    name: str | None
    description: str | None


class EntityListResponse(BaseModel):
    """A paginated list of entities."""

    items: list[EntityResponse]
    total: int
    next_after_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------


class MentionPolygonPoint(BaseModel):
    """A polygon point in source-space coordinates."""

    x: float
    y: float


class MentionPolygon(BaseModel):
    """One mention polygon represented by ordered points."""

    points: list[MentionPolygonPoint] = Field(min_length=3)


class MentionCreateRequest(ModificationMetadata):
    """Request body for ingesting a mention."""

    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    offset_start: int
    offset_end: int
    polygons: list[MentionPolygon] | None = None
    model_agent_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class MentionResponse(ModificationMetadata):
    """A single mention record."""

    mention_id: uuid.UUID
    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    offset_start: int
    offset_end: int
    polygons: list[MentionPolygon] | None
    model_agent_id: uuid.UUID
    confidence: float


# ---------------------------------------------------------------------------
# Information
# ---------------------------------------------------------------------------


class InformationCreateRequest(ModificationMetadata):
    """Request body for ingesting information."""

    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    model_agent_id: uuid.UUID


class InformationResponse(ModificationMetadata):
    """A single information record."""

    information_id: uuid.UUID
    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    model_agent_id: uuid.UUID


# ---------------------------------------------------------------------------
# Document Mentions
# ---------------------------------------------------------------------------


class DocumentMentionCreateRequest(ModificationMetadata):
    """Request body for creating a document-level mention aggregator."""

    name: str
    information: str
    model_agent_id: uuid.UUID
    source_id: uuid.UUID
    entity_id: uuid.UUID


class DocumentMentionResponse(ModificationMetadata):
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


class FaceCreateRequest(ModificationMetadata):
    """Request body for ingesting a face detection."""

    source_id: uuid.UUID
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    model_agent_id: uuid.UUID
    entity_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class FaceResponse(ModificationMetadata):
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


class DescriptionCreateRequest(ModificationMetadata):
    """Request body for adding a description."""

    text: str
    language: str
    source_id: uuid.UUID
    entity_id: uuid.UUID


class DescriptionResponse(ModificationMetadata):
    """A single description record."""

    description_id: uuid.UUID
    text: str
    language: str
    source_id: uuid.UUID
    entity_id: uuid.UUID


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


class NameCreateRequest(ModificationMetadata):
    """Request body for adding a name."""

    name: str
    source_id: uuid.UUID
    entity_id: uuid.UUID


class NameResponse(ModificationMetadata):
    """A single name record."""

    name_id: uuid.UUID
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
    name_ids: list[uuid.UUID]

