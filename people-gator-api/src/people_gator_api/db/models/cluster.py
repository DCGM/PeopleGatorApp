import logging
import uuid
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6

logger = logging.getLogger(__name__)


class Cluster(Base):
    """Stable identity for a cluster across its entire version history.

    ``cluster_role`` is **not** stored here — it is computed on read from
    ``VERSION.cluster_role`` via ``head_version_id``.  This eliminates the
    dual-write invariant that required application-level enforcement.

    The ``head_version_id`` is advanced using an optimistic CAS UPDATE:

        UPDATE cluster
        SET head_version_id = :new_id
        WHERE cluster_id = :id AND head_version_id = :expected_id

    If zero rows are updated a concurrent write raced ahead and the caller
    must re-read before retrying.
    """

    __tablename__ = "cluster"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # Circular reference resolved with use_alter — cluster points to its head
    # version, and version points back to cluster.
    head_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "version.version_id",
            use_alter=True,
            name="fk_cluster_head_version_id",
        ),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> "Cluster | None":
        result = await session.scalars(
            select(cls).where(cls.cluster_id == cluster_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Cluster"]:
        stmt = select(cls).order_by(cls.cluster_id.asc()).limit(limit)
        if after_id is not None:
            stmt = stmt.where(cls.cluster_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
    ) -> "Cluster":
        cluster = cls(cluster_id=new_uuid6(), head_version_id=None)
        session.add(cluster)
        logger.info("Created cluster", extra={"cluster_id": str(cluster.cluster_id)})
        return cluster

    async def advance_head(
        self,
        session: AsyncSession,
        new_version_id: uuid.UUID,
        expected_current_id: uuid.UUID | None,
    ) -> bool:
        """Optimistic CAS update for head_version_id.

        Returns True when the update succeeded, False when a concurrent write
        raced ahead (caller should re-read and retry).
        """
        stmt = (
            sa.update(Cluster)
            .where(
                Cluster.cluster_id == self.cluster_id,
                Cluster.head_version_id == expected_current_id,
            )
            .values(head_version_id=new_version_id)
        )
        result = cast(CursorResult[Any], await session.execute(stmt))
        if result.rowcount == 0:
            return False
        self.head_version_id = new_version_id
        return True


