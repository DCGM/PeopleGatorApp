from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from pydantic import AnyUrl

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
    DocumentSourceMetadata,
    DocumentCreateRequest,
    ImageCreateRequest,
    NlcrAuthoritySourceMetadata,
    PageCreateRequest,
    SourceDescriptorRequest,
    SourceResponse,
)
from people_gator_api.services.crud_services import source_service


def _source(source_type: SourceKind) -> SourceResponse:
    return SourceResponse(
        source_id=uuid.uuid4(),
        source_type=source_type,
        uri="https://example.test/source",
        metadata=None,
    )


def test_document_storage_includes_flat_archive_identity() -> None:
    document_id = uuid.uuid4()

    properties = source_service._source_storage_properties(
        SourceKind.document,
        "https://library.example/document/1",
        DocumentSourceMetadata(
            library="mzk",
            document=document_id,
            kramerius_url=AnyUrl("https://library.example/document/1"),
        ),
    )

    assert properties["library"] == "mzk"
    assert properties["document"] == document_id
    assert properties["page"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("include_document", [False, True])
async def test_resolve_source_filter_accepts_both_page_paths(
    monkeypatch: pytest.MonkeyPatch,
    include_document: bool,
) -> None:
    page_source = _source(SourceKind.page)
    page_id = uuid.uuid4()
    document_id = uuid.uuid4()

    async def fake_get_source_by_page_path(
        _client: object,
        _principal_id: uuid.UUID,
        library: str,
        requested_page_id: uuid.UUID,
        *,
        document_id: uuid.UUID | None = None,
    ) -> SourceResponse:
        assert library == "mzk"
        assert requested_page_id == page_id
        assert document_id == (expected_document_id if include_document else None)
        return page_source

    expected_document_id = document_id
    monkeypatch.setattr(
        source_service,
        "get_source_by_page_path",
        fake_get_source_by_page_path,
    )
    canonical_path = (
        f"mzk/{document_id}/{page_id}" if include_document else f"mzk/{page_id}"
    )

    resolved = await source_service.resolve_source_filter(
        object(),  # pyright: ignore[reportArgumentType] - database lookup is mocked.
        uuid.uuid4(),
        source_id=None,
        page=canonical_path,
        document=None,
        image=None,
    )

    assert resolved == page_source.source_id


@pytest.mark.asyncio
async def test_resolve_source_filter_accepts_document_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_source = _source(SourceKind.document)
    document_id = uuid.uuid4()

    async def fake_get_source_by_document_identity(
        _client: object,
        _principal_id: uuid.UUID,
        library: str,
        requested_document_id: uuid.UUID,
    ) -> SourceResponse:
        assert library == "mzk"
        assert requested_document_id == document_id
        return document_source

    monkeypatch.setattr(
        source_service,
        "get_source_by_document_identity",
        fake_get_source_by_document_identity,
    )

    resolved = await source_service.resolve_source_filter(
        object(),  # pyright: ignore[reportArgumentType] - database lookup is mocked.
        uuid.uuid4(),
        source_id=None,
        page=None,
        document=f"mzk/{document_id}",
        image=None,
    )

    assert resolved == document_source.source_id


@pytest.mark.asyncio
async def test_resolve_source_filter_accepts_image_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_source = _source(SourceKind.image)
    image_url = "https://images.example.test/portrait.jpg?size=large"

    async def fake_get_source_by_types_uri(
        _client: object,
        _principal_id: uuid.UUID,
        source_types: tuple[SourceKind, ...],
        uri: str,
    ) -> SourceResponse:
        assert source_types == (
            SourceKind.image,
            SourceKind.wikimedia,
            SourceKind.obalkyknih,
        )
        assert uri == image_url
        return image_source

    monkeypatch.setattr(
        source_service,
        "get_source_by_types_uri",
        fake_get_source_by_types_uri,
    )

    resolved = await source_service.resolve_source_filter(
        object(),  # pyright: ignore[reportArgumentType] - database lookup is mocked.
        uuid.uuid4(),
        source_id=None,
        page=None,
        document=None,
        image=image_url,
    )

    assert resolved == image_source.source_id


@pytest.mark.asyncio
async def test_resolve_source_filter_rejects_conflicting_selectors() -> None:
    with pytest.raises(source_service.SourceResolutionError) as exc_info:
        await source_service.resolve_source_filter(
            object(),  # pyright: ignore[reportArgumentType] - rejected before database access.
            uuid.uuid4(),
            source_id=uuid.uuid4(),
            page=f"mzk/{uuid.uuid4()}",
            document=None,
            image=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_source_filter"


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

    client = SimpleNamespace(
        collections=SimpleNamespace(get=lambda _name: _Collection())
    )

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

    class _Data:
        async def insert(
            self,
            *,
            uuid: uuid.UUID,
            properties: dict[str, object],
        ) -> None:
            created_ids.append(uuid)
            created_properties.append(properties)

    monkeypatch.setattr(
        source_service, "get_source_by_type_uri", fake_get_source_by_type_uri
    )

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    descriptor = SourceDescriptorRequest(uri="https://www.wikidata.org/entity/Q42")
    resolved = await source_service.resolve_source_reference(
        client=client,  # type: ignore[reportArgumentType]
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
            "library": None,
            "document": None,
            "page": None,
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

    class _Data:
        async def insert(
            self,
            *,
            uuid: uuid.UUID,
            properties: dict[str, object],
        ) -> None:
            del uuid
            assert properties["uri"] == "nlcr:abc-123"
            assert properties["source_type"] == SourceKind.nlcr.value

    monkeypatch.setattr(
        source_service, "get_source_by_type_uri", fake_get_source_by_type_uri
    )

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    descriptor = SourceDescriptorRequest(
        metadata=NlcrAuthoritySourceMetadata(nlcr_id="abc-123")
    )
    resolved = await source_service.resolve_source_reference(
        client=client,  # type: ignore[reportArgumentType]
        principal_id=uuid.uuid4(),
        source_id=None,
        source=descriptor,
    )

    assert resolved.source_type == SourceKind.nlcr
    assert resolved.uri == "nlcr:abc-123"


@pytest.mark.asyncio
async def test_resolve_source_reference_creates_and_links_inline_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted: dict[str, object] = {}
    document_id = uuid.uuid4()
    page_id = uuid.uuid4()

    async def fake_get_source_by_page_identity(
        _client: object,
        _principal_id: uuid.UUID,
        library: str,
        requested_document_id: uuid.UUID,
        requested_page_id: uuid.UUID,
    ) -> None:
        assert library == "mzk"
        assert requested_document_id == document_id
        assert requested_page_id == page_id
        return None

    class _Data:
        async def insert(
            self,
            *,
            uuid: uuid.UUID,
            properties: dict[str, object],
        ) -> None:
            inserted["uuid"] = uuid
            inserted["properties"] = properties

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    monkeypatch.setattr(
        source_service,
        "get_source_by_page_identity",
        fake_get_source_by_page_identity,
    )
    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))
    descriptor = SourceDescriptorRequest(
        page=PageCreateRequest(
            library="mzk",
            document_id=document_id,
            page_id=page_id,
        )
    )

    resolved = await source_service.resolve_source_reference(
        client,  # pyright: ignore[reportArgumentType] - lightweight client double.
        uuid.uuid4(),
        source_id=None,
        source=descriptor,
    )

    assert resolved.source_id == inserted["uuid"]
    assert resolved.source_type == SourceKind.page
    assert inserted["properties"] == {
        "source_type": "page",
        "uri": (
            f"https://www.digitalniknihovna.cz/mzk/view/uuid:{document_id}"
            f"?page=uuid:{page_id}"
        ),
        "metadata": {
            "library": "mzk",
            "document": str(document_id),
            "page": str(page_id),
            "kramerius_url": (
                f"https://www.digitalniknihovna.cz/mzk/view/uuid:{document_id}"
                f"?page=uuid:{page_id}"
            ),
        },
        "library": "mzk",
        "document": document_id,
        "page": page_id,
    }


@pytest.mark.asyncio
async def test_resolve_source_reference_creates_inline_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid.uuid4()
    inserted: dict[str, object] = {}

    async def fake_get_source_by_document_identity(*_args: object) -> None:
        return None

    class _Data:
        async def insert(
            self,
            *,
            uuid: uuid.UUID,
            properties: dict[str, object],
        ) -> None:
            inserted["uuid"] = uuid
            inserted["properties"] = properties

    monkeypatch.setattr(
        source_service,
        "get_source_by_document_identity",
        fake_get_source_by_document_identity,
    )
    client = SimpleNamespace(
        collections=SimpleNamespace(get=lambda _name: SimpleNamespace(data=_Data()))
    )

    resolved = await source_service.resolve_source_reference(
        client,  # pyright: ignore[reportArgumentType] - lightweight client double.
        uuid.uuid4(),
        source_id=None,
        source=SourceDescriptorRequest(
            document=DocumentCreateRequest(
                library="mzk",
                document_id=document_id,
            )
        ),
    )

    expected_uri = f"https://www.digitalniknihovna.cz/mzk/uuid/uuid:{document_id}"
    assert resolved.source_id == inserted["uuid"]
    assert resolved.source_type == SourceKind.document
    assert resolved.uri == expected_uri
    assert inserted["properties"] == {
        "source_type": "document",
        "uri": expected_uri,
        "metadata": {
            "library": "mzk",
            "document": str(document_id),
            "kramerius_url": expected_uri,
        },
        "library": "mzk",
        "document": document_id,
        "page": None,
    }


@pytest.mark.asyncio
async def test_resolve_source_reference_reuses_inline_image_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SourceResponse(
        source_id=uuid.uuid4(),
        source_type=SourceKind.image,
        uri="https://images.example/portrait.jpg",
        metadata=None,
    )

    async def fake_get_source_by_type_uri(
        _client: object,
        _principal_id: uuid.UUID,
        source_type: SourceKind,
        uri: str,
    ) -> SourceResponse:
        assert source_type == SourceKind.image
        assert uri == existing.uri
        return existing

    monkeypatch.setattr(
        source_service, "get_source_by_type_uri", fake_get_source_by_type_uri
    )

    resolved = await source_service.resolve_source_reference(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType] - no database write expected.
        uuid.uuid4(),
        source_id=None,
        source=SourceDescriptorRequest(
            image=ImageCreateRequest(url=AnyUrl(existing.uri))
        ),
    )

    assert resolved == existing
