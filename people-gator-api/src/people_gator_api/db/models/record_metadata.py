"""Pydantic schemas for RECORD.metadata JSONB payloads.

Each class corresponds to a RecordType value and defines the expected
structure of the `metadata` column for records of that type.

See: docs/01-product-spec.md §5.4.1 – §5.4.2
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# §5.4.1 Shared sub-schemas
# ---------------------------------------------------------------------------


class Point(BaseModel):
    """Single spatial coordinate, normalised to [0, 1] relative to image dimensions."""

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class Rectangle(BaseModel):
    """Axis-aligned bounding rectangle, normalised to [0, 1]."""

    min: Point
    max: Point


class Polygon(BaseModel):
    """Closed polygon defined by an ordered sequence of vertices."""

    vertices: list[Point]


class PolyLine(BaseModel):
    """Open polyline defined by an ordered sequence of points."""

    points: list[Point]


class TextSpan(BaseModel):
    """Character-level span within a string (end is exclusive)."""

    start: int
    end: int


class Image(BaseModel):
    """Metadata describing the source image for a detection."""

    image_format: Literal["jpeg", "png", "tiff"]
    width_px: int
    height_px: int


class Keypoint(BaseModel):
    """A named landmark on an image."""

    point: Point
    label: str


class BoundingBox(BaseModel):
    """Labelled bounding box wrapping a detected region."""

    box: Rectangle
    label: str


class PhysicalTextSpan(BaseModel):
    """A span of text with optional spatial baseline on the image."""

    span: TextSpan
    baseline: list[Point] | None = None
    text: str
    normalized_text: str
    label: str


class PhysicalTextRegion(BaseModel):
    """A polygonal text region with optional spatial baseline on the image."""

    area: Polygon
    baseline: list[Point] | None = None
    text: str
    normalized_text: str
    label: str


# ---------------------------------------------------------------------------
# §5.4.2 Per record-type metadata schemas
# ---------------------------------------------------------------------------


class FaceDetectionMetadata(BaseModel):
    """Metadata for RecordType.face_detection records."""

    bounding_box: BoundingBox
    keypoints: list[Keypoint] | None = None
    image: Image
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: str


class NamedEntityMetadata(BaseModel):
    """Metadata for RecordType.named_entity records."""

    span: PhysicalTextSpan
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: str


class TextRegionMetadata(BaseModel):
    """Metadata for RecordType.text_region records."""

    area: PhysicalTextRegion
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: str


class GroundedNameMetadata(BaseModel):
    """Metadata for RecordType.grounded_name records."""

    name: str
    type: Literal["preferred", "alias"]
    language: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class GroundedDescriptionMetadata(BaseModel):
    """Metadata for RecordType.grounded_description records."""

    description: str
    language: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
