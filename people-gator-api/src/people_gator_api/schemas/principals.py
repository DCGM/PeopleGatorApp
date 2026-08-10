import uuid

from pydantic import BaseModel

from people_gator_api.schemas.enums import (
    PrincipalType,
)

from people_gator_api.schemas.common import GenericListResponse


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserPatchRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    is_active: bool | None = None

class UserResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    external_subject: str
    external_issuer: str
    email: str | None
    is_active: bool

class UserListResponse(GenericListResponse[UserResponse]):
    """A paginated list of users."""
    items: list[UserResponse]

# ---------------------------------------------------------------------------
# Model agent schemas
# ---------------------------------------------------------------------------

class ModelAgentCreateRequest(BaseModel):
    display_name: str
    is_active: bool
    model_slug: str
    model_version: str

class ModelAgentPatchRequest(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None

class ModelAgentResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    is_active: bool
    model_slug: str
    model_version: str

class ModelAgentListResponse(GenericListResponse[ModelAgentResponse]):
    """A paginated list of model agents."""
    items: list[ModelAgentResponse]

# ---------------------------------------------------------------------------
# Me schema
# ---------------------------------------------------------------------------

class PrincipalResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    is_active: bool

class PrincipalListResponse(GenericListResponse[PrincipalResponse]):
    """A paginated list of principals."""
    items: list[PrincipalResponse]