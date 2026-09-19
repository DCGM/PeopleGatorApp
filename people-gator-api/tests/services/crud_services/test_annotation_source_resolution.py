from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.entities import BoundingBox, FaceCreateRequest
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    ImageCreateRequest,
    SourceDescriptorRequest,
    SourceResponse,
)
from people_gator_api.services.crud_services import annotation_service


@pytest.mark.asyncio
async def test_create_face_resolves_source_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_source_id = uuid.uuid4()
    insert_references: list[dict[str, uuid.UUID]] = []
    insert_properties: list[dict[str, object]] = []

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
            del vector
            insert_properties.append(properties)
            insert_references.append(references)

    monkeypatch.setattr(
        annotation_service, "resolve_source_reference", fake_resolve_source_reference
    )

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    payload = FaceCreateRequest(
        identifier="archive-face-42",
        source=SourceDescriptorRequest(
            image=ImageCreateRequest(url="https://example.test/image.jpg")
        ),
        bounding_box=BoundingBox(x=1, y=2, width=3, height=4),
        keypoints=[],
        entity_id=uuid.uuid4(),
        confidence=0.9,
    )
    user_id = uuid.uuid4()
    created = await annotation_service.create_face(
        client=client,  # type: ignore[reportArgumentType]
        payload=payload,
        user_id=user_id,
    )

    assert created.source_id == resolved_source_id
    assert created.identifier == "archive-face-42"
    assert insert_properties[0]["identifier"] == "archive-face-42"
    assert insert_references[0]["source"] == resolved_source_id
