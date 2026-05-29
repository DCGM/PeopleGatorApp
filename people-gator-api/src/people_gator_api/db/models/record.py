import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, Index, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import RecordType

logger = logging.getLogger(__name__)


class Record(Base):
    __tablename__ = "record"

    record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    record_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    record_type: Mapped[RecordType] = mapped_column(
        SAEnum(RecordType, name="record_type_enum"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    source_provider: Mapped[str] = mapped_column(String, nullable=False)
    source_schema: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metadata_schema: Mapped[str] = mapped_column(String, nullable=False)
    # Mapped to "metadata" in DB; renamed in Python to avoid collision with
    # DeclarativeBase.metadata.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False
    )
    storage_location: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("ix_record_content_hash", "content_hash"),)

    # -------------------------------------------------------------------------
    # Hybrid predicates — work in Python and as SQL expressions
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_face_detection(self) -> bool:  # type: ignore[misc]
        return self.record_type == RecordType.face_detection

    @is_face_detection.expression  # type: ignore[override]
    @classmethod
    def is_face_detection(cls) -> sa.ColumnElement[bool]:
        return cls.record_type == RecordType.face_detection.value

    @hybrid_method
    def has_type(self, record_type: RecordType) -> bool:  # type: ignore[misc]
        return self.record_type == record_type

    @has_type.expression  # type: ignore[override]
    @classmethod
    def has_type(cls, record_type: RecordType) -> sa.ColumnElement[bool]:
        return cls.record_type == record_type.value

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        record_id: uuid.UUID,
        record_version_id: uuid.UUID,
    ) -> "Record | None":
        result = await session.execute(
            select(cls).where(
                cls.record_id == record_id,
                cls.record_version_id == record_version_id,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_latest_version(
        cls,
        session: AsyncSession,
        record_id: uuid.UUID,
    ) -> "Record | None":
        result = await session.execute(
            select(cls)
            .where(cls.record_id == record_id)
            .order_by(cls.record_version_id.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        logger.debug(
            "Fetched latest record version",
            extra={"record_id": str(record_id), "found": record is not None},
        )
        return record

    @classmethod
    async def get_by_content_hash(
        cls,
        session: AsyncSession,
        content_hash: str,
    ) -> "Record | None":
        result = await session.execute(
            select(cls)
            .where(cls.content_hash == content_hash)
            .order_by(cls.record_version_id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        record_type: RecordType,
        content_hash: str,
        source_provider: str,
        source_schema: str,
        source: dict[str, Any],
        metadata_schema: str,
        metadata: dict[str, Any],
        storage_location: str,
        record_id: uuid.UUID | None = None,
    ) -> "Record":
        record = cls(
            record_id=record_id or new_uuid6(),
            record_version_id=new_uuid6(),
            record_type=record_type,
            content_hash=content_hash,
            source_provider=source_provider,
            source_schema=source_schema,
            source=source,
            metadata_schema=metadata_schema,
            metadata_=metadata,
            storage_location=storage_location,
        )
        session.add(record)
        logger.info(
            "Created record",
            extra={
                "record_id": str(record.record_id),
                "record_version_id": str(record.record_version_id),
                "record_type": record_type.value,
                "content_hash": content_hash,
            },
        )
        return record

    # -------------------------------------------------------------------------
    # Instance-level operations
    # -------------------------------------------------------------------------

    async def create_new_version(
        self,
        session: AsyncSession,
        content_hash: str,
        source: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        storage_location: str | None = None,
    ) -> "Record":
        new_version = Record(
            record_id=self.record_id,
            record_version_id=new_uuid6(),
            record_type=self.record_type,
            content_hash=content_hash,
            source_provider=self.source_provider,
            source_schema=self.source_schema,
            source=source if source is not None else self.source,
            metadata_schema=self.metadata_schema,
            metadata_=metadata if metadata is not None else self.metadata_,
            storage_location=storage_location or self.storage_location,
        )
        session.add(new_version)
        logger.info(
            "Created new record version",
            extra={
                "record_id": str(self.record_id),
                "old_version_id": str(self.record_version_id),
                "new_version_id": str(new_version.record_version_id),
                "content_hash": content_hash,
            },
        )
        return new_version
