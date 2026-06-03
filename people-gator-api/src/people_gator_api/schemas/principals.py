import uuid

from pydantic import BaseModel

from people_gator_api.db.models.enums import EvidenceType, PrincipalType, RegistrySource


class PrincipalResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    is_active: bool


class ServiceAgentCreateRequest(BaseModel):
    agent_slug: str
    display_name: str
    description: str | None = None


class ModelAgentCreateRequest(BaseModel):
    display_name: str
    evidence_type: EvidenceType
    role: str
    model_slug: str
    model_version: str
    registry_source: RegistrySource
    registry_uri: str
    is_active: bool = True


class ModelAgentPatchRequest(BaseModel):
    is_active: bool


class MeResponse(BaseModel):
    principal_id: uuid.UUID
    principal_type: str
    display_name: str
    is_active: bool
