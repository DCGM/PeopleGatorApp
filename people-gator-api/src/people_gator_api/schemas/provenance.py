"""Recorded creation/import provenance, independent of assignment and edits."""
from enum import StrEnum
import uuid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, AwareDatetime, model_validator


class EvidenceOrigin(StrEnum):
    automatic = "automatic"
    manual = "manual"
    authority = "authority"
    unknown = "unknown"


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: EvidenceOrigin = EvidenceOrigin.unknown
    source_name: str | None = Field(default=None, min_length=1)
    reference_id: str | None = Field(default=None, min_length=1)
    reference_url: HttpUrl | None = None

    @model_validator(mode="after")
    def authority_reference(self):
        if self.origin == EvidenceOrigin.authority and not (
            self.source_name and self.reference_id and self.reference_url
        ):
            raise ValueError("Authority provenance requires a source name, identifier and HTTP(S) reference")
        return self


class ProvenanceCreate(BaseModel):
    provenance: Provenance = Field(default_factory=Provenance)


class ProvenanceResponse(ProvenanceCreate):
    created_at: AwareDatetime | None = None
    created_by_user_id: uuid.UUID | None = None
    created_by_api_key_id: uuid.UUID | None = None
