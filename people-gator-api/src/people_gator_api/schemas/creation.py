"""Recorded server creation time and actor, independent of later edits."""
import uuid

from pydantic import AwareDatetime, BaseModel


class CreationMetadata(BaseModel):
    created_at: AwareDatetime | None = None
    created_by_user_id: uuid.UUID | None = None
    created_by_api_key_id: uuid.UUID | None = None
