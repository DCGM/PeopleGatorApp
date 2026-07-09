"""Evidence schema package — shared geometric primitives.

The original typed metadata schemas (derived.py, authority.py, registry.py)
were tied to the old EvidenceType enum and the EVIDENCE table hierarchy.
Under the new spec-1 data model, annotation tables (DETECTION, NAMED_ENTITY,
DESCRIPTION, ALTERNATIVE_NAME) store simpler JSON fields directly.

The shared geometric primitives in ``shared.py`` are retained for callers
that need to construct well-validated detection payloads (bounding boxes,
keypoints, polygons, etc.) before serialising them into the JSONB columns.
"""

from people_gator_api.evidence_schemas.shared import (
    BoundingBox,
    Image,
    Keypoint,
    PhysicalTextRegion,
    PhysicalTextSpan,
    Point,
    PolyLine,
    Polygon,
    Rectangle,
    TextSpan,
)

__all__ = [
    "BoundingBox",
    "Image",
    "Keypoint",
    "PhysicalTextRegion",
    "PhysicalTextSpan",
    "Point",
    "PolyLine",
    "Polygon",
    "Rectangle",
    "TextSpan",
]
