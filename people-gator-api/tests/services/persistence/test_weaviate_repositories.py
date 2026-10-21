import uuid
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import AnyUrl, ValidationError
from weaviate import WeaviateAsyncClient

from people_gator_api.persistence.contracts import CreateResult, Database
from people_gator_api.persistence.weaviate import (
    WeaviateEntityRepository,
    WeaviateFaceModelRepository,
    WeaviateFaceRepository,
    WeaviateSourceRepository,
    WeaviateTextMentionRepository,
    weaviate_database,
)
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.entities import EntityCreateRequest, EntityListRequest
from people_gator_api.schemas.enums import EntityType, SourceKind
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListRequest,
)
from people_gator_api.schemas.search import (
    SearchDocumentsRequest,
    SearchEntitiesRequest,
    SearchPagesRequest,
)
from people_gator_api.schemas.sources import (
    GenericSourceCreateRequest,
    PageCreateRequest,
    DocumentCreateRequest,
    ImageCreateRequest,
)


def _client(collection: Mock) -> WeaviateAsyncClient:
    return cast(
        WeaviateAsyncClient,
        SimpleNamespace(
            collections=SimpleNamespace(get=lambda name: collection),
        ),
    )


def _stored(properties: dict[str, object], **references: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=uuid.uuid4(),
        properties=properties,
        vector={},
        references={
            name: SimpleNamespace(objects=[SimpleNamespace(uuid=value)])
            for name, value in references.items()
        },
    )


def _collection() -> Mock:
    return Mock(
        data=Mock(exists=AsyncMock(return_value=True), insert=AsyncMock(), update=AsyncMock(), replace=AsyncMock()),
        query=Mock(
            fetch_object_by_id=AsyncMock(return_value=None),
            fetch_objects=AsyncMock(return_value=SimpleNamespace(objects=[])),
        ),
        aggregate=Mock(over_all=AsyncMock(return_value=SimpleNamespace(total_count=0, groups=[]))),
    )


def test_factory_returns_contract_facade() -> None:
    database = weaviate_database(_client(_collection()))
    assert isinstance(database, Database)
    assert isinstance(database.entities, WeaviateEntityRepository)
    assert isinstance(database.sources, WeaviateSourceRepository)
    assert isinstance(database.faces, WeaviateFaceRepository)
    assert isinstance(database.face_models, WeaviateFaceModelRepository)
    assert isinstance(database.text_mentions, WeaviateTextMentionRepository)


@pytest.mark.asyncio
async def test_entity_creation_serializes_properties_and_preserves_response_types() -> (
    None
):
    collection = _collection()
    repository = WeaviateEntityRepository(_client(collection))
    actor = GenericActor(user_id=uuid.uuid4())
    result = await repository.create(
        payload=EntityCreateRequest(name="Ada", entity_type=EntityType.person),
        context=actor,
    )
    assert result.entity_type is EntityType.person
    assert result.user_id == actor.user_id
    assert result.aliases is None
    properties = collection.data.insert.await_args.kwargs["properties"]
    assert properties["entity_type"] == "person"
    assert "description" not in properties


@pytest.mark.asyncio
async def test_list_sorts_and_resumes_with_opaque_cursor() -> None:
    collection = _collection()
    owner = uuid.uuid4()
    objects = [
        _stored({"name": "Ada", "entity_type": "person"}, user=owner) for _ in range(3)
    ]
    objects.sort(key=lambda item: item.uuid)
    collection.query.fetch_objects.return_value = SimpleNamespace(objects=objects[::-1])
    collection.aggregate.over_all.return_value = SimpleNamespace(total_count=9, groups=[])
    repository = WeaviateEntityRepository(_client(collection))
    result = await repository.list(
        query=EntityListRequest(limit=2, return_total_count=True)
    )
    assert [item.entity_id for item in result.items] == [
        item.uuid for item in objects[:2]
    ]
    assert result.total_count == 9
    assert result.cursor is not None
    collection.query.fetch_objects.return_value = SimpleNamespace(objects=objects[2:])
    resumed = await repository.list(
        query=EntityListRequest(
            limit=2,
            return_total_count=True,
            cursor=result.cursor,
        )
    )
    assert collection.query.fetch_objects.await_args.kwargs["after"] == objects[1].uuid
    assert resumed.cursor is None
    with pytest.raises(ValueError, match="different query"):
        await repository.list(query=EntityListRequest(limit=1, cursor=result.cursor))


