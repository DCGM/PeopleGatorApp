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
from people_gator_api.services.crud_services import annotation_service


@pytest.mark.asyncio
async def test_create_face_resolves_source_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_source_id = uuid.uuid4()
    insert_references: list[dict[str, uuid.UUID]] = []

    async def fake_resolve_source_reference(
        client: object,
        principal_id: uuid.UUID,
        *,
        source_id: uuid.UUID | None,
        source: SourceDescriptorRequest | None,
    ) -> SourceResponse:
        del client
        del principal_id
        assert source_id is None
        assert source is not None
        return SourceResponse(
            source_id=resolved_source_id,
            source_type=SourceKind.wikidata,
            uri=source.uri or "",
            metadata=source.metadata,
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
        source=SourceDescriptorRequest(uri="https://www.wikidata.org/entity/Q42"),
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
        principal_id: uuid.UUID,
        *,
        source_id: uuid.UUID | None,
        source: SourceDescriptorRequest | None,
    ) -> SourceResponse:
        del client
        del principal_id
        del source_id
        assert source is not None
        if source.uri == "https://kramerius.example/document/1":
            return SourceResponse(
                source_id=parent_source_id,
                source_type=SourceKind.document,
                uri=source.uri,
                metadata=source.metadata,
            )
        return SourceResponse(
            source_id=child_source_id,
            source_type=SourceKind.page,
            uri=source.uri or "",
            metadata=source.metadata,
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
        source=SourceDescriptorRequest(uri="https://kramerius.example/document/1"),
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
                source=SourceDescriptorRequest(uri="https://kramerius.example/page/1"),
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
