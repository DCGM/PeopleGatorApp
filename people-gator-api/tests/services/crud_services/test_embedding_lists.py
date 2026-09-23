from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from people_gator_api.schemas.entities import (
    BoundingBox,
    EntityCreateRequest,
    EntityEmbeddingInput,
    EntityEmbeddingUpdateRequest,
    FaceCreateRequest,
    FaceEmbeddingUpdateRequest,
    ModelEmbedding,
)
from people_gator_api.services.crud_services import entity_service
from people_gator_api.weaviate_schema import model_vector_name


class _Data:
    def __init__(self) -> None:
        self.objects: list[dict[str, object]] = []

    async def insert(self, **kwargs: object) -> None:
        self.objects.append(kwargs)


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


def _entity_client(*, data: _Data | None = None, batch: _Batch | None = None) -> object:
    collection = SimpleNamespace(
        data=data,
        batch=_BatchStream(batch) if batch is not None else None,
    )
    return SimpleNamespace(
        collections=SimpleNamespace(
            get=lambda _name: collection,
            use=lambda _name: collection,
        )
    )


def _entity_embeddings() -> list[EntityEmbeddingInput]:
    return [
        EntityEmbeddingInput(
            field="name",
            model_identifier="text/model-a",
            vector=[0.1, 0.2],
        ),
        EntityEmbeddingInput(
            field="description",
            model_identifier="text/model-b",
            vector=[0.3, 0.4, 0.5],
        ),
    ]


@pytest.mark.asyncio
async def test_create_entity_inserts_all_embeddings_together() -> None:
    data = _Data()
    payload = EntityCreateRequest(name="Ada Lovelace", embeddings=_entity_embeddings())

    await entity_service.create_entity(
        _entity_client(data=data),  # pyright: ignore[reportArgumentType]
        payload,
        uuid.uuid4(),
    )

    assert data.objects[0]["vector"] == {
        model_vector_name("name", "text/model-a"): [0.1, 0.2],
        model_vector_name("description", "text/model-b"): [0.3, 0.4, 0.5],
    }


@pytest.mark.asyncio
async def test_update_entity_embeddings_groups_vectors_by_entity() -> None:
    batch = _Batch()
    entity_ids = [uuid.uuid4(), uuid.uuid4()]

    updated = await entity_service.update_entity_embeddings_batch(
        _entity_client(batch=batch),  # pyright: ignore[reportArgumentType]
        [
            EntityEmbeddingUpdateRequest(
                entity_id=entity_ids[0], embeddings=_entity_embeddings()
            ),
            EntityEmbeddingUpdateRequest(
                entity_id=entity_ids[1],
                embeddings=[
                    EntityEmbeddingInput(
                        field="short_description",
                        model_identifier="text/model-a",
                        vector=[0.6, 0.7],
                    )
                ],
            ),
        ],
    )

    assert updated == 3
    assert batch.objects == [
        {
            "uuid": entity_ids[0],
            "vector": {
                model_vector_name("name", "text/model-a"): [0.1, 0.2],
                model_vector_name("description", "text/model-b"): [0.3, 0.4, 0.5],
            },
        },
        {
            "uuid": entity_ids[1],
            "vector": {
                model_vector_name("short_description", "text/model-a"): [0.6, 0.7]
            },
        },
    ]


def test_duplicate_entity_field_and_model_is_rejected() -> None:
    duplicate = EntityEmbeddingInput(
        field="name", model_identifier="same-model", vector=[0.1]
    )

    with pytest.raises(ValidationError, match="field/model embedding pair"):
        EntityCreateRequest(embeddings=[duplicate, duplicate])

    with pytest.raises(ValidationError, match="field/model embedding pair"):
        EntityEmbeddingUpdateRequest(
            entity_id=uuid.uuid4(), embeddings=[duplicate, duplicate]
        )


def test_duplicate_face_model_is_rejected() -> None:
    duplicate = ModelEmbedding(model_identifier="same-model", vector=[0.1])

    with pytest.raises(ValidationError, match="embedding model must be unique"):
        FaceCreateRequest(
            source_id=uuid.uuid4(),
            bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
            keypoints=[],
            embeddings=[duplicate, duplicate],
            confidence=1,
        )

    with pytest.raises(ValidationError, match="embedding model must be unique"):
        FaceEmbeddingUpdateRequest(
            detection_id=uuid.uuid4(), embeddings=[duplicate, duplicate]
        )
