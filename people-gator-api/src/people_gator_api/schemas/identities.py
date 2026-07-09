"""Pydantic schemas for identity and annotation endpoints."""

import uuid

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class IdentityCreateRequest(BaseModel):
    """Request body for creating a new identity."""


class IdentityResponse(BaseModel):
    """A single identity record."""

    identity_id: uuid.UUID
    principal_id: uuid.UUID


class IdentityListResponse(BaseModel):
    """A paginated list of identities."""

    items: list[IdentityResponse]
    total: int
    next_after_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------


class MentionCreateRequest(BaseModel):
    """Request body for ingesting a mention."""

    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    offset_start: int
    offset_end: int
    model_agent_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class MentionResponse(BaseModel):
    """A single mention record."""

    mention_id: uuid.UUID
    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    offset_start: int
    offset_end: int
    model_agent_id: uuid.UUID
    confidence: float


# ---------------------------------------------------------------------------
# Information
# ---------------------------------------------------------------------------


class InformationCreateRequest(BaseModel):
    """Request body for ingesting information."""

    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    model_agent_id: uuid.UUID


class InformationResponse(BaseModel):
    """A single information record."""

    information_id: uuid.UUID
    text: str
    document_mention_id: uuid.UUID
    source_id: uuid.UUID
    model_agent_id: uuid.UUID


# ---------------------------------------------------------------------------
# Document Mentions
# ---------------------------------------------------------------------------


class DocumentMentionCreateRequest(BaseModel):
    """Request body for creating a document-level mention aggregator."""

    name: str
    information: str
    model_agent_id: uuid.UUID
    identity_id: uuid.UUID


class DocumentMentionResponse(BaseModel):
    """A single document mention record."""

    document_mention_id: uuid.UUID
    name: str
    information: str
    model_agent_id: uuid.UUID
    identity_id: uuid.UUID


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
    model_agent_id: uuid.UUID
    identity_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class FaceResponse(BaseModel):
    """A single face detection record."""

    detection_id: uuid.UUID
    source_id: uuid.UUID
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    model_agent_id: uuid.UUID
    identity_id: uuid.UUID
    confidence: float


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


class DescriptionCreateRequest(BaseModel):
    """Request body for adding a description."""

    text: str
    language: str
    source_id: uuid.UUID
    identity_id: uuid.UUID


class DescriptionResponse(BaseModel):
    """A single description record."""

    description_id: uuid.UUID
    text: str
    language: str
    source_id: uuid.UUID
    identity_id: uuid.UUID


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


class NameCreateRequest(BaseModel):
    """Request body for adding a name."""

    name: str
    source_id: uuid.UUID
    identity_id: uuid.UUID


class NameResponse(BaseModel):
    """A single name record."""

    name_id: uuid.UUID
    name: str
    source_id: uuid.UUID
    identity_id: uuid.UUID


# ---------------------------------------------------------------------------
# Identity View
# ---------------------------------------------------------------------------


class IdentityViewResponse(BaseModel):
    """Current identity view grouped by attached entity IDs."""

    identity_id: uuid.UUID
    document_mention_ids: list[uuid.UUID]
    face_ids: list[uuid.UUID]
    description_ids: list[uuid.UUID]
    name_ids: list[uuid.UUID]
