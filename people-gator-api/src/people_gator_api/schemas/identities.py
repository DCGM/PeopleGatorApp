"""Pydantic schemas for identity and annotation endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from people_gator_api.models.enums import (
    ConsensusMethod,
    EntityType,
    NameType,
)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class IdentityCreateRequest(BaseModel):
    """Request body for creating a new identity."""


class IdentityResponse(BaseModel):
    """A single identity record."""
    identity_id: uuid.UUID
    created_at: datetime
    principal_id: uuid.UUID


class IdentityListResponse(BaseModel):
    """A paginated list of identities."""
    items: list[IdentityResponse]
    total: int
    next_after_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Named entity
# ---------------------------------------------------------------------------


class NamedEntityCreateRequest(BaseModel):
    """Request body for ingesting a named entity mention."""
    text: str
    source_id: uuid.UUID
    offset_start: int
    offset_end: int
    entity_type: EntityType
    principal_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class NamedEntityResponse(BaseModel):
    """A single named entity record."""
    annotation_id: uuid.UUID
    text: str
    source_id: uuid.UUID
    offset_start: int
    offset_end: int
    entity_type: EntityType
    principal_id: uuid.UUID
    confidence: float
    created_at: datetime


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class DetectionCreateRequest(BaseModel):
    """Request body for ingesting a face detection."""
    source_id: uuid.UUID
    bounding_box: dict[str, int]
    keypoints: list[dict[str, object]] | None = None
    principal_id: uuid.UUID
    confidence: float = Field(ge=0.0, le=1.0)


class DetectionResponse(BaseModel):
    """A single detection record."""
    annotation_id: uuid.UUID
    source_id: uuid.UUID
    bounding_box: dict[str, int]
    keypoints: list[dict[str, object]] | None
    principal_id: uuid.UUID
    confidence: float
    created_at: datetime


# ---------------------------------------------------------------------------
# Description
# ---------------------------------------------------------------------------


class DescriptionCreateRequest(BaseModel):
    """Request body for adding a description."""
    text: str
    source_id: uuid.UUID
    language: str | None = None


class DescriptionResponse(BaseModel):
    """A single description record."""
    annotation_id: uuid.UUID
    text: str
    source_id: uuid.UUID
    language: str | None
    principal_id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Alternative name
# ---------------------------------------------------------------------------


class AlternativeNameCreateRequest(BaseModel):
    """Request body for adding an alternative name."""
    name: str
    name_type: NameType
    source_id: uuid.UUID
    language: str


class AlternativeNameResponse(BaseModel):
    """A single alternative name record."""

    annotation_id: uuid.UUID
    name: str
    name_type: NameType
    source_id: uuid.UUID
    language: str
    principal_id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Consensus — annotation decisions and consensus snapshots
# ---------------------------------------------------------------------------


class LinkDecisionCreateRequest(BaseModel):
    """Request body for an annotator's decision on an annotation."""
    annotation_id: uuid.UUID
    identity_id: uuid.UUID
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

class LinkDecisionUpdateRequest(BaseModel):
    """Request body for updating an annotator's decision on an annotation."""
    annotation_id: uuid.UUID
    identity_id: uuid.UUID | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class LinkDecisionResponse(BaseModel):
    """A single annotator decision."""
    annotation_id: uuid.UUID
    identity_id: uuid.UUID
    principal_id: uuid.UUID
    confidence: float | None
    created_at: datetime


class LinkConsensusCreateRequest(BaseModel):
    """Request body for creating a consensus snapshot.

    ``decision_cutoff_at`` optionally restricts which LINK_DECISION rows are
    considered to those created at or before this time (spec §2.6.3).
    """

    identity_id: uuid.UUID
    annotation_id: uuid.UUID
    method: ConsensusMethod


class LinkConsensusResponse(BaseModel):
    """A single consensus snapshot."""
    identity_id: uuid.UUID
    annotation_id: uuid.UUID
    principal_id: uuid.UUID
    method: ConsensusMethod
    created_at: datetime


class IdentityAnnotationEntry(BaseModel):
    """One included annotation in an identity's current view."""
    annotation_id: uuid.UUID


class IdentityViewResponse(BaseModel):
    """An identity's current view — the annotations with an ``include`` consensus."""
    identity_id: uuid.UUID
    included: list[IdentityAnnotationEntry]


# ---------------------------------------------------------------------------
# Bulk link decision create
# ---------------------------------------------------------------------------


class BulkLinkDecisionRequest(BaseModel):
    """Bulk wrapper for creating multiple annotator decisions at once."""
    decisions: list[LinkDecisionCreateRequest] = Field(max_length=500)


class BulkLinkDecisionResponse(BaseModel):
    """Result of a bulk decision create."""
    created: list[LinkDecisionResponse]
