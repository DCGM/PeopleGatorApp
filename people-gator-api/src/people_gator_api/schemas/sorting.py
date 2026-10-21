"""Backend-neutral sort contract shared by browsable list and search requests.

Each resource allowlists its own fields; no request names a storage column.
Sorting applies to the complete matching set before pagination. Unknown values
sort last in both directions and every order ends with the resource's canonical
identity ascending, so equal keys page deterministically.

Text fields compare case- and accent-insensitively (lowercased, unaccented) in
Unicode code-point order, then by the exact recorded text in code-point order.
Counts compare numerically and times chronologically. Assignment state orders
``verified``, ``manual``, ``automatic``, then unassigned (unknown) last.
``relevance`` is the final search score and is valid only for searches.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class EntitySortField(StrEnum):
    RELEVANCE = "relevance"
    NAME = "name"
    ENTITY_ID = "entity_id"
    LAST_TOUCHED_AT = "last_touched_at"
    CREATED_AT = "created_at"


class DocumentSortField(StrEnum):
    RELEVANCE = "relevance"
    NAME = "name"
    DOCUMENT_ID = "document_id"
    LIBRARY = "library"
    PAGE_COUNT = "page_count"
    LAST_TOUCHED_AT = "last_touched_at"


class PageSortField(StrEnum):
    RELEVANCE = "relevance"
    LIBRARY = "library"
    DOCUMENT_ID = "document_id"
    PAGE_ID = "page_id"
    LAST_TOUCHED_AT = "last_touched_at"


class FaceSortField(StrEnum):
    RELEVANCE = "relevance"
    DETECTION_ID = "detection_id"
    LAST_TOUCHED_AT = "last_touched_at"
    LINK_STATE = "link_state"
    CONFIDENCE = "confidence"
    SOURCE = "source"


class TextMentionSortField(StrEnum):
    TEXT = "text"
    MENTION_ID = "mention_id"
    LAST_TOUCHED_AT = "last_touched_at"
    LINK_STATE = "link_state"
    SOURCE = "source"


class TextMentionGroupSortField(StrEnum):
    TEXT = "text"
    COUNT = "count"
    LAST_TOUCHED_AT = "last_touched_at"


RELEVANCE = "relevance"

# Fields whose natural first direction is descending: newest, largest, best.
DESCENDING_BY_DEFAULT = frozenset({"relevance", "last_touched_at", "created_at", "page_count", "count"})

SORT_DESCRIPTION = (
    "Sort field. Ordinary lists default to canonical identity ascending; "
    "searches default to relevance descending. Unknown values sort last."
)
SORT_DIRECTION_DESCRIPTION = (
    "Sort direction; requires sort. Defaults to descending for relevance, "
    "times and counts and ascending otherwise."
)


def default_direction(field: str) -> SortDirection:
    return SortDirection.DESC if field in DESCENDING_BY_DEFAULT else SortDirection.ASC


class SortableRequest[S: StrEnum](BaseModel):
    """Optional resource-specific ordering for one list or search request."""

    sort: S | None = Field(default=None, description=SORT_DESCRIPTION)
    sort_direction: SortDirection | None = Field(
        default=None, description=SORT_DIRECTION_DESCRIPTION
    )

    @model_validator(mode="after")
    def validate_sort(self) -> Self:
        if self.sort_direction is not None and self.sort is None:
            raise ValueError("sort_direction requires sort")
        if self.sort is not None and str(self.sort) == RELEVANCE and not self.is_search():
            raise ValueError("relevance sorting is available only for searches")
        return self

    @classmethod
    def is_search(cls) -> bool:
        return False

    def effective_sort(self) -> tuple[str | None, SortDirection]:
        """Return the requested field and direction; None means the default order."""
        if self.sort is None:
            if self.is_search():
                return RELEVANCE, SortDirection.DESC
            return None, SortDirection.ASC
        field = str(self.sort)
        return field, self.sort_direction or default_direction(field)


__all__ = [
    "DocumentSortField",
    "EntitySortField",
    "FaceSortField",
    "PageSortField",
    "RELEVANCE",
    "SortDirection",
    "SortableRequest",
    "TextMentionGroupSortField",
    "TextMentionSortField",
    "default_direction",
]
