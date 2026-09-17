from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.entities import (
    BoundingBox,
    FaceListResponse,
    FaceResponse,
)
from people_gator_api.services.crud_services import annotation_service


@pytest.mark.asyncio
async def test_list_faces_returns_paginated_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                objects=[
                    SimpleNamespace(properties={}, references={}, uuid=uuid.uuid4())
                ]
            )

    class _Aggregate:
        async def over_all(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(total_count=42)

    class _Collection:
        query = _Query()
        aggregate = _Aggregate()

    def _get_collection(name: str) -> _Collection:
        del name
        return _Collection()

    client = SimpleNamespace(collections=SimpleNamespace(get=_get_collection))

    def _face_response(*_args: object, **_kwargs: object) -> FaceResponse:
        return FaceResponse(
            detection_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
            keypoints=[],
            user_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            confidence=0.5,
        )

    monkeypatch.setattr(annotation_service, "parse_face", _face_response)

    result = await annotation_service.list_faces(
        client,  # type: ignore[reportArgumentType]
        uuid.uuid4(),
        None,
        None,
        None,
        10,
    )

    assert isinstance(result, FaceListResponse)
    assert result.limit == 10
    assert result.total_count == 42
    assert isinstance(result.items[0], FaceResponse)
