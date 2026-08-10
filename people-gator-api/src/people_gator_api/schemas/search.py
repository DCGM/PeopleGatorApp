"""Pydantic schemas for search and search endpoints."""

import uuid

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
)
from people_gator_api.schemas.common import GenericListResponse

# ---------------------------------------------------------------------------
# Search result type
# ---------------------------------------------------------------------------


class EntitySearchResult(BaseModel):
    """A single result from a nearest-neighbour search over an annotation collection."""

    entity_id: uuid.UUID = Field(..., description="The entity ID of the annotation.")
    entity_type: str = Field(..., description="The entity type of the annotation.")
    name: str = Field(..., description="The name of the annotation.")
    description: str = Field(..., description="The description of the annotation.")
    short_description: str = Field(
        ..., description="The short description of the annotation."
    )
    aliases: list[str] = Field(..., description="The aliases of the annotation.")
    matching_score: float = Field(
        ..., description="The matching score of the annotation."
    )


class SearchResultListResponse(GenericListResponse[EntitySearchResult]):
    """A paginated list of search results."""

    items: list[EntitySearchResult]


# ---------------------------------------------------------------------------
# Search request and response
# ---------------------------------------------------------------------------


class SearchQuery(BaseModel):
    """Typed query signals the caller wants to find matches for."""

    name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("name", "query_name"),
        description="The name to search for.",
    )
    limit: int = Field(
        default=20,
        validation_alias=AliasChoices("limit", "query_limit"),
        description="The maximum number of results to return.",
    )
    after_id: uuid.UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("after_id", "query_after_id"),
        description="The ID of the last result from the previous page of results.",
    )
