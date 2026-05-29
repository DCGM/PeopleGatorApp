import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6

logger = logging.getLogger(__name__)


class Source(Base):
    """A specific document, scan, or artifact from which RECORDs are derived.

    Belongs to one SOURCE_SCHEMA that determines how its storage paths are
    resolved.  The ``(provider, provider_id)`` pair is unique and serves as
    the natural deduplication key for re-ingestion runs.
    """

    __tablename__ = "source"

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # FK to source_schema — determines path resolution for all records in this source.
    source_schema_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_schema.schema_id"),
        nullable=False,
    )
    # Originating system, e.g. "kramerius", "nkcr", "local-ingest".
    provider: Mapped[str] = mapped_column(String, nullable=False)
    # The external system's stable identifier for this artifact.
    provider_id: Mapped[str] = mapped_column(String, nullable=False)
    # Source-level descriptive metadata: title, publication date, page number,
    # language, collection name, etc.
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_source_provider_id"),
        sa.Index("ix_source_provider", "provider"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID,
    ) -> "Source | None":
        result = await session.execute(
            select(cls).where(cls.source_id == source_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_provider(
        cls,
        session: AsyncSession,
        provider: str,
        provider_id: str,
    ) -> "Source | None":
        result = await session.execute(
            select(cls).where(
                cls.provider == provider,
                cls.provider_id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_or_create(
        cls,
        session: AsyncSession,
        source_schema_id: uuid.UUID,
        provider: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple["Source", bool]:
        """Return ``(source, created)`` — idempotent for re-ingestion runs.

        If the source already exists its ``metadata_`` is refreshed when a
        new value is provided.
        """
        source = await cls.get_by_provider(session, provider, provider_id)
        if source is not None:
            if metadata is not None and source.metadata_ != metadata:
                source.metadata_ = metadata
                session.add(source)
                logger.debug(
                    "Refreshed source metadata",
                    extra={
                        "source_id": str(source.source_id),
                        "provider": provider,
                        "provider_id": provider_id,
                    },
                )
            return source, False

        source = cls(
            source_id=new_uuid6(),
            source_schema_id=source_schema_id,
            provider=provider,
            provider_id=provider_id,
            metadata_=metadata,
        )
        session.add(source)
        logger.info(
            "Created source",
            extra={
                "source_id": str(source.source_id),
                "source_schema_id": str(source_schema_id),
                "provider": provider,
                "provider_id": provider_id,
            },
        )
        return source, True
