from enum import StrEnum
from typing import Self
import uuid

from pydantic import BaseModel, Field, FiniteFloat, model_validator


class ErrorResponse(BaseModel):
    code: str
    message: str


class GenericActor(BaseModel):
    """A generic actor with an ID and optional name."""
    user_id: uuid.UUID


class GenericListRequest(BaseModel):
    """Request one deterministic page of results.

    Ordinary lists are ordered by object UUID ascending. Searches are ordered by
    score descending and then object UUID ascending. The cursor identifies the
    last item of the preceding request and is always exclusive.
    """

    limit: int = Field(
        ge=0,
        description="The maximum number of items to return. 0 can be used to get total_count only and no actual items."
    )
    return_total_count: bool = Field(
        default=False,
        description=(
            "Whether to count all records matching the filter, independently of "
            "the cursor and limit."
        ),
    )
    cursor: uuid.UUID | None = Field(
        default=None,
        description=(
            "Exclusive cursor returned by the preceding request. The query and "
            "filter must otherwise be identical."
        ),
    )


class GenericListResponse[T: BaseModel](BaseModel):
    """A generic paginated list response."""

    items: list[T]
    limit: int = Field(
        ge=0,
        description="The requested page size, not the number of returned items.",
    )
    total_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Count of all records matching the filter before cursor and limit, "
            "or None when it was not requested."
        ),
    )
    cursor: uuid.UUID | None = Field(
        default=None,
        description=(
            "Exclusive cursor for the next page, or None when no later item exists."
        ),
    )

    @model_validator(mode="after")
    def validate_page_shape(self) -> Self:
        if len(self.items) > self.limit:
            raise ValueError("items must not exceed the requested limit")
        if self.limit == 0 and (self.items or self.cursor is not None):
            raise ValueError("limit=0 responses must not contain items or a cursor")
        if self.cursor is not None and len(self.items) != self.limit:
            raise ValueError("a next-page cursor requires a full page")
        if self.total_count is not None and self.total_count < len(self.items):
            raise ValueError("total_count must not be smaller than the page")
        return self


class ListFilterBase(BaseModel):
    """Backend-neutral semantics shared by all list filters.

    Different fields are combined with logical AND and values inside one list
    with logical OR. Empty lists are rejected rather than treated differently
    by different backends.
    """

    @model_validator(mode="after")
    def reject_empty_lists(self) -> Self:
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, list) and not value:
                raise ValueError(f"filter field '{field_name}' must not be empty")
        return self


class ModelEmbedding[T: StrEnum](BaseModel):
    """One vector produced by one explicitly identified embedding model."""

    model_identifier: T = Field(min_length=1)
    vector: list[FiniteFloat] = Field(
        min_length=1,
        description=(
            "A non-empty, finite vector whose dimension must match "
            "model_identifier."
        ),
    )


def require_unique_model_embeddings[T: StrEnum](
    embeddings: list[ModelEmbedding[T]],
) -> None:
    models = [embedding.model_identifier for embedding in embeddings]
    if len(models) != len(set(models)):
        raise ValueError("each embedding model must be unique")


__all__ = [
    "ErrorResponse",
    "GenericActor",
    "GenericListRequest",
    "GenericListResponse",
    "ListFilterBase",
    "ModelEmbedding",
    "require_unique_model_embeddings",
]
