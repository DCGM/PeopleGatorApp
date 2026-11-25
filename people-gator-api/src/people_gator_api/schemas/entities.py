"""Pydantic schemas for entity and annotation endpoints."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    model_validator,
    Field,
    field_validator,
)
from people_gator_api.schemas.entity_links import SharedFilter, EntityLinkStats
from people_gator_api.settings import settings
from people_gator_api.schemas.entity_counts import EntityCountFilter
from people_gator_api.schemas.sorting import EntitySortField, PersonSortField, SortableRequest
from people_gator_api.schemas.common import (
    CreationMetadata,
    TouchMetadata,
    GenericListRequest,
    GenericListResponse,
    ListFilterBase,
)
from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.missing import MISSING, MissingType, is_missing, missing_to_none

# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

MAX_ENTITY_BATCH_SIZE = settings.batch.max_entity_batch_size

PERSON_NAME_FIELDS = ("first_name", "middle_names", "surname")
PERSON_FIELDS = (*PERSON_NAME_FIELDS, "birth_date", "death_date")
PERSON_DATES_MESSAGE = "death_date must not be earlier than birth_date"


def normalize_person_name(value: str | None | MissingType) -> str | None | MissingType:
    """Collapse repeated and surrounding whitespace; a blank name clears the field."""
    if isinstance(value, str):
        return " ".join(value.split()) or None
    return value


def validate_life_dates(birth_date: date | None, death_date: date | None) -> None:
    """Reject a death date before the birth date when both are known."""
    if birth_date is not None and death_date is not None and death_date < birth_date:
        raise ValueError(PERSON_DATES_MESSAGE)


class PersonFields(BaseModel):
    """Optional structured person fields; omit preserves and null clears them."""

    first_name: str | None | MissingType = Field(
        default=MISSING, description="Person only: given name."
    )
    middle_names: str | None | MissingType = Field(
        default=MISSING,
        description="Person only: space-separated middle names; repeated and surrounding whitespace is normalized.",
    )
    surname: str | None | MissingType = Field(
        default=MISSING, description="Person only: family name."
    )
    birth_date: date | None | MissingType = Field(
        default=MISSING, description="Person only: full date of birth (YYYY-MM-DD)."
    )
    death_date: date | None | MissingType = Field(
        default=MISSING,
        description="Person only: full date of death (YYYY-MM-DD); not earlier than birth_date.",
    )

    _normalize_names = field_validator(*PERSON_NAME_FIELDS)(
        classmethod(lambda cls, value: normalize_person_name(value))
    )

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        validate_life_dates(missing_to_none(self.birth_date), missing_to_none(self.death_date))
        return self

    def person_values(self) -> dict[str, object]:
        """Person fields present in the request, including explicit nulls."""
        return {name: value for name in PERSON_FIELDS if not is_missing(value := getattr(self, name))}


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


def entity_replacement(payload: EntityCreateRequest) -> EntityPatchRequest:
    """Patch that sets every replaceable field, clearing omitted optional ones.

    A generic payload (from a typed person request) also replaces the person
    fields; a shared ``EntityCreateRequest`` leaves them unchanged. The portrait
    selection is not part of the payload, so it is left unchanged.
    """
    shared = dict(
        name=payload.name,
        aliases=missing_to_none(payload.aliases) or [],
        description=missing_to_none(payload.description),
        short_description=missing_to_none(payload.short_description),
        wikidata_id=missing_to_none(payload.wikidata_id),
        nlcr_authority_id=missing_to_none(payload.nlcr_authority_id),
    )
    if isinstance(payload, PersonFields):
        return GenericEntityPatchRequest(
            **shared, **{name: missing_to_none(getattr(payload, name)) for name in PERSON_FIELDS}
        )
    return EntityPatchRequest(**shared)


class EntityPatchBatchItem(EntityPatchRequest):
    """An item representing a single entity patch operation in a batch."""

    entity_id: uuid.UUID = Field(
        description="The unique identifier of the entity to be patched."
    )


type EntityBatchPatchRequest = Annotated[
    list[EntityPatchBatchItem], Field(max_length=MAX_ENTITY_BATCH_SIZE)
]


class EntityResponse(CreationMetadata, TouchMetadata):
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


EntityListResponse = GenericListResponse[EntityResponse]


class EntityFilterBase(ListFilterBase, SharedFilter, EntityCountFilter):
    """\
    Filter criteria shared by entity and typed person lists.
    Every field is optional and can be used to narrow down the results.
    Filter fields are combined using logical AND.
    Lists of criteria in each field are combined using logical OR.\
    """

    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="The unique identifiers of the entities."
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


class EntityListFilter(EntityFilterBase):
    """\
    Filter criteria for listing entities.
    Every field is optional and can be used to narrow down the results.
    Filter fields are combined using logical AND.
    Lists of criteria in each field are combined using logical OR.\
    """

    entity_type: list[EntityType] | MissingType = Field(
        default=MISSING, description="The exact type of the entity."
    )


class EntityListRequest(GenericListRequest, SortableRequest[EntitySortField]):
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



# ---------------------------------------------------------------------------
# Person subtype (#123)
#
# Like sources, entities have one repository and generic schemas carrying every
# subtype field. The generic entity routes expose only the shared fields; the
# typed person routes use the Person* schemas, which convert with to_generic()
# and from_generic().
# ---------------------------------------------------------------------------


class PersonResponseFields(BaseModel):
    """Person subtype values; null means unknown."""

    first_name: str | None = Field(default=None, description="Given name.")
    middle_names: str | None = Field(default=None, description="Space-separated middle names.")
    surname: str | None = Field(default=None, description="Family name.")
    birth_date: date | None = Field(default=None, description="Date of birth.")
    death_date: date | None = Field(default=None, description="Date of death.")


class LifeDateFilter(BaseModel):
    """Inclusive person life-date ranges; unknown dates never match."""

    birth_date_from: date | MissingType = Field(
        default=MISSING,
        description="Inclusive earliest birth date; excludes unknown birth dates.",
    )
    birth_date_to: date | MissingType = Field(
        default=MISSING,
        description="Inclusive latest birth date; excludes unknown birth dates.",
    )
    death_date_from: date | MissingType = Field(
        default=MISSING,
        description="Inclusive earliest death date; excludes unknown death dates.",
    )
    death_date_to: date | MissingType = Field(
        default=MISSING,
        description="Inclusive latest death date; excludes unknown death dates.",
    )

    @model_validator(mode="after")
    def validate_life_date_ranges(self) -> Self:
        for prefix in ("birth_date", "death_date"):
            lower = missing_to_none(getattr(self, f"{prefix}_from"))
            upper = missing_to_none(getattr(self, f"{prefix}_to"))
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{prefix}_from must not be later than {prefix}_to")
        return self


def person_values_of(model: BaseModel | None) -> dict[str, object]:
    """Person fields present in a generic or typed request; none for shared ones."""
    return model.person_values() if isinstance(model, PersonFields) else {}


class GenericEntityCreateRequest(EntityCreateRequest, PersonFields):
    """Repository create/replace payload: shared fields plus subtype fields."""

    @model_validator(mode="after")
    def validate_person_fields(self) -> Self:
        if self.entity_type != EntityType.person and any(
            value is not None for value in self.person_values().values()
        ):
            raise ValueError("person fields require entity_type person")
        return self


class GenericEntityPatchRequest(EntityPatchRequest, PersonFields):
    """Repository patch payload: shared fields plus subtype fields."""


class GenericEntityPatchBatchItem(EntityPatchBatchItem, PersonFields):
    """Repository batch patch item with subtype fields."""


class GenericEntityResponse(EntityResponse, PersonResponseFields):
    """Repository record with every subtype field; generic routes expose the shared ones."""


GenericEntityListResponse = GenericListResponse[GenericEntityResponse]


class GenericEntityListFilter(EntityListFilter, LifeDateFilter):
    """Repository filter: shared entity criteria plus subtype criteria."""


class GenericEntityListRequest(GenericListRequest, SortableRequest[PersonSortField]):
    """Repository list request accepting subtype filters and sorts."""

    filter_: GenericEntityListFilter | MissingType = Field(default=MISSING)


class GenericEntityMergeTargetPatch(EntityMergeTargetPatch, PersonFields):
    """Repository merge target patch with subtype fields."""


class PersonCreateRequest(GenericEntityCreateRequest):
    """Request body for creating or replacing a person."""

    entity_type: Literal[EntityType.person] = Field(
        default=EntityType.person, description="Always person."
    )

    def to_generic(self) -> GenericEntityCreateRequest:
        return GenericEntityCreateRequest.model_validate(self.model_dump())


type PersonBatchCreateRequest = Annotated[
    list[PersonCreateRequest], Field(max_length=MAX_ENTITY_BATCH_SIZE)
]


class PersonPatchRequest(GenericEntityPatchRequest):
    """Request body for patching a person; omit preserves and null clears."""

    def to_generic(self) -> GenericEntityPatchRequest:
        return GenericEntityPatchRequest.model_validate(self.model_dump())


class PersonPatchBatchItem(PersonPatchRequest):
    """A single person patch operation in a batch."""

    entity_id: uuid.UUID = Field(description="The unique identifier of the person to patch.")

    def to_generic(self) -> GenericEntityPatchBatchItem:  # type: ignore[override]
        return GenericEntityPatchBatchItem.model_validate(self.model_dump())


type PersonBatchPatchRequest = Annotated[
    list[PersonPatchBatchItem], Field(max_length=MAX_ENTITY_BATCH_SIZE)
]


class PersonResponse(EntityResponse, PersonResponseFields):
    """A single person record."""

    @classmethod
    def from_generic(cls, generic: EntityResponse) -> PersonResponse:
        if generic.entity_type != EntityType.person:
            raise ValueError(f"entity {generic.entity_id} is not a person")
        return cls.model_validate(generic.model_dump())


PersonListResponse = GenericListResponse[PersonResponse]


class PersonListFilter(EntityFilterBase, LifeDateFilter):
    """\
    Filter criteria for listing people.
    Every field is optional and can be used to narrow down the results.
    Filter fields are combined using logical AND.
    Lists of criteria in each field are combined using logical OR.\
    """

    def to_generic(self) -> GenericEntityListFilter:
        return GenericEntityListFilter.model_validate(
            {**self.model_dump(), "entity_type": [EntityType.person]}
        )


class PersonListRequest(GenericListRequest, SortableRequest[PersonSortField]):
    """Request for listing people with optional filters and sorting."""

    filter_: PersonListFilter | MissingType = Field(
        default=MISSING, description="The filter criteria to select people."
    )

    def to_generic(self) -> GenericEntityListRequest:
        filter_ = missing_to_none(self.filter_)
        return GenericEntityListRequest(
            limit=self.limit,
            return_total_count=self.return_total_count,
            cursor=self.cursor,
            sort=self.sort,
            sort_direction=self.sort_direction,
            filter_=(filter_ or PersonListFilter()).to_generic(),
        )


class PersonMergeFromRequest(EntityMergeFromRequest, PersonFields):
    """Merge one person into the person in the URL; the target keeps its person fields unless set."""

    def to_generic(self) -> GenericEntityMergeTargetPatch:
        return GenericEntityMergeTargetPatch.model_validate(
            self.model_dump(exclude={"source_entity_id"})
        )


class PersonMergeBatchRequest(EntityMergeBatchRequest, PersonFields):
    """Merge people into the person in the URL; the target keeps its person fields unless set."""

    def to_generic(self) -> GenericEntityMergeTargetPatch:
        return GenericEntityMergeTargetPatch.model_validate(
            self.model_dump(exclude={"source_entity_ids"})
        )


class PersonMergeBatchResponse(BaseModel):
    """Result of merging and deleting source people."""

    source_entity_ids: list[uuid.UUID]
    target_entity_id: uuid.UUID
    faces_reassigned: int = Field(ge=0)
    text_mentions_reassigned: int = Field(ge=0)
    merged_entity: PersonResponse

    @classmethod
    def from_generic(cls, generic: EntityMergeBatchResponse) -> PersonMergeBatchResponse:
        return cls(
            **generic.model_dump(exclude={"merged_entity"}),
            merged_entity=PersonResponse.from_generic(generic.merged_entity),
        )


class PersonMergeResponse(BaseModel):
    """Result of merging and deleting one source person."""

    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    faces_reassigned: int = Field(ge=0)
    text_mentions_reassigned: int = Field(ge=0)
    merged_entity: PersonResponse

    @classmethod
    def from_generic(cls, generic: EntityMergeResponse) -> PersonMergeResponse:
        return cls(
            **generic.model_dump(exclude={"merged_entity"}),
            merged_entity=PersonResponse.from_generic(generic.merged_entity),
        )


__all__ = [
    "MAX_ENTITY_BATCH_SIZE",
    "EntityFilterBase",
    "GenericEntityCreateRequest",
    "GenericEntityListFilter",
    "GenericEntityListRequest",
    "GenericEntityListResponse",
    "GenericEntityMergeTargetPatch",
    "GenericEntityPatchBatchItem",
    "GenericEntityPatchRequest",
    "GenericEntityResponse",
    "LifeDateFilter",
    "PersonBatchCreateRequest",
    "PersonBatchPatchRequest",
    "PersonCreateRequest",
    "PersonListFilter",
    "PersonListRequest",
    "PersonListResponse",
    "PersonMergeBatchRequest",
    "PersonMergeBatchResponse",
    "PersonMergeFromRequest",
    "PersonMergeResponse",
    "PersonPatchBatchItem",
    "PersonPatchRequest",
    "PersonResponse",
    "PersonResponseFields",
    "person_values_of",
    "PERSON_FIELDS",
    "PERSON_DATES_MESSAGE",
    "PersonFields",
    "normalize_person_name",
    "validate_life_dates",
    "EntityCreateRequest",
    "EntityBatchCreateRequest",
    "EntityPatchRequest",
    "entity_replacement",
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
