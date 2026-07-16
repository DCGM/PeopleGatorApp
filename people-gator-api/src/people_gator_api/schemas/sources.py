"""Pydantic schemas for source endpoints (spec §2.7 simplified source model)."""

import uuid

from pydantic import BaseModel

from people_gator_api.schemas.enums import SourceKind

type JsonValue = (
    str | int | float | bool | None | dict[str, "JsonValue"] | list["JsonValue"]
)


class SourceCreateRequest(BaseModel):
    """Request body for registering a source."""

    source_type: SourceKind
    uri: str
    metadata: dict[str, JsonValue] | None = None


class SourceResponse(BaseModel):
    """A single source record."""

    source_id: uuid.UUID
    source_type: SourceKind
    uri: str
    metadata: dict[str, JsonValue] | None


class SourceListResponse(BaseModel):
    """A paginated list of sources."""

    items: list[SourceResponse]
    total: int
    next_after_id: uuid.UUID | None = None
