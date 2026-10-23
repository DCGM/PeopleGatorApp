"""Routes for the current user and contract-backed user administration."""

import uuid
from pydantic import BaseModel
from people_gator_api.schemas.common import GenericListResponse

from fastapi import APIRouter, Query, status

from people_gator_api.schemas.users import (
    UserListRequest,
    UserListFilter,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.routes.v1.query_dependencies import (
    ListRequestDependency,
    UserListFilterDependency,
)
from people_gator_api.services.auth_service import (
    AdminActorDependency,
    BrowseActorDependency,
    AnnotatorActorDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["users"])


class UserFilterOption(BaseModel):
    user_id: uuid.UUID
    display_name: str


@router.get("/user-filter-options", response_model=GenericListResponse[UserFilterOption])
async def list_user_filter_options_route(
    database: DatabaseDependency, actor: BrowseActorDependency,
    list_request: ListRequestDependency,
    q: str | None = Query(default=None, max_length=256),
) -> GenericListResponse[UserFilterOption]:
    try:
        result = await database.users.list(UserListRequest(**list_request.model_dump(), filter_=UserListFilter(search=q.strip()) if q and q.strip() else UserListFilter()))
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))
    return GenericListResponse[UserFilterOption](
        items=[UserFilterOption(user_id=user.user_id, display_name=user.display_name) for user in result.items],
        limit=result.limit, total_count=result.total_count, cursor=result.cursor,
    )


@router.get("/me", response_model=UserResponse)
async def get_me_route(
    current_user: AnnotatorActorDependency, database: DatabaseDependency,
) -> UserResponse:
    # Profile data is read on demand; it is not an active-state gate.
    user = await database.users.get(current_user.user_id)
    if user is None:
        raise_api_error(404, "not_found", "User not found")
    return user


@router.get("/users", response_model=UserListResponse)
async def list_users_route(
    database: DatabaseDependency,
    current_user: AdminActorDependency,
    filter: UserListFilterDependency,
    list_request: ListRequestDependency,
) -> UserListResponse:
    del current_user
    try:
        return await database.users.list(
            UserListRequest(
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
            )
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.delete("/users:batch", response_model=int)
async def delete_user_batch_route(
    user_id: list[uuid.UUID],
    database: DatabaseDependency,
    current_user: AdminActorDependency,
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
    current_user: AdminActorDependency,
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
    current_user: AdminActorDependency,
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
    current_user: AdminActorDependency,
) -> None:
    del current_user
    try:
        deleted = await database.users.delete(user_id)
    except ValueError as exc:
        raise_api_error(409, "user_is_referenced", str(exc))
    if not deleted:
        raise_api_error(404, "not_found", "User not found")
