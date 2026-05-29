import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import ClusterRole, HeadConstraint

logger = logging.getLogger(__name__)


class Cluster(Base):
    __tablename__ = "cluster"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    cluster_role: Mapped[ClusterRole] = mapped_column(
        SAEnum(ClusterRole, name="cluster_role_enum"), nullable=False
    )
    # Circular reference resolved with use_alter — cluster points to its head
    # commit, and commit points back to cluster. The FK is deferred to ALTER
    # TABLE so both tables can be created first.
    head_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commit.commit_id", use_alter=True, name="fk_cluster_head_commit_id"),
        nullable=True,
    )
    head_constraints: Mapped[HeadConstraint] = mapped_column(
        SAEnum(HeadConstraint, name="head_constraint_enum"), nullable=False
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates — work in Python and as SQL expressions
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_grounded(self) -> bool:  # type: ignore[misc]
        return self.cluster_role == ClusterRole.grounded_cluster

    @is_grounded.expression  # type: ignore[override]
    @classmethod
    def is_grounded(cls) -> sa.ColumnElement[bool]:
        return cls.cluster_role == ClusterRole.grounded_cluster.value

    @hybrid_property
    def is_mutable(self) -> bool:  # type: ignore[misc]
        return self.cluster_role == ClusterRole.mutable_cluster

    @is_mutable.expression  # type: ignore[override]
    @classmethod
    def is_mutable(cls) -> sa.ColumnElement[bool]:
        return cls.cluster_role == ClusterRole.mutable_cluster.value

    @hybrid_property
    def is_under_review(self) -> bool:  # type: ignore[misc]
        return self.cluster_role == ClusterRole.review_cluster

    @is_under_review.expression  # type: ignore[override]
    @classmethod
    def is_under_review(cls) -> sa.ColumnElement[bool]:
        return cls.cluster_role == ClusterRole.review_cluster.value

    @hybrid_property
    def is_authority(self) -> bool:  # type: ignore[misc]
        return self.cluster_role == ClusterRole.authority_cluster

    @is_authority.expression  # type: ignore[override]
    @classmethod
    def is_authority(cls) -> sa.ColumnElement[bool]:
        return cls.cluster_role == ClusterRole.authority_cluster.value

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> "Cluster | None":
        result = await session.execute(
            select(cls).where(cls.cluster_id == cluster_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_role(
        cls,
        session: AsyncSession,
        role: ClusterRole,
    ) -> list["Cluster"]:
        result = await session.execute(
            select(cls).where(cls.cluster_role == role)
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        cluster_role: ClusterRole,
        head_constraints: HeadConstraint,
        cluster_id: uuid.UUID | None = None,
    ) -> "Cluster":
        cluster = cls(
            cluster_id=cluster_id or new_uuid6(),
            cluster_role=cluster_role,
            head_commit_id=None,
            head_constraints=head_constraints,
        )
        session.add(cluster)
        logger.info(
            "Created cluster",
            extra={
                "cluster_id": str(cluster.cluster_id),
                "cluster_role": cluster_role.value,
                "head_constraints": head_constraints.value,
            },
        )
        return cluster

    # -------------------------------------------------------------------------
    # Instance-level operations
    # -------------------------------------------------------------------------

    async def update_head_commit(
        self,
        session: AsyncSession,
        commit_id: uuid.UUID,
        cluster_role: ClusterRole | None = None,
    ) -> None:
        old_head = self.head_commit_id
        self.head_commit_id = commit_id
        if cluster_role is not None:
            self.cluster_role = cluster_role
        session.add(self)
        logger.info(
            "Updated cluster head commit",
            extra={
                "cluster_id": str(self.cluster_id),
                "old_head_commit_id": str(old_head) if old_head else None,
                "new_head_commit_id": str(commit_id),
                "new_role": cluster_role.value if cluster_role else None,
            },
        )
