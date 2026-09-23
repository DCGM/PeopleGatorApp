"""Pydantic schemas for API users."""

from pydantic import BaseModel, Field
from pydantic.experimental.missing_sentinel import MISSING
from people_gator_api.schemas.common import (
    GenericActor,
    GenericListRequest,
    GenericListResponse,
    ListFilterBase,
)


class UserCreateRequest(BaseModel):
    """Request schema for creating a new user."""
    display_name: str = Field(description="The display name of the user.")
    is_active: bool = Field(description="Indicates whether the user is active.")
    external_subject: str = Field(description="The external subject identifier of the user.")
    external_issuer: str = Field(description="The external issuer of the user's identity.")


class UserPatchRequest(BaseModel):
    """Request schema for patching an existing user."""

    display_name: str | MISSING = Field(
        default=MISSING,
        description="The display name of the user."
    )
    is_active: bool | MISSING = Field(
        default=MISSING,
        description="Indicates whether the user is active."
    )
    external_subject: str | MISSING = Field(
        default=MISSING,
        description="The external subject identifier of the user."
    )
    external_issuer: str | MISSING = Field(
        default=MISSING,
        description="The external issuer of the user's identity."
    )
    email: str | None | MISSING = Field(
        default=MISSING,
        description="The email address of the user."
    )


class UserResponse(GenericActor):
    """Response schema for a user."""

    email: str | None = Field(description="The email address of the user.")
    display_name: str = Field(description="The display name of the user.")
    is_active: bool = Field(description="Indicates whether the user is active.")
    external_subject: str = Field(
        description="The external subject identifier of the user."
    )
    external_issuer: str = Field(
        description="The external issuer of the user's identity."
    )


class UserListFilter(ListFilterBase):
    """Filter schema for listing users."""

    display_name: list[str] | MISSING = Field(
        default=MISSING,
        description="Filter by the display name of the user."
    )
    is_active: list[bool] | MISSING = Field(
        default=MISSING,
        description="Filter by the active status of the user."
    )
    external_subject: list[str] | MISSING = Field(
        default=MISSING,
        description="Filter by the external subject identifier of the user."
    )
    external_issuer: list[str] | MISSING = Field(
        default=MISSING,
        description="Filter by the external issuer of the user's identity."
    )
    email: list[str] | MISSING = Field(
        default=MISSING,
        description="Filter by the email address of the user."
    )

class UserListRequest(GenericListRequest):
    filter: UserListFilter | MISSING = Field(
        default=MISSING,
        description="Filter criteria for listing users."
    )

UserListResponse = GenericListResponse[UserResponse]


__all__ = [
    "UserCreateRequest",
    "UserPatchRequest",
    "UserResponse",
    "UserListFilter",
    "UserListRequest",
    "UserListResponse",
]
