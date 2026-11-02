"""Resource-specific audit lists and typed historical object states.

Persisted snapshots retain their original data independently of live records.
Validation aliases translate storage names to the public object identifiers.
"""

import json
from typing import Annotated, Literal
from uuid import UUID
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from people_gator_api.schemas.common import BoundingBox
from people_gator_api.schemas.enums import EntityLinkState, SourceKind


class HistoricalActivity(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: int = Field(ge=1)
    last_touched_at: AwareDatetime | None = None
    last_touched_by_user_id: UUID | None = None
    last_touched_by_api_key_id: UUID | None = None


class HistoricalCreation(HistoricalActivity):
    created_at: AwareDatetime | None = None
    created_by_user_id: UUID | None = None
    created_by_api_key_id: UUID | None = None


class EntityAliasAuditState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    alias_id: UUID = Field(validation_alias="id")
    entity_id: UUID
    name: str
    name_normalized: str | None = None
    search_document: str | None = None


class EntityAuditState(HistoricalCreation):
    entity_id: UUID = Field(validation_alias="id")
    user_id: UUID
    entity_type: str | None = Field(validation_alias="kind")
    name: str | None
    name_normalized: str | None = None
    description: str | None = None
    short_description: str | None = None
    wikidata_id: str | None = None
    nlcr_authority_id: str | None = None
    thumbnail_face_id: UUID | None = None
    thumbnail_mode: Literal["automatic", "manual"]
    aliases: list[EntityAliasAuditState]
    search_document: str | None = None


class AnnotationAuditState(HistoricalCreation):
    source_id: UUID
    entity_id: UUID | None
    entity_link_state: EntityLinkState | None
    entity_link_verified_by_user_id: UUID | None = None
    entity_link_verified_at: AwareDatetime | None = None


class FaceEmbeddingAuditState(BaseModel):
    face_id: UUID
    model_id: str
    embedding: list[float]

    @field_validator("embedding", mode="before")
    @classmethod
    def decode_stored_vector(cls, value):
        # PostgreSQL's vector JSON representation is a numeric JSON array string.
        return json.loads(value) if isinstance(value, str) else value


class FaceAuditState(AnnotationAuditState):
    detection_id: UUID = Field(validation_alias="id")
    occurrence_type: Literal["face"]
    user_id: UUID
    identifier: str | None
    confidence: float
    bounding_box: BoundingBox = Field(validation_alias="roi")
    keypoints: list[tuple[float, float]]
    keypoint_types: list[str]
    embeddings: list[FaceEmbeddingAuditState]


class TextMentionAuditState(AnnotationAuditState):
    mention_id: UUID = Field(validation_alias="id")
    name: str = Field(validation_alias="mention")
    mention_normalized: str | None = None
    context: str | None


class SourceAuditStateBase(HistoricalActivity):
    source_id: UUID = Field(validation_alias="id")
    url: str


class PageAuditState(SourceAuditStateBase):
    source_type: Literal["page"]
    library: str
    document_id: UUID
    page_id: UUID
    page_number: int | None


class DocumentAuditState(SourceAuditStateBase):
    source_type: Literal["document"]
    library: str
    document_id: UUID
    name: str | None
    name_normalized: str | None = None


class ImageAuditState(SourceAuditStateBase):
    source_type: Literal["image"]


type SourceAuditState = Annotated[
    PageAuditState | DocumentAuditState | ImageAuditState,
    Field(discriminator="source_type"),
]


class AuditItemMetadata(BaseModel):
    version: int = Field(ge=1)
    changed_at: AwareDatetime
    actor_user_id: UUID
    actor_api_key_id: UUID | None
    deleted: bool


class EntityAuditItem(AuditItemMetadata):
    entity_id: UUID
    state: EntityAuditState


class FaceAuditItem(AuditItemMetadata):
    detection_id: UUID
    state: FaceAuditState


class TextMentionAuditItem(AuditItemMetadata):
    mention_id: UUID
    state: TextMentionAuditState


class SourceAuditItem(AuditItemMetadata):
    source_id: UUID
    state: SourceAuditState


class AuditListOptions(BaseModel):
    """AND between criteria; OR between repeated IDs within one criterion."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    actor_user_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.actor_user_id"
    )
    since: AwareDatetime | None = Field(default=None, alias="filter.since")
    until: AwareDatetime | None = Field(default=None, alias="filter.until")
    version_min: int | None = Field(default=None, ge=1, alias="filter.version_min")
    version_max: int | None = Field(default=None, ge=1, alias="filter.version_max")
    deleted: bool | None = Field(default=None, alias="filter.deleted")
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


class EntityAuditListRequest(AuditListOptions):
    entity_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.entity_id"
    )


class FaceAuditListRequest(AuditListOptions):
    detection_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.detection_id"
    )
    entity_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.entity_id"
    )
    source_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.source_id"
    )


class TextMentionAuditListRequest(AuditListOptions):
    mention_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.mention_id"
    )
    entity_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.entity_id"
    )
    source_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.source_id"
    )


class SourceAuditListRequest(AuditListOptions):
    source_type: list[SourceKind] | None = Field(
        default=None, min_length=1, alias="filter.source_type"
    )
    library: list[str] | None = Field(
        default=None, min_length=1, alias="filter.library"
    )
    document_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.document_id"
    )
    page_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.page_id"
    )
    source_id: list[UUID] | None = Field(
        default=None, min_length=1, alias="filter.source_id"
    )


class TypedAuditListResponse[T: AuditItemMetadata](BaseModel):
    items: list[T]
    total_count: int
    limit: int
    offset: int


class EntityAuditListResponse(TypedAuditListResponse[EntityAuditItem]):
    pass


class FaceAuditListResponse(TypedAuditListResponse[FaceAuditItem]):
    pass


class TextMentionAuditListResponse(TypedAuditListResponse[TextMentionAuditItem]):
    pass


class SourceAuditListResponse(TypedAuditListResponse[SourceAuditItem]):
    pass
