"""OPERATION table — directed edges in the VERSION DAG.

Each logical operation may span multiple rows (e.g. union/intersection have one
row per source version).  All rows belonging to the same logical operation
share the same ``operation_id``.  A surrogate ``op_row_id`` is the actual
DB primary key.

Sealing semantics: a VERSION is sealed once it appears as
``source_version_id`` in any OPERATION row.  Sealed versions cannot receive
new DELTAs.
"""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import OperationType

logger = logging.getLogger(__name__)


class Operation(Base):
    """One row in the VERSION DAG representing a directed edge (or part thereof).

    Multi-row operations (``union``, ``intersection``, ``split``,
    ``conflict_free_join``) all share the same ``operation_id``.  A logical
    operation is complete only when all expected rows sharing an
    ``operation_id`` are present.

    ``op_row_id`` is the surrogate DB primary key so that multiple rows can
    coexist for the same logical operation.
    """

    __tablename__ = "operation"

    # Surrogate PK — unique per DB row.
    op_row_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    # Logical grouping key shared across all rows of the same operation.
    operation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=new_uuid6
    )
    operation_type: Mapped[OperationType] = mapped_column(
        SAEnum(OperationType, name="operation_type_enum"), nullable=False
    )
    # Null for ``empty`` operations (no prior version exists).
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

    __table_args__ = (
        # Index for DAG walk: find all operations where a version is a source.
        sa.Index("ix_operation_source_version", "source_cluster_id", "source_version_id"),
        # Index for finding all operations that produced a target version.
        sa.Index("ix_operation_target_version", "target_cluster_id", "target_version_id"),
        # Index for grouping all rows of one logical operation.
        sa.Index("ix_operation_operation_id", "operation_id"),
    )

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_empty(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.operation_type == OperationType.empty

    @is_empty.expression
    @classmethod
    def is_empty(cls) -> sa.ColumnElement[bool]:
        return cls.operation_type == OperationType.empty.value

    @hybrid_property
    def is_merge_type(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.operation_type in (
            OperationType.union,
            OperationType.intersection,
            OperationType.conflict_free_join,
        )

    @is_merge_type.expression
    @classmethod
    def is_merge_type(cls) -> sa.ColumnElement[bool]:
        return cls.operation_type.in_([
            OperationType.union.value,
            OperationType.intersection.value,
            OperationType.conflict_free_join.value,
        ])

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_ancestors_of(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> list["Operation"]:
        """Return all operation rows that have this version as their target."""
        result = await session.execute(
            select(cls).where(
                cls.target_cluster_id == cluster_id,
                cls.target_version_id == version_id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def get_outgoing_from(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> list["Operation"]:
        """Return all operation rows that have this version as their source.

        If any rows are returned the version is sealed — no further DELTAs
        may be written.
        """
        result = await session.execute(
            select(cls).where(
                cls.source_cluster_id == cluster_id,
                cls.source_version_id == version_id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def is_version_sealed(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> bool:
        """Return True if any outgoing operation row exists for this version."""
        result = await session.scalars(
            select(cls).where(
                cls.source_cluster_id == cluster_id,
                cls.source_version_id == version_id,
            ).limit(1)
        )
        return result.first() is not None

    @classmethod
    async def create_single(
        cls,
        session: AsyncSession,
        operation_id: uuid.UUID,
        operation_type: OperationType,
        target_cluster_id: uuid.UUID,
        target_version_id: uuid.UUID,
        source_cluster_id: uuid.UUID | None = None,
        source_version_id: uuid.UUID | None = None,
    ) -> "Operation":
        """Insert one operation row (for single-row operations)."""
        op = cls(
            op_row_id=new_uuid6(),
            operation_id=operation_id,
            operation_type=operation_type,
            source_cluster_id=source_cluster_id,
            source_version_id=source_version_id,
            target_cluster_id=target_cluster_id,
            target_version_id=target_version_id,
        )
        session.add(op)
        logger.info(
            "Created operation row",
            extra={
                "operation_id": str(operation_id),
                "operation_type": operation_type.value,
                "target_version_id": str(target_version_id),
            },
        )
        return op
