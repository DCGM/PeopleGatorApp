from __future__ import annotations

import os
from types import SimpleNamespace
import uuid

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

from people_gator_api.app import app
from people_gator_api.routes.v1.sources import delete_source_route, get_source_route
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.users import UserResponse


class FakeCollection:
    def __init__(self, owner: FakeClient) -> None:
        super().__init__()
        self.owner = owner

    @property
    def data(self) -> FakeData:
        return FakeData(self.owner)

    @property
    def query(self) -> FakeQuery:
        return FakeQuery(self.owner)


class FakeData:
    def __init__(self, owner: FakeClient) -> None:
        super().__init__()
        self.owner = owner

    async def delete_by_id(self, object_id: uuid.UUID) -> bool:
        return self.owner.objects.pop(str(object_id), None) is not None


class FakeQuery:
    def __init__(self, owner: FakeClient) -> None:
        super().__init__()
        self.owner = owner

    async def fetch_object_by_id(
        self,
        object_id: uuid.UUID,
        **_kwargs: object,
    ) -> object | None:
        entry = self.owner.objects.get(str(object_id))
        if entry is None:
            return None
        return SimpleNamespace(
            uuid=entry["uuid"],
            properties=entry["properties"],
            references={},
        )


class FakeClient:
    def __init__(self) -> None:
        super().__init__()
        self.objects: dict[str, dict[str, object]] = {}

    @property
    def collections(self) -> FakeCollections:
        return FakeCollections(self)


class FakeCollections:
    def __init__(self, owner: FakeClient) -> None:
        super().__init__()
        self.owner = owner

    def get(self, _collection_name: str) -> FakeCollection:
        return FakeCollection(self.owner)


def _user() -> UserResponse:
    return UserResponse(
        user_id=uuid.uuid4(),
        display_name="Test User",
        is_active=True,
        external_subject="test-subject",
        external_issuer="test-issuer",
        email=None,
    )


def test_sources_contract_is_read_only_and_has_no_metadata() -> None:
    openapi = app.openapi()

    assert "post" not in openapi["paths"]["/api/v1/sources"]
    source_properties = openapi["components"]["schemas"]["SourceResponse"]["properties"]
    assert set(source_properties) == {"source_id", "source_type", "uri"}


@pytest.mark.asyncio
async def test_source_get_delete_roundtrip() -> None:
    session = FakeClient()
    source_id = uuid.uuid4()
    uri = "https://example.test/roundtrip-image.jpg"
    session.objects[str(source_id)] = {
        "uuid": source_id,
        "properties": {
            "source_type": SourceKind.image.value,
            "uri": uri,
            "library": None,
            "document": None,
            "page": None,
        },
    }

    fetched = await get_source_route(
        source_id=source_id,
        user=_user(),
        session=session,  # pyright: ignore[reportArgumentType]
    )
    assert fetched.source_id == source_id
    assert fetched.uri == uri
    assert fetched.model_dump() == {
        "source_id": source_id,
        "source_type": SourceKind.image,
        "uri": uri,
    }

    await delete_source_route(
        source_id=source_id,
        user=_user(),
        session=session,  # pyright: ignore[reportArgumentType]
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_source_route(
            source_id=source_id,
            user=_user(),
            session=session,  # pyright: ignore[reportArgumentType]
        )

    assert exc_info.value.status_code == 404
