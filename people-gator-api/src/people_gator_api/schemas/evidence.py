import uuid

from pydantic import BaseModel

from people_gator_api.db.models.enums import EvidenceType


class DerivedEvidenceIngestRequest(BaseModel):
    evidence_id: uuid.UUID | None = None
    source_id: uuid.UUID
    source_path: str | None = None
    evidence_type: EvidenceType
    schema_version: str
    producer_id: uuid.UUID
    content_hash: str
    produced_metadata: dict[str, object]


class AuthorityEvidenceIngestRequest(BaseModel):
    evidence_id: uuid.UUID | None = None
    source_id: uuid.UUID
    source_path: str | None = None
    evidence_type: EvidenceType
    schema_version: str
    producer_id: uuid.UUID
    content_hash: str
    metadata: dict[str, object]


class BulkDerivedEvidenceRequest(BaseModel):
    items: list[DerivedEvidenceIngestRequest] = []


class BulkAuthorityEvidenceRequest(BaseModel):
    items: list[AuthorityEvidenceIngestRequest] = []


class EvidenceIngestResult(BaseModel):
    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    status: str


class EvidenceReviseRequest(BaseModel):
    evidence_version_id: uuid.UUID
    revised_metadata: dict[str, object]


class EvidenceResponse(BaseModel):
    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    source_id: uuid.UUID
    source_path: str | None
    evidence_type: EvidenceType
    schema_version: str
    content_hash: str
    is_deleted: bool
    is_stale: bool
