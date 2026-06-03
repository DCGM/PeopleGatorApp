"""Pydantic metadata schemas for authority-sourced evidence types.

Each class corresponds to an ``EvidenceType`` value in the ``_AUTHORITY_TYPES``
set and defines the expected structure of ``AuthorityEvidence.metadata_``.
"""

from pydantic import BaseModel


class GroundedNameMetadata(BaseModel):
    """Metadata payload for ``EvidenceType.grounded_name``."""

    name: str
    type: str
    language: str


class GroundedDescriptionMetadata(BaseModel):
    """Metadata payload for ``EvidenceType.grounded_description``."""

    description: str
    language: str


class AuthorityIdentifierMetadata(BaseModel):
    """Metadata payload for ``EvidenceType.authority_identifier``."""

    identifier: str
    authority_type: str
