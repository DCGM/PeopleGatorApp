"""Shared annotation link schemas. Omission and null have distinct meanings."""

from datetime import datetime, timezone
from pydantic import AwareDatetime
from .provenance import ProvenanceCreate, ProvenanceResponse, EvidenceOrigin
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .enums import EntityLinkState
from .missing import MISSING, MissingType, is_missing


class EntityLinkCreate(ProvenanceCreate):
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


class EntityLinkResponse(ProvenanceResponse):
    last_touched_at: AwareDatetime | None = None
    last_touched_by_user_id: uuid.UUID | None = None
    last_touched_by_api_key_id: uuid.UUID | None = None
    entity_link_state: EntityLinkState | None = None
    entity_link_verified_by_user_id: uuid.UUID | None = None
    entity_link_verified_at: datetime | None = None


class EntityLinkFilter(BaseModel):
    evidence_origin: list[EvidenceOrigin] | MissingType = MISSING
    evidence_library: list[str] | MissingType = MISSING
    evidence_source_id: list[uuid.UUID] | MissingType = MISSING
    document_source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Internal registered document source IDs; constrain the same annotation to direct evidence or pages in that library/document."
    )
    evidence_touched_from: AwareDatetime | MissingType = MISSING
    evidence_touched_to: AwareDatetime | MissingType = MISSING
    evidence_touched_by_user_id: list[uuid.UUID] | MissingType = MISSING
    evidence_touched_by_api_key_id: list[uuid.UUID] | MissingType = MISSING

    def evidence_values(self):
        return {name: getattr(self, name) for name in EntityLinkFilter.model_fields if name != "entity_link_state"}

    @model_validator(mode="after")
    def validate_evidence_range(self):
        for name in ("evidence_touched_from", "evidence_touched_to"):
            value = getattr(self, name)
            if not is_missing(value):
                setattr(self, name, value.astimezone(timezone.utc))
        if (not is_missing(self.evidence_touched_from) and not is_missing(self.evidence_touched_to)
                and self.evidence_touched_from > self.evidence_touched_to):
            raise ValueError("evidence_touched_from must be before or equal to evidence_touched_to")
        return self

    @field_validator("evidence_origin", "evidence_library", "evidence_source_id", "document_source_id",
                     "evidence_touched_by_user_id", "evidence_touched_by_api_key_id")
    @classmethod
    def normalize_evidence_values(cls, value):
        if is_missing(value):
            return value
        if not value or any(isinstance(item, str) and not item.strip() for item in value):
            raise ValueError("Evidence selections must be nonempty")
        return sorted(set(value))

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
