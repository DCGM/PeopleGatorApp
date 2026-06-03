"""Pydantic metadata schemas for ML-derived evidence types.

Each class corresponds to an ``EvidenceType`` value in the ``_DERIVED_TYPES``
set and defines the expected structure of ``DerivedEvidence.produced_metadata``.
"""

from pydantic import BaseModel, Field

from people_gator_api.evidence_schemas.shared import BoundingBox, Image, Keypoint, TextSpan


class FaceDetectionMetadata(BaseModel):
    """Metadata payload for ``EvidenceType.face_detection``."""

    bounding_box: BoundingBox
    keypoints: list[Keypoint] = []
    image: Image | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class NamedEntityMetadata(BaseModel):
    """Metadata payload for ``EvidenceType.named_entity``."""

    span: TextSpan
    entity_label: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class TextRegionMetadata(BaseModel):
    """Metadata payload for ``EvidenceType.text_region``."""

    area: list[tuple[float, float]] = Field(..., min_length=3)
    text: str | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
