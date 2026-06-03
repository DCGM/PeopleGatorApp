import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Float, ForeignKeyConstraint, delete, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base

logger = logging.getLogger(__name__)


class Membership(Base):
    """Materialized current membership for each cluster.

    Derived from the DELTA table by replaying the OPERATION DAG.  Updated
    in the same transaction as each OPERATION that seals a version.

    ``as_of_version_id`` equals ``CLUSTER.head_version_id`` at the time of
    the last update, enabling staleness detection.
    """

    __tablename__ = "membership"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cluster.cluster_id"),
        primary_key=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    evidence_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    as_of_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("version.version_id"),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["evidence_id", "evidence_version_id"],
            ["evidence.evidence_id", "evidence.evidence_version_id"],
            name="fk_membership_evidence_version",
        ),
        sa.Index("ix_membership_cluster_id", "cluster_id"),
        sa.Index("ix_membership_evidence_id", "evidence_id"),
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_method
    def has_evidence(self, evidence_id: uuid.UUID) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.evidence_id == evidence_id

    @has_evidence.expression
    @classmethod
    def has_evidence(cls, evidence_id: uuid.UUID) -> sa.ColumnElement[bool]:
        return cls.evidence_id == evidence_id

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
        evidence_id: uuid.UUID,
    ) -> "Membership | None":
        result = await session.scalars(
            select(cls).where(
                cls.cluster_id == cluster_id,
                cls.evidence_id == evidence_id,
            )
        )
        return result.one_or_none()

    @classmethod
    async def upsert(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        evidence_id: uuid.UUID,
        evidence_version_id: uuid.UUID,
        weight: float,
        as_of_version_id: uuid.UUID,
    ) -> None:
        stmt = pg_insert(cls).values(
            cluster_id=cluster_id,
            evidence_id=evidence_id,
            evidence_version_id=evidence_version_id,
            weight=weight,
            as_of_version_id=as_of_version_id,
        ).on_conflict_do_update(
            index_elements=["cluster_id", "evidence_id"],
            set_={
                "evidence_version_id": evidence_version_id,
                "weight": weight,
                "as_of_version_id": as_of_version_id,
            },
        )
        await session.execute(stmt)

    @classmethod
    async def remove_entry(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        evidence_id: uuid.UUID,
    ) -> None:
        await session.execute(
            delete(cls).where(
                cls.cluster_id == cluster_id,
                cls.evidence_id == evidence_id,
            )
        )

    @classmethod
    async def delete_for_cluster(
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
