"""Verify keys against filesystem configuration on every request."""

import argon2
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from people_gator_api.services.filesystem_service import get_filesystem
from people_gator_api.settings import settings


class APIKeyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    hash: str = Field(min_length=1, repr=False)
    username: str = Field(min_length=1)
    scopes: set[str]


_keys_adapter = TypeAdapter(dict[str, APIKeyRecord])


async def verify_api_key(secret: str) -> tuple[str, APIKeyRecord]:
    # Do not cache: removing a key must revoke access on its next use. Missing,
    # malformed, or unreadable configuration is an operational error, not a 401.
    data = await get_filesystem().read_bytes(settings.api_keys.keys_path)
    records = _keys_adapter.validate_json(data)
    from people_gator_api.services.auth_service import KNOWN_SCOPES
    for identifier, record in records.items():
        if not identifier or not record.scopes.issubset(KNOWN_SCOPES):
            raise ValueError("Invalid API key identifier or scopes in configuration")
    for identifier, record in records.items():
        try:
            # Invalid hashes remain configuration errors; only mismatches are credentials errors.
            valid = argon2.PasswordHasher().verify(record.hash, secret)
        except argon2.exceptions.VerifyMismatchError:
            continue
        if valid:
            return identifier, record
    raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "APIKey"})
