"""Consensus model — multi-annotator annotation adjudication (spec §2.6).

Annotators do not directly modify identity state.  Instead they create
immutable LINK_DECISION records about whether a specific annotation belongs
to an identity.  A separate explicit LINK_CONSENSUS snapshot is then
created from these decisions and attached to the identity as its current
state.

This design preserves individual annotator decisions, supports multiple
consensus methods (union/majority/reviewer), and lets annotators inspect
whether their decisions were included in, contradicted by, or ignored by
the current consensus.
"""

import logging
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.models.enums import ConsensusMethod
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class LinkDecision(Base):
    """An immutable decision by one annotator about one annotation's identity.

    Multiple annotators may create decisions for the same
    ``(identity_id, annotation_id)`` triple.  The same
    annotator may create multiple decisions over time; the latest decision
    (by ``created_at``) is used when generating a new consensus (spec §2.6.1).
    """

    __tablename__ = "link_decision"
    annotation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("base_annotation.annotation_id"),
        nullable=False,
        primary_key=True,
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
        primary_key=True,
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.identity_id"),
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=sa.func.now()
    )

    __table_args__ = (
        sa.Index("ix_link_decision_identity_id", "identity_id"),
        sa.Index("ix_link_decision_principal_id", "principal_id"),
        sa.Index(
            "ix_link_decision_target",
            "identity_id",
            "annotation_id",
        ),
        sa.Index(
            "ix_link_decision_target_principal",
            "identity_id",
            "annotation_id",
            "principal_id",
        ),
        sa.Index("ix_link_decision_created_at", "created_at"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        annotation_id: uuid.UUID,
        principal_id: uuid.UUID,
    ) -> "LinkDecision | None":
        result = await session.scalars(
            select(cls).where(
                cls.annotation_id == annotation_id,
                cls.principal_id == principal_id
            )
        )
        return result.one_or_none()

    @classmethod
    async def list_for_target(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID,
        principal_id: uuid.UUID,
    ) -> list["LinkDecision"]:
        """Return all decisions for a specific annotation target, newest first."""
        result = await session.execute(
            select(cls)
            .where(
                cls.identity_id == identity_id,
                cls.principal_id == principal_id,
            )
            .order_by(cls.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def list_for_identity(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID,
    ) -> list["LinkDecision"]:
        """Return all decisions for an identity, newest first."""
        result = await session.execute(
            select(cls)
            .where(cls.identity_id == identity_id)
            .order_by(cls.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID,
        annotation_id: uuid.UUID,
        principal_id: uuid.UUID,
        confidence: float | None = None,
    ) -> "LinkDecision":
        obj = cls(
            decision_id=new_uuid6(),
            identity_id=identity_id,
            annotation_id=annotation_id,
            principal_id=principal_id,
            confidence=confidence,
        )
        session.add(obj)
        logger.info(
            "Created link decision",
            extra={
                "annotation_id": str(annotation_id),
                "identity_id": str(identity_id),
                "principal_id": str(principal_id),
            },
        )
        return obj


class LinkConsensus(Base):
    """An explicitly created consensus for a single evidence annotation.

    At most one consensus row exists per
    ``(identity_id, annotation_id)`` triple — the unique
    constraint prevents assigning conflicting consensus decisions to the
    same evidence item (spec §2.6.3).  The latest consensus for each target
    represents the identity's current view.
    """

    __tablename__ = "link_consensus"
    annotation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("base_annotation.annotation_id"),
        nullable=False,
        primary_key=True,
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.identity_id"),
        nullable=False,
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )
    method: Mapped[ConsensusMethod] = mapped_column(
        SAEnum(ConsensusMethod, name="consensus_method_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=sa.func.now()
    )

    __table_args__ = (
        # One consensus per evidence item — avoids conflicting consensus
        # decisions on the same annotation (spec §2.6.3 constraints).
        UniqueConstraint(
            "identity_id",
            "annotation_id",
            name="uq_link_consensus_target",
        ),
        sa.Index("ix_link_consensus_identity_id", "identity_id"),
        sa.Index("ix_link_consensus_method", "method"),
        sa.Index("ix_link_consensus_principal_id", "principal_id"),
        sa.Index("ix_link_consensus_created_at", "created_at"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        annotation_id: uuid.UUID,
    ) -> "LinkConsensus | None":
        result = await session.scalars(
            select(cls).where(cls.annotation_id == annotation_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_for_identity(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID,
    ) -> list["LinkConsensus"]:
        """Return all consensus rows for an identity."""
        result = await session.execute(
            select(cls)
            .where(cls.identity_id == identity_id)
            .order_by(cls.annotation_id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        identity_id: uuid.UUID,
        annotation_id: uuid.UUID,
        method: ConsensusMethod,
        created_by: uuid.UUID,
        decision_cutoff_at: datetime | None = None,
    ) -> "LinkConsensus":
        obj = cls(
            consensus_id=new_uuid6(),
            identity_id=identity_id,
            annotation_id=annotation_id,
            method=method,
            created_by=created_by,
            decision_cutoff_at=decision_cutoff_at,
        )
        session.add(obj)
        logger.info(
            "Created link consensus",
            extra={
                "annotation_id": str(annotation_id),
                "identity_id": str(identity_id),
                "method": method.value,
            },
        )
        return obj
