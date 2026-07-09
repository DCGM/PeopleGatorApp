"""IDENTITY table — the central entity representing a distinct person.

All annotations (named entities, detections, descriptions, alternative
names) link to one or more identities through the *_LINK join tables and
are adjudicated through the LINK_DECISION / LINK_CONSENSUS consensus model
(spec §2.1, §2.6).

The ``identity_id`` is a UUIDv6 whose embedded timestamp serves as the
creation time — there is no separate ``created_at`` column.
"""

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
    """A distinct person identity that annotations relate to.

    An identity is created by a principal (user, service agent, or model
    agent) and accrues annotations over time.  Its current "view" is the
    set of annotations whose latest LINK_CONSENSUS decision is ``include``.
    """

    __tablename__ = "identity"

    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # UUIDv6 timestamp embedded in identity_id serves as created_at; kept
    # as an explicit column for ergonomic querying and indexing.
    created_at: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    # FK → PRINCIPAL — who created this identity.
    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_identity_created_at", "created_at"),
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
            created_at=new_id,
            principal_id=principal_id,
        )
        session.add(identity)
        logger.info(
            "Created identity",
            extra={"identity_id": str(identity.identity_id)},
        )
        return identity
