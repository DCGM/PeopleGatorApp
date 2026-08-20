from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_SECURE", "false")

from people_gator_api.routes.v1.sources import create_source_route, delete_source_route, get_source_route
from people_gator_api.schemas.enums import SourceKind, PrincipalType
from people_gator_api.schemas.sources import SourceCreateRequest, WikidataSourceMetadata
from people_gator_api.schemas.principals import UserResponse
from people_gator_api.services.sse import LocalTopicBroker


class FakeCollection:
    def __init__(self, owner: "FakeClient") -> None:
        super().__init__()
        self.owner = owner

    @property
    def data(self) -> "FakeData":
        return FakeData(self.owner)

    @property
    def query(self) -> "FakeQuery":
        return FakeQuery(self.owner)


class FakeData:
    def __init__(self, owner: "FakeClient") -> None:
        super().__init__()
        self.owner = owner

    async def exists(self, object_id: uuid.UUID) -> bool:
        return str(object_id) in self.owner.objects

    async def insert(self, *, uuid: uuid.UUID, properties: dict[str, object], **_kwargs: object) -> None:
        self.owner.objects[str(uuid)] = {"uuid": uuid, "properties": properties}

    async def replace(self, *, uuid: uuid.UUID, properties: dict[str, object], **_kwargs: object) -> None:
        self.owner.objects[str(uuid)] = {"uuid": uuid, "properties": properties}

    async def delete_by_id(self, object_id: uuid.UUID) -> None:
        self.owner.objects.pop(str(object_id), None)


class FakeQuery:
    def __init__(self, owner: "FakeClient") -> None:
        super().__init__()
        self.owner = owner

    async def fetch_object_by_id(self, object_id: uuid.UUID, **kwargs: object) -> object | None:
        del kwargs
        entry = self.owner.objects.get(str(object_id))
        if entry is None:
            return None
        return SimpleNamespace(uuid=entry["uuid"], properties=entry["properties"], references={})

    async def fetch_objects(self, *, filters: object | None = None, limit: int = 1, **kwargs: object) -> object:
        del filters
        del kwargs
        objects = [
            SimpleNamespace(uuid=entry["uuid"], properties=entry["properties"])
            for entry in self.owner.objects.values()
        ][:limit]
        return SimpleNamespace(objects=objects)


class FakeClient:
    def __init__(self) -> None:
        super().__init__()
        self.objects: dict[str, dict[str, object]] = {}

    @property
    def collections(self) -> "FakeCollections":
        return FakeCollections(self)


class FakeCollections:
    def __init__(self, owner: FakeClient) -> None:
        super().__init__()
        self.owner = owner

    def get(self, _collection_name: str) -> FakeCollection:
        return FakeCollection(self.owner)


@pytest.mark.asyncio
async def test_source_post_get_delete_roundtrip() -> None:
    session = FakeClient()  # pyright: ignore[reportArgumentType] - tests use a lightweight client double
    principal = UserResponse(
        principal_id=uuid.uuid4(),
        principal_type=PrincipalType.user,
        display_name="Test User",
        is_active=True,
        external_subject="test-subject",
        external_issuer="test-issuer",
        email=None,
    )
    broker = LocalTopicBroker()

    payload = SourceCreateRequest(
        source_type=SourceKind.wikidata,
        uri="https://example.test/authority-roundtrip",
        metadata=WikidataSourceMetadata(
            entity_id="Q999999",
            wikidata_url="https://www.wikidata.org/entity/Q999999",  # pyright: ignore[reportArgumentType]
        ),
    )

    created = await create_source_route(payload=payload, principal=principal, session=session, broker=broker)  # pyright: ignore[reportArgumentType]
    assert created.source_type == payload.source_type
    assert created.uri == payload.uri
    assert created.metadata is not None
    assert created.metadata.entity_id == payload.metadata.entity_id

    fetched = await get_source_route(source_id=created.source_id, principal=principal, session=session)  # pyright: ignore[reportArgumentType]
    assert fetched.source_id == created.source_id
    assert fetched.uri == payload.uri
    assert fetched.metadata is not None
    assert fetched.metadata.entity_id == payload.metadata.entity_id

    await delete_source_route(source_id=created.source_id, principal=principal, session=session, broker=broker)  # pyright: ignore[reportArgumentType]

    with pytest.raises(HTTPException) as exc_info:
        await get_source_route(source_id=created.source_id, principal=principal, session=session)  # pyright: ignore[reportArgumentType]

    assert exc_info.value.status_code == 404

