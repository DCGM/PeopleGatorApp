from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.entities import EntityCreateRequest
from people_gator_api.schemas.enums import EntityType
from people_gator_api.services.crud_services import entity_service


@pytest.mark.asyncio
async def test_create_entity_persists_aliases_as_text_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_properties: dict[str, object] = {}

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
            del references
            del vector
            captured_properties.update(properties)

    monkeypatch.setattr(entity_service, "new_uuid6", lambda: uuid.UUID(int=1))

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    payload = EntityCreateRequest(
        entity_type=EntityType.person,
        name="Zoltan Mihaly Nagy",
        aliases=["Zoltan Mihaly Nagy", "Zoltan Nagy"],
    )

    result = await entity_service.create_entity(
        client=client,  # pyright: ignore[reportArgumentType] - test double for Weaviate client.
        payload=payload,
        principal_id=uuid.UUID(int=2),
    )

    assert captured_properties["aliases"] == ["Zoltan Mihaly Nagy", "Zoltan Nagy"]
    assert result.aliases == ["Zoltan Mihaly Nagy", "Zoltan Nagy"]


@pytest.mark.asyncio
async def test_create_entity_defaults_missing_aliases_to_empty_text_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_properties: dict[str, object] = {}

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
            del references
            del vector
            captured_properties.update(properties)

    monkeypatch.setattr(entity_service, "new_uuid6", lambda: uuid.UUID(int=3))

    def get_collection(_name: str) -> SimpleNamespace:
        return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    payload = EntityCreateRequest(
        entity_type=EntityType.person, name="Zoltan Mihaly Nagy"
    )

    result = await entity_service.create_entity(
        client=client,  # pyright: ignore[reportArgumentType] - test double for Weaviate client.
        payload=payload,
        principal_id=uuid.UUID(int=4),
    )

    assert captured_properties["aliases"] == []
    assert result.aliases is None