@pytest.mark.asyncio
async def test_count_only_list_skips_object_query() -> None:
    collection = _collection()
    collection.aggregate.over_all.return_value = SimpleNamespace(total_count=9, groups=[])
    response = await WeaviateEntityRepository(_client(collection)).list(
        query=EntityListRequest(limit=0, return_total_count=True),
    )
    assert response.items == []
    assert response.total_count == 9
    assert response.cursor is None
    collection.query.fetch_objects.assert_not_awaited()


@pytest.mark.asyncio
async def test_required_entity_reference_is_validated() -> None:
    collection = _collection()
    stored = _stored({"name": "Ada", "entity_type": "person"})
    collection.query.fetch_object_by_id.return_value = stored
    with pytest.raises(ValueError, match="lacks user reference"):
        await WeaviateEntityRepository(_client(collection)).get(entity_id=stored.uuid)


@pytest.mark.asyncio
async def test_invalid_stored_property_is_rejected_at_schema_boundary() -> None:
    collection = _collection()
    stored = _stored({"name": "Ada", "entity_type": "invalid"}, user=uuid.uuid4())
    collection.query.fetch_object_by_id.return_value = stored
    with pytest.raises(ValidationError):
        await WeaviateEntityRepository(_client(collection)).get(entity_id=stored.uuid)


@pytest.mark.asyncio
async def test_mentions_preserve_default_context_and_response_subclass() -> None:
    collection = _collection()
    repository = WeaviateTextMentionRepository(_client(collection))
    mention = await repository.create(
        payload=TextMentionCreateRequest(
            name="Ada", source_id=uuid.uuid4(), entity_id=uuid.uuid4()
        ),
        context=GenericActor(user_id=uuid.uuid4()),
    )
    assert mention.context is None
    assert collection.data.insert.await_args.kwargs["properties"]["context"] is None
    collection.query.fetch_objects.return_value = SimpleNamespace(
        objects=[
            _stored(
                {"name": mention.name, "context": None},
                source=mention.source_id,
                entity=mention.entity_id,
            )
        ]
    )
    result = await repository.list(query=TextMentionListRequest(limit=10))
    assert result.items[0].context is None
    assert result.items[0].source_id == mention.source_id


def _source_spec(kind: SourceKind) -> GenericSourceCreateRequest:
    if kind is SourceKind.page:
        return PageCreateRequest(
            library="library", document_id=uuid.uuid4(), page_id=uuid.uuid4()
        ).to_generic()
    if kind is SourceKind.document:
        return DocumentCreateRequest(
            library="library", document_id=uuid.uuid4()
        ).to_generic()
    return ImageCreateRequest(url=AnyUrl("https://example.org/image.png")).to_generic()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", [SourceKind.page, SourceKind.document, SourceKind.image]
)
async def test_source_creation_and_repeated_identity(kind: SourceKind) -> None:
    collection = _collection()
    spec = _source_spec(kind)
    repository = WeaviateSourceRepository(_client(collection))
    source, created = await repository.get_or_create(spec=spec)
    assert created is CreateResult.CREATED
    inserted = collection.data.insert.await_args.kwargs
    existing = _stored(inserted["properties"])
    existing.uuid = inserted["uuid"]
    collection.query.fetch_object_by_id.return_value = existing
    repeated, created = await repository.get_or_create(spec=spec)
    assert created is CreateResult.EXISTING
    assert repeated == source
    collection.data.insert.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [SourceKind.page, SourceKind.document])
async def test_source_search_supplies_score_before_validation(kind: SourceKind) -> None:
    collection = _collection()
    spec = _source_spec(kind)
    properties: dict[str, object] = {
        "source_type": kind.value,
        "uri": str(spec.url),
        "library": spec.library,
        "document": spec.document_id,
        "page": spec.page_id if kind is SourceKind.page else None,
    }
    collection.query.fetch_objects.return_value = SimpleNamespace(
        objects=[_stored(properties)]
    )
    repository = WeaviateSourceRepository(_client(collection))
    if kind is SourceKind.page:
        result = await repository.search_pages(
            query=SearchPagesRequest.model_validate(
                {
                    "query": {"text": ["Ada"]},
                    "limit": 10,
                }
            )
        )
    else:
        result = await repository.search_documents(
            query=SearchDocumentsRequest.model_validate(
                {
                    "query": {"text": ["Ada"]},
                    "limit": 10,
                }
            )
        )
    assert result.items[0].score > 0
    assert isinstance(result.items[0].document_id, uuid.UUID)


