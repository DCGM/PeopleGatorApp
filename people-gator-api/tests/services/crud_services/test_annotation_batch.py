from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest

from people_gator_api.routes.v1.annotations import router
from people_gator_api.schemas.entities import (
    BoundingBox,
    FaceCreateRequest,
    FaceEmbeddingUpdateRequest,
)
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import SourceResponse
from people_gator_api.services.crud_services import annotation_service
from people_gator_api.services.weaviate_service.db_schema import DEFAULT_FACE_VECTOR


async def _payloads[T](items: list[T]) -> AsyncGenerator[T, None]:
    for item in items:
        yield item


class _Batch:
    def __init__(self) -> None:
        self.objects: list[dict[str, object]] = []

    async def add_object(self, **kwargs: object) -> uuid.UUID:
        self.objects.append(kwargs)
        return kwargs["uuid"]  # type: ignore[return-value]


class _BatchStream:
    def __init__(self, batch: _Batch) -> None:
        self.batch = batch

    def stream(self) -> _BatchStream:
        return self

    async def __aenter__(self) -> _Batch:
        return self.batch

    async def __aexit__(self, *_args: object) -> None:
        return None


def _client(batch: _Batch) -> SimpleNamespace:
    collection = SimpleNamespace(batch=_BatchStream(batch))
    return SimpleNamespace(collections=SimpleNamespace(use=lambda _name: collection))


async def _resolve_source(
    _client: object,
    *,
    source_id: uuid.UUID | None,
    source: object | None,
) -> SourceResponse:
    del source
    assert source_id is not None
    return SourceResponse(
        source_id=source_id,
        source_type=SourceKind.image,
        uri=f"https://example.test/{source_id}",
    )


def test_only_face_batch_annotation_route_is_registered() -> None:
    paths = {route.path for route in router.routes}

    assert "/faces:batch" in paths
    assert "/faces:embeddings" in paths
    assert not any("mention" in path for path in paths)


@pytest.mark.asyncio
async def test_create_face_batch_resolves_sources_and_preserves_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = _Batch()
    user_id = uuid.uuid4()
    source_ids = [uuid.uuid4(), uuid.uuid4()]
    entity_ids = [uuid.uuid4(), None]
    payloads = [
        FaceCreateRequest(
            source_id=source_id,
            bounding_box=BoundingBox(x=index, y=2, width=3, height=4),
            keypoints=[],
            embedding=[0.1, 0.2] if index == 0 else None,
            entity_id=entity_ids[index],
            confidence=0.9,
        )
        for index, source_id in enumerate(source_ids)
    ]
    monkeypatch.setattr(annotation_service, "resolve_source_reference", _resolve_source)

    faces = await annotation_service.create_face_batch(
        _client(batch),  # pyright: ignore[reportArgumentType]
        _payloads(payloads),
        user_id,
    )

    assert [face.source_id for face in faces] == source_ids
    assert [face.entity_id for face in faces] == entity_ids
    assert len(batch.objects) == 2
    assert batch.objects[0]["references"] == {
        "entity": entity_ids[0],
        "source": source_ids[0],
        "user": user_id,
    }
    assert batch.objects[0]["vector"] == {DEFAULT_FACE_VECTOR: [0.1, 0.2]}
    assert batch.objects[1]["references"] == {
        "source": source_ids[1],
        "user": user_id,
    }
    assert batch.objects[1]["vector"] is None


@pytest.mark.asyncio
async def test_update_face_embedding_batch_uses_named_vectors() -> None:
    batch = _Batch()
    client = _client(batch)
    detection_ids = [uuid.uuid4(), uuid.uuid4()]

    updated = await annotation_service.update_face_embedding_batch(
        client,  # pyright: ignore[reportArgumentType]
        [
            FaceEmbeddingUpdateRequest(
                detection_id=detection_id,
                embedding=[float(index), 0.5],
            )
            for index, detection_id in enumerate(detection_ids)
        ],
    )

    assert updated == 2
    assert batch.objects == [
        {
            "uuid": detection_ids[0],
            "vector": {DEFAULT_FACE_VECTOR: [0.0, 0.5]},
        },
        {
            "uuid": detection_ids[1],
            "vector": {DEFAULT_FACE_VECTOR: [1.0, 0.5]},
        },
    ]
