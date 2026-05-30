import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import ClusterRole

logger = logging.getLogger(__name__)


class Version(Base):
    __tablename__ = "version"

    version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cluster.cluster_id"),
        nullable=False,
    )
    # Source of truth for cluster_role at this commit version.
    cluster_role: Mapped[ClusterRole] = mapped_column(
        SAEnum(ClusterRole, name="cluster_role_enum"),
        nullable=False,
    )
    # The principal (user or service agent) that created this commit version.
    actor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates — work in Python and as SQL expressions
    # -------------------------------------------------------------------------

    @hybrid_method
    def belongs_to_cluster(self, cluster_id: uuid.UUID) -> bool:  # type: ignore[misc]
        return self.cluster_id == cluster_id

    @belongs_to_cluster.expression  # type: ignore[override]
    @classmethod
    def belongs_to_cluster(cls, cluster_id: uuid.UUID) -> sa.ColumnElement[bool]:
        return cls.cluster_id == cluster_id

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        version_id: uuid.UUID,
    ) -> "Version | None":
        result = await session.execute(
            select(cls).where(cls.version_id == version_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_for_cluster(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> list["Version"]:
        result = await session.execute(
            select(cls)
            .where(cls.cluster_id == cluster_id)
            .order_by(cls.version_id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        cluster_role: ClusterRole,
        actor_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
    ) -> "Version":
        version = cls(
            version_id=version_id or new_uuid6(),
            cluster_id=cluster_id,
            cluster_role=cluster_role,
            actor_id=actor_id,
        )
        session.add(version)
        logger.info(
            "Created version",
            extra={
                "version_id": str(version.version_id),
                "cluster_id": str(cluster_id),
                "cluster_role": cluster_role.value,
                "actor_id": str(actor_id),
            },
        )
        return version
