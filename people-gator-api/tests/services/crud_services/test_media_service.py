from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from pydantic import AnyUrl

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentSourceMetadata,
    PageCreateRequest,
    PageSourceMetadata,
    SourceResponse,
)
from people_gator_api.services.crud_services import media_service
from people_gator_api.services.weaviate_service.db_schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
)


def _reference(object_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(objects=[SimpleNamespace(uuid=object_id)])


def test_parse_page_source_exposes_typed_archive_identity() -> None:
    page_source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    page_id = uuid.uuid4()
    source = SourceResponse(
        source_id=page_source_id,
        source_type=SourceKind.page,
        uri="https://library.example/scan",
        metadata=PageSourceMetadata(
            library="mzk",
            document=document_id,
            page=page_id,
            kramerius_url=AnyUrl("https://library.example/scan"),
        ),
    )

    page = media_service.parse_page_source(source)

    assert page.page_source_id == page_source_id
    assert page.library == "mzk"
    assert page.document_id == document_id
    assert page.page_id == page_id


def test_parse_image_source_accepts_arbitrary_image_source() -> None:
    image_id = uuid.uuid4()
    image = media_service.parse_image_source(
        SourceResponse(
            source_id=image_id,
            source_type=SourceKind.image,
            uri="https://cdn.example.test/path/portrait.jpeg?size=original",
            metadata=None,
        )
    )

    assert image.image_id == image_id
    assert str(image.url) == "https://cdn.example.test/path/portrait.jpeg?size=original"


def test_parse_document_source_exposes_typed_archive_identity() -> None:
    source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source = SourceResponse(
        source_id=source_id,
        source_type=SourceKind.document,
        uri="https://library.example/document",
        metadata=DocumentSourceMetadata(
            library="mzk",
            document=document_id,
        ),
    )

    document = media_service.parse_document_source(source)

    assert document.document_source_id == source_id
    assert document.library == "mzk"
    assert document.document_id == document_id


@pytest.mark.asyncio
async def test_create_document_derives_canonical_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid.uuid4()
    expected_uri = f"https://www.digitalniknihovna.cz/mzk/uuid/uuid:{document_id}"

    async def fake_create_source(
        _client: object,
        source_type: SourceKind,
        **kwargs: object,
    ) -> tuple[SourceResponse, bool]:
        assert source_type == SourceKind.document
        assert kwargs == {"library": "mzk", "document_id": document_id}
        metadata = DocumentSourceMetadata(library="mzk", document=document_id)
        return (
            SourceResponse(
                source_id=uuid.uuid4(),
                source_type=SourceKind.document,
                uri=expected_uri,
                metadata=metadata,
            ),
            True,
        )

    monkeypatch.setattr(media_service, "create_source", fake_create_source)

    document, created = await media_service.create_document(
        object(),  # pyright: ignore[reportArgumentType] - database is mocked above.
        DocumentCreateRequest(library="mzk", document_id=document_id),
    )

    assert created is True
    assert str(document.url) == expected_uri


@pytest.mark.asyncio
async def test_get_document_by_path_returns_typed_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source = SourceResponse(
        source_id=document_source_id,
        source_type=SourceKind.document,
        uri="https://library.example/document/1",
        metadata=DocumentSourceMetadata(
            library="mzk",
            document=document_id,
        ),
    )

    async def fake_get_source(
        _client: object,
        _source_id: uuid.UUID | None = None,
        **kwargs: object,
    ) -> SourceResponse:
        assert kwargs == {
            "source_type": SourceKind.document,
            "library": "mzk",
            "document_id": document_id,
        }
        return source

    monkeypatch.setattr(media_service, "get_source", fake_get_source)

    document = await media_service.get_document_by_path(
        object(),  # pyright: ignore[reportArgumentType] - database is mocked above.
        "mzk",
        document_id,
    )

    assert document is not None
    assert document.document_source_id == document_source_id
    assert document.document_id == document_id


@pytest.mark.asyncio
async def test_create_page_reuses_archive_identity_when_url_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    page_id = uuid.uuid4()
    existing = SourceResponse(
        source_id=page_source_id,
        source_type=SourceKind.page,
        uri="https://old-library.example/scan",
        metadata=PageSourceMetadata(
            library="mzk",
            document=document_id,
            page=page_id,
            kramerius_url=AnyUrl("https://old-library.example/scan"),
        ),
    )

    async def fake_create_source(
        _client: object,
        source_type: SourceKind,
        **kwargs: object,
    ) -> tuple[SourceResponse, bool]:
        assert source_type == SourceKind.page
        assert kwargs == {
            "library": "mzk",
            "document_id": document_id,
            "page_id": page_id,
        }
        return existing, False

    monkeypatch.setattr(media_service, "create_source", fake_create_source)

    page, created = await media_service.create_page(
        object(),  # pyright: ignore[reportArgumentType] - database is mocked above.
        PageCreateRequest(
            library="mzk",
            document_id=document_id,
            page_id=page_id,
        ),
    )

    assert created is False
    assert page.page_source_id == page_source_id


@pytest.mark.asyncio
@pytest.mark.parametrize("include_document", [False, True])
async def test_get_page_by_path_supports_both_canonical_forms(
    monkeypatch: pytest.MonkeyPatch,
    include_document: bool,
) -> None:
    page_source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    page_id = uuid.uuid4()
    source = SourceResponse(
        source_id=page_source_id,
        source_type=SourceKind.page,
        uri="https://library.example/scan",
        metadata=PageSourceMetadata(
            library="mzk",
            document=document_id,
            page=page_id,
            kramerius_url=AnyUrl("https://library.example/scan"),
        ),
    )

    async def fake_get_source(
        _client: object,
        _source_id: uuid.UUID | None = None,
        **kwargs: object,
    ) -> SourceResponse:
        assert kwargs == {
            "source_type": SourceKind.page,
            "library": "mzk",
            "document_id": (
                source.metadata.document if include_document else None
            ),
            "page_id": page_id,
        }
        return source

    monkeypatch.setattr(media_service, "get_source", fake_get_source)

    page = await media_service.get_page_by_path(
        object(),  # pyright: ignore[reportArgumentType] - database is mocked above.
        "mzk",
        page_id,
        document_id=document_id if include_document else None,
    )

    assert page is not None
    assert page.page_source_id == page_source_id


@pytest.mark.asyncio
async def test_entity_ids_for_source_combines_direct_links_and_face_detections() -> (
    None
):
    source_id = uuid.uuid4()
    face_entity_id = uuid.uuid4()
    mentioned_entity_id = uuid.uuid4()

    face = SimpleNamespace(
        uuid=uuid.uuid4(),
        properties={},
        references={"entity": _reference(face_entity_id)},
    )
    mentioned_entity = SimpleNamespace(
        uuid=mentioned_entity_id,
        properties={},
        references={},
    )

    class _Query:
        def __init__(self, collection_name: str) -> None:
            super().__init__()
            self.collection_name = collection_name

        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            objects = {
                FACE_COLLECTION: [face],
                ENTITY_COLLECTION: [mentioned_entity],
            }.get(self.collection_name, [])
            return SimpleNamespace(objects=objects)

    def get_collection(collection_name: str) -> SimpleNamespace:
        return SimpleNamespace(query=_Query(collection_name))

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    result = await media_service.entity_ids_for_source(
        client,  # pyright: ignore[reportArgumentType] - lightweight Weaviate client double.
        source_id,
    )

    assert result == {
        face_entity_id,
        mentioned_entity_id,
    }
