"""DELTA table — evidence additions and removals for a specific CLUSTER VERSION.

DELTAs may only be written to an unsealed (working) version — a version that
does not yet appear as ``source_version_id`` in any OPERATION row.

``delta_id`` is a UUIDv6 so sorting ascending gives creation-time order,
which is required by the membership resolution algorithm (§4.8.1).
"""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, Float, ForeignKeyConstraint, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import DeltaType

logger = logging.getLogger(__name__)


class Delta(Base):
    """Associates an EVIDENCE item (as an add or remove) with a CLUSTER VERSION.

    The composite FK ``(version_id, cluster_id) → VERSION (version_id, cluster_id)``
    means the DB enforces that ``cluster_id`` always matches the cluster of the
    referenced version — no application-level invariant required.
    """

    __tablename__ = "delta"

    delta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # Denormalised from VERSION for query performance.
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cluster.cluster_id"),
        nullable=False,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    evidence_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    delta_type: Mapped[DeltaType] = mapped_column(
        SAEnum(DeltaType, name="delta_type_enum"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # FK → PRINCIPAL — the user, service agent, or model agent that authored this.
    actor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("principal.principal_id"),
        nullable=False,
    )

    __table_args__ = (
        # Composite FK enforces (version_id, cluster_id) consistency with VERSION.
        ForeignKeyConstraint(
            ["version_id", "cluster_id"],
            ["version.version_id", "version.cluster_id"],
            name="fk_delta_version_cluster",
        ),
        # Evidence FK.
        ForeignKeyConstraint(
            ["evidence_id", "evidence_version_id"],
            ["evidence.evidence_id", "evidence.evidence_version_id"],
            name="fk_delta_evidence_version",
        ),
        sa.Index("ix_delta_cluster_version", "cluster_id", "version_id"),
        sa.Index("ix_delta_evidence", "evidence_id", "evidence_version_id"),
        sa.Index("ix_delta_actor", "actor_id"),
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_add(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.delta_type == DeltaType.add

    @is_add.expression
    @classmethod
    def is_add(cls) -> sa.ColumnElement[bool]:
        return cls.delta_type == DeltaType.add.value

    @hybrid_property
    def is_remove(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.delta_type == DeltaType.remove

    @is_remove.expression
    @classmethod
    def is_remove(cls) -> sa.ColumnElement[bool]:
        return cls.delta_type == DeltaType.remove.value

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_for_version(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> list["Delta"]:
        """Return all deltas for a version, sorted by delta_id (creation order)."""
        result = await session.execute(
            select(cls)
            .where(
                cls.cluster_id == cluster_id,
                cls.version_id == version_id,
            )
            .order_by(cls.delta_id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
        evidence_id: uuid.UUID,
        evidence_version_id: uuid.UUID,
        delta_type: DeltaType,
        actor_id: uuid.UUID,
        weight: float = 1.0,
    ) -> "Delta":
        delta = cls(
            delta_id=new_uuid6(),
            cluster_id=cluster_id,
            version_id=version_id,
            evidence_id=evidence_id,
            evidence_version_id=evidence_version_id,
            delta_type=delta_type,
            weight=weight,
            actor_id=actor_id,
        )
        session.add(delta)
        logger.debug(
            "Created delta",
            extra={
                "delta_id": str(delta.delta_id),
                "cluster_id": str(cluster_id),
                "version_id": str(version_id),
                "evidence_id": str(evidence_id),
                "delta_type": delta_type.value,
            },
        )
        return delta
