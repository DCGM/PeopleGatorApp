"""Routes for the current user and contract-backed user administration."""

import uuid

from fastapi import APIRouter, Query, status

from people_gator_api.schemas.users import (
    UserListFilter,
    UserListRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.services.http_errors import raise_api_error


router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me_route(current_user: AnnotatorUserDependency) -> UserResponse:
    return current_user


@router.get("/users", response_model=UserListResponse)
async def list_users_route(
    database: DatabaseDependency,
    current_user: AdminUserDependency,
    display_name: list[str] | None = Query(default=None),
    is_active: list[bool] | None = Query(default=None),
    external_subject: list[str] | None = Query(default=None),
    external_issuer: list[str] | None = Query(default=None),
    email: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=0),
    return_total_count: bool = False,
    cursor: str | None = None,
) -> UserListResponse:
    del current_user
    values = {
        name: value
        for name, value in {
            "display_name": display_name,
            "is_active": is_active,
            "external_subject": external_subject,
            "external_issuer": external_issuer,
            "email": email,
        }.items()
        if value is not None
    }
    try:
        return await database.users.list(
            UserListRequest(
                filter=UserListFilter.model_validate(values),
                limit=limit,
                return_total_count=return_total_count,
                cursor=cursor,
            )
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.delete("/users:batch", response_model=int)
async def delete_user_batch_route(
    user_id: list[uuid.UUID],
    database: DatabaseDependency,
    current_user: AdminUserDependency,
) -> int:
    del current_user
    try:
        return await database.users.delete_batch(user_id)
    except ValueError as exc:
        raise_api_error(409, "user_is_referenced", str(exc))


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_route(
    user_id: uuid.UUID,
    database: DatabaseDependency,
    current_user: AdminUserDependency,
) -> UserResponse:
    del current_user
    found_user = await database.users.get(user_id)
    if found_user is None:
        raise_api_error(404, "not_found", "User not found")
    return found_user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def patch_user_route(
    user_id: uuid.UUID,
    payload: UserPatchRequest,
    database: DatabaseDependency,
    current_user: AdminUserDependency,
) -> UserResponse:
    del current_user
    try:
        updated_user = await database.users.patch(user_id, payload)
    except ValueError as exc:
        raise_api_error(409, "identity_conflict", str(exc))
    if updated_user is None:
        raise_api_error(404, "not_found", "User not found")
    return updated_user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_route(
    user_id: uuid.UUID,
    database: DatabaseDependency,
    current_user: AdminUserDependency,
) -> None:
    del current_user
    try:
        deleted = await database.users.delete(user_id)
    except ValueError as exc:
        raise_api_error(409, "user_is_referenced", str(exc))
    if not deleted:
        raise_api_error(404, "not_found", "User not found")
