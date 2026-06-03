import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import ProviderType

logger = logging.getLogger(__name__)


class Source(Base):
    """A specific document, scan, or artifact from which EVIDENCEs are derived.

    Belongs to one SOURCE_SCHEMA (referenced by name) that determines how its
    storage paths are resolved.  The ``source`` field is an opaque string
    identifier for the original artifact, parsable via ``source_schema_name``.
    """

    __tablename__ = "source"

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # Opaque string identifier for the original source, e.g. a filename.
    # Parsable via the associated SOURCE_SCHEMA's resolver logic.
    source: Mapped[str] = mapped_column(String, nullable=False)
    # FK to SOURCE_SCHEMA by string name — determines path resolution.
    source_schema_name: Mapped[str] = mapped_column(
        String,
        ForeignKey("source_schema.schema_name"),
        nullable=False,
    )
    # Coarse provenance identifier — set at ingest time.
    provider: Mapped[ProviderType] = mapped_column(
        SAEnum(ProviderType, name="provider_type_enum"), nullable=False
    )
    # Source-level descriptive metadata: title, publication date, page number,
    # language, collection name, etc.  Structure conforms to the SOURCE_SCHEMA's
    # resolver config placeholder rules.
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    # BLAKE3 hash of the raw source bytes — used for application-layer
    # staleness detection and deduplication.  No DB UNIQUE constraint.
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # FK → PRINCIPAL — the service agent or user that ingested this source.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=True,
    )

    __table_args__ = (
        sa.Index("ix_source_provider", "provider"),
        sa.Index("ix_source_schema_name", "source_schema_name"),
        sa.Index("ix_source_content_hash", "content_hash"),
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
        result = await session.scalars(
            select(cls).where(cls.source_id == source_id)
        )
        return result.one_or_none()

    @classmethod
    async def get_by_content_hash(
        cls,
        session: AsyncSession,
        content_hash: str,
    ) -> "Source | None":
        result = await session.scalars(
            select(cls).where(cls.content_hash == content_hash)
        )
        return result.first()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        source: str,
        source_schema_name: str,
        provider: ProviderType,
        metadata: dict[str, Any] | None = None,
        content_hash: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> "Source":
        obj = cls(
            source_id=new_uuid6(),
            source=source,
            source_schema_name=source_schema_name,
            provider=provider,
            metadata_=metadata,
            content_hash=content_hash,
            created_by=created_by,
        )
        session.add(obj)
        logger.info(
            "Created source",
            extra={
                "source_id": str(obj.source_id),
                "source_schema_name": source_schema_name,
                "provider": provider.value,
            },
        )
        return obj


