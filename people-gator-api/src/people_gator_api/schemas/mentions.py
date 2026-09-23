"""Pydantic schemas for text mention endpoints."""

import uuid

from pydantic import BaseModel, Field
from typing import Annotated

from people_gator_api.schemas.common import (
    GenericListRequest,
    GenericListResponse,
    ListFilterBase,
)
from people_gator_api.schemas.missing import MISSING, MissingType

# ---------------------------------------------------------------------------
# Text mention schemas
# ---------------------------------------------------------------------------


MAX_TEXT_MENTION_BATCH_SIZE = 1_000


class TextMentionCreateRequest(BaseModel):
    """Request body for recording an entity name found in a source."""

    name: str = Field(
        min_length=1,
        description="The name of the entity being mentioned."
    )
    context: str | None = Field(
        default=None,
        description="The context in which the entity name was found.",
    )
    entity_id: uuid.UUID = Field(
        description="The ID of the entity being mentioned.",
    )
    source_id: uuid.UUID = Field(
        description="The ID of the source where the entity name was found.",
    )


type TextMentionsBatchCreateRequest = Annotated[
    list[TextMentionCreateRequest], Field(max_length=MAX_TEXT_MENTION_BATCH_SIZE)
]


class TextMentionPatchRequest(BaseModel):
    """Assign a mention to an entity, or unassign it with null."""

    entity_id: uuid.UUID | None


class TextMentionPatchBatchItem(TextMentionPatchRequest):
    """Request body for assigning a mention to another entity in a batch."""
    mention_id: uuid.UUID


type TextMentionsBatchPatchRequest = Annotated[
    list[TextMentionPatchBatchItem], Field(max_length=MAX_TEXT_MENTION_BATCH_SIZE)
]


class TextMentionResponse(BaseModel):
    """A single mention of an entity name in a text source."""

    mention_id: uuid.UUID
    name: str
    context: str | None
    entity_id: uuid.UUID | None
    source_id: uuid.UUID


class TextMentionListFilter(ListFilterBase):
    """Filter criteria for listing text mentions.
    Every field is optional and can be used to narrow down the results.
    Filter fields are combined using logical AND.
    Lists of criteria in each field are combined using logical OR.
    """
    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING, description="Filter by entity IDs."
    )
    source_id: list[uuid.UUID] | MissingType = Field(default=MISSING, description="Filter by source IDs.")


class TextMentionListRequest(GenericListRequest):
    """Request body for listing text mentions."""
    filter_: TextMentionListFilter | MissingType = Field(default=MISSING)


class TextMentionListResponse(GenericListResponse[TextMentionResponse]):
    """A paginated list of text mentions."""

    items: list[TextMentionResponse]


__all__ = [
    "MAX_TEXT_MENTION_BATCH_SIZE",
    "TextMentionCreateRequest",
    "TextMentionsBatchCreateRequest",
    "TextMentionPatchRequest",
    "TextMentionPatchBatchItem",
    "TextMentionsBatchPatchRequest",
    "TextMentionResponse",
    "TextMentionListFilter",
    "TextMentionListRequest",
    "TextMentionListResponse",
]
