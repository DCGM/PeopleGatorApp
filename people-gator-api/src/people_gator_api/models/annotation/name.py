"""NAME table model."""

import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Text, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6


class Name(Base):
    """Name record linked to an identity."""

    __tablename__ = "name"

    name_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source.source_id"), nullable=False
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.identity_id"), nullable=False
    )

    __table_args__ = (
        sa.Index("ix_name_source_id", "source_id"),
        sa.Index("ix_name_identity_id", "identity_id"),
    )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        name_id: uuid.UUID,
    ) -> "Name | None":
        result = await session.scalars(select(cls).where(cls.name_id == name_id))
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Name"]:
        stmt = select(cls).order_by(cls.name_id.asc()).limit(limit)
        if identity_id is not None:
            stmt = stmt.where(cls.identity_id == identity_id)
        if after_id is not None:
            stmt = stmt.where(cls.name_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        name: str,
        source_id: uuid.UUID,
        identity_id: uuid.UUID,
    ) -> "Name":
        item = cls(
            name_id=new_uuid6(),
            name=name,
            source_id=source_id,
            identity_id=identity_id,
        )
        session.add(item)
        return item
