import uuid

from pydantic import BaseModel

from people_gator_api.db.models.enums import TaskRole, TaskStatus


class TaskResponse(BaseModel):
    task_id: uuid.UUID
    cluster_id: uuid.UUID
    pinned_version_id: uuid.UUID
    head_version_id: uuid.UUID
    assignee_id: uuid.UUID
    created_by: uuid.UUID
    task_role: TaskRole
    status: TaskStatus


class TaskCreateRequest(BaseModel):
    cluster_id: uuid.UUID
    pinned_version_id: uuid.UUID
    assignee_id: uuid.UUID
    task_role: TaskRole


class TaskPatchRequest(BaseModel):
    status: TaskStatus
