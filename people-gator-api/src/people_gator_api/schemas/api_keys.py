"""Public API-key identities. Credentials are never persisted or returned."""

import uuid
from pydantic import BaseModel, Field
from people_gator_api.schemas.common import GenericListRequest, GenericListResponse


class APIKeyCreateRequest(BaseModel):
    identifier: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    user_id: uuid.UUID


class APIKeyResponse(APIKeyCreateRequest):
    api_key_id: uuid.UUID


class APIKeyListRequest(GenericListRequest):
    q: str | None = Field(default=None, max_length=256)


APIKeyListResponse = GenericListResponse[APIKeyResponse]
