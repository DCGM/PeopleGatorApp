import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.enums import TaskStatus
from people_gator_api.db.models.task import Task
from people_gator_api.schemas.tasks import TaskResponse


async def list_tasks(
    session: AsyncSession,
    assignee_id: uuid.UUID | None,
    task_role: str | None,
    status: TaskStatus | None,
    cluster_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[TaskResponse]:
    stmt = sa.select(Task).order_by(Task.task_id.asc()).limit(limit)
    if assignee_id is not None:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if task_role is not None:
        stmt = stmt.where(Task.task_role == task_role)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if cluster_id is not None:
        stmt = stmt.where(Task.cluster_id == cluster_id)
    if after_id is not None:
        stmt = stmt.where(Task.task_id > after_id)

    result = await session.execute(stmt)
    return [_to_response(item) for item in result.scalars().all()]


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> TaskResponse | None:
    task = await Task.get(session, task_id)
    if task is None:
        return None
    return _to_response(task)


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        cluster_id=task.cluster_id,
        pinned_version_id=task.pinned_version_id,
        head_version_id=task.head_version_id,
        assignee_id=task.assignee_id,
        created_by=task.created_by,
        task_role=task.task_role,
        status=task.status,
    )
