"""Schema registry mapping (EvidenceType, schema_version) → Pydantic model class.

Callers should use ``get_schema`` to resolve the correct validator for an
incoming evidence payload.  Raising ``KeyError`` on unknown pairs is
intentional — ingestion code must provide a supported schema_version.
"""

from pydantic import BaseModel

from people_gator_api.db.models.enums import EvidenceType
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

type SchemaKey = tuple[EvidenceType, str]
type SchemaModel = type[BaseModel]

_REGISTRY: dict[SchemaKey, SchemaModel] = {
    (EvidenceType.face_detection, "1"): FaceDetectionMetadata,
    (EvidenceType.named_entity, "1"): NamedEntityMetadata,
    (EvidenceType.text_region, "1"): TextRegionMetadata,
    (EvidenceType.grounded_name, "1"): GroundedNameMetadata,
    (EvidenceType.grounded_description, "1"): GroundedDescriptionMetadata,
    (EvidenceType.authority_identifier, "1"): AuthorityIdentifierMetadata,
}


def get_schema(evidence_type: EvidenceType, schema_version: str) -> SchemaModel:
    """Return the Pydantic model class for this (evidence_type, schema_version) pair.

    Raises ``KeyError`` when the pair is not registered.
    """
    return _REGISTRY[(evidence_type, schema_version)]


def list_schemas() -> list[SchemaKey]:
    """Return all registered (evidence_type, schema_version) pairs."""
    return list(_REGISTRY.keys())
