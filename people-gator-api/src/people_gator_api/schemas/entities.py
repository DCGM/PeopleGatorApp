"""Pydantic schemas for entity and annotation endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Self, Literal
from datetime import timezone

from pydantic import (
    BaseModel,
    AwareDatetime,
    model_validator,
    Field,
    field_validator,
)
from people_gator_api.schemas.entity_links import EntityLinkFilter, EntityLinkStats
from people_gator_api.settings import settings
from people_gator_api.schemas.common import (
    GenericListRequest,
    GenericListResponse,
    ListFilterBase,
)
from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.missing import MISSING, MissingType

# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

MAX_ENTITY_BATCH_SIZE = settings.batch.max_entity_batch_size


from .creation import CreationMetadata


class EntityCreateRequest(BaseModel):
    """Request body for creating a new entity."""

    entity_type: EntityType = Field(
        description="The type of the entity. Immutable after creation."
    )
    name: str = Field(description="The name of the entity.")
    description: str | None | MissingType = Field(
        default=MISSING, description="A detailed description of the entity."
    )
    short_description: str | None | MissingType = Field(
        default=MISSING, description="A brief description of the entity."
    )
    aliases: list[str] | MissingType = Field(
        default=MISSING, description="Alternative names or aliases for the entity."
    )
    wikidata_id: str | None | MissingType = Field(
        default=MISSING, description="The Wikidata identifier for the entity."
    )
    nlcr_authority_id: str | None | MissingType = Field(
        default=MISSING, description="The NLCR authority identifier for the entity."
    )

    @field_validator("aliases")
    @classmethod
    def validate_aliases(
        cls, aliases: list[str] | MissingType
    ) -> list[str] | MissingType:
        if isinstance(aliases, list) and len(aliases) != len(set(aliases)):
            raise ValueError("aliases must be unique")
        return aliases


type EntityBatchCreateRequest = Annotated[
    list[EntityCreateRequest], Field(max_length=MAX_ENTITY_BATCH_SIZE)
]


class EntityPatchRequest(BaseModel):
    """Request body for patching an existing entity."""

    thumbnail_face_id: uuid.UUID | None | MissingType = Field(
        default=MISSING,
        description="Person portrait selection: omit to preserve; a linked face UUID selects it manually; null returns to automatic mode. The first assigned face is saved and kept while linked, including on later assignments and identity edits. Resetting a manual choice selects the lowest currently linked face UUID; resetting automatic mode preserves its saved choice.",
    )

    name: str | MissingType = Field(default=MISSING, description="The name of the entity.")
    aliases: list[str] | MissingType = Field(
        default=MISSING, description="Alternative names or aliases for the entity."
    )
    description: str | None | MissingType = Field(
        default=MISSING, description="A detailed description of the entity."
    )
    short_description: str | None | MissingType = Field(
        default=MISSING, description="A brief description of the entity."
    )
    wikidata_id: str | None | MissingType = Field(
        default=MISSING, description="The Wikidata identifier for the entity."
    )
    nlcr_authority_id: str | None | MissingType = Field(
        default=MISSING, description="The NLCR authority identifier for the entity."
    )

    @field_validator("aliases")
    @classmethod
    def validate_aliases(
        cls, aliases: list[str] | MissingType
    ) -> list[str] | MissingType:
        if isinstance(aliases, list) and len(aliases) != len(set(aliases)):
            raise ValueError("aliases must be unique")
        return aliases


class EntityPatchBatchItem(EntityPatchRequest):
    """An item representing a single entity patch operation in a batch."""

    entity_id: uuid.UUID = Field(
        description="The unique identifier of the entity to be patched."
    )


type EntityBatchPatchRequest = Annotated[
    list[EntityPatchBatchItem], Field(max_length=MAX_ENTITY_BATCH_SIZE)
]


class EntityResponse(CreationMetadata):
    """A single entity record."""

    entity_id: uuid.UUID = Field(description="The unique identifier of the entity.")
    entity_type: EntityType = Field(description="The type of the entity.")
    name: str = Field(description="The name of the entity.")
    description: str | None = Field(
        default=None, description="A detailed description of the entity."
    )
    short_description: str | None = Field(
        default=None, description="A brief description of the entity."
    )
    aliases: list[str] | None = Field(
        default=None, description="Alternative names or aliases for the entity."
    )
    wikidata_id: str | None = Field(
        default=None, description="The Wikidata identifier for the entity."
    )
    nlcr_authority_id: str | None = Field(
        default=None, description="The NLCR authority identifier for the entity."
    )
    user_id: uuid.UUID = Field(
        description="The unique identifier of the user who created or owns the entity."
    )


    thumbnail_face_id: uuid.UUID | None = Field(
        default=None, description="Persisted effective portrait face; null means no eligible portrait. Load through authenticated GET /api/v1/faces/{id}/aligned_crop.",
    )
    thumbnail_mode: Literal["automatic", "manual"] = Field(
        default="automatic", description="Selection policy. Automatic with a null thumbnail_face_id means no thumbnail. Non-person entities always have automatic/null.",
    )

    entity_link_stats: EntityLinkStats = Field(default_factory=EntityLinkStats)
    last_touched_at: AwareDatetime | None = None
    last_touched_by_user_id: uuid.UUID | None = None
    last_touched_by_api_key_id: uuid.UUID | None = None


EntityListResponse = GenericListResponse[EntityResponse]


class EntityListFilter(ListFilterBase, EntityLinkFilter):
    """\
    Filter criteria for listing entities.
    Every field is optional and can be used to narrow down the results.
    Filter fields are combined using logical AND.
    Lists of criteria in each field are combined using logical OR.\
    """

    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="The unique identifiers of the entities."
    )
    entity_type: list[EntityType] | MissingType = Field(
        default=MISSING, description="The exact type of the entity."
    )
    wikidata_id: list[str] | MissingType = Field(
        default=MISSING, description="The Wikidata identifier for the entity."
    )
    nlcr_authority_id: list[str] | MissingType = Field(
        default=MISSING, description="The NLCR authority identifier for the entity."
    )
    source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="The source identifiers associated with the entity.",
    )
    detection_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="The detection identifiers associated with the entity.",
    )
    mention_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="The mention identifiers associated with the entity.",
    )
    has_mentions: bool | MissingType = Field(
        default=MISSING, description="Whether the entity has mentions."
    )
    has_detections: bool | MissingType = Field(
        default=MISSING, description="Whether the entity has detections."
    )


    last_touched_from: AwareDatetime | MissingType = Field(
        default=MISSING, description="Inclusive UTC lower bound of the last touch."
    )
    last_touched_to: AwareDatetime | MissingType = Field(
        default=MISSING, description="Inclusive UTC upper bound of the last touch."
    )
    document_source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Internal document source IDs; match faces or mentions on any page."
    )
    last_touched_by_user_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Users responsible for the last touch, independent of entity ownership."
    )
    last_touched_by_api_key_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Registered API keys used for the last touch."
    )

    @model_validator(mode="after")
    def validate_touch_range(self) -> Self:
        from people_gator_api.schemas.missing import is_missing
        for name in ("last_touched_from", "last_touched_to"):
            value = getattr(self, name)
            if not is_missing(value):
                setattr(self, name, value.astimezone(timezone.utc))
        if (not is_missing(self.last_touched_from) and not is_missing(self.last_touched_to)
                and self.last_touched_from > self.last_touched_to):
            raise ValueError("last_touched_from must be before or equal to last_touched_to")
        return self


class EntityListRequest(GenericListRequest):
    """Request body for listing entities with optional filters."""

    filter_: EntityListFilter | MissingType = Field(
        default=MISSING, description="The filter criteria to select entities."
    )


class EntityDeleteManyRequest(BaseModel):
    """Request body for deleting multiple entities by filter criteria."""

    filter: EntityListFilter | MissingType = Field(
        default=MISSING,
        description="The filter criteria to select entities for deletion.",
    )
    limit: int = Field(ge=1, description="The maximum number of entities to delete, selected by entity UUID ascending.")


class EntityDeleteManyResponse(BaseModel):
    """Summary of a bulk entity delete operation."""

    deleted_count: int = Field(ge=0)


class EntityMergeTargetPatch(BaseModel):
    """Optional target fields to update as part of an entity merge."""

    description: str | None | MissingType = Field(
        default=MISSING,
        description="New target description; null clears it and omission preserves it.",
    )
    short_description: str | None | MissingType = Field(
        default=MISSING,
        description="New target short description; null clears it and omission preserves it.",
    )


class EntityMergeFromRequest(EntityMergeTargetPatch):
    """Identify the source to merge into the entity addressed by the URL."""

    source_entity_id: uuid.UUID


class EntityMergeBatchRequest(EntityMergeTargetPatch):
    """Identify the sources to merge into the entity addressed by the URL."""

    source_entity_ids: list[uuid.UUID] = Field(
        min_length=1, max_length=MAX_ENTITY_BATCH_SIZE
    )

    @field_validator("source_entity_ids")
    @classmethod
    def validate_unique_source_ids(cls, source_entity_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(source_entity_ids) != len(set(source_entity_ids)):
            raise ValueError("source_entity_ids must be unique")
        return source_entity_ids


class EntityMergeResponse(BaseModel):
    """Result of merging and deleting a source entity."""

    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    faces_reassigned: int = Field(ge=0)
    text_mentions_reassigned: int = Field(ge=0)
    merged_entity: EntityResponse


class EntityMergeBatchResponse(BaseModel):
    """Result of merging and deleting multiple source entities."""

    source_entity_ids: list[uuid.UUID]
    target_entity_id: uuid.UUID
    faces_reassigned: int = Field(ge=0)
    text_mentions_reassigned: int = Field(ge=0)
    merged_entity: EntityResponse


__all__ = [
    "MAX_ENTITY_BATCH_SIZE",
    "EntityCreateRequest",
    "EntityBatchCreateRequest",
    "EntityPatchRequest",
    "EntityPatchBatchItem",
    "EntityBatchPatchRequest",
    "EntityResponse",
    "EntityListResponse",
    "EntityListFilter",
    "EntityListRequest",
    "EntityDeleteManyRequest",
    "EntityDeleteManyResponse",
    "EntityMergeFromRequest",
    "EntityMergeTargetPatch",
    "EntityMergeResponse",
    "EntityMergeBatchRequest",
    "EntityMergeBatchResponse",
]
