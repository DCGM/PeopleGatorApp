"""TASK table — permission declarations that tie VERSION chains to the formal workflow.

A TASK grants its assignee the right to write DELTAs against the designated
VERSION chain and makes that chain eligible for workflow-advancing operations
(``union``, ``intersection``, ``conflict_free_join``).
"""

import logging
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import TaskRole, TaskStatus

logger = logging.getLogger(__name__)


class Task(Base):
    """Ties a VERSION chain to the formal annotation and review workflow.

    - ``pinned_version_id``: immutable — the version when the task was created.
      Provides the stable traceability anchor for merge operations.
    - ``head_version_id``: the current working head of this task's branch.
      Starts equal to ``pinned_version_id`` and advances as the assignee works.
    """

    __tablename__ = "task"

    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cluster.cluster_id"),
        nullable=False,
    )
    # Immutable — the version that existed when the task was created.
    pinned_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("version.version_id"),
        nullable=False,
    )
    # Current working head of this task's branch.
    head_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("version.version_id"),
        nullable=False,
    )
    # The user assigned to perform this task.
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )
    # The user or service agent that created this task.
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )
    task_role: Mapped[TaskRole] = mapped_column(
        SAEnum(TaskRole, name="task_role_enum"), nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status_enum"),
        nullable=False,
        default=TaskStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.Index("ix_task_cluster_id", "cluster_id"),
        sa.Index("ix_task_assignee_id", "assignee_id"),
        sa.Index("ix_task_status", "status"),
        sa.Index("ix_task_pinned_version", "pinned_version_id"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        task_id: uuid.UUID,
    ) -> "Task | None":
        result = await session.scalars(
            select(cls).where(cls.task_id == task_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_for_cluster(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
    ) -> list["Task"]:
        result = await session.execute(
            select(cls)
            .where(cls.cluster_id == cluster_id)
            .order_by(cls.task_id.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def list_for_assignee(
        cls,
        session: AsyncSession,
        assignee_id: uuid.UUID,
        status: TaskStatus | None = None,
    ) -> list["Task"]:
        stmt = (
            select(cls)
            .where(cls.assignee_id == assignee_id)
            .order_by(cls.task_id.asc())
        )
        if status is not None:
            stmt = stmt.where(cls.status == status)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        cluster_id: uuid.UUID,
        pinned_version_id: uuid.UUID,
        assignee_id: uuid.UUID,
        created_by: uuid.UUID,
        task_role: TaskRole,
    ) -> "Task":
        task = cls(
            task_id=new_uuid6(),
            cluster_id=cluster_id,
            pinned_version_id=pinned_version_id,
            head_version_id=pinned_version_id,
            assignee_id=assignee_id,
            created_by=created_by,
            task_role=task_role,
            status=TaskStatus.pending,
        )
        session.add(task)
        logger.info(
            "Created task",
            extra={
                "task_id": str(task.task_id),
                "cluster_id": str(cluster_id),
                "task_role": task_role.value,
                "assignee_id": str(assignee_id),
            },
        )
        return task
