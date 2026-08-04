from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest

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

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import SourceResponse
from people_gator_api.services.crud_services import source_service


@pytest.mark.asyncio
async def test_delete_source_returns_false_for_unknown_source() -> None:
    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[])

    class _Collection:
        query = _Query()
        data = SimpleNamespace(delete_by_id=lambda _object_id: None)

    client = SimpleNamespace(collections=SimpleNamespace(get=lambda _name: _Collection()))

    deleted = await source_service.delete_source(client, uuid.uuid4())

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_source_removes_existing_source() -> None:
    source_id = uuid.uuid4()
    deleted_ids: list[uuid.UUID] = []

    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[])

    class _Collection:
        query = _Query()

        class _Data:
            async def delete_by_id(self, object_id: uuid.UUID) -> None:
                deleted_ids.append(object_id)

        data = _Data()

    class _Collections:
        def get(self, _collection_name: str) -> _Collection:
            return _Collection()

    client = SimpleNamespace(collections=_Collections())

    async def fake_get_source(_client: object, _source_id: uuid.UUID) -> SourceResponse:
        return SourceResponse(
            source_id=source_id,
            source_type=SourceKind.document,
            uri="https://example.test/source",
            metadata=None,
        )

    source_service.get_source = fake_get_source  # type: ignore[assignment]

    deleted = await source_service.delete_source(client, source_id)

    assert deleted is True
    assert deleted_ids == [source_id]
