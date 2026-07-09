"""DOCUMENT_MENTION table model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6

if TYPE_CHECKING:
    class Mention: ...

    class Information: ...


class DocumentMention(Base):
    """Document-level aggregator combining mention and information output."""

    __tablename__ = "document_mention"

    document_mention_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    information: Mapped[str] = mapped_column(String, nullable=False)
    model_agent_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("principal.principal_id"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source.source_id"), nullable=False
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.identity_id"), nullable=False
    )

    mentions: Mapped[list["Mention"]] = relationship(
        "Mention",
        back_populates="document_mention",
        lazy="selectin",
    )
    information_records: Mapped[list["Information"]] = relationship(
        "Information",
        back_populates="document_mention",
        lazy="selectin",
    )

    __table_args__ = (
        sa.Index("ix_document_mention_model_agent_id", "model_agent_id"),
        sa.Index("ix_document_mention_source_id", "source_id"),
        sa.Index("ix_document_mention_identity_id", "identity_id"),
    )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        document_mention_id: uuid.UUID,
    ) -> "DocumentMention | None":
        result = await session.scalars(
            select(cls).where(cls.document_mention_id == document_mention_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID | None = None,
        source_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["DocumentMention"]:
        stmt = select(cls).order_by(cls.document_mention_id.asc()).limit(limit)
        if identity_id is not None:
            stmt = stmt.where(cls.identity_id == identity_id)
        if source_id is not None:
            stmt = stmt.where(cls.source_id == source_id)
        if after_id is not None:
            stmt = stmt.where(cls.document_mention_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        name: str,
        information: str,
        model_agent_id: uuid.UUID,
        source_id: uuid.UUID,
        identity_id: uuid.UUID,
    ) -> "DocumentMention":
        item = cls(
            document_mention_id=new_uuid6(),
            name=name,
            information=information,
            model_agent_id=model_agent_id,
            source_id=source_id,
            identity_id=identity_id,
        )
        session.add(item)
        return item
