"""Resource-wide annotation count minima, independent of evidence filters."""

from typing import Annotated, Any, Self
from pydantic import BaseModel, BeforeValidator, Field, model_validator
from people_gator_api.schemas.missing import MISSING, MissingType


def validate_count(value: Any) -> int:
    # HTTP supplies decimal strings; internal callers supply integers. Reject
    # booleans and floats too, including 1.0, rather than silently truncating.
    if isinstance(value, bool) or not (
        isinstance(value, int)
        or isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
    ):
        raise ValueError("count must be a non-negative integer")
    return int(value)


type MinimumCount = Annotated[
    int, BeforeValidator(validate_count), Field(ge=0, le=9_007_199_254_740_991)
]


class AnnotationCountFilter(BaseModel):
    min_annotations_total_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum annotations total; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_annotations_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum annotations automatic; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_annotations_manual_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum annotations manual; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_annotations_verified_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum annotations verified; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_annotations_unassigned_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum annotations unassigned; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_faces_total_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum faces total; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_faces_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum faces automatic; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_faces_manual_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum faces manual; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_faces_verified_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum faces verified; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_faces_unassigned_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum faces unassigned; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_mentions_total_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum mentions total; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_mentions_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum mentions automatic; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_mentions_manual_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum mentions manual; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_mentions_verified_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum mentions verified; zero imposes no restriction. Counts cover the complete resource scope.",
    )
    min_mentions_unassigned_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum mentions unassigned; zero imposes no restriction. Counts cover the complete resource scope.",
    )

    def count_values(self):
        return {
            name: getattr(self, name) for name in AnnotationCountFilter.model_fields
        }


ANNOTATION_COUNT_FIELDS = (
    "annotations_total_count",
    "annotations_automatic_count",
    "annotations_manual_count",
    "annotations_verified_count",
    "annotations_unassigned_count",
    "faces_total_count",
    "faces_automatic_count",
    "faces_manual_count",
    "faces_verified_count",
    "faces_unassigned_count",
    "mentions_total_count",
    "mentions_automatic_count",
    "mentions_manual_count",
    "mentions_verified_count",
    "mentions_unassigned_count",
)


LINKED_ENTITY_COUNT_FIELD = "linked_entity_count"
DOCUMENT_RANGE_FIELDS = (*ANNOTATION_COUNT_FIELDS, LINKED_ENTITY_COUNT_FIELD)


class DocumentCountRangeFilter(BaseModel):
    """Document-wide upper bounds and linked-people bounds, beside the shared minima."""

    max_annotations_total_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum annotations total; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_annotations_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum annotations automatic; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_annotations_manual_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum annotations manual; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_annotations_verified_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum annotations verified; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_annotations_unassigned_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum annotations unassigned; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_faces_total_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum faces total; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_faces_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum faces automatic; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_faces_manual_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum faces manual; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_faces_verified_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum faces verified; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_faces_unassigned_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum faces unassigned; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_mentions_total_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum mentions total; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_mentions_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum mentions automatic; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_mentions_manual_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum mentions manual; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_mentions_verified_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum mentions verified; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    max_mentions_unassigned_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum mentions unassigned; documents without such annotations count as zero. Counts cover the complete resource scope.",
    )
    min_linked_entity_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive minimum number of distinct people linked anywhere in the document scope; zero imposes no restriction.",
    )
    max_linked_entity_count: MinimumCount | MissingType = Field(
        default=MISSING,
        description="Inclusive maximum number of distinct people linked anywhere in the document scope.",
    )

    @model_validator(mode="after")
    def validate_count_ranges(self) -> Self:
        for field in DOCUMENT_RANGE_FIELDS:
            lower = getattr(self, f"min_{field}", MISSING)
            upper = getattr(self, f"max_{field}")
            if isinstance(lower, int) and isinstance(upper, int) and lower > upper:
                raise ValueError(f"min_{field} must not exceed max_{field}")
        return self

    def range_values(self):
        return {
            name: getattr(self, name) for name in DocumentCountRangeFilter.model_fields
        }
