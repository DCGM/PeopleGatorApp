from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.entities import EntityDeleteManyRequest
from people_gator_api.services.crud_services import entity_service


@pytest.mark.asyncio
async def test_delete_entities_by_ids_counts_existing_deletions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    payload = EntityDeleteManyRequest(entity_ids=requested_ids)

    async def fake_delete_entity(
        _client: object,
        _principal_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> bool:
        return entity_id != requested_ids[1]

    monkeypatch.setattr(entity_service, "delete_entity", fake_delete_entity)

    response = await entity_service.delete_entities(
        client=SimpleNamespace(),  # pyright: ignore[reportArgumentType] - tests use a lightweight client double.
        principal_id=uuid.uuid4(),
        payload=payload,
    )

    assert response.mode == "entity_ids"
    assert response.deleted_count == 2


@pytest.mark.asyncio
async def test_delete_entities_by_type_deletes_every_matching_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_filters: list[object] = []

    async def fake_delete_entities_by_filters(
        _client: object,
        _principal_id: uuid.UUID,
        filters: list[object],
        _batch_limit: int = 200,
    ) -> int:
        captured_filters.extend(filters)
        return 2

    monkeypatch.setattr(
        entity_service,
        "_delete_entities_by_filters",
        fake_delete_entities_by_filters,
    )

    response = await entity_service.delete_entities(
        client=SimpleNamespace(),  # pyright: ignore[reportArgumentType] - tests use a lightweight client double.
        principal_id=uuid.uuid4(),
        payload=EntityDeleteManyRequest(entity_type="person"),
    )

    assert response.mode == "entity_type"
    assert response.deleted_count == 2
    assert len(captured_filters) == 1


@pytest.mark.asyncio
async def test_delete_entities_all_deletes_all_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_filters: list[object] = []

    async def fake_delete_entities_by_filters(
        _client: object,
        _principal_id: uuid.UUID,
        filters: list[object],
        _batch_limit: int = 200,
    ) -> int:
        captured_filters.extend(filters)
        return 1

    monkeypatch.setattr(
        entity_service,
        "_delete_entities_by_filters",
        fake_delete_entities_by_filters,
    )

    response = await entity_service.delete_entities(
        client=SimpleNamespace(),  # pyright: ignore[reportArgumentType] - tests use a lightweight client double.
        principal_id=uuid.uuid4(),
        payload=EntityDeleteManyRequest(delete_all=True),
    )

    assert response.mode == "all"
    assert response.deleted_count == 1
    assert captured_filters == []
