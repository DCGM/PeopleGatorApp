import uuid

from pydantic import BaseModel

from people_gator_api.schemas.enums import AnnotationType, PrincipalType, RegistrySource


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

# ---------------------------------------------------------------------------
# Model agent schemas
# ---------------------------------------------------------------------------

class ModelAgentCreateRequest(BaseModel):
    display_name: str
    annotation_type: AnnotationType
    role: str
    model_slug: str
    model_version: str
    registry_source: RegistrySource
    registry_uri: str
    is_active: bool

class ModelAgentPatchRequest(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None

class ModelAgentResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    annotation_type: AnnotationType
    role: str
    model_slug: str
    model_version: str
    registry_source: RegistrySource
    registry_uri: str
    is_active: bool


# ---------------------------------------------------------------------------
# Me schema
# ---------------------------------------------------------------------------

class PrincipalResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    is_active: bool
