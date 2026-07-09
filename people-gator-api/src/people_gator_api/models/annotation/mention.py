"""MENTION table model."""

import uuid

import sqlalchemy as sa
from sqlalchemy import Float, ForeignKey, Integer, Text, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6


class Mention(Base):
    """Text mention extracted from a source."""

    __tablename__ = "mention"

    mention_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    offset_start: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_end: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source.source_id"), nullable=False
    )
    model_agent_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("principal.principal_id"), nullable=False
    )

    __table_args__ = (
        sa.Index("ix_mention_source_id", "source_id"),
        sa.Index("ix_mention_model_agent_id", "model_agent_id"),
    )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        mention_id: uuid.UUID,
    ) -> "Mention | None":
        result = await session.scalars(select(cls).where(cls.mention_id == mention_id))
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Mention"]:
        stmt = select(cls).order_by(cls.mention_id.asc()).limit(limit)
        if source_id is not None:
            stmt = stmt.where(cls.source_id == source_id)
        if after_id is not None:
            stmt = stmt.where(cls.mention_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        text: str,
        source_id: uuid.UUID,
        offset_start: int,
        offset_end: int,
        model_agent_id: uuid.UUID,
        confidence: float,
    ) -> "Mention":
        item = cls(
            mention_id=new_uuid6(),
            text=text,
            source_id=source_id,
            offset_start=offset_start,
            offset_end=offset_end,
            model_agent_id=model_agent_id,
            confidence=confidence,
        )
        session.add(item)
        return item
