"""Pydantic schemas for API users."""

import uuid

from pydantic import BaseModel

from people_gator_api.schemas.common import GenericListResponse


class UserCreateRequest(BaseModel):
    display_name: str
    is_active: bool
    external_subject: str
    external_issuer: str


class UserPatchRequest(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    external_subject: str | None = None
    external_issuer: str | None = None
    email: str | None = None


class UserResponse(UserCreateRequest):
    user_id: uuid.UUID
    email: str | None


class UserListResponse(GenericListResponse[UserResponse]):
    """A paginated list of users."""

    items: list[UserResponse]
