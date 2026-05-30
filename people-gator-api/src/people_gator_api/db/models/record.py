import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, String, select
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
    # FK to SOURCE — the document or artifact this record was derived from.
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("source.source_id"),
        nullable=False,
    )
    # Within-source coordinates, e.g. {"page": 3, "region_index": 7}.
    # Combined with SOURCE_SCHEMA.resolver_config this fully resolves the
    # physical location without storing duplicate paths on the record.
    source_path: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Top-level reference to the embedding vector in the external vector store
    # (Qdrant, Weaviate, Milvus, etc.).  Non-null when this record is the root
    # of an embedding (i.e. the crop or text span that was directly encoded).
    embedding_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # FK → METADATA_SCHEMA — identifies the versioned contract for metadata.
    metadata_schema_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("metadata_schema.schema_id"),
        nullable=False,
    )
    # Mapped to "metadata" in DB; renamed in Python to avoid collision with
    # DeclarativeBase.metadata.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_record_content_hash", "content_hash"),
        sa.Index("ix_record_source", "source_id"),
        sa.Index("ix_record_embedding", "embedding_id"),
        sa.Index("ix_record_metadata_schema", "metadata_schema_id"),
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates — work in Python and as SQL expressions
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_face_detection(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.record_type == RecordType.face_detection

    @is_face_detection.expression
    @classmethod
    def is_face_detection(cls) -> sa.ColumnElement[bool]:
        return cls.record_type == RecordType.face_detection.value

    @hybrid_method
    def has_type(self, record_type: RecordType) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.record_type == record_type

    @has_type.expression
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
        result = await session.scalars(
            select(cls).where(
                cls.record_id == record_id,
                cls.record_version_id == record_version_id,
            )
        )
        return result.one_or_none()

    @classmethod
    async def get_latest_version(
        cls,
        session: AsyncSession,
        record_id: uuid.UUID,
    ) -> "Record | None":
        result = await session.scalars(
            select(cls)
            .where(cls.record_id == record_id)
            .order_by(cls.record_version_id.desc())
            .limit(1)
        )
        record = result.one_or_none()
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
        result = await session.scalars(
            select(cls)
            .where(cls.content_hash == content_hash)
            .order_by(cls.record_version_id.desc())
            .limit(1)
        )
        return result.one_or_none()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        record_type: RecordType,
        content_hash: str,
        source_id: uuid.UUID,
        source_path: dict[str, Any],
        metadata_schema_id: uuid.UUID,
        metadata: dict[str, Any],
        embedding_id: str | None = None,
        record_id: uuid.UUID | None = None,
    ) -> "Record":
        record = cls(
            record_id=record_id or new_uuid6(),
            record_version_id=new_uuid6(),
            record_type=record_type,
            content_hash=content_hash,
            source_id=source_id,
            source_path=source_path,
            embedding_id=embedding_id,
            metadata_schema_id=metadata_schema_id,
            metadata_=metadata,
        )
        session.add(record)
        logger.info(
            "Created record",
            extra={
                "record_id": str(record.record_id),
                "record_version_id": str(record.record_version_id),
                "record_type": record_type.value,
                "content_hash": content_hash,
                "source_id": str(source_id),
                "embedding_id": embedding_id,
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
        source_path: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_id: str | None = None,
    ) -> "Record":
        new_version = Record(
            record_id=self.record_id,
            record_version_id=new_uuid6(),
            record_type=self.record_type,
            content_hash=content_hash,
            source_id=self.source_id,
            source_path=source_path if source_path is not None else self.source_path,
            embedding_id=embedding_id if embedding_id is not None else self.embedding_id,
            metadata_schema_id=self.metadata_schema_id,
            metadata_=metadata if metadata is not None else self.metadata_,
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
