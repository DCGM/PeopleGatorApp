"""SOURCE table — metadata about the origin of annotations (spec §2.7).

A simplified source model: every annotation (named entity, detection,
description, alternative name) references exactly one SOURCE that records
where the annotation was found.  The source tracks its physical type, a
URI, and opaque metadata.

Replaces the previous SOURCE + SOURCE_SCHEMA + SOURCE_PROCESSING trio.
Path resolution is no longer modelled in the database — the ``uri`` field
is the canonical locator and consumers interpret it directly.
"""

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.models.enums import SourceKind
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class Source(Base):
    """A specific document, scan, or authority record that annotations derive from.

    Uniqueness is enforced on ``(source_type, uri)`` so the same physical
    artifact cannot be registered twice (spec §2.7 constraints).
    """

    __tablename__ = "source"
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    source_type: Mapped[SourceKind] = mapped_column(
        SAEnum(SourceKind, name="source_kind_enum"), nullable=False
    )
    # Canonical locator — URL, file path, or authority identifier.
    uri: Mapped[str] = mapped_column(String, nullable=False)
    # Source-specific metadata: page number, image dimensions, publication
    # info, etc.  Free-form JSONB; structure is not DB-enforced.
    metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    # FK → PRINCIPAL — who registered this source.
    principal_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=True,
    )
    created_at: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("source_type", "uri", name="uq_source_type_uri"),
        sa.Index("ix_source_source_type", "source_type"),
        sa.Index("ix_source_uri", "uri"),
        sa.Index("ix_source_principal_id", "principal_id"),
        sa.Index("ix_metadata", "metadata", postgresql_using="gin")
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
    async def get_by_type_uri(
        cls,
        session: AsyncSession,
        source_type: SourceKind,
        uri: str,
    ) -> "Source | None":
        result = await session.scalars(
            select(cls).where(
                cls.source_type == source_type,
                cls.uri == uri,
            )
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        source_type: SourceKind | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Source"]:
        stmt = select(cls).order_by(cls.source_id.asc()).limit(limit)
        if source_type is not None:
            stmt = stmt.where(cls.source_type == source_type)
        if after_id is not None:
            stmt = stmt.where(cls.source_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        source_type: SourceKind,
        uri: str,
        metadata: dict[str, Any] | None = None,
        principal_id: uuid.UUID | None = None,
    ) -> "Source":
        new_id = new_uuid6()
        obj = cls(
            source_id=new_id,
            source_type=source_type,
            uri=uri,
            metadata=metadata,
            principal_id=principal_id,
            created_at=new_id,
        )
        session.add(obj)
        logger.info(
            "Created source",
            extra={
                "source_id": str(obj.source_id),
                "source_type": source_type.value,
            },
        )
        return obj


