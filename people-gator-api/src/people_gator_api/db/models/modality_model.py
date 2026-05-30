import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, Enum as SAEnum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import RecordType, RegistrySource


class ModalityModel(Base):
    """Registry of available embedding models per modality.

    Each row represents one deployable vector slot — a specific model that can
    encode records of a given ``record_type`` into a named slot in the vector
    store.  The vector slot name is derived as ``<role>:<model_slug>``.

    ``(registry_source, registry_uri)`` forms the canonical lineage reference
    and is denormalised onto every vector store document that carries this
    model's slot.
    """

    __tablename__ = "modality_model"

    model_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    record_type: Mapped[RecordType] = mapped_column(
        SAEnum(RecordType, name="record_type_enum"), nullable=False
    )
    # Slot role prefix, e.g. "face", "text", "layout".
    role: Mapped[str] = mapped_column(String, nullable=False)
    # Suffix component of the vector slot name: <role>:<model_slug>.
    # Globally unique within a (record_type, role) pair.
    model_slug: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Model registry that hosts this version, e.g. "mlflow", "huggingface".
    registry_source: Mapped[RegistrySource] = mapped_column(
        SAEnum(RegistrySource, name="registry_source_enum"), nullable=False
    )
    # Version-pinned URI within the registry, e.g. "models:/face-detector/3".
    registry_uri: Mapped[str] = mapped_column(String, nullable=False)
    # False once this model is no longer used for new embeddings; rows are
    # retained while any vector store document still references the slot.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "record_type", "role", "model_slug",
            name="uq_modality_model_record_type_role_slug",
        ),
        sa.Index("ix_modality_model_record_type_active", "record_type", "is_active"),
    )

    @property
    def slot_name(self) -> str:
        """Full vector slot name as stored in the vector store."""
        return f"{self.role}:{self.model_slug}"
