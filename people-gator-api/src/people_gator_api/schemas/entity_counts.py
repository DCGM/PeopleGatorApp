"""Person-wide annotation ranges; ownerless evidence has no person count."""

from typing import Self
from pydantic import BaseModel, Field, model_validator
from .annotation_counts import MinimumCount
from .missing import MISSING, MissingType

ENTITY_COUNT_FIELDS = (
    "faces_total_count",
    "faces_verified_count",
    "faces_manual_count",
    "faces_automatic_count",
    "mentions_total_count",
    "mentions_verified_count",
    "mentions_manual_count",
    "mentions_automatic_count",
    "annotations_total_count",
    "annotations_verified_count",
    "annotations_manual_count",
    "annotations_automatic_count",
)


class EntityCountFilter(BaseModel):
    min_faces_total_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum faces total count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_faces_total_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum faces total count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_faces_verified_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum faces verified count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_faces_verified_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum faces verified count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_faces_manual_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum faces manual count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_faces_manual_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum faces manual count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_faces_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum faces automatic count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_faces_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum faces automatic count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_mentions_total_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum mentions total count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_mentions_total_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum mentions total count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_mentions_verified_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum mentions verified count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_mentions_verified_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum mentions verified count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_mentions_manual_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum mentions manual count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_mentions_manual_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum mentions manual count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_mentions_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum mentions automatic count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_mentions_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum mentions automatic count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_annotations_total_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum annotations total count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_annotations_total_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum annotations total count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_annotations_verified_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum annotations verified count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_annotations_verified_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum annotations verified count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_annotations_manual_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum annotations manual count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_annotations_manual_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum annotations manual count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    min_annotations_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive minimum annotations automatic count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )
    max_annotations_automatic_count: MinimumCount | MissingType = Field(
        default=MISSING, description="Inclusive maximum annotations automatic count across the complete entity, independent of evidence filters; integer 0 through 9007199254740991.",
    )

    @model_validator(mode="after")
    def validate_count_ranges(self) -> Self:
        for field in ENTITY_COUNT_FIELDS:
            lower = getattr(self, f"min_{field}")
            upper = getattr(self, f"max_{field}")
            if isinstance(lower, int) and isinstance(upper, int) and lower > upper:
                raise ValueError(f"min_{field} must not exceed max_{field}")
        return self
