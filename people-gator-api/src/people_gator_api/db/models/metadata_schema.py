import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import RecordType

logger = logging.getLogger(__name__)


class MetadataSchema(Base):
    """Registry of versioned metadata payload schemas for each RECORD type.

    Each row defines the contract that ``RECORD.metadata`` conforms to.
    ``schema_name`` is the canonical versioned identifier used in APIs and
    ingestion code (e.g. ``face-detection/v1``).  ``json_schema`` optionally
    carries a machine-readable JSON Schema (draft-07) for runtime validation
    at ingest time.

    The ``(record_type, version)`` pair is unique — adding a new schema
    version creates a new row; old RECORDs retain their FK and remain valid.
    """

    __tablename__ = "metadata_schema"

    schema_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    schema_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    record_type: Mapped[RecordType] = mapped_column(
        SAEnum(RecordType, name="record_type_enum"), nullable=False
    )
    version: Mapped[str] = mapped_column(String, nullable=False)
    json_schema: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "record_type", "version", name="uq_metadata_schema_type_version"
        ),
        sa.Index("ix_metadata_schema_record_type", "record_type"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        schema_id: uuid.UUID,
    ) -> "MetadataSchema | None":
        result = await session.scalars(
            select(cls).where(cls.schema_id == schema_id)
        )
        return result.one_or_none()

    @classmethod
    async def get_by_name(
        cls,
        session: AsyncSession,
        schema_name: str,
    ) -> "MetadataSchema | None":
        result = await session.scalars(
            select(cls).where(cls.schema_name == schema_name)
        )
        return result.one_or_none()

    @classmethod
    async def get_by_type_version(
        cls,
        session: AsyncSession,
        record_type: RecordType,
        version: str,
    ) -> "MetadataSchema | None":
        result = await session.scalars(
            select(cls).where(
                cls.record_type == record_type,
                cls.version == version,
            )
        )
        return result.one_or_none()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        schema_name: str,
        record_type: RecordType,
        version: str,
        json_schema: dict[str, object] | None = None,
        description: str | None = None,
    ) -> "MetadataSchema":
        entry = cls(
            schema_id=new_uuid6(),
            schema_name=schema_name,
            record_type=record_type,
            version=version,
            json_schema=json_schema,
            description=description,
        )
        session.add(entry)
        logger.info(
            "Created metadata schema",
            extra={
                "schema_id": str(entry.schema_id),
                "schema_name": schema_name,
                "record_type": record_type.value,
                "version": version,
            },
        )
        return entry