@pytest.mark.asyncio
async def test_entity_search_parses_typed_results() -> None:
    collection = _collection()
    stored = _stored({"name": "Ada", "entity_type": "person"}, user=uuid.uuid4())
    collection.query.bm25 = AsyncMock(return_value=SimpleNamespace(objects=[stored]))
    result = await WeaviateEntityRepository(_client(collection)).search(
        query=SearchEntitiesRequest.model_validate(
            {"query": {"text": ["Ada"]}, "limit": 1}
        ),
    )
    assert result.items[0].entity_id == stored.uuid
    assert result.items[0].score > 0


@pytest.mark.asyncio
async def test_face_model_reregistration_checks_stored_dimension() -> None:
    collection = _collection()
    collection.query.fetch_object_by_id.return_value = _stored(
        {
            "model_stub": "test-model",
            "embedding_dim": 512,
        }
    )
    fake_client = _client(collection)
    fake_client.collections.exists = AsyncMock(return_value=True)
    repository = WeaviateFaceModelRepository(fake_client)
    result = await repository.register(
        payload=FaceModelRegisterRequest(
            model_stub="test-model",
            embedding_dim=512,
        )
    )
    assert result.embedding_dim == 512
    with pytest.raises(ValueError, match="cannot change"):
        await repository.register(
            payload=FaceModelRegisterRequest(model_stub="test-model", embedding_dim=128)
        )
    collection.data.insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_state_only_mention_patch_is_atomic_preserves_identity_and_verification():
    from people_gator_api.schemas.mentions import TextMentionPatchRequest
    from people_gator_api.schemas.enums import EntityLinkState
    collection = _collection()
    actor = GenericActor(user_id=uuid.uuid4())
    entity_id, source_id = uuid.uuid4(), uuid.uuid4()
    stored = _stored({"name": "Ada", "context": "A caption", "entity_link_state": "automatic"}, entity=entity_id, source=source_id)
    collection.query.fetch_object_by_id.return_value = stored
    repo = WeaviateTextMentionRepository(_client(collection))
    verified = await repo.patch(stored.uuid, TextMentionPatchRequest(entity_link_state="verified"), actor)
    assert verified.entity_id == entity_id and verified.mention_id == stored.uuid
    assert verified.entity_link_verified_by_user_id == actor.user_id
    replaced = collection.data.replace.await_args.kwargs
    assert replaced["references"] == {"entity": entity_id, "source": source_id}
    assert replaced["properties"]["name"] == "Ada"
    assert replaced["properties"]["entity_link_verified_at"] is not None
    # Simulate persisted data; repeated verification must do no writes/touches.
    stored.properties = replaced["properties"]
    collection.data.replace.reset_mock()
    collection.data.update.reset_mock()
    repeated = await repo.patch(stored.uuid, TextMentionPatchRequest(entity_link_state="verified"), GenericActor(user_id=uuid.uuid4()))
    assert repeated.entity_link_verified_at == verified.entity_link_verified_at
    assert repeated.entity_link_verified_by_user_id == actor.user_id
    collection.data.replace.assert_not_awaited()
    collection.data.update.assert_not_awaited()
    with pytest.raises(ValueError):
        await repo.patch(stored.uuid, TextMentionPatchRequest(entity_link_state=None), actor)
    collection.data.replace.assert_not_awaited()
    reassigned = await repo.patch(stored.uuid, TextMentionPatchRequest(entity_id=uuid.uuid4()), actor)
    assert reassigned.entity_link_state == EntityLinkState.manual
    assert reassigned.entity_link_verified_at is None
    assert reassigned.name == verified.name and reassigned.source_id == source_id


@pytest.mark.asyncio
async def test_explicit_sort_is_rejected_not_ignored() -> None:
    from people_gator_api.schemas.search import QueryBase, SearchEntitiesRequest

    repository = WeaviateEntityRepository(_client(_collection()))
    with pytest.raises(NotImplementedError, match="sorting"):
        await repository.list(query=EntityListRequest(limit=1, sort="name"))
    with pytest.raises(NotImplementedError, match="sorting"):
        await repository.search(SearchEntitiesRequest(limit=1, query=QueryBase(text=["Ada"]), sort="name"))
