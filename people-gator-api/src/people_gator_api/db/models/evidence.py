"""Evidence base table and its two specialised child tables.

The class-table (joined) inheritance pattern is used:
- EVIDENCE           — shared identity and provenance fields (base table)
- DERIVED_EVIDENCE   — ML-model-produced detections (child table)
- AUTHORITY_EVIDENCE — authority-sourced records (child table)

All DELTA and MEMBERSHIP FKs reference the base EVIDENCE table so membership
queries never need to know which family an item belongs to.
"""

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import EvidenceType

logger = logging.getLogger(__name__)

# Evidence types that specialise into DERIVED_EVIDENCE.
_DERIVED_TYPES: frozenset[EvidenceType] = frozenset(
    {EvidenceType.face_detection, EvidenceType.named_entity, EvidenceType.text_region}
)

# Evidence types that specialise into AUTHORITY_EVIDENCE.
_AUTHORITY_TYPES: frozenset[EvidenceType] = frozenset(
    {
        EvidenceType.grounded_name,
        EvidenceType.grounded_description,
        EvidenceType.authority_identifier,
    }
)


class Evidence(Base):
    """Shared identity and provenance fields for all evidence items.

    Every DERIVED_EVIDENCE and AUTHORITY_EVIDENCE row has a corresponding
    EVIDENCE row with the same ``evidence_id``.
    """

    __tablename__ = "evidence"

    # Stable identifier across all versions of this evidence item.
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # Incremented only when a human revises the evidence metadata.
    # Re-running inference produces a NEW evidence_id, not a new version.
    evidence_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=new_uuid6
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, name="evidence_type_enum"),
        nullable=False,
    )
    # Together with evidence_type identifies the Pydantic model in the
    # application-layer schema registry.  No DB FK — validated at ingest time.
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    # FK → SOURCE — the document or artifact this evidence was derived from.
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source.source_id"),
        nullable=False,
    )
    # Sub-path within the SOURCE identifying the specific artifact, e.g. a page
    # ID within a zip or a crop region URI.  Null means the evidence covers the
    # entire source document.  Opaque to the DB; interpreted by the resolver.
    source_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # BLAKE3 hash of the evidence payload for application-layer staleness
    # detection and deduplication.  No DB UNIQUE constraint.
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Soft-delete flag — hard deletes are not permitted.
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set when a newer EVIDENCE supersedes this one (e.g. re-inference with
    # an updated model).  Retained for audit.
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __mapper_args__ = {
        "polymorphic_on": "evidence_type",
        "polymorphic_identity": None,
    }

    __table_args__ = (
        sa.Index("ix_evidence_source_id", "source_id"),
        sa.Index("ix_evidence_type", "evidence_type"),
        sa.Index("ix_evidence_content_hash", "content_hash"),
        sa.Index("ix_evidence_version", "evidence_id", "evidence_version_id"),
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_derived(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.evidence_type in _DERIVED_TYPES

    @is_derived.expression
    @classmethod
    def is_derived(cls) -> sa.ColumnElement[bool]:
        return cls.evidence_type.in_([t.value for t in _DERIVED_TYPES])

    @hybrid_property
    def is_authority(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.evidence_type in _AUTHORITY_TYPES

    @is_authority.expression
    @classmethod
    def is_authority(cls) -> sa.ColumnElement[bool]:
        return cls.evidence_type.in_([t.value for t in _AUTHORITY_TYPES])

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        evidence_id: uuid.UUID,
    ) -> "Evidence | None":
        result = await session.scalars(
            select(cls).where(cls.evidence_id == evidence_id)
        )
        return result.one_or_none()

    @classmethod
    async def get_version(
        cls,
        session: AsyncSession,
        evidence_id: uuid.UUID,
        evidence_version_id: uuid.UUID,
    ) -> "Evidence | None":
        result = await session.scalars(
            select(cls).where(
                cls.evidence_id == evidence_id,
                cls.evidence_version_id == evidence_version_id,
            )
        )
        return result.one_or_none()


class DerivedEvidence(Evidence):
    """ML-model-produced detections: ``face_detection``, ``named_entity``, ``text_region``.

    ``producer_id`` is a FK to ``MODEL_AGENT.principal_id``.  Because
    MODEL_AGENT is a proper subtype table, this FK is DB-enforced without any
    CHECK constraint or trigger.

    A partial GIN index per ``evidence_type`` on ``produced_metadata`` supports
    modality-specific JSONB field access and faceting.
    """

    __tablename__ = "derived_evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evidence.evidence_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Non-null FK → MODEL_AGENT.principal_id — the model that produced this.
    producer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_agent.principal_id"),
        nullable=False,
    )
    # Typed detection payload validated by the schema registry at ingest time.
    produced_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Nullable FK → USER.principal_id — the human who last revised the metadata.
    revisor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.principal_id"),
        nullable=True,
    )
    # Human correction of produced_metadata.  When present, supersedes
    # produced_metadata for display; produced_metadata is always retained.
    revised_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        sa.Index("ix_derived_evidence_producer", "producer_id"),
        # Partial GIN indexes per evidence_type for modality-specific faceting.
        sa.Index(
            "ix_derived_evidence_face_metadata_gin",
            "produced_metadata",
            postgresql_where=sa.text("evidence_type = 'face_detection'"),
            postgresql_using="gin",
        ),
        sa.Index(
            "ix_derived_evidence_ner_metadata_gin",
            "produced_metadata",
            postgresql_where=sa.text("evidence_type = 'named_entity'"),
            postgresql_using="gin",
        ),
        sa.Index(
            "ix_derived_evidence_text_region_metadata_gin",
            "produced_metadata",
            postgresql_where=sa.text("evidence_type = 'text_region'"),
            postgresql_using="gin",
        ),
    )

    __mapper_args__ = {
        "polymorphic_abstract": True,
        "inherit_condition": evidence_id == Evidence.evidence_id,
    }


