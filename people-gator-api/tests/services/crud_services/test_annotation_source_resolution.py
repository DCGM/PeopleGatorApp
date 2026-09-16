from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.entities import (
    BoundingBox,
    DocumentMentionCreateRequest,
    FaceCreateRequest,
    PageMentionInlineCreateRequest,
    Polygon,
    PolygonPoint,
)
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import SourceDescriptorRequest, SourceResponse
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    ImageCreateRequest,
    PageCreateRequest,
)
from people_gator_api.services.crud_services import annotation_service


@pytest.mark.asyncio
async def test_create_face_resolves_source_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_source_id = uuid.uuid4()
    insert_references: list[dict[str, uuid.UUID]] = []

    async def fake_resolve_source_reference(
        client: object,
        *,
        source_id: uuid.UUID | None,
        source: SourceDescriptorRequest | None,
    ) -> SourceResponse:
        del client
        assert source_id is None
        assert source is not None
        return SourceResponse(
            source_id=resolved_source_id,
            source_type=SourceKind.image,
            uri=str(source.image.url) if source.image is not None else "",
            metadata=None,
        )

    class _Data:
        async def insert(
            self,
            *,
            uuid: uuid.UUID,
            properties: dict[str, object],
            references: dict[str, uuid.UUID],
            vector: dict[str, list[float]] | None,
        ) -> None:
            del uuid
            del properties
            del vector
            insert_references.append(references)

    monkeypatch.setattr(
        annotation_service, "resolve_source_reference", fake_resolve_source_reference
    )

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    payload = FaceCreateRequest(
        source=SourceDescriptorRequest(
            image=ImageCreateRequest(url="https://example.test/image.jpg")
        ),
        bounding_box=BoundingBox(x=1, y=2, width=3, height=4),
        keypoints=[],
        entity_id=uuid.uuid4(),
        confidence=0.9,
    )
    principal_id = uuid.uuid4()
    created = await annotation_service.create_face(
        client=client,  # type: ignore[reportArgumentType]
        payload=payload,
        principal_id=principal_id,
    )

    assert created.source_id == resolved_source_id
    assert insert_references[0]["source"] == resolved_source_id


@pytest.mark.asyncio
async def test_create_document_mention_resolves_nested_page_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_source_id = uuid.uuid4()
    child_source_id = uuid.uuid4()
    create_many_payloads: list[object] = []

    async def fake_resolve_source_reference(
        client: object,
        *,
        source_id: uuid.UUID | None,
        source: SourceDescriptorRequest | None,
    ) -> SourceResponse:
        del client
        del source_id
        assert source is not None
        if source.document is not None:
            return SourceResponse(
                source_id=parent_source_id,
                source_type=SourceKind.document,
                uri="https://www.digitalniknihovna.cz/mzk/uuid/uuid:"
                + str(source.document.document_id),
                metadata=None,
            )
        return SourceResponse(
            source_id=child_source_id,
            source_type=SourceKind.page,
            uri="https://www.digitalniknihovna.cz/mzk/view/uuid:"
            + str(source.page.document_id if source.page else "")
            + "?page=uuid:"
            + str(source.page.page_id if source.page else ""),
            metadata=None,
        )

    class _Data:
        async def insert(self, **_kwargs: object) -> None:
            pass

    async def fake_create_many_page_mentions(
        client: object,
        payloads: list[object],
        principal_id: uuid.UUID,
    ) -> list[object]:
        del client
        del principal_id
        create_many_payloads.extend(payloads)
        return []

    monkeypatch.setattr(
        annotation_service, "resolve_source_reference", fake_resolve_source_reference
    )
    monkeypatch.setattr(
        annotation_service,
        "create_many_page_mentions",
        fake_create_many_page_mentions,
    )

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    payload = DocumentMentionCreateRequest(
        name="John Doe",
        information="info",
        aliases=["JD"],
        source=SourceDescriptorRequest(
            document=DocumentCreateRequest(
                library="mzk",
                document_id=uuid.uuid4(),
            )
        ),
        entity_id=uuid.uuid4(),
        page_mentions=[
            PageMentionInlineCreateRequest(
                name="John Doe",
                information="line mention",
                aliases=["JD"],
                polygons=[
                    Polygon(
                        points=[
                            PolygonPoint(x=0, y=0),
                            PolygonPoint(x=1, y=0),
                            PolygonPoint(x=0, y=1),
                        ]
                    )
                ],
                source=SourceDescriptorRequest(
                    page=PageCreateRequest(
                        library="mzk",
                        document_id=uuid.uuid4(),
                        page_id=uuid.uuid4(),
                    )
                ),
            )
        ],
    )
    principal_id = uuid.uuid4()
    created = await annotation_service.create_document_mention(
        client=client,  # type: ignore[reportArgumentType]
        payload=payload,
        principal_id=principal_id,
    )

    assert created.source_id == parent_source_id
    assert len(create_many_payloads) == 1
    page_payload = create_many_payloads[0]
    assert getattr(page_payload, "source_id") == child_source_id


@pytest.mark.asyncio
async def test_patch_document_mention_replaces_only_entity_reference() -> None:
    mention_id = uuid.uuid4()
    principal_id = uuid.uuid4()
    source_id = uuid.uuid4()
    old_entity_id = uuid.uuid4()
    new_entity_id = uuid.uuid4()
    fetch_count = 0
    replaced: dict[str, object] = {}

    def reference(object_id: uuid.UUID) -> SimpleNamespace:
        return SimpleNamespace(objects=[SimpleNamespace(uuid=object_id)])

    class _Query:
        async def fetch_object_by_id(
            self, _object_id: uuid.UUID, **_kwargs: object
        ) -> SimpleNamespace:
            nonlocal fetch_count
            fetch_count += 1
            return SimpleNamespace(
                uuid=mention_id,
                properties={"name": "Name", "information": "Info", "aliases": []},
                references={
                    "principal": reference(principal_id),
                    "source": reference(source_id),
                    "entity": reference(old_entity_id),
                },
            )

    class _Data:
        async def reference_replace(self, **kwargs: object) -> None:
            replaced.update(kwargs)

    collection = SimpleNamespace(query=_Query(), data=_Data())
    client = SimpleNamespace(
        collections=SimpleNamespace(get=lambda _name: collection)
    )

    updated = await annotation_service.patch_document_mention_entity(
        client,  # pyright: ignore[reportArgumentType] - lightweight client double.
        principal_id,
        mention_id,
        new_entity_id,
    )

    assert updated is not None
    assert updated.entity_id == new_entity_id
    assert fetch_count == 1
    assert replaced == {
        "from_uuid": mention_id,
        "from_property": "entity",
        "to": new_entity_id,
    }
