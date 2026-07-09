"""SOURCE table model."""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.models.enums import SourceKind
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)

type JsonValue = (
    str | int | float | bool | None | dict[str, "JsonValue"] | list["JsonValue"]
)


class Source(Base):
    """A source document or media record."""

    __tablename__ = "source"
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    source_type: Mapped[SourceKind] = mapped_column(
        SAEnum(SourceKind, name="source_kind_enum"), nullable=False
    )
    uri: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict[str, JsonValue] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    __table_args__ = (
        UniqueConstraint("source_type", "uri", name="uq_source_type_uri"),
        sa.Index("ix_source_source_type", "source_type"),
        sa.Index("ix_source_uri", "uri"),
        sa.Index("ix_source_metadata", "metadata", postgresql_using="gin")
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
        metadata: dict[str, JsonValue] | None = None,
    ) -> "Source":
        obj = cls(
            source_id=new_uuid6(),
            source_type=source_type,
            uri=uri,
            metadata_=metadata,
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


