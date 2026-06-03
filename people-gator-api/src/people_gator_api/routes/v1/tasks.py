import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.engine import get_session
from people_gator_api.db.models.enums import TaskRole, TaskStatus
from people_gator_api.db.models.task import Task
from people_gator_api.schemas.tasks import TaskCreateRequest, TaskPatchRequest, TaskResponse
from people_gator_api.services.authz import AuthContext, require_scopes
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.task_service import get_task, list_tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks_route(
    assignee_id: uuid.UUID | None = None,
    task_role: TaskRole | None = None,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    cluster_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> list[TaskResponse]:
    return await list_tasks(
        session,
        assignee_id=assignee_id,
        task_role=task_role.value if task_role else None,
        status=status_filter,
        cluster_id=cluster_id,
        after_id=after_id,
        limit=limit,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task_route(
    task_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    task = await get_task(session, task_id)
    if task is None:
        raise_api_error(404, "not_found", "Task not found")
    return task


@router.options("/tasks/{task_id}")
async def options_task_route(
    task_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
) -> dict[str, object]:
    return {
        "task_id": str(task_id),
        "allowed_methods": ["GET", "HEAD", "OPTIONS", "PATCH"],
        "allowed_operations": [],
    }


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task_route(
    payload: TaskCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:admin")),
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    assert auth.principal is not None
    task = await Task.create(
        session=session,
        cluster_id=payload.cluster_id,
        pinned_version_id=payload.pinned_version_id,
        assignee_id=payload.assignee_id,
        created_by=auth.principal.principal_id,
        task_role=payload.task_role,
    )
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


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def patch_task_route(
    task_id: uuid.UUID,
    payload: TaskPatchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> TaskResponse:
    task = await Task.get(session, task_id)
    if task is None:
        raise_api_error(404, "not_found", "Task not found")
    task.status = payload.status
    session.add(task)
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
