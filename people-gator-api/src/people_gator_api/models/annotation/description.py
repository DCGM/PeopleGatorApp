"""DESCRIPTION table model."""

import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6


class Description(Base):
    """Description record linked to an entity."""

    __tablename__ = "description"

    description_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source.source_id"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entity.entity_id"), nullable=False
    )
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    model_identifier: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        sa.Index("ix_description_source_id", "source_id"),
        sa.Index("ix_description_entity_id", "entity_id"),
    )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        description_id: uuid.UUID,
    ) -> "Description | None":
        result = await session.scalars(
            select(cls).where(cls.description_id == description_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        entity_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Description"]:
        stmt = select(cls).order_by(cls.description_id.asc()).limit(limit)
        if entity_id is not None:
            stmt = stmt.where(cls.entity_id == entity_id)
        if after_id is not None:
            stmt = stmt.where(cls.description_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        text: str,
        language: str,
        source_id: uuid.UUID,
        entity_id: uuid.UUID,
        embedding: list[float] | None = None,
        model_identifier: str | None = None,
    ) -> "Description":
        item = cls(
            description_id=new_uuid6(),
            text=text,
            language=language,
            source_id=source_id,
            entity_id=entity_id,
            embedding=embedding,
            model_identifier=model_identifier,
        )
        session.add(item)
        return item
