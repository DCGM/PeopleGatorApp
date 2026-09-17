"""Routes for the current user and user administration."""

import uuid

from fastapi import APIRouter, Query

from people_gator_api.schemas.users import (
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
)
from people_gator_api.services.crud_services.user_service import (
    get_user,
    list_users,
    update_user,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me_route(current_user: AnnotatorUserDependency) -> UserResponse:
    return current_user


@router.get("/users", response_model=UserListResponse)
async def list_users_route(
    session: WeaviateSessionDependency,
    current_user: AdminUserDependency,
    is_active: bool | None = True,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> UserListResponse:
    return await list_users(
        session,
        current_user.user_id,
        is_active,
        after_id,
        limit,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_route(
    user_id: uuid.UUID,
    session: WeaviateSessionDependency,
    current_user: AdminUserDependency,
) -> UserResponse:
    found_user = await get_user(session, current_user.user_id, user_id)
    if found_user is None:
        raise_api_error(404, "not_found", "User not found")
    return found_user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def patch_user_route(
    user_id: uuid.UUID,
    payload: UserPatchRequest,
    session: WeaviateSessionDependency,
    current_user: AdminUserDependency,
) -> UserResponse:
    updated_user = await update_user(
        session,
        current_user.user_id,
        user_id,
        payload,
    )
    if updated_user is None:
        raise_api_error(404, "not_found", "User not found")
    return updated_user
