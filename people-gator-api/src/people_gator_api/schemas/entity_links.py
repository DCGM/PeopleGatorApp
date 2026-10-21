"""Shared annotation link schemas. Omission and null have distinct meanings."""

from datetime import datetime, timezone
from pydantic import AwareDatetime
from .creation import CreationMetadata
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


class EntityLinkResponse(CreationMetadata):
    last_touched_at: AwareDatetime | None = None
    last_touched_by_user_id: uuid.UUID | None = None
    last_touched_by_api_key_id: uuid.UUID | None = None
    entity_link_state: EntityLinkState | None = None
    entity_link_verified_by_user_id: uuid.UUID | None = None
    entity_link_verified_at: datetime | None = None


LEGACY_FILTER_REPLACEMENTS = {
    "evidence_library": "filter.library",
    "evidence_source_id": "filter.page_source_id",
    "evidence_touched_from": "filter.last_touched_from",
    "evidence_touched_to": "filter.last_touched_to",
    "evidence_touched_by_user_id": "filter.last_touched_by_user_id",
    "evidence_touched_by_api_key_id": "filter.last_touched_by_api_key_id",
}
"""Removed #31 parameters. Their replacements describe the filtered record itself."""


class SharedFilter(BaseModel):
    """Canonical criteria shared by documents, pages, entities, faces and mentions.

    Source scope uses actual library/document/page relationships. Last-touch
    criteria describe the latest recorded change of each returned record, never
    its owner, creator/importer, verifier or an earlier editor. Different fields
    combine with AND and repeated values with OR.
    """

    # Removed #31 names must fail loudly instead of being ignored by callers.
    model_config = ConfigDict(extra="forbid")

    entity_link_state: list[EntityLinkState] | MissingType = Field(
        default=MISSING,
        description="Assignment states of the linked faces/mentions; the same annotation must satisfy the selected source scope. Omit to include unassigned annotations.",
    )
    library: list[str] | MissingType = Field(
        default=MISSING,
        description="Libraries of the record's source: documents/pages in the library, or faces/mentions/entities linked through a source in it.",
    )
    document_source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Internal registered document source UUIDs (not archive IDs). A document scope includes its registered pages in the same library/archive document.",
    )
    page_source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Internal page source UUIDs. Documents match the registered document containing the page; other records match links on that page.",
    )
    last_touched_from: AwareDatetime | MissingType = Field(
        default=MISSING, description="Inclusive, timezone-aware lower bound of the record's latest recorded change."
    )
    last_touched_to: AwareDatetime | MissingType = Field(
        default=MISSING, description="Inclusive, timezone-aware upper bound of the record's latest recorded change."
    )
    last_touched_by_user_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Users who made the record's latest recorded change; unknown history never matches."
    )
    last_touched_by_api_key_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Registered API keys used for the record's latest recorded change."
    )

    def shared_values(self) -> dict:
        return {name: getattr(self, name) for name in SharedFilter.model_fields}

    @model_validator(mode="after")
    def validate_touch_range(self):
        for name in ("last_touched_from", "last_touched_to"):
            value = getattr(self, name)
            if not is_missing(value):
                setattr(self, name, value.astimezone(timezone.utc))
        if (not is_missing(self.last_touched_from) and not is_missing(self.last_touched_to)
                and self.last_touched_from > self.last_touched_to):
            raise ValueError("last_touched_from must be before or equal to last_touched_to")
        return self

    @field_validator("library", "document_source_id", "page_source_id",
                     "last_touched_by_user_id", "last_touched_by_api_key_id")
    @classmethod
    def normalize_selections(cls, value):
        if is_missing(value):
            return value
        if not value or any(isinstance(item, str) and not item.strip() for item in value):
            raise ValueError("Filter selections must be nonempty")
        return sorted(set(value))

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
