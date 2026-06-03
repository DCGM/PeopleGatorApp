import uuid

from pydantic import BaseModel

from people_gator_api.db.models.enums import ProcessingStatus, ProviderType, ResolverType


class SourceSchemaCreateRequest(BaseModel):
    schema_name: str
    resolver_type: ResolverType
    resolver_config: dict[str, object]


class SourceSchemaResponse(BaseModel):
    schema_name: str
    resolver_type: ResolverType
    resolver_config: dict[str, object]


class SourceCreateRequest(BaseModel):
    source_schema_name: str
    source: str
    provider: ProviderType
    content_hash: str
    metadata: dict[str, object] | None = None


class SourceResponse(BaseModel):
    source_id: uuid.UUID
    source_schema_name: str
    source: str
    provider: ProviderType
    content_hash: str | None
    metadata: dict[str, object] | None


class SourceProcessingEntry(BaseModel):
    producer_id: uuid.UUID
    processing_status: ProcessingStatus
    started_at: str | None
    completed_at: str | None
    error_message: str | None


class SourceProcessingResponse(BaseModel):
    source_id: uuid.UUID
    processing: list[SourceProcessingEntry]
