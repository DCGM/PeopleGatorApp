import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, Float, ForeignKeyConstraint, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import ActionReason, ActionType

logger = logging.getLogger(__name__)


class Action(Base):
    """Associates a RECORD with a specific CLUSTER VERSION.

    Represents the addition or removal of a record from a cluster at the given
    version.  The ``action_id`` is UUID v6 so sorting ascending gives
    creation-time order, which is required by the membership resolution
    algorithm.
    """

    __tablename__ = "action"

    action_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # Denormalized from COMMIT for query performance.
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cluster.cluster_id"),
        nullable=False,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("version.version_id"),
        nullable=False,
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    record_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    action_type: Mapped[ActionType] = mapped_column(
        SAEnum(ActionType, name="action_type_enum"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    reason: Mapped[str] = mapped_column(
        SAEnum(ActionReason, name="action_reason_enum"), nullable=False
    )
    # The principal (user or service agent) that authored this action.
    actor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("principal.principal_id"),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["record_id", "record_version_id"],
            ["record.record_id", "record.record_version_id"],
            name="fk_action_record_version",
        ),
        sa.Index("ix_action_cluster_version", "cluster_id", "version_id"),
        sa.Index("ix_action_record", "record_id", "record_version_id"),
        sa.Index("ix_action_actor", "actor_id"),
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_add(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.action_type == ActionType.add

    @is_add.expression
    @classmethod
    def is_add(cls) -> sa.ColumnElement[bool]:
        return cls.action_type == ActionType.add.value

    @hybrid_property
    def is_remove(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.action_type == ActionType.remove

    @is_remove.expression
    @classmethod
    def is_remove(cls) -> sa.ColumnElement[bool]:
        return cls.action_type == ActionType.remove.value

    @hybrid_method
    def matches_record(self, record_id: uuid.UUID) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.record_id == record_id

    @matches_record.expression
    @classmethod
    def matches_record(cls, record_id: uuid.UUID) -> sa.ColumnElement[bool]:
        return cls.record_id == record_id

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_for_version(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> list["Action"]:
        result = await session.execute(
            select(cls)
            .where(
                cls.cluster_id == cluster_id,
                cls.version_id == version_id,
            )
            .order_by(cls.action_id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
        record_id: uuid.UUID,
        record_version_id: uuid.UUID,
        action_type: ActionType,
        reason: ActionReason,
        actor_id: uuid.UUID,
        weight: float = 1.0,
    ) -> "Action":
        action = cls(
            action_id=new_uuid6(),
            cluster_id=cluster_id,
            version_id=version_id,
            record_id=record_id,
            record_version_id=record_version_id,
            action_type=action_type,
            weight=weight,
            reason=reason,
            actor_id=actor_id,
        )
        session.add(action)
        logger.debug(
            "Created action",
            extra={
                "action_id": str(action.action_id),
                "cluster_id": str(cluster_id),
                "version_id": str(version_id),
                "record_id": str(record_id),
                "record_version_id": str(record_version_id),
                "action_type": action_type.value,
                "reason": reason.value,
                "actor_id": str(actor_id),
                "weight": weight,
            },
        )
        return action
