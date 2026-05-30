import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Float, ForeignKeyConstraint, String, delete, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base

logger = logging.getLogger(__name__)


class Membership(Base):
    """Materialized current membership for each cluster.

    Updated in the same transaction as every ACTION write.  The
    The ``as_of_version_id`` records which version this state was derived from —
    equal to ``CLUSTER.head_version_id`` at the time of the last update.
    """

    __tablename__ = "membership"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cluster.cluster_id"),
        primary_key=True,
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    record_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    as_of_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("version.version_id"),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["record_id", "record_version_id"],
            ["record.record_id", "record.record_version_id"],
            name="fk_membership_record_version",
        ),
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_method
    def has_record(self, record_id: uuid.UUID) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.record_id == record_id

    @has_record.expression
    @classmethod
    def has_record(cls, record_id: uuid.UUID) -> sa.ColumnElement[bool]:
        return cls.record_id == record_id

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_for_cluster(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> list["Membership"]:
        result = await session.execute(
            select(cls).where(cls.cluster_id == cluster_id)
        )
        return list(result.scalars().all())

    @classmethod
    async def get_entry(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> "Membership | None":
        result = await session.execute(
            select(cls).where(
                cls.cluster_id == cluster_id,
                cls.record_id == record_id,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def upsert(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        record_id: uuid.UUID,
        record_version_id: uuid.UUID,
        weight: float,
        reason: str,
        as_of_version_id: uuid.UUID,
    ) -> None:
        stmt = (
            pg_insert(cls)
            .values(
                cluster_id=cluster_id,
                record_id=record_id,
                record_version_id=record_version_id,
                weight=weight,
                reason=reason,
                as_of_version_id=as_of_version_id,
            )
            .on_conflict_do_update(
                index_elements=["cluster_id", "record_id"],
                set_={
                    "record_version_id": record_version_id,
                    "weight": weight,
                    "reason": reason,
                    "as_of_version_id": as_of_version_id,
                },
            )
        )
        await session.execute(stmt)
        logger.debug(
            "Upserted membership entry",
            extra={
                "cluster_id": str(cluster_id),
                "record_id": str(record_id),
                "record_version_id": str(record_version_id),
                "as_of_version_id": str(as_of_version_id),
            },
        )

    @classmethod
    async def delete_record(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> None:
        await session.execute(
            delete(cls).where(
                cls.cluster_id == cluster_id,
                cls.record_id == record_id,
            )
        )
        logger.debug(
            "Deleted membership entry",
            extra={"cluster_id": str(cluster_id), "record_id": str(record_id)},
        )

    @classmethod
    async def delete_all_for_cluster(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> None:
        await session.execute(
            delete(cls).where(cls.cluster_id == cluster_id)
        )
        logger.debug(
            "Cleared all membership entries for cluster",
            extra={"cluster_id": str(cluster_id)},
        )
