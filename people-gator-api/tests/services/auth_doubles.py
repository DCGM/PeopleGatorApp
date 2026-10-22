"""Typed in-memory identity repositories for authentication tests."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from types import TracebackType

from people_gator_api.persistence.contracts import APIKeyRepository, UserRepository
from people_gator_api.schemas.api_keys import (
    APIKeyCreateRequest,
    APIKeyListRequest,
    APIKeyListResponse,
    APIKeyResponse,
)
from people_gator_api.schemas.missing import is_missing
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)


class InMemoryUserRepository(UserRepository):
    """Get-or-create by (issuer, subject), never changing existing records."""

    def __init__(self) -> None:
        super().__init__()
        self.records: dict[uuid.UUID, UserResponse] = {}
        self.calls: list[str] = []

    def by_subject(self, issuer: str, subject: str) -> UserResponse | None:
        return next((
            user for user in self.records.values()
            if (user.external_issuer, user.external_subject) == (issuer, subject)
        ), None)

    def set_active(self, user_id: uuid.UUID, active: bool) -> None:
        self.records[user_id] = self.records[user_id].model_copy(update={"is_active": active})

    async def get(self, user_id: uuid.UUID) -> UserResponse | None:
        self.calls.append("get")
        return self.records.get(user_id)

    async def list(self, query: UserListRequest) -> UserListResponse:
        self.calls.append("list")
        items = sorted(self.records.values(), key=lambda user: user.user_id)
        return UserListResponse(items=items[:query.limit], limit=query.limit)

    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        self.calls.append("get_or_create")
        existing = self.by_subject(payload.external_issuer, payload.external_subject)
        if existing is not None:
            return existing
        user = UserResponse(user_id=uuid.uuid4(), email=None, **payload.model_dump())
        self.records[user.user_id] = user
        return user

    async def patch(self, user_id: uuid.UUID, payload: UserPatchRequest) -> UserResponse | None:
        self.calls.append("patch")
        user = self.records.get(user_id)
        if user is None:
            return None
        if not is_missing(payload.is_active):
            self.set_active(user_id, payload.is_active)
        return self.records[user_id]

    async def delete(self, user_id: uuid.UUID) -> bool:
        self.calls.append("delete")
        return self.records.pop(user_id, None) is not None

    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int:
        self.calls.append("delete_batch")
        return sum(self.records.pop(user_id, None) is not None for user_id in set(user_ids))


class InMemoryAPIKeyRepository(APIKeyRepository):
    """Registers each identifier once, preserving its ID."""

    def __init__(self) -> None:
        super().__init__()
        self.records: dict[str, APIKeyResponse] = {}
        self.requests: list[APIKeyCreateRequest] = []

    async def get_or_create(self, payload: APIKeyCreateRequest) -> APIKeyResponse:
        self.requests.append(payload)
        if payload.identifier not in self.records:
            self.records[payload.identifier] = APIKeyResponse(
                api_key_id=uuid.uuid4(), identifier=payload.identifier,
                display_name=payload.display_name, user_id=payload.user_id,
            )
        return self.records[payload.identifier]

    async def list(self, query: APIKeyListRequest) -> APIKeyListResponse:
        items = sorted(self.records.values(), key=lambda key: key.api_key_id)
        return APIKeyListResponse(items=items[:query.limit], limit=query.limit)


@dataclass
class IdentityStore:
    """Satisfies ``IdentityRepositories`` and counts entered database scopes."""

    users: InMemoryUserRepository = field(default_factory=InMemoryUserRepository)
    api_keys: InMemoryAPIKeyRepository | None = field(default_factory=InMemoryAPIKeyRepository)
    entries: int = 0

    def context(self) -> "IdentityStoreContext":
        return IdentityStoreContext(self)


@dataclass(frozen=True)
class IdentityStoreContext:
    """Single-use async context, like ``get_database_context()``."""

    store: IdentityStore

    async def __aenter__(self) -> IdentityStore:
        self.store.entries += 1
        return self.store

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None
