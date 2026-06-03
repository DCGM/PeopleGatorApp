"""Shared geometric and textual primitive types for evidence metadata schemas.

All types are Pydantic BaseModel subclasses with strict validation enabled.
They are composed by the derived and authority evidence schema modules.
"""

from pydantic import BaseModel, Field


class Point(BaseModel):
    """A 2-D coordinate in normalised image space (0.0–1.0)."""

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class Rectangle(BaseModel):
    """Axis-aligned bounding box in normalised image space."""

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., gt=0.0, le=1.0)
    height: float = Field(..., gt=0.0, le=1.0)


class Polygon(BaseModel):
    """Arbitrary convex or concave polygon."""

    points: list[Point] = Field(..., min_length=3)


class PolyLine(BaseModel):
    """Ordered sequence of points (not necessarily closed)."""

    points: list[Point] = Field(..., min_length=2)


class BoundingBox(BaseModel):
    """Alias for Rectangle, used in detection contexts."""

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., gt=0.0, le=1.0)
    height: float = Field(..., gt=0.0, le=1.0)


class Keypoint(BaseModel):
    """Named landmark point with optional visibility flag."""

    name: str
    point: Point
    visible: bool = True


class TextSpan(BaseModel):
    """Character-level span in a plain-text string."""

    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    text: str | None = None


class PhysicalTextSpan(BaseModel):
    """Span within a physical-layout text region."""

    region_id: str
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)


class PhysicalTextRegion(BaseModel):
    """A polygonal region from a PAGE-XML or equivalent layout document."""

    region_id: str
    polygon: Polygon
    text: str | None = None


class Image(BaseModel):
    """Reference to an image crop or thumbnail stored in S3."""

    bucket: str
    key: str
    width: int | None = None
    height: int | None = None
