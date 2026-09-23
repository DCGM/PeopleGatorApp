"""Pydantic schemas for entity and annotation endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)
from pydantic.experimental.missing_sentinel import MISSING
from people_gator_api.schemas.common import (
    GenericListRequest,
    GenericListResponse,
    ListFilterBase,
)
from people_gator_api.schemas.enums import EntityType

# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

MAX_ENTITY_BATCH_SIZE = 1_000


class EntityCreateRequest(BaseModel):
    """Request body for creating a new entity."""

    entity_type: EntityType = Field(
        description="The type of the entity. Immutable after creation."
    )
    name: str = Field(description="The name of the entity.")
    description: str | None | MISSING = Field(
        default=MISSING, description="A detailed description of the entity."
    )
    short_description: str | None | MISSING = Field(
        default=MISSING, description="A brief description of the entity."
    )
    aliases: list[str] | MISSING = Field(
        default=MISSING, description="Alternative names or aliases for the entity."
    )
    wikidata_id: str | None | MISSING = Field(
        default=MISSING, description="The Wikidata identifier for the entity."
    )
    nlcr_authority_id: str | None | MISSING = Field(
        default=MISSING, description="The NLCR authority identifier for the entity."
    )

    @field_validator("aliases")
    @classmethod
    def validate_aliases(
        cls, aliases: list[str] | MISSING
    ) -> list[str] | MISSING:
        if isinstance(aliases, list) and len(aliases) != len(set(aliases)):
            raise ValueError("aliases must be unique")
        return aliases


type EntityBatchCreateRequest = Annotated[
    list[EntityCreateRequest], Field(max_length=MAX_ENTITY_BATCH_SIZE)
]


class EntityPatchRequest(BaseModel):
    """Request body for patching an existing entity."""

    name: str | MISSING = Field(default=MISSING, description="The name of the entity.")
    aliases: list[str] | MISSING = Field(
        default=MISSING, description="Alternative names or aliases for the entity."
    )
    description: str | None | MISSING = Field(
        default=MISSING, description="A detailed description of the entity."
    )
    short_description: str | None | MISSING = Field(
        default=MISSING, description="A brief description of the entity."
    )
    wikidata_id: str | None | MISSING = Field(
        default=MISSING, description="The Wikidata identifier for the entity."
    )
    nlcr_authority_id: str | None | MISSING = Field(
        default=MISSING, description="The NLCR authority identifier for the entity."
    )

    @field_validator("aliases")
    @classmethod
    def validate_aliases(
        cls, aliases: list[str] | MISSING
    ) -> list[str] | MISSING:
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


class EntityResponse(BaseModel):
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


EntityListResponse = GenericListResponse[EntityResponse]


class EntityListFilter(ListFilterBase):
    """\
    Filter criteria for listing entities.
    Every field is optional and can be used to narrow down the results.
    Filter fields are combined using logical AND.
    Lists of criteria in each field are combined using logical OR.\
    """

    entity_id: list[uuid.UUID] | MISSING = Field(
        default=MISSING, description="The unique identifiers of the entities."
    )
    entity_type: list[EntityType] | MISSING = Field(
        default=MISSING, description="The exact type of the entity."
    )
    wikidata_id: list[str] | MISSING = Field(
        default=MISSING, description="The Wikidata identifier for the entity."
    )
    nlcr_authority_id: list[str] | MISSING = Field(
        default=MISSING, description="The NLCR authority identifier for the entity."
    )
    source_id: list[uuid.UUID] | MISSING = Field(
        default=MISSING,
        description="The source identifiers associated with the entity.",
    )
    detection_id: list[uuid.UUID] | MISSING = Field(
        default=MISSING,
        description="The detection identifiers associated with the entity.",
    )
    mention_id: list[uuid.UUID] | MISSING = Field(
        default=MISSING,
        description="The mention identifiers associated with the entity.",
    )
    has_mentions: bool | MISSING = Field(
        default=MISSING, description="Whether the entity has mentions."
    )
    has_detections: bool | MISSING = Field(
        default=MISSING, description="Whether the entity has detections."
    )


class EntityListRequest(GenericListRequest):
    """Request body for listing entities with optional filters."""

    filter: EntityListFilter | MISSING = Field(
        default=MISSING, description="The filter criteria to select entities."
    )


class EntityDeleteManyRequest(BaseModel):
    """Request body for deleting multiple entities by filter criteria."""

    filter: EntityListFilter | MISSING = Field(
        default=MISSING,
        description="The filter criteria to select entities for deletion.",
    )
    limit: int = Field(ge=1, description="The maximum number of entities to delete, selected by entity UUID ascending.")


class EntityDeleteManyResponse(BaseModel):
    """Summary of a bulk entity delete operation."""

    deleted_count: int = Field(ge=0)


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
]
