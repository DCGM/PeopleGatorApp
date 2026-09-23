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
os.environ.setdefault("PEOPLE_GATOR_API__OPENROUTER__API_KEY", "test")

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentSourceMetadata,
    ImageCreateRequest,
    PageCreateRequest,
    SourceDescriptorRequest,
    SourceResponseBase,
)
from people_gator_api.services.crud_services import (
    source_resolution_service,
    source_service,
)
from people_gator_api.services.crud_services.source_service import SourceCreateSpec


def _source(source_type: SourceKind) -> SourceResponseBase:
    return SourceResponseBase(
        source_id=uuid.uuid4(),
        source_type=source_type,
        url="https://example.test/source",
    )


def test_document_storage_includes_flat_archive_identity() -> None:
    document_id = uuid.uuid4()

    properties = source_service._storage_properties(
        SourceKind.document,
        "https://library.example/document/1",
        DocumentSourceMetadata(library="mzk", document=document_id),
    )

    assert properties == {
        "source_type": "document",
        "uri": "https://library.example/document/1",
        "library": "mzk",
        "document": document_id,
        "page": None,
    }


@pytest.mark.parametrize(
    ("source_type", "kwargs"),
    [
        (SourceKind.image, {}),
        (SourceKind.image, {"url": "https://example.test", "library": "mzk"}),
        (SourceKind.document, {"library": "mzk"}),
        (
            SourceKind.document,
            {"library": "mzk", "document_id": uuid.uuid4(), "page_id": uuid.uuid4()},
        ),
        (
            SourceKind.page,
            {"library": "mzk", "document_id": uuid.uuid4()},
        ),
    ],
)
def test_source_content_rejects_invalid_type_combinations(
    source_type: SourceKind,
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        source_service._source_content(
            source_type,
            library=kwargs.get("library"),
            document_id=kwargs.get("document_id"),
            page_id=kwargs.get("page_id"),
            url=kwargs.get("url"),
        )


@pytest.mark.asyncio
async def test_create_source_checks_identity_and_inserts_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid.uuid4()
    inserted: dict[str, object] = {}

    async def fake_get_source(*_args: object, **kwargs: object) -> None:
        assert kwargs == {
            "source_type": SourceKind.document,
            "library": "mzk",
            "document_id": document_id,
            "page_id": None,
            "url": None,
        }
        return None

    class _Data:
        async def insert(self, **kwargs: object) -> None:
            inserted.update(kwargs)

    monkeypatch.setattr(source_service, "get_source", fake_get_source)
    client = SimpleNamespace(
        collections=SimpleNamespace(get=lambda _name: SimpleNamespace(data=_Data()))
    )

    source, created = await source_service.create_source(
        client,
        SourceKind.document,
        library="mzk",
        document_id=document_id,
    )

    expected_url = f"https://www.digitalniknihovna.cz/mzk/uuid/uuid:{document_id}"
    assert created is True
    assert source.uri == expected_url
    assert inserted == {
        "uuid": source.source_id,
        "properties": {
            "source_type": "document",
            "uri": expected_url,
            "library": "mzk",
            "document": document_id,
            "page": None,
        },
    }


@pytest.mark.asyncio
async def test_create_source_reuses_existing_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _source(SourceKind.image)

    async def fake_get_source(*_args: object, **_kwargs: object) -> SourceResponseBase:
        return existing

    monkeypatch.setattr(source_service, "get_source", fake_get_source)
    source, created = await source_service.create_source(
        SimpleNamespace(),
        SourceKind.image,
        url=existing.url,
    )

    assert source == existing
    assert created is False


@pytest.mark.asyncio
async def test_create_source_batch_uses_one_lookup_and_preserves_input_order() -> None:
    existing_document_id = uuid.uuid4()
    new_document_id = uuid.uuid4()
    existing_source_id = uuid.uuid4()
    existing_object = SimpleNamespace(
        uuid=existing_source_id,
        properties={
            "source_type": "document",
            "uri": "https://old.example.test/document",
            "library": "mzk",
            "document": existing_document_id,
            "page": None,
        },
        references={},
    )
    lookup_calls: list[dict[str, object]] = []
    inserted: list[dict[str, object]] = []

    class _Query:
        async def fetch_objects(self, **kwargs: object) -> SimpleNamespace:
            lookup_calls.append(kwargs)
            return SimpleNamespace(objects=[existing_object])

    class _Batch:
        async def __aenter__(self) -> "_Batch":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def add_object(self, **kwargs: object) -> None:
            inserted.append(kwargs)

    batch = _Batch()
    collection = SimpleNamespace(
        query=_Query(),
        batch=SimpleNamespace(stream=lambda: batch, failed_objects=[]),
    )
    client = SimpleNamespace(
        collections=SimpleNamespace(use=lambda _name: collection)
    )

    result = await source_service.create_source_batch(
        client,  # pyright: ignore[reportArgumentType] - lightweight client double.
        [
            SourceCreateSpec(
                source_type=SourceKind.document,
                library="mzk",
                document_id=new_document_id,
            ),
            SourceCreateSpec(
                source_type=SourceKind.document,
                library="mzk",
                document_id=existing_document_id,
            ),
            SourceCreateSpec(
                source_type=SourceKind.document,
                library="mzk",
                document_id=new_document_id,
            ),
        ],
    )

    assert len(lookup_calls) == 1
    assert lookup_calls[0]["limit"] == 2
    assert len(inserted) == 1
    assert inserted[0]["properties"] == {
        "source_type": "document",
        "uri": (
            "https://www.digitalniknihovna.cz/mzk/uuid/"
            f"uuid:{new_document_id}"
        ),
        "library": "mzk",
        "document": new_document_id,
        "page": None,
    }
    assert [item.source_id for item in result] == [
        inserted[0]["uuid"],
        existing_source_id,
        inserted[0]["uuid"],
    ]


@pytest.mark.asyncio
async def test_create_source_batch_skips_weaviate_for_empty_input() -> None:
    result = await source_service.create_source_batch(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        [],
    )

    assert result == []


@pytest.mark.asyncio
@pytest.mark.parametrize("include_document", [False, True])
async def test_resolve_source_filter_accepts_both_page_paths(
    monkeypatch: pytest.MonkeyPatch,
    include_document: bool,
) -> None:
    page_source = _source(SourceKind.page)
    page_id = uuid.uuid4()
    document_id = uuid.uuid4()

    async def fake_get_source(
        _client: object,
        _source_id: uuid.UUID | None = None,
        **kwargs: object,
    ) -> SourceResponseBase:
        assert kwargs == {
            "source_type": SourceKind.page,
            "library": "mzk",
            "document_id": document_id if include_document else None,
            "page_id": page_id,
        }
        return page_source

    monkeypatch.setattr(source_resolution_service, "get_source", fake_get_source)
    path = f"mzk/{document_id}/{page_id}" if include_document else f"mzk/{page_id}"

    resolved = await source_resolution_service.resolve_source_filter(
        object(),
        source_id=None,
        page=path,
        document=None,
        image=None,
    )

    assert resolved == page_source.source_id


@pytest.mark.asyncio
async def test_resolve_source_filter_rejects_conflicting_selectors() -> None:
    with pytest.raises(source_service.SourceResolutionError) as exc_info:
        await source_resolution_service.resolve_source_filter(
            object(),
            source_id=uuid.uuid4(),
            page=f"mzk/{uuid.uuid4()}",
            document=None,
            image=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_source_filter"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("descriptor", "source_type", "kwargs"),
    [
        (
            SourceDescriptorRequest(
                page=PageCreateRequest(
                    library="mzk",
                    document_id=(document_id := uuid.uuid4()),
                    page_id=(page_id := uuid.uuid4()),
                )
            ),
            SourceKind.page,
            {
                "library": "mzk",
                "document_id": document_id,
                "page_id": page_id,
            },
        ),
        (
            SourceDescriptorRequest(
                document=DocumentCreateRequest(
                    library="mzk",
                    document_id=(document_id := uuid.uuid4()),
                )
            ),
            SourceKind.document,
            {"library": "mzk", "document_id": document_id},
        ),
        (
            SourceDescriptorRequest(
                image=ImageCreateRequest(url=AnyUrl("https://example.test/image.jpg"))
            ),
            SourceKind.image,
            {"url": "https://example.test/image.jpg"},
        ),
    ],
)
async def test_resolve_source_reference_uses_generic_create(
    monkeypatch: pytest.MonkeyPatch,
    descriptor: SourceDescriptorRequest,
    source_type: SourceKind,
    kwargs: dict[str, object],
) -> None:
    expected = _source(source_type)

    async def fake_create_source(
        _client: object,
        actual_type: SourceKind,
        **actual_kwargs: object,
    ) -> tuple[SourceResponseBase, bool]:
        assert actual_type == source_type
        assert actual_kwargs == kwargs
        return expected, True

    monkeypatch.setattr(
        source_resolution_service,
        "create_source",
        fake_create_source,
    )

    resolved = await source_resolution_service.resolve_source_reference(
        object(),
        source_id=None,
        source=descriptor,
    )

    assert resolved == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", [False, True])
async def test_delete_source_returns_storage_result(deleted: bool) -> None:
    source_id = uuid.uuid4()
    deleted_ids: list[uuid.UUID] = []

    class _Data:
        async def delete_by_id(self, object_id: uuid.UUID) -> bool:
            deleted_ids.append(object_id)
            return deleted

    client = SimpleNamespace(
        collections=SimpleNamespace(get=lambda _name: SimpleNamespace(data=_Data()))
    )

    assert await source_service.delete_source(client, source_id) is deleted
    assert deleted_ids == [source_id]
