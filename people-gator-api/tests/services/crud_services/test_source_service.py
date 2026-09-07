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
from people_gator_api.schemas.sources import (
    NlcrAuthoritySourceMetadata,
    SourceDescriptorRequest,
    SourceResponse,
)
from people_gator_api.services.crud_services import source_service


@pytest.mark.asyncio
async def test_delete_source_returns_false_for_unknown_source() -> None:
    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[])

        async def fetch_object_by_id(self, *_args: object, **_kwargs: object) -> None:
            return None

    class _Collection:
        query = _Query()
        data = SimpleNamespace(delete_by_id=lambda _object_id: None)

    client = SimpleNamespace(collections=SimpleNamespace(get=lambda _name: _Collection()))

    deleted = await source_service.delete_source(client, uuid.uuid4(), uuid.uuid4())

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

    async def fake_get_source(
        _client: object,
        _principal_id: uuid.UUID,
        _source_id: uuid.UUID,
    ) -> SourceResponse:
        return SourceResponse(
            source_id=source_id,
            source_type=SourceKind.document,
            uri="https://example.test/source",
            metadata=None,
        )

    source_service.get_source = fake_get_source  # type: ignore[assignment]

    deleted = await source_service.delete_source(client, uuid.uuid4(), source_id)

    assert deleted is True
    assert deleted_ids == [source_id]


@pytest.mark.asyncio
async def test_resolve_source_reference_creates_source_from_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_ids: list[uuid.UUID] = []
    created_properties: list[dict[str, object]] = []

    async def fake_get_source_by_type_uri(
        _client: object,
        _principal_id: uuid.UUID,
        _source_type: SourceKind,
        _uri: str,
    ) -> SourceResponse | None:
        return None

    async def fake_upsert(
        _client: object,
        _collection_name: str,
        object_uuid: uuid.UUID,
        *,
        properties: dict[str, object],
        references: object | None = None,
        vector: object | None = None,
    ) -> None:
        del references
        del vector
        created_ids.append(object_uuid)
        created_properties.append(properties)

    monkeypatch.setattr(
        source_service, "get_source_by_type_uri", fake_get_source_by_type_uri
    )
    monkeypatch.setattr(source_service, "upsert", fake_upsert)

    descriptor = SourceDescriptorRequest(uri="https://www.wikidata.org/entity/Q42")
    resolved = await source_service.resolve_source_reference(
        client=SimpleNamespace(),  # type: ignore[reportArgumentType]
        principal_id=uuid.uuid4(),
        source_id=None,
        source=descriptor,
    )

    assert resolved.source_type == SourceKind.wikidata
    assert resolved.uri == "https://www.wikidata.org/entity/Q42"
    assert resolved.metadata is None
    assert created_ids == [resolved.source_id]
    assert created_properties == [
        {
            "source_type": SourceKind.wikidata.value,
            "uri": "https://www.wikidata.org/entity/Q42",
            "metadata": None,
        }
    ]


@pytest.mark.asyncio
async def test_resolve_source_reference_derives_uri_from_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_source_by_type_uri(
        _client: object,
        _principal_id: uuid.UUID,
        _source_type: SourceKind,
        _uri: str,
    ) -> SourceResponse | None:
        return None

    async def fake_upsert(
        _client: object,
        _collection_name: str,
        _object_uuid: uuid.UUID,
        *,
        properties: dict[str, object],
        references: object | None = None,
        vector: object | None = None,
    ) -> None:
        del references
        del vector
        assert properties["uri"] == "nlcr:abc-123"
        assert properties["source_type"] == SourceKind.nlcr.value

    monkeypatch.setattr(
        source_service, "get_source_by_type_uri", fake_get_source_by_type_uri
    )
    monkeypatch.setattr(source_service, "upsert", fake_upsert)

    descriptor = SourceDescriptorRequest(
        metadata=NlcrAuthoritySourceMetadata(nlcr_id="abc-123")
    )
    resolved = await source_service.resolve_source_reference(
        client=SimpleNamespace(),  # type: ignore[reportArgumentType]
        principal_id=uuid.uuid4(),
        source_id=None,
        source=descriptor,
    )

    assert resolved.source_type == SourceKind.nlcr
    assert resolved.uri == "nlcr:abc-123"
