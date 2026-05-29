import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import LineageType

logger = logging.getLogger(__name__)


class Lineage(Base):
    """One directed edge in the version DAG.

    For ``initial``: source fields are NULL.
    For ``merge``/``cluster_merge``: multiple rows share the same
    ``target_commit_id`` — one row per source commit.
    For ``split``: multiple rows share the same ``source_commit_id`` — one row
    per target commit.
    """

    __tablename__ = "lineage"

    # Surrogate PK — the natural key has no single-column identity for merge
    # rows (multiple sources → one target) or split rows.
    lineage_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    lineage_type: Mapped[LineageType] = mapped_column(
        SAEnum(LineageType, name="lineage_type_enum"), nullable=False
    )
    source_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cluster.cluster_id"),
        nullable=True,
    )
    source_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commit.commit_id"),
        nullable=True,
    )
    target_cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cluster.cluster_id"),
        nullable=False,
    )
    target_commit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commit.commit_id"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_initial(self) -> bool:  # type: ignore[misc]
        return self.lineage_type == LineageType.initial

    @is_initial.expression  # type: ignore[override]
    @classmethod
    def is_initial(cls) -> sa.ColumnElement[bool]:
        return cls.lineage_type == LineageType.initial.value

    @hybrid_property
    def is_cross_cluster(self) -> bool:  # type: ignore[misc]
        return self.lineage_type == LineageType.cluster_merge

    @is_cross_cluster.expression  # type: ignore[override]
    @classmethod
    def is_cross_cluster(cls) -> sa.ColumnElement[bool]:
        return cls.lineage_type == LineageType.cluster_merge.value

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_ancestors_of(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        commit_id: uuid.UUID,
    ) -> list["Lineage"]:
        """Return all lineage entries that point TO the given commit."""
        result = await session.execute(
            select(cls).where(
                cls.target_cluster_id == cluster_id,
                cls.target_commit_id == commit_id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def get_descendants_of(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        commit_id: uuid.UUID,
    ) -> list["Lineage"]:
        """Return all lineage entries that originate FROM the given commit."""
        result = await session.execute(
            select(cls).where(
                cls.source_cluster_id == cluster_id,
                cls.source_commit_id == commit_id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def get_for_cluster(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> list["Lineage"]:
        """Return all lineage entries whose target belongs to this cluster."""
        result = await session.execute(
            select(cls)
            .where(cls.target_cluster_id == cluster_id)
            .order_by(cls.target_commit_id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_initial_commit_id(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """Return the commit_id of the initial commit for a cluster."""
        result = await session.execute(
            select(cls.target_commit_id).where(
                cls.target_cluster_id == cluster_id,
                cls.lineage_type == LineageType.initial,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def create_initial(
        cls,
        session: AsyncSession,
        target_cluster_id: uuid.UUID,
        target_commit_id: uuid.UUID,
    ) -> "Lineage":
        entry = cls(
            lineage_id=new_uuid6(),
            lineage_type=LineageType.initial,
            source_cluster_id=None,
            source_commit_id=None,
            target_cluster_id=target_cluster_id,
            target_commit_id=target_commit_id,
        )
        session.add(entry)
        logger.info(
            "Created initial lineage entry",
            extra={
                "target_cluster_id": str(target_cluster_id),
                "target_commit_id": str(target_commit_id),
            },
        )
        return entry

    @classmethod
    async def create_next(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        source_commit_id: uuid.UUID,
        target_commit_id: uuid.UUID,
    ) -> "Lineage":
        entry = cls(
            lineage_id=new_uuid6(),
            lineage_type=LineageType.next,
            source_cluster_id=cluster_id,
            source_commit_id=source_commit_id,
            target_cluster_id=cluster_id,
            target_commit_id=target_commit_id,
        )
        session.add(entry)
        logger.info(
            "Created next lineage entry",
            extra={
                "cluster_id": str(cluster_id),
                "source_commit_id": str(source_commit_id),
                "target_commit_id": str(target_commit_id),
            },
        )
        return entry

    @classmethod
    async def create_branch(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        source_commit_id: uuid.UUID,
        target_commit_id: uuid.UUID,
    ) -> "Lineage":
        entry = cls(
            lineage_id=new_uuid6(),
            lineage_type=LineageType.branch,
            source_cluster_id=cluster_id,
            source_commit_id=source_commit_id,
            target_cluster_id=cluster_id,
            target_commit_id=target_commit_id,
        )
        session.add(entry)
        logger.info(
            "Created branch lineage entry",
            extra={
                "cluster_id": str(cluster_id),
                "source_commit_id": str(source_commit_id),
                "target_commit_id": str(target_commit_id),
            },
        )
        return entry

    @classmethod
    async def create_merge_entry(
        cls,
        session: AsyncSession,
        source_cluster_id: uuid.UUID,
        source_commit_id: uuid.UUID,
        target_cluster_id: uuid.UUID,
        target_commit_id: uuid.UUID,
        lineage_type: LineageType = LineageType.merge,
    ) -> "Lineage":
        """Create one row of a merge (call once per source commit)."""
        entry = cls(
            lineage_id=new_uuid6(),
            lineage_type=lineage_type,
            source_cluster_id=source_cluster_id,
            source_commit_id=source_commit_id,
            target_cluster_id=target_cluster_id,
            target_commit_id=target_commit_id,
        )
        session.add(entry)
        logger.info(
            "Created merge lineage entry",
            extra={
                "lineage_type": lineage_type.value,
                "source_cluster_id": str(source_cluster_id),
                "source_commit_id": str(source_commit_id),
                "target_cluster_id": str(target_cluster_id),
                "target_commit_id": str(target_commit_id),
            },
        )
        return entry

    @classmethod
    async def create_split_entry(
        cls,
        session: AsyncSession,
        source_cluster_id: uuid.UUID,
        source_commit_id: uuid.UUID,
        target_cluster_id: uuid.UUID,
        target_commit_id: uuid.UUID,
    ) -> "Lineage":
        """Create one row of a split (call once per target commit)."""
        entry = cls(
            lineage_id=new_uuid6(),
            lineage_type=LineageType.cluster_split,
            source_cluster_id=source_cluster_id,
            source_commit_id=source_commit_id,
            target_cluster_id=target_cluster_id,
            target_commit_id=target_commit_id,
        )
        session.add(entry)
        logger.info(
            "Created split lineage entry",
            extra={
                "source_cluster_id": str(source_cluster_id),
                "source_commit_id": str(source_commit_id),
                "target_cluster_id": str(target_cluster_id),
                "target_commit_id": str(target_commit_id),
            },
        )
        return entry
