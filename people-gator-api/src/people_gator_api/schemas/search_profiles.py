"""Pydantic schemas for search and search-profile endpoints.
"""

import uuid
from pydantic import BaseModel

from people_gator_api.schemas.enums import AnnotationType

# ---------------------------------------------------------------------------
# Search profile modality schemas
# ---------------------------------------------------------------------------

class SearchProfileModalityIn(BaseModel):
    """Input modality for a search profile."""

    annotation_type: AnnotationType
    weight: float
    model_id: uuid.UUID | None = None
    min_confidence: float | None = None


class SearchProfileModalityOut(BaseModel):
    """Output modality for a search profile."""

    annotation_type: AnnotationType
    weight: float
    model_id: uuid.UUID | None
    min_confidence: float | None
    

# ---------------------------------------------------------------------------
# Search profile schemas
# ---------------------------------------------------------------------------

class SearchProfileCreateRequest(BaseModel):
    """Request body for creating a search profile."""
    profile_name: str
    description: str | None = None
    is_public: bool = False
    modalities: list[SearchProfileModalityIn]


class SearchProfilePatchRequest(BaseModel):
    """Request body for patching a search profile."""
    profile_name: str | None = None
    description: str | None = None
    is_public: bool | None = None
    modalities: list[SearchProfileModalityIn] | None = None

class SearchProfileCloneRequest(BaseModel):
    """Request body for cloning a search profile."""
    profile_name: str | None = None

class SearchProfileResponse(BaseModel):
    """Full search profile record."""
    profile_id: uuid.UUID
    profile_name: str
    description: str | None
    owner_id: uuid.UUID | None
    is_public: bool
    is_system: bool
    modalities: list[SearchProfileModalityOut]
