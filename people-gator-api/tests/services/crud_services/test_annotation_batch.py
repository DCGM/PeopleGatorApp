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
    FaceResponse,
    ModelEmbedding,
)
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import SourceResponseBase
from people_gator_api.services.crud_services import annotation_service
from people_gator_api.weaviate_schema import DEFAULT_FACE_VECTOR


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


class _ReferenceData:
    def __init__(self) -> None:
        self.replacements: list[dict[str, object]] = []

    async def reference_replace(self, **kwargs: object) -> None:
        self.replacements.append(kwargs)


def _client(batch: _Batch) -> SimpleNamespace:
    collection = SimpleNamespace(batch=_BatchStream(batch))
    return SimpleNamespace(collections=SimpleNamespace(use=lambda _name: collection))


async def _resolve_source(
    _client: object,
    *,
    source_id: uuid.UUID | None,
    source: object | None,
) -> SourceResponseBase:
    del source
    assert source_id is not None
    return SourceResponseBase(
        source_id=source_id,
        source_type=SourceKind.image,
        url=f"https://example.test/{source_id}",
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
            embeddings=(
                [
                    ModelEmbedding(
                        model_identifier="vit_small_patch8_gap_112.cosface_ms1mv3",
                        vector=[0.1, 0.2],
                    )
                ]
                if index == 0
                else []
            ),
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
async def test_patch_face_entity_accepts_null_to_remove_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detection_id = uuid.uuid4()
    current = FaceResponse(
        detection_id=detection_id,
        source_id=uuid.uuid4(),
        bounding_box=BoundingBox(x=1, y=2, width=3, height=4),
        keypoints=[],
        user_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        confidence=0.9,
    )
    data = _ReferenceData()
    collection = SimpleNamespace(data=data)
    client = SimpleNamespace(
        collections=SimpleNamespace(get=lambda _name: collection),
    )

    async def fetch_face(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(properties={}, references={}, uuid=detection_id)

    monkeypatch.setattr(annotation_service, "fetch_collection_object", fetch_face)
    monkeypatch.setattr(annotation_service, "parse_face", lambda *_args: current)

    updated = await annotation_service.patch_face_entity(
        client,  # pyright: ignore[reportArgumentType]
        current.user_id,
        detection_id,
        None,
    )

    assert updated is not None
    assert updated.entity_id is None
    assert data.replacements == [
        {
            "from_uuid": detection_id,
            "from_property": "entity",
            "to": [],
        }
    ]


@pytest.mark.asyncio
async def test_update_face_embedding_batch_uses_named_vectors() -> None:
    batch = _Batch()
    client = _client(batch)
    detection_ids = [uuid.uuid4(), uuid.uuid4()]

    updated = await annotation_service.update_face_embedding_batch(
        client,  # pyright: ignore[reportArgumentType]
        [
            FaceEmbeddingUpdateRequest(
                detection_id=detection_ids[0],
                embeddings=[
                    ModelEmbedding(
                        model_identifier="vit_small_patch8_gap_112.cosface_ms1mv3",
                        vector=[0.0, 0.5],
                    ),
                    ModelEmbedding(
                        model_identifier="second-face-model",
                        vector=[0.2, 0.8],
                    ),
                ],
            ),
            FaceEmbeddingUpdateRequest(
                detection_id=detection_ids[1],
                embeddings=[
                    ModelEmbedding(
                        model_identifier="vit_small_patch8_gap_112.cosface_ms1mv3",
                        vector=[1.0, 0.5],
                    )
                ],
            ),
        ],
    )

    assert updated == 3
    assert batch.objects == [
        {
            "uuid": detection_ids[0],
            "vector": {
                DEFAULT_FACE_VECTOR: [0.0, 0.5],
                "face_second_face_model": [0.2, 0.8],
            },
        },
        {
            "uuid": detection_ids[1],
            "vector": {DEFAULT_FACE_VECTOR: [1.0, 0.5]},
        },
    ]
