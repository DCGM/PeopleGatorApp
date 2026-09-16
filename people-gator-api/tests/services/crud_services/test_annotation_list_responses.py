from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.entities import (
    BoundingBox,
    DocumentMentionListResponse,
    DocumentMentionResponse,
    FaceListResponse,
    FaceResponse,
    PageMentionListResponse,
    PageMentionResponse,
)
from people_gator_api.services.crud_services import annotation_service


@pytest.mark.asyncio
async def test_list_page_mentions_returns_paginated_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[SimpleNamespace(properties={}, references={}, uuid=uuid.uuid4())])

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

    def _page_mention_response(*_args: object, **_kwargs: object) -> PageMentionResponse:
        return PageMentionResponse(
            page_mention_id=uuid.uuid4(),
            name="Example",
            information="",
            aliases=[],
            polygons=[],
            document_mention_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            principal_id=uuid.uuid4(),
        )

    monkeypatch.setattr(
        annotation_service,
        "parse_page_mention",
        _page_mention_response,
    )

    result = await annotation_service.list_page_mentions(
        client,  # type: ignore[reportArgumentType] - test double for WeaviateAsyncClient
        uuid.uuid4(),
        None,
        None,
        None,
        10,
    )

    assert isinstance(result, PageMentionListResponse)
    assert result.limit == 10
    assert result.total_count == 42
    assert isinstance(result.items[0], PageMentionResponse)


@pytest.mark.asyncio
async def test_list_document_mentions_returns_paginated_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[SimpleNamespace(properties={}, references={}, uuid=uuid.uuid4())])

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

    def _document_mention_response(*_args: object, **_kwargs: object) -> DocumentMentionResponse:
        return DocumentMentionResponse(
            document_mention_id=uuid.uuid4(),
            name="Example",
            information="",
            aliases=[],
            principal_id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
        )

    monkeypatch.setattr(
        annotation_service,
        "parse_document_mention",
        _document_mention_response,
    )

    result = await annotation_service.list_document_mentions(
        client,  # type: ignore[reportArgumentType] - test double for WeaviateAsyncClient
        uuid.uuid4(),
        None,
        None,
        None,
        10,
    )

    assert isinstance(result, DocumentMentionListResponse)
    assert result.limit == 10
    assert result.total_count == 42
    assert isinstance(result.items[0], DocumentMentionResponse)


@pytest.mark.asyncio
async def test_list_faces_returns_paginated_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[SimpleNamespace(properties={}, references={}, uuid=uuid.uuid4())])

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
            principal_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            confidence=0.5,
        )

    monkeypatch.setattr(
        annotation_service,
        "parse_face",
        _face_response,
    )

    result = await annotation_service.list_faces(
        client,  # type: ignore[reportArgumentType] - test double for WeaviateAsyncClient
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