class FaceDetectionEvidence(DerivedEvidence):
    """Concrete subtype to allow polymorphic_identity on face_detection."""

    __mapper_args__ = {"polymorphic_identity": EvidenceType.face_detection}


class NamedEntityEvidence(DerivedEvidence):
    """Concrete subtype to allow polymorphic_identity on named_entity."""

    __mapper_args__ = {"polymorphic_identity": EvidenceType.named_entity}


class TextRegionEvidence(DerivedEvidence):
    """Concrete subtype to allow polymorphic_identity on text_region."""

    __mapper_args__ = {"polymorphic_identity": EvidenceType.text_region}


class AuthorityEvidence(Evidence):
    """Authority-sourced records: ``grounded_name``, ``grounded_description``, ``authority_identifier``.

    ``producer_id`` is a FK to ``SERVICE_AGENT.principal_id`` — DB-enforced
    via the subtype table.  No ``revised_metadata`` — authority evidence is
    replaced wholesale on re-sync by creating a new EVIDENCE version.

    A partial GIN index per ``evidence_type`` on ``metadata`` supports
    modality-specific JSONB access.
    """

    __tablename__ = "authority_evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evidence.evidence_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Non-null FK → SERVICE_AGENT.principal_id — the pipeline that produced this.
    producer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_agent.principal_id"),
        nullable=False,
    )
    # Typed authority payload validated by the schema registry at ingest time.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_authority_evidence_producer", "producer_id"),
        # Partial GIN indexes per evidence_type.
        sa.Index(
            "ix_authority_evidence_gname_metadata_gin",
            "metadata",
            postgresql_where=sa.text("evidence_type = 'grounded_name'"),
            postgresql_using="gin",
        ),
        sa.Index(
            "ix_authority_evidence_gdesc_metadata_gin",
            "metadata",
            postgresql_where=sa.text("evidence_type = 'grounded_description'"),
            postgresql_using="gin",
        ),
        sa.Index(
            "ix_authority_evidence_auth_id_metadata_gin",
            "metadata",
            postgresql_where=sa.text("evidence_type = 'authority_identifier'"),
            postgresql_using="gin",
        ),
    )

    __mapper_args__ = {
        "polymorphic_abstract": True,
        "inherit_condition": evidence_id == Evidence.evidence_id,
    }


class GroundedNameEvidence(AuthorityEvidence):
    """Concrete subtype to allow polymorphic_identity on grounded_name."""

    __mapper_args__ = {"polymorphic_identity": EvidenceType.grounded_name}


class GroundedDescriptionEvidence(AuthorityEvidence):
    """Concrete subtype to allow polymorphic_identity on grounded_description."""

    __mapper_args__ = {"polymorphic_identity": EvidenceType.grounded_description}


class AuthorityIdentifierEvidence(AuthorityEvidence):
    """Concrete subtype to allow polymorphic_identity on authority_identifier."""

    __mapper_args__ = {"polymorphic_identity": EvidenceType.authority_identifier}
