"""Pydantic schemas for entity and annotation endpoints."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from people_gator_api.schemas.common import GenericListResponse
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceEmbeddingModel,
)
from people_gator_api.schemas.sources import SourceDescriptorRequest

# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class EntityCreateRequest(BaseModel):
    """Request body for creating a new entity."""

    entity_type: EntityType | None = None
    name: str | None = None
    description: str | None = None
    short_description: str | None = None
    aliases: list[str] | None = None
    wikidata_id: str | None = None
    nlcr_authority_id: str | None = None
    name_embedding: list[float] | None = None
    fulltext_embedding: list[float] | None = None


class EntityPatchRequest(BaseModel):
    """Request body for patching an existing entity."""

    name: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    short_description: str | None = None
    wikidata_id: str | None = None
    nlcr_authority_id: str | None = None


class EntityResponse(BaseModel):
    """A single entity record."""

    entity_id: uuid.UUID
    entity_type: EntityType | None
    name: str | None
    description: str | None
    short_description: str | None
    aliases: list[str] | None
    wikidata_id: str | None
    nlcr_authority_id: str | None
    user_id: uuid.UUID


class EntityListResponse(GenericListResponse[EntityResponse]):
    """A paginated list of entities."""

    items: list[EntityResponse]


class EntityDeleteManyRequest(BaseModel):
    """Request body for deleting multiple entities by selector."""

    delete_all: bool = False
    entity_type: EntityType | None = None
    entity_ids: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def validate_selector(self) -> EntityDeleteManyRequest:
        has_type = self.entity_type is not None
        has_ids = bool(self.entity_ids)

        if self.delete_all:
            if has_type or has_ids:
                raise ValueError(
                    "When delete_all is true, entity_type and entity_ids must be omitted"
                )
            return self

        if not has_type and not has_ids:
            raise ValueError(
                "Provide at least one selector: delete_all, entity_type, or entity_ids"
            )
        return self


class EntityDeleteManyResponse(BaseModel):
    """Summary of a bulk entity delete operation."""

    mode: Literal["all", "entity_type", "entity_ids"]
    deleted_count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """Face detection bounding box."""

    x: int
    y: int
    width: int
    height: int


class FaceKeypoint(BaseModel):
    """One keypoint of a face detection."""

    type: str
    x: float
    y: float


class FaceCreateRequest(BaseModel):
    """Request body for ingesting a face detection."""

    identifier: str | None = None
    source_id: uuid.UUID | None = None
    source: SourceDescriptorRequest | None = None
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    embedding: list[float] | None = None
    model_identifier: str | None = None
    entity_id: uuid.UUID | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_source_selector(self) -> "FaceCreateRequest":
        has_source_id = self.source_id is not None
        has_source = self.source is not None
        if has_source_id == has_source:
            raise ValueError("provide exactly one of source_id or source")
        return self


class FaceEmbeddingUpdateRequest(BaseModel):
    """Named vector update for an existing face detection."""

    detection_id: uuid.UUID
    embedding: list[float] = Field(min_length=1)
    model_identifier: FaceEmbeddingModel = DEFAULT_FACE_EMBEDDING_MODEL


class FaceEmbeddingBatchUpdateResponse(BaseModel):
    """Summary of a face embedding backfill batch."""

    updated_count: int = Field(ge=0)


class FaceResponse(BaseModel):
    """A single face detection record."""

    detection_id: uuid.UUID
    identifier: str | None = None
    source_id: uuid.UUID
    bounding_box: BoundingBox
    keypoints: list[FaceKeypoint]
    user_id: uuid.UUID
    entity_id: uuid.UUID | None = Field(default=None)
    confidence: float


class FaceListResponse(GenericListResponse[FaceResponse]):
    """A paginated list of face detections."""

    items: list[FaceResponse]


class FaceEntityPatchRequest(BaseModel):
    """Patch body for reassigning a face annotation to a different entity."""

    entity_id: uuid.UUID
