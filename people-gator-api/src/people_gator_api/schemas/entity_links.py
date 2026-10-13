"""Shared annotation link schemas. Omission and null have distinct meanings."""

from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .enums import EntityLinkState
from .missing import MISSING, MissingType, is_missing


class EntityLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_link_state: EntityLinkState | MissingType = MISSING

    @model_validator(mode="after")
    def validate_link(self):
        if self.entity_link_state == EntityLinkState.verified:
            raise ValueError("Create the link before verifying it")
        if not is_missing(self.entity_link_state) and is_missing(self.entity_id):
            raise ValueError("A link state requires an entity")
        return self


class EntityLinkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_link_state: EntityLinkState | None | MissingType = MISSING


class EntityLinkResponse(BaseModel):
    entity_link_state: EntityLinkState | None = None
    entity_link_verified_by_user_id: uuid.UUID | None = None
    entity_link_verified_at: datetime | None = None


class EntityLinkFilter(BaseModel):
    entity_link_state: list[EntityLinkState] | MissingType = Field(
        default=MISSING,
        description="Match any selected link state on the same annotation as other evidence filters. Omit to include unassigned annotations.",
    )

    @field_validator("entity_link_state")
    @classmethod
    def normalize_states(cls, value):
        if is_missing(value):
            return value
        if not value:
            raise ValueError("entity_link_state must not be empty")
        return sorted(set(value), key=lambda item: item.value)


class EntityLinkStateCounts(BaseModel):
    automatic: int = Field(default=0, ge=0)
    manual: int = Field(default=0, ge=0)
    verified: int = Field(default=0, ge=0)
    unassigned: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class EntityLinkStats(BaseModel):
    faces: EntityLinkStateCounts = Field(default_factory=EntityLinkStateCounts)
    mentions: EntityLinkStateCounts = Field(default_factory=EntityLinkStateCounts)
