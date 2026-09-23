"""Weaviate implementation of the backend-neutral persistence contracts."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Awaitable, Sequence

from weaviate import WeaviateAsyncClient
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter

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
from people_gator_api.schemas.search import (
    SearchDocumentsResultListResponse,
    SearchFacesRequest,
    SearchFacesResultListResponse,
    SearchPagesResultListResponse,
    SearchDocumentsQuery,
    SearchEntitiesRequest,
    SearchEntitiesResultListResponse,
    SearchPagesQuery,
)
from people_gator_api.schemas.enums import DEFAULT_FACE_EMBEDDING_MODEL
from people_gator_api.schemas.face_models import (
    FaceModelListResponse,
    FaceModelRegisterRequest,
    FaceModelResponse,
)
from people_gator_api.schemas.sources import SourceRecord, SourceRecordListResponse
from people_gator_api.schemas.mentions import (
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
from people_gator_api.services.crud_services import (
    annotation_service,
    entity_service,
    search_service,
    source_service,
    text_mention_service,
    user_service,
)
from people_gator_api.services.crud_services.source_service import SourceCreateSpec
from people_gator_api.persistence.contracts import (
    Database,
    EntityListQuery,
    EntityPatchCommand,
    EntityRepository,
    FaceModelRepository,
    FaceListQuery,
    FacePatchCommand,
    FaceRepository,
    SourceListQuery,
    SourceLookup,
    SourceRepository,
    TextMentionListQuery,
    TextMentionPatchCommand,
    TextMentionRepository,
    UserListQuery,
    UserPatchCommand,
    UserRepository,
    GenericActor,
)
from people_gator_api.weaviate_schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
    TEXT_MENTION_COLLECTION,
    USER_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    empty_reference_queries,
    parse_entity,
    parse_face,
    parse_text_mention,
    parse_user,
)
from people_gator_api.utils.uuid_utils import new_uuid6


async def _as_async_iterable[T](items: Sequence[T]) -> AsyncGenerator[T]:
    for item in items:
        yield item


async def _bounded_gather[T](
    operations: Sequence[Awaitable[T]], *, concurrency: int = 32
) -> list[T]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run(operation: Awaitable[T]) -> T:
        async with semaphore:
            return await operation

    return list(await asyncio.gather(*(run(operation) for operation in operations)))


def _require_unique_ids(ids: Sequence[uuid.UUID], operation: str) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError(f"{operation} requires unique object IDs")


async def _delete_many(
    client: WeaviateAsyncClient,
    collection_name: str,
    ids: Sequence[uuid.UUID],
) -> int:
    unique_ids = list(dict.fromkeys(ids))
    if not unique_ids:
        return 0
    result = await client.collections.get(collection_name).data.delete_many(
        where=Filter.by_id().contains_any(unique_ids)
    )
    return result.successful


class WeaviateEntityRepository(EntityRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        return await entity_service.get_entity(self._client, entity_id)

    async def list(self, query: EntityListQuery) -> EntityListResponse:
        return await entity_service.list_entities(
            self._client,
            uuid.UUID(int=0),
            query.after_id,
            query.limit,
            entity_type=query.entity_type,
            wikidata_id=query.wikidata_id,
            nlcr_authority_id=query.nlcr_authority_id,
            owner_user_id=query.owner_user_id,
            source_id=query.source_id,
            assignment=query.assignment,
        )

    async def create(
        self, payload: EntityCreateRequest, context: GenericActor
    ) -> EntityResponse:
        return await entity_service.create_entity(
            self._client, payload, context.user_id
        )

    async def create_batch(
        self, payloads: Sequence[EntityCreateRequest], context: GenericActor
    ) -> list[EntityResponse]:
        return await entity_service.create_entity_batch(
            self._client, _as_async_iterable(payloads), context.user_id
        )

    async def patch(
        self, entity_id: uuid.UUID, payload: EntityPatchRequest
    ) -> EntityResponse | None:
        return await entity_service.patch_entity(self._client, entity_id, payload)

    async def patch_batch(
        self, commands: Sequence[EntityPatchCommand]
    ) -> list[EntityResponse | None]:
        ids = [command.entity_id for command in commands]
        _require_unique_ids(ids, "entity patch batch")
        if not ids:
            return []
        collection = self._client.collections.get(ENTITY_COLLECTION)
        fetched = await collection.query.fetch_objects_by_ids(
            ids, return_references=empty_reference_queries(["user"])
        )
        by_id = {item.uuid: item for item in fetched.objects}
        updates = [command.patch.model_dump(exclude_unset=True) for command in commands]
        for update in updates:
            if update.get("aliases") is None and "aliases" in update:
                update["aliases"] = []
        await _bounded_gather(
            [
                collection.data.update(uuid=command.entity_id, properties=update)
                for command, update in zip(commands, updates)
                if command.entity_id in by_id
            ]
        )
        results: list[EntityResponse | None] = []
        for command, update in zip(commands, updates):
            item = by_id.get(command.entity_id)
            if item is None:
                results.append(None)
                continue
            properties = dict(item.properties)
            properties.update(update)
            results.append(parse_entity(properties, item.references, item.uuid))
        return results

    async def update_embeddings_batch(
        self, payloads: Sequence[EntityEmbeddingUpdateRequest]
    ) -> int:
        return await entity_service.update_entity_embeddings_batch(
            self._client, list(payloads)
        )

    async def delete(self, entity_id: uuid.UUID) -> bool:
        return await entity_service.delete_entity(self._client, entity_id)

    async def delete_batch(self, entity_ids: Sequence[uuid.UUID]) -> int:
        return await _delete_many(self._client, ENTITY_COLLECTION, entity_ids)

    async def delete_many(
        self, selector: EntityDeleteManyRequest
    ) -> EntityDeleteManyResponse:
        return await entity_service.delete_entities(self._client, selector)

    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        return await search_service.search_entities(self._client, query)


class WeaviateSourceRepository(SourceRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def lookup(self, lookup: SourceLookup) -> SourceRecord | None:
        return await source_service.get_source(
            self._client,
            lookup.source_id,
            source_type=lookup.source_type,
            library=lookup.library,
            document_id=lookup.document_id,
            page_id=lookup.page_id,
            url=lookup.url,
        )

    async def list(self, query: SourceListQuery) -> SourceRecordListResponse:
        return await source_service.list_sources(
            self._client,
            query.source_type,
            query.after_id,
            query.limit,
            library=query.library,
            document_id=query.document_id,
            page_id=query.page_id,
            url=query.url,
            source_ids=query.source_ids,
        )

    async def get_or_create(self, spec: SourceCreateSpec) -> tuple[SourceRecord, bool]:
        return await source_service.create_source(
            self._client,
            spec.source_type,
            library=spec.library,
            document_id=spec.document_id,
            page_id=spec.page_id,
            url=spec.url,
        )

    async def get_or_create_batch(
        self, specs: Sequence[SourceCreateSpec]
    ) -> list[SourceRecord]:
        return await source_service.create_source_batch(self._client, specs)

    async def delete(self, source_id: uuid.UUID) -> bool:
        return await source_service.delete_source(self._client, source_id)

    async def delete_batch(self, source_ids: Sequence[uuid.UUID]) -> int:
        return await _delete_many(
            self._client, source_service.SOURCE_COLLECTION, source_ids
        )

    async def search_pages(
        self, query: SearchPagesQuery
    ) -> SearchPagesResultListResponse:
        return await search_service.search_pages(self._client, query)

    async def search_documents(
        self, query: SearchDocumentsQuery
    ) -> SearchDocumentsResultListResponse:
        return await search_service.search_documents(self._client, query)


class WeaviateFaceRepository(FaceRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None:
        return await annotation_service.get_face(
            self._client, uuid.UUID(int=0), detection_id
        )

    async def list(self, query: FaceListQuery) -> FaceListResponse:
        return await annotation_service.list_faces(
            self._client,
            uuid.UUID(int=0),
            query.source_id,
            query.entity_id,
            query.after_id,
            query.limit,
            owner_user_id=query.owner_user_id,
        )

    async def create(
        self, payload: FaceCreateRequest, context: GenericActor
    ) -> FaceResponse:
        return await annotation_service.create_face(
            self._client, payload, context.user_id
        )

    async def create_batch(
        self, payloads: Sequence[FaceCreateRequest], context: GenericActor
    ) -> list[FaceResponse]:
        return await annotation_service.create_face_batch(
            self._client, _as_async_iterable(payloads), context.user_id
        )

    async def patch(
        self, detection_id: uuid.UUID, entity_id: uuid.UUID | None
    ) -> FaceResponse | None:
        return await annotation_service.patch_face_entity(
            self._client, uuid.UUID(int=0), detection_id, entity_id
        )

    async def patch_batch(
        self, commands: Sequence[FacePatchCommand]
    ) -> list[FaceResponse | None]:
        ids = [command.detection_id for command in commands]
        _require_unique_ids(ids, "face patch batch")
        if not ids:
            return []
        collection = self._client.collections.get(FACE_COLLECTION)
        fetched = await collection.query.fetch_objects_by_ids(
            ids,
            return_references=empty_reference_queries(["user", "entity", "source"]),
        )
        by_id = {item.uuid: item for item in fetched.objects}
        await _bounded_gather(
            [
                collection.data.reference_replace(
                    from_uuid=command.detection_id,
                    from_property="entity",
                    to=command.entity_id,
                )
                for command in commands
                if command.detection_id in by_id
            ]
        )
        return [
            (
                parse_face(item.properties, item.references, item.uuid).model_copy(
                    update={"entity_id": command.entity_id}
                )
                if (item := by_id.get(command.detection_id)) is not None
                else None
            )
            for command in commands
        ]

    async def update_embeddings_batch(
        self, payloads: Sequence[FaceEmbeddingUpdateRequest]
    ) -> int:
        return await annotation_service.update_face_embedding_batch(
            self._client, list(payloads)
        )

    async def delete(self, detection_id: uuid.UUID) -> bool:
        return await self._client.collections.get(FACE_COLLECTION).data.delete_by_id(
            detection_id
        )

    async def delete_batch(self, detection_ids: Sequence[uuid.UUID]) -> int:
        return await _delete_many(self._client, FACE_COLLECTION, detection_ids)

    async def search(self, query: SearchFacesRequest) -> SearchFacesResultListResponse:
        return await search_service.search_faces(self._client, query)


class WeaviateTextMentionRepository(TextMentionRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None:
        return await text_mention_service.get_text_mention(self._client, mention_id)

    async def list(self, query: TextMentionListQuery) -> TextMentionListResponse:
        return await text_mention_service.list_text_mentions(
            self._client,
            source_id=query.source_id,
            entity_id=query.entity_id,
            after_id=query.after_id,
            limit=query.limit,
        )

    async def create(self, payload: TextMentionCreateRequest) -> TextMentionResponse:
        return await text_mention_service.create_text_mention(self._client, payload)

    async def create_batch(
        self, payloads: Sequence[TextMentionCreateRequest]
    ) -> list[TextMentionResponse]:
        return await text_mention_service.create_text_mention_batch(
            self._client, _as_async_iterable(payloads)
        )

    async def patch(
        self, mention_id: uuid.UUID, entity_id: uuid.UUID
    ) -> TextMentionResponse | None:
        return await text_mention_service.reassign_text_mention_entity(
            self._client, mention_id, entity_id
        )

    async def patch_batch(
        self, commands: Sequence[TextMentionPatchCommand]
    ) -> list[TextMentionResponse | None]:
        ids = [command.mention_id for command in commands]
        _require_unique_ids(ids, "text mention patch batch")
        if not ids:
            return []
        collection = self._client.collections.get(TEXT_MENTION_COLLECTION)
        fetched = await collection.query.fetch_objects_by_ids(
            ids, return_references=empty_reference_queries(["entity", "source"])
        )
        by_id = {item.uuid: item for item in fetched.objects}
        await _bounded_gather(
            [
                collection.data.reference_replace(
                    from_uuid=command.mention_id,
                    from_property="entity",
                    to=command.entity_id,
                )
                for command in commands
                if command.mention_id in by_id
            ]
        )
        return [
            (
                parse_text_mention(
                    item.properties, item.references, item.uuid
                ).model_copy(update={"entity_id": command.entity_id})
                if (item := by_id.get(command.mention_id)) is not None
                else None
            )
            for command in commands
        ]

    async def delete(self, mention_id: uuid.UUID) -> bool:
        return await self._client.collections.get(
            TEXT_MENTION_COLLECTION
        ).data.delete_by_id(mention_id)

    async def delete_batch(self, mention_ids: Sequence[uuid.UUID]) -> int:
        return await _delete_many(self._client, TEXT_MENTION_COLLECTION, mention_ids)


class WeaviateUserRepository(UserRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, user_id: uuid.UUID) -> UserResponse | None:
        return await user_service.get_user(self._client, uuid.UUID(int=0), user_id)

    async def list(self, query: UserListQuery) -> UserListResponse:
        return await user_service.list_users(
            self._client,
            uuid.UUID(int=0),
            query.is_active,
            query.after_id,
            query.limit,
        )

    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        user_id = new_uuid6()
        await self._client.collections.get(USER_COLLECTION).data.insert(
            uuid=user_id,
            properties={**payload.model_dump(), "email": None},
        )
        return UserResponse(user_id=user_id, **payload.model_dump(), email=None)

    async def import_batch(
        self, payloads: Sequence[UserCreateRequest]
    ) -> list[UserResponse]:
        user_ids = [new_uuid6() for _ in payloads]
        objects = [
            DataObject(
                uuid=user_id,
                properties={**payload.model_dump(), "email": None},
            )
            for user_id, payload in zip(user_ids, payloads)
        ]
        if objects:
            result = await self._client.collections.get(
                USER_COLLECTION
            ).data.insert_many(objects)
            if result.has_errors:
                raise RuntimeError(f"User batch import failed: {result.errors}")
        return [
            UserResponse(user_id=user_id, **payload.model_dump(), email=None)
            for user_id, payload in zip(user_ids, payloads)
        ]

    async def patch(
        self, user_id: uuid.UUID, payload: UserPatchRequest
    ) -> UserResponse | None:
        return await user_service.update_user(
            self._client, uuid.UUID(int=0), user_id, payload
        )

    async def patch_batch(
        self, commands: Sequence[UserPatchCommand]
    ) -> list[UserResponse | None]:
        ids = [command.user_id for command in commands]
        _require_unique_ids(ids, "user patch batch")
        if not ids:
            return []
        collection = self._client.collections.get(USER_COLLECTION)
        fetched = await collection.query.fetch_objects_by_ids(ids)
        by_id = {item.uuid: item for item in fetched.objects}
        updates = [command.patch.model_dump(exclude_unset=True) for command in commands]
        await _bounded_gather(
            [
                collection.data.update(uuid=command.user_id, properties=update)
                for command, update in zip(commands, updates)
                if command.user_id in by_id
            ]
        )
        results: list[UserResponse | None] = []
        for command, update in zip(commands, updates):
            item = by_id.get(command.user_id)
            if item is None:
                results.append(None)
                continue
            properties = dict(item.properties)
            properties.update(update)
            results.append(parse_user(properties, item.references or {}, item.uuid))
        return results

    async def delete(self, user_id: uuid.UUID) -> bool:
        return await self._client.collections.get(USER_COLLECTION).data.delete_by_id(
            user_id
        )

    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int:
        return await _delete_many(self._client, USER_COLLECTION, user_ids)

    async def get_or_create(
        self, *, external_subject: str, external_issuer: str
    ) -> UserResponse:
        return await user_service.get_or_create_user(
            self._client,
            external_subject=external_subject,
            external_issuer=external_issuer,
        )


class WeaviateFaceModelRepository(FaceModelRepository):
    """Expose the statically configured Weaviate face vector model."""

    _model = FaceModelResponse(
        model_stub=DEFAULT_FACE_EMBEDDING_MODEL,
        embedding_dim=512,
    )

    async def register(self, payload: FaceModelRegisterRequest) -> FaceModelResponse:
        if (
            payload.model_stub != self._model.model_stub
            or payload.embedding_dim != self._model.embedding_dim
        ):
            raise ValueError(
                "dynamic face model registration is only supported by PostgreSQL"
            )
        return self._model

    async def list(self) -> FaceModelListResponse:
        return FaceModelListResponse(items=[self._model])


def weaviate_database(client: WeaviateAsyncClient) -> Database:
    """Bind all repositories to one request-scoped Weaviate client."""
    return Database(
        entities=WeaviateEntityRepository(client),
        sources=WeaviateSourceRepository(client),
        faces=WeaviateFaceRepository(client),
        face_models=WeaviateFaceModelRepository(),
        text_mentions=WeaviateTextMentionRepository(client),
        users=WeaviateUserRepository(client),
    )
