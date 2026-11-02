"""Read-only audit queries and optimistic edit preconditions."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID
from typing import Any, Literal
from pydantic import AwareDatetime, BaseModel, Field, model_validator


class ObjectKind(StrEnum):
    entity = "entity"
    face = "face"
    mention = "mention"
    source = "source"


class VersionConflict(Exception):
    """The caller must reload the object before attempting another edit."""


class VersionedEdit(BaseModel):
    expected_version: int = Field(
        ge=1, description="Version read by the caller; stale edits return 409."
    )


class AuditQuery(BaseModel):
    object_type: ObjectKind | None = None
    object_id: UUID | None = None
    entity_id: UUID | None = None
    source_id: UUID | None = None
    actor_user_id: UUID | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    version_min: int | None = Field(default=None, ge=1)
    version_max: int | None = Field(default=None, ge=1)
    deleted: bool | None = None
    sort: Literal["time", "version"] = "time"
    direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_ranges(self):
        if self.since and self.until and self.since > self.until:
            raise ValueError("since must precede until")
        if (
            self.version_min
            and self.version_max
            and self.version_min > self.version_max
        ):
            raise ValueError("version_min must not exceed version_max")
        return self


class AuditRevision(BaseModel):
    object_type: ObjectKind
    object_id: UUID
    version: int
    changed_at: datetime
    actor_user_id: UUID
    actor_api_key_id: UUID | None
    deleted: bool
    entity_id: UUID | None
    source_id: UUID | None
    state: dict[str, Any]


class AuditListResponse(BaseModel):
    items: list[AuditRevision]
    total_count: int
    limit: int
    offset: int
