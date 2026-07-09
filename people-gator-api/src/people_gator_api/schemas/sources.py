"""Pydantic schemas for source endpoints (spec §2.7 simplified source model)."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from people_gator_api.models.enums import SourceKind


class SourceCreateRequest(BaseModel):
    """Request body for registering a source."""

    source_type: SourceKind
    uri: str
    metadata: dict[str, str] | None = None


class SourceResponse(BaseModel):
    """A single source record."""

    source_id: uuid.UUID
    source_type: SourceKind
    uri: str
    metadata: dict[str, str] | None
    principal_id: uuid.UUID | None
    created_at: datetime


class SourceListResponse(BaseModel):
    """A paginated list of sources."""

    items: list[SourceResponse]
    total: int
    next_after_id: uuid.UUID | None = None
