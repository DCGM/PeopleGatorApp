"""INFORMATION table model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Text, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6

if TYPE_CHECKING:
    from people_gator_api.models.annotation.document_mention import DocumentMention


class Information(Base):
    """Relevant information extracted from page-level content."""

    __tablename__ = "information"

    information_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    document_mention_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_mention.document_mention_id"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source.source_id"), nullable=False
    )
    model_agent_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("principal.principal_id"), nullable=False
    )

    document_mention: Mapped["DocumentMention"] = relationship(
        "DocumentMention",
        back_populates="information_records",
    )

    __table_args__ = (
        sa.Index("ix_information_source_id", "source_id"),
        sa.Index("ix_information_model_agent_id", "model_agent_id"),
    )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        information_id: uuid.UUID,
    ) -> "Information | None":
        result = await session.scalars(
            select(cls).where(cls.information_id == information_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Information"]:
        stmt = select(cls).order_by(cls.information_id.asc()).limit(limit)
        if source_id is not None:
            stmt = stmt.where(cls.source_id == source_id)
        if after_id is not None:
            stmt = stmt.where(cls.information_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        text: str,
        document_mention_id: uuid.UUID,
        source_id: uuid.UUID,
        model_agent_id: uuid.UUID,
    ) -> "Information":
        item = cls(
            information_id=new_uuid6(),
            text=text,
            document_mention_id=document_mention_id,
            source_id=source_id,
            model_agent_id=model_agent_id,
        )
        session.add(item)
        return item
