import uuid

from pydantic import BaseModel

from people_gator_api.schemas.enums import (
    PrincipalType,
)

from people_gator_api.schemas.common import GenericListResponse


# ---------------------------------------------------------------------------
# Shared principal schemas
# ---------------------------------------------------------------------------


class PrincipalCreateRequest(BaseModel):
    display_name: str
    is_active: bool


class PrincipalPatchRequest(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class UserCreateRequest(PrincipalCreateRequest):
    external_subject: str
    external_issuer: str


class UserPatchRequest(PrincipalPatchRequest):
    external_subject: str | None = None
    external_issuer: str | None = None
    email: str | None = None


class UserResponse(PrincipalCreateRequest):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    external_subject: str
    external_issuer: str
    email: str | None


class UserListResponse(GenericListResponse[UserResponse]):
    """A paginated list of users."""

    items: list[UserResponse]


# ---------------------------------------------------------------------------
# Model agent schemas
# ---------------------------------------------------------------------------


class ModelAgentCreateRequest(PrincipalCreateRequest):
    model_slug: str
    model_version: str


class ModelAgentPatchRequest(PrincipalPatchRequest):
    model_slug: str | None = None
    model_version: str | None = None


class ModelAgentResponse(PrincipalCreateRequest):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    model_slug: str
    model_version: str


class ModelAgentListResponse(GenericListResponse[ModelAgentResponse]):
    """A paginated list of model agents."""

    items: list[ModelAgentResponse]


# ---------------------------------------------------------------------------
# Me schema
# ---------------------------------------------------------------------------


class PrincipalResponse(PrincipalCreateRequest):
    principal_id: uuid.UUID
    principal_type: PrincipalType


class PrincipalListResponse(GenericListResponse[PrincipalResponse]):
    """A paginated list of principals."""

    items: list[PrincipalResponse]
