"""Evidence schema package — Pydantic models for all EvidenceType metadata payloads."""

from people_gator_api.evidence_schemas.authority import (
    AuthorityIdentifierMetadata,
    GroundedDescriptionMetadata,
    GroundedNameMetadata,
)
from people_gator_api.evidence_schemas.derived import (
    FaceDetectionMetadata,
    NamedEntityMetadata,
    TextRegionMetadata,
)
from people_gator_api.evidence_schemas.registry import get_schema, list_schemas
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
    # shared primitives
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
    # derived
    "FaceDetectionMetadata",
    "NamedEntityMetadata",
    "TextRegionMetadata",
    # authority
    "AuthorityIdentifierMetadata",
    "GroundedDescriptionMetadata",
    "GroundedNameMetadata",
    # registry
    "get_schema",
    "list_schemas",
]
