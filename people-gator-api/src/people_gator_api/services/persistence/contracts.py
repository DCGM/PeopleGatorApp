"""Public persistence interface shared by Weaviate and PostgreSQL.

Contracts speak in API schemas and deliberately do not expose Weaviate clients,
SQLAlchemy sessions, filters, or transactions. A repository instance is scoped
to one backend session/client. Batch defaults are correct but conservative;
backends override them when they have a native bulk operation.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityEmbeddingUpdateRequest,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
    FaceCreateRequest,
    FaceEmbeddingUpdateRequest,
    FaceListResponse,
    FaceResponse,
)
from people_gator_api.schemas.enums import AssignmentType, EntityType, SourceKind
from people_gator_api.schemas.search import (
    DocumentSearchResultListResponse,
    FaceSearchQuery,
    FaceSearchResultListResponse,
    PageSearchResultListResponse,
    SearchDocumentsQuery,
    SearchEntitiesQuery,
    SearchEntitiesResultListResponse,
    SearchPagesQuery,
)
from people_gator_api.schemas.sources import SourceRecord, SourceRecordListResponse
from people_gator_api.schemas.text_mentions import (
    TextMentionCreateRequest,
    TextMentionListResponse,
    TextMentionResponse,
)
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.services.crud_services.source_service import SourceCreateSpec


@dataclass(frozen=True, slots=True)
class WriteContext:
    """Actor metadata required by owner-aware records."""

    user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class EntityListQuery:
    after_id: uuid.UUID | None = None
    limit: int = 50
    entity_type: EntityType | None = None
    wikidata_id: str | None = None
    nlcr_authority_id: str | None = None
    owner_user_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    assignment: AssignmentType | None = None


@dataclass(frozen=True, slots=True)
class EntityPatchCommand:
    entity_id: uuid.UUID
    patch: EntityPatchRequest


@dataclass(frozen=True, slots=True)
class SourceLookup:
    source_id: uuid.UUID | None = None
    source_type: SourceKind | None = None
    library: str | None = None
    document_id: uuid.UUID | None = None
    page_id: uuid.UUID | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class SourceListQuery:
    source_type: SourceKind | None = None
    after_id: uuid.UUID | None = None
    limit: int = 50
    library: str | None = None
    document_id: uuid.UUID | None = None
    page_id: uuid.UUID | None = None
    url: str | None = None
    source_ids: frozenset[uuid.UUID] | None = None


@dataclass(frozen=True, slots=True)
class FaceListQuery:
    source_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    after_id: uuid.UUID | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class FacePatchCommand:
    detection_id: uuid.UUID
    entity_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class TextMentionListQuery:
    source_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    after_id: uuid.UUID | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class TextMentionPatchCommand:
    mention_id: uuid.UUID
    entity_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class UserListQuery:
    is_active: bool | None = None
    after_id: uuid.UUID | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class UserPatchCommand:
    user_id: uuid.UUID
    patch: UserPatchRequest


class EntityRepository(ABC):
    @abstractmethod
    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None: ...

    @abstractmethod
    async def list(self, query: EntityListQuery) -> EntityListResponse: ...

    @abstractmethod
    async def insert(
        self, payload: EntityCreateRequest, context: WriteContext
    ) -> EntityResponse: ...

    @abstractmethod
    async def import_batch(
        self, payloads: Sequence[EntityCreateRequest], context: WriteContext
    ) -> list[EntityResponse]: ...

    @abstractmethod
    async def patch(
        self, entity_id: uuid.UUID, payload: EntityPatchRequest
    ) -> EntityResponse | None: ...

    @abstractmethod
    async def patch_batch(
        self, commands: Sequence[EntityPatchCommand]
    ) -> list[EntityResponse | None]: ...

    @abstractmethod
    async def update_embeddings_batch(
        self, payloads: Sequence[EntityEmbeddingUpdateRequest]
    ) -> int: ...

    @abstractmethod
    async def delete(self, entity_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def delete_batch(self, entity_ids: Sequence[uuid.UUID]) -> int: ...

    @abstractmethod
    async def delete_many(
        self, selector: EntityDeleteManyRequest
    ) -> EntityDeleteManyResponse: ...

    @abstractmethod
    async def search(
        self, query: SearchEntitiesQuery
    ) -> SearchEntitiesResultListResponse: ...


class SourceRepository(ABC):
    """Source identities are immutable; changes are delete-and-reinsert operations."""

    @abstractmethod
    async def get(self, lookup: SourceLookup) -> SourceRecord | None: ...

    @abstractmethod
    async def list(self, query: SourceListQuery) -> SourceRecordListResponse: ...

    @abstractmethod
    async def insert(self, spec: SourceCreateSpec) -> tuple[SourceRecord, bool]: ...

    @abstractmethod
    async def import_batch(
        self, specs: Sequence[SourceCreateSpec]
    ) -> list[SourceRecord]: ...

    @abstractmethod
    async def delete(self, source_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def delete_batch(self, source_ids: Sequence[uuid.UUID]) -> int: ...

    @abstractmethod
    async def search_pages(
        self, query: SearchPagesQuery
    ) -> PageSearchResultListResponse: ...

    @abstractmethod
    async def search_documents(
        self, query: SearchDocumentsQuery
    ) -> DocumentSearchResultListResponse: ...


class FaceRepository(ABC):
    @abstractmethod
    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None: ...

    @abstractmethod
    async def list(self, query: FaceListQuery) -> FaceListResponse: ...

    @abstractmethod
    async def insert(
        self, payload: FaceCreateRequest, context: WriteContext
    ) -> FaceResponse: ...

    @abstractmethod
    async def import_batch(
        self, payloads: Sequence[FaceCreateRequest], context: WriteContext
    ) -> list[FaceResponse]: ...

    @abstractmethod
    async def patch_entity(
        self, detection_id: uuid.UUID, entity_id: uuid.UUID | None
    ) -> FaceResponse | None: ...

    @abstractmethod
    async def patch_batch(
        self, commands: Sequence[FacePatchCommand]
    ) -> list[FaceResponse | None]: ...

    @abstractmethod
    async def update_embeddings_batch(
        self, payloads: Sequence[FaceEmbeddingUpdateRequest]
    ) -> int: ...

    @abstractmethod
    async def delete(self, detection_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def delete_batch(self, detection_ids: Sequence[uuid.UUID]) -> int: ...

    @abstractmethod
    async def search(self, query: FaceSearchQuery) -> FaceSearchResultListResponse: ...


class TextMentionRepository(ABC):
    @abstractmethod
    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None: ...

    @abstractmethod
    async def list(self, query: TextMentionListQuery) -> TextMentionListResponse: ...

    @abstractmethod
    async def insert(
        self, payload: TextMentionCreateRequest
    ) -> TextMentionResponse: ...

    @abstractmethod
    async def import_batch(
        self, payloads: Sequence[TextMentionCreateRequest]
    ) -> list[TextMentionResponse]: ...

    @abstractmethod
    async def patch_entity(
        self, mention_id: uuid.UUID, entity_id: uuid.UUID
    ) -> TextMentionResponse | None: ...

    @abstractmethod
    async def patch_batch(
        self, commands: Sequence[TextMentionPatchCommand]
    ) -> list[TextMentionResponse | None]: ...

    @abstractmethod
    async def delete(self, mention_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def delete_batch(self, mention_ids: Sequence[uuid.UUID]) -> int: ...


class UserRepository(ABC):
    @abstractmethod
    async def get(self, user_id: uuid.UUID) -> UserResponse | None: ...

    @abstractmethod
    async def list(self, query: UserListQuery) -> UserListResponse: ...

    @abstractmethod
    async def insert(self, payload: UserCreateRequest) -> UserResponse: ...

    @abstractmethod
    async def import_batch(
        self, payloads: Sequence[UserCreateRequest]
    ) -> list[UserResponse]: ...

    @abstractmethod
    async def patch(
        self, user_id: uuid.UUID, payload: UserPatchRequest
    ) -> UserResponse | None: ...

    @abstractmethod
    async def patch_batch(
        self, commands: Sequence[UserPatchCommand]
    ) -> list[UserResponse | None]: ...

    @abstractmethod
    async def delete(self, user_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int: ...

    @abstractmethod
    async def get_or_create(
        self, *, external_subject: str, external_issuer: str
    ) -> UserResponse: ...


@dataclass(frozen=True, slots=True)
class Database:
    """One request-scoped, backend-neutral entry point."""

    entities: EntityRepository
    sources: SourceRepository
    faces: FaceRepository
    text_mentions: TextMentionRepository
    users: UserRepository
