"""IDENTITY table model."""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class Identity(Base):
    """A distinct person identity."""

    __tablename__ = "identity"

    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_identity_principal_id", "principal_id"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID,
    ) -> "Identity | None":
        result = await session.scalars(
            select(cls).where(cls.identity_id == identity_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Identity"]:
        stmt = select(cls).order_by(cls.identity_id.asc()).limit(limit)
        if after_id is not None:
            stmt = stmt.where(cls.identity_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        principal_id: uuid.UUID,
        identity_id: uuid.UUID | None = None,
    ) -> "Identity":
        new_id = identity_id or new_uuid6()
        identity = cls(
            identity_id=new_id,
            principal_id=principal_id,
        )
        session.add(identity)
        logger.info(
            "Created identity",
            extra={"identity_id": str(identity.identity_id)},
        )
        return identity
