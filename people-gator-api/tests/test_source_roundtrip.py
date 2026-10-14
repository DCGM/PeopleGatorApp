from __future__ import annotations

import os
from types import SimpleNamespace
import uuid

from pydantic import AnyUrl
import pytest
from fastapi import HTTPException


os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PORT", "5432")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__OPENROUTER__API_KEY", "test")


from people_gator_api.app import app
from people_gator_api.routes.v1.sources import delete_source_route, get_source_route
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import SourceResponseBase
from people_gator_api.schemas.users import UserResponse


class FakeSources:
    def __init__(self) -> None:
        super().__init__()
        self.objects: dict[uuid.UUID, SourceResponseBase] = {}

    async def get_source(self, source_id: uuid.UUID) -> SourceResponseBase | None:
        return self.objects.get(source_id)

    async def delete(self, source_id: uuid.UUID, *, context: UserResponse) -> bool:
        return self.objects.pop(source_id, None) is not None


def _user() -> UserResponse:
    return UserResponse(
        user_id=uuid.uuid4(),
        display_name="Test User",
        is_active=True,
        external_subject="test-subject",
        external_issuer="test-issuer",
        email=None,
    )


def test_sources_contract_is_read_only_and_has_no_polymorphic_metadata() -> None:
    openapi = app.openapi()

    assert "post" not in openapi["paths"]["/api/v1/sources"]
    source_properties = openapi["components"]["schemas"]["SourceResponseBase"][
        "properties"
    ]
    assert set(source_properties) == {"source_id", "source_type", "url", "last_touched_at", "last_touched_by_user_id", "last_touched_by_api_key_id"}


@pytest.mark.asyncio
async def test_source_get_delete_roundtrip_through_contract() -> None:
    sources = FakeSources()
    database = SimpleNamespace(sources=sources)
    source_id = uuid.uuid4()
    url = "https://example.test/roundtrip-image.jpg"
    sources.objects[source_id] = SourceResponseBase(
        source_id=source_id,
        source_type=SourceKind.image,
        url=AnyUrl(url),
    )

    fetched = await get_source_route(
        source_id=source_id,
        user=_user(),
        database=database,  # type: ignore[arg-type]
    )
    assert fetched.source_id == source_id
    assert str(fetched.url) == url
    assert fetched.source_type == SourceKind.image

    await delete_source_route(
        source_id=source_id,
        user=_user(),
        database=database,  # type: ignore[arg-type]
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_source_route(
            source_id=source_id,
            user=_user(),
            database=database,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404


@pytest.mark.parametrize('kind', list(SourceKind))
def test_processing_survives_all_source_response_conversions(kind):
    from datetime import datetime, timezone
    from people_gator_api.schemas.sources import GenericSourceResponse, PageResponse, DocumentResponse, ImageResponse, document_url, page_url
    identity, page = uuid.uuid4(), uuid.uuid4()
    timestamp, actor, key = datetime.now(timezone.utc), uuid.uuid4(), uuid.uuid4()
    archive = {'library':'test','document_id':identity} if kind != SourceKind.image else {}
    if kind == SourceKind.page: archive['page_id'] = page
    url = page_url('test',identity,page) if kind == SourceKind.page else document_url('test',identity) if kind == SourceKind.document else 'https://preview.invalid/source.png'
    generic = GenericSourceResponse(source_id=uuid.uuid4(),source_type=kind,url=url,last_touched_at=timestamp,last_touched_by_user_id=actor,last_touched_by_api_key_id=key,**archive)
    cls = {SourceKind.page:PageResponse,SourceKind.document:DocumentResponse,SourceKind.image:ImageResponse}[kind]
    for response in [SourceResponseBase.from_generic(generic),cls.from_generic(generic)]:
        assert (response.last_touched_at,response.last_touched_by_user_id,response.last_touched_by_api_key_id) == (timestamp,actor,key)
