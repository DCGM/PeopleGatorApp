"""Pydantic schemas for text mention endpoints."""

import uuid

from pydantic import BaseModel, Field

from people_gator_api.schemas.common import GenericListResponse


class TextMentionCreateRequest(BaseModel):
    """Request body for recording an entity name found in a source."""

    name: str = Field(min_length=1)
    context: str | None = None
    entity_id: uuid.UUID
    source_id: uuid.UUID


class TextMentionResponse(BaseModel):
    """A single mention of an entity name in a text source."""

    mention_id: uuid.UUID
    name: str
    context: str | None
    entity_id: uuid.UUID
    source_id: uuid.UUID


class TextMentionListResponse(GenericListResponse[TextMentionResponse]):
    """A paginated list of text mentions."""

    items: list[TextMentionResponse]


class TextMentionEntityPatchRequest(BaseModel):
    """Request body for assigning a mention to another entity."""

    entity_id: uuid.UUID
