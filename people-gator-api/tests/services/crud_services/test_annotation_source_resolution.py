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
    upsert_references: list[dict[str, uuid.UUID]] = []

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

    async def fake_upsert(
        _client: object,
        _collection_name: str,
        _object_uuid: uuid.UUID,
        *,
        properties: dict[str, object],
        references: dict[str, uuid.UUID] | None = None,
        vector: dict[str, list[float]] | None = None,
    ) -> None:
        del properties
        del vector
        assert references is not None
        upsert_references.append(references)

    monkeypatch.setattr(
        annotation_service, "resolve_source_reference", fake_resolve_source_reference
    )
    monkeypatch.setattr(annotation_service, "upsert", fake_upsert)

    payload = FaceCreateRequest(
        source=SourceDescriptorRequest(uri="https://www.wikidata.org/entity/Q42"),
        bounding_box=BoundingBox(x=1, y=2, width=3, height=4),
        keypoints=[],
        entity_id=uuid.uuid4(),
        confidence=0.9,
    )
    principal_id = uuid.uuid4()
    created = await annotation_service.create_face(
        client=SimpleNamespace(),  # type: ignore[reportArgumentType]
        payload=payload,
        principal_id=principal_id,
    )

    assert created.source_id == resolved_source_id
    assert upsert_references[0]["source"] == resolved_source_id


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

    async def fake_upsert(
        _client: object,
        _collection_name: str,
        _object_uuid: uuid.UUID,
        *,
        properties: dict[str, object],
        references: dict[str, uuid.UUID] | None = None,
        vector: dict[str, list[float]] | None = None,
    ) -> None:
        del properties
        del references
        del vector

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
    monkeypatch.setattr(annotation_service, "upsert", fake_upsert)
    monkeypatch.setattr(
        annotation_service,
        "create_many_page_mentions",
        fake_create_many_page_mentions,
    )

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
                source=SourceDescriptorRequest(
                    uri="https://kramerius.example/page/1"
                ),
            )
        ],
    )
    principal_id = uuid.uuid4()
    created = await annotation_service.create_document_mention(
        client=SimpleNamespace(),  # type: ignore[reportArgumentType]
        payload=payload,
        principal_id=principal_id,
    )

    assert created.source_id == parent_source_id
    assert len(create_many_payloads) == 1
    page_payload = create_many_payloads[0]
    assert getattr(page_payload, "source_id") == child_source_id
