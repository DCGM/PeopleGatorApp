import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import TransitionType

logger = logging.getLogger(__name__)


class Transition(Base):
    """One directed edge in the version DAG.

    For ``initial``: source fields are NULL.
    For ``merge``/``cluster_merge``: multiple rows share the same
    ``target_version_id`` — one row per source version.
    For ``split``: multiple rows share the same ``source_version_id`` — one row
    per target version.
    """

    __tablename__ = "transition"

    # Surrogate PK — the natural key has no single-column identity for merge
    # rows (multiple sources → one target) or split rows.
    transition_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    transition_type: Mapped[TransitionType] = mapped_column(
        SAEnum(TransitionType, name="transition_type_enum"), nullable=False
    )
    source_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cluster.cluster_id"),
        nullable=True,
    )
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("version.version_id"),
        nullable=True,
    )
    target_cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cluster.cluster_id"),
        nullable=False,
    )
    target_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("version.version_id"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_initial(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.transition_type == TransitionType.initial

    @is_initial.expression
    @classmethod
    def is_initial(cls) -> sa.ColumnElement[bool]:
        return cls.transition_type == TransitionType.initial.value

    @hybrid_property
    def is_cross_cluster(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.transition_type == TransitionType.cluster_merge

    @is_cross_cluster.expression
    @classmethod
    def is_cross_cluster(cls) -> sa.ColumnElement[bool]:
        return cls.transition_type == TransitionType.cluster_merge.value

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_ancestors_of(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> list["Transition"]:
        """Return all transition entries that point TO the given version."""
        result = await session.execute(
            select(cls).where(
                cls.target_cluster_id == cluster_id,
                cls.target_version_id == version_id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def get_descendants_of(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> list["Transition"]:
        """Return all transition entries that originate FROM the given version."""
        result = await session.execute(
            select(cls).where(
                cls.source_cluster_id == cluster_id,
                cls.source_version_id == version_id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def get_for_cluster(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> list["Transition"]:
        """Return all transition entries whose target belongs to this cluster."""
        result = await session.execute(
            select(cls)
            .where(cls.target_cluster_id == cluster_id)
            .order_by(cls.target_version_id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_initial_version_id(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """Return the version_id of the initial version for a cluster."""
        result = await session.scalars(
            select(cls.target_version_id).where(
                cls.target_cluster_id == cluster_id,
                cls.transition_type == TransitionType.initial,
            )
        )
        return result.one_or_none()

    @classmethod
    async def create_initial(
        cls,
        session: AsyncSession,
        target_cluster_id: uuid.UUID,
        target_version_id: uuid.UUID,
    ) -> "Transition":
        entry = cls(
            transition_id=new_uuid6(),
            transition_type=TransitionType.initial,
            source_cluster_id=None,
            source_version_id=None,
            target_cluster_id=target_cluster_id,
            target_version_id=target_version_id,
        )
        session.add(entry)
        logger.info(
            "Created initial transition entry",
            extra={
                "target_cluster_id": str(target_cluster_id),
                "target_version_id": str(target_version_id),
            },
        )
        return entry

    @classmethod
    async def create_next(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        source_version_id: uuid.UUID,
        target_version_id: uuid.UUID,
    ) -> "Transition":
        entry = cls(
            transition_id=new_uuid6(),
            transition_type=TransitionType.next,
            source_cluster_id=cluster_id,
            source_version_id=source_version_id,
            target_cluster_id=cluster_id,
            target_version_id=target_version_id,
        )
        session.add(entry)
        logger.info(
            "Created next transition entry",
            extra={
                "cluster_id": str(cluster_id),
                "source_version_id": str(source_version_id),
                "target_version_id": str(target_version_id),
            },
        )
        return entry

    @classmethod
    async def create_branch(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        source_version_id: uuid.UUID,
        target_version_id: uuid.UUID,
    ) -> "Transition":
        entry = cls(
            transition_id=new_uuid6(),
            transition_type=TransitionType.branch,
            source_cluster_id=cluster_id,
            source_version_id=source_version_id,
            target_cluster_id=cluster_id,
            target_version_id=target_version_id,
        )
        session.add(entry)
        logger.info(
            "Created branch transition entry",
            extra={
                "cluster_id": str(cluster_id),
                "source_version_id": str(source_version_id),
                "target_version_id": str(target_version_id),
            },
        )
        return entry

    @classmethod
    async def create_merge_entry(
        cls,
        session: AsyncSession,
        source_cluster_id: uuid.UUID,
        source_version_id: uuid.UUID,
        target_cluster_id: uuid.UUID,
        target_version_id: uuid.UUID,
        transition_type: TransitionType = TransitionType.merge,
    ) -> "Transition":
        """Create one row of a merge (call once per source version)."""
        entry = cls(
            transition_id=new_uuid6(),
            transition_type=transition_type,
            source_cluster_id=source_cluster_id,
            source_version_id=source_version_id,
            target_cluster_id=target_cluster_id,
            target_version_id=target_version_id,
        )
        session.add(entry)
        logger.info(
            "Created merge transition entry",
            extra={
                "transition_type": transition_type.value,
                "source_cluster_id": str(source_cluster_id),
                "source_version_id": str(source_version_id),
                "target_cluster_id": str(target_cluster_id),
                "target_version_id": str(target_version_id),
            },
        )
        return entry

    @classmethod
    async def create_split_entry(
        cls,
        session: AsyncSession,
        source_cluster_id: uuid.UUID,
        source_version_id: uuid.UUID,
        target_cluster_id: uuid.UUID,
        target_version_id: uuid.UUID,
    ) -> "Transition":
        """Create one row of a split (call once per target version)."""
        entry = cls(
            transition_id=new_uuid6(),
            transition_type=TransitionType.cluster_split,
            source_cluster_id=source_cluster_id,
            source_version_id=source_version_id,
            target_cluster_id=target_cluster_id,
            target_version_id=target_version_id,
        )
        session.add(entry)
        logger.info(
            "Created split transition entry",
            extra={
                "source_cluster_id": str(source_cluster_id),
                "source_version_id": str(source_version_id),
                "target_cluster_id": str(target_cluster_id),
                "target_version_id": str(target_version_id),
            },
        )
        return entry
