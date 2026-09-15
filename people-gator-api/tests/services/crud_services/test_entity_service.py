from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.entities import (
    EntityDeleteManyRequest,
    EntityPatchRequest,
)
from people_gator_api.schemas.enums import EntityType
from people_gator_api.services.crud_services import entity_service


@pytest.mark.asyncio
async def test_delete_entities_by_ids_counts_existing_deletions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    payload = EntityDeleteManyRequest(entity_ids=requested_ids)

    async def fake_delete_entity(
        _client: object,
        entity_id: uuid.UUID,
    ) -> bool:
        return entity_id != requested_ids[1]

    monkeypatch.setattr(entity_service, "delete_entity", fake_delete_entity)

    response = await entity_service.delete_entities(
        client=SimpleNamespace(),  # pyright: ignore[reportArgumentType] - tests use a lightweight client double.
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
        payload=EntityDeleteManyRequest(entity_type=EntityType.person),
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
        payload=EntityDeleteManyRequest(delete_all=True),
    )

    assert response.mode == "all"
    assert response.deleted_count == 1
    assert captured_filters == []


@pytest.mark.asyncio
async def test_patch_entity_returns_none_when_entity_does_not_exist() -> None:
    entity_id = uuid.uuid4()

    class _Query:
        async def fetch_object_by_id(
            self,
            _entity_id: uuid.UUID,
            **_kwargs: object,
        ) -> None:
            return None

    class _Collection:
        query = _Query()

    class _Collections:
        def get(self, _name: str) -> _Collection:
            return _Collection()

    client = SimpleNamespace(collections=_Collections())

    patched = await entity_service.patch_entity(
        client=client,  # pyright: ignore[reportArgumentType] - tests use a lightweight client double.
        entity_id=entity_id,
        principal_id=uuid.uuid4(),
        payload=EntityPatchRequest(name="Updated name"),
    )

    assert patched is None


@pytest.mark.asyncio
async def test_patch_entity_updates_allowed_fields_and_preserves_vectors() -> None:
    entity_id = uuid.uuid4()
    principal_id = uuid.uuid4()
    captured: dict[str, object] = {}
    stored_properties: dict[str, object] = {
        "entity_type": "person",
        "name": "Old name",
        "description": "Old description",
        "short_description": "Old short",
        "aliases": ["Old alias"],
        "wikidata_id": "Q1",
        "nlcr_authority_id": "A1",
    }

    references = {
        "principal": SimpleNamespace(objects=[SimpleNamespace(uuid=principal_id)])
    }
    vectors = {
        "name": [0.1, 0.2],
        "fulltext": [0.3, 0.4],
    }

    fetch_calls = 0

    class _Query:
        async def fetch_object_by_id(
            self,
            _entity_id: uuid.UUID,
            **_kwargs: object,
        ) -> SimpleNamespace:
            nonlocal fetch_calls
            fetch_calls += 1
            if fetch_calls == 1:
                return SimpleNamespace(
                    properties=dict(stored_properties),
                    references=references,
                    uuid=entity_id,
                    vector=vectors,
                )
            return SimpleNamespace(
                properties=dict(stored_properties),
                references=references,
                uuid=entity_id,
                vector=vectors,
            )

    class _Data:
        async def replace(
            self,
            *,
            uuid: uuid.UUID,
            properties: dict[str, object],
            references: dict[str, uuid.UUID],
            vector: dict[str, list[float]] | None,
        ) -> None:
            del uuid
            captured["properties"] = properties
            captured["references"] = references
            captured["vector"] = vector
            stored_properties.update(properties)

    collection = SimpleNamespace(query=_Query(), data=_Data())

    def _get_collection(_name: str) -> SimpleNamespace:
        return collection

    collections = SimpleNamespace(get=_get_collection)
    client = SimpleNamespace(collections=collections)
    patched = await entity_service.patch_entity(
        client=client,  # pyright: ignore[reportArgumentType] - tests use a lightweight client double.
        entity_id=entity_id,
        principal_id=principal_id,
        payload=EntityPatchRequest(
            name="New name",
            aliases=["Alias 1", "Alias 2"],
            description="New description",
            short_description="New short",
            wikidata_id="Q2",
            nlcr_authority_id="A2",
        ),
    )

    assert patched is not None
    assert patched.name == "New name"
    assert patched.aliases == ["Alias 1", "Alias 2"]
    assert patched.description == "New description"
    assert patched.short_description == "New short"
    assert patched.wikidata_id == "Q2"
    assert patched.nlcr_authority_id == "A2"
    assert captured["properties"] == {
        "entity_type": "person",
        "name": "New name",
        "description": "New description",
        "short_description": "New short",
        "aliases": ["Alias 1", "Alias 2"],
        "wikidata_id": "Q2",
        "nlcr_authority_id": "A2",
    }
    assert captured["references"] == {"principal": principal_id}
    assert captured["vector"] == {
        "name": [0.1, 0.2],
        "fulltext": [0.3, 0.4],
    }


def test_build_entity_filters_supports_exact_identity_filters() -> None:
    filters = entity_service._build_entity_filters(
        entity_type=EntityType.person,
        wikidata_id="Q42",
        nlcr_authority_id="A100",
        principal_id=uuid.uuid4(),
    )
    assert len(filters) == 4


@pytest.mark.asyncio
async def test_list_entities_returns_empty_when_source_has_no_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = uuid.uuid4()

    async def fake_entity_ids_for_source(
        _client: object,
        requested_source_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        assert requested_source_id == source_id
        return set()

    monkeypatch.setattr(
        entity_service,
        "entity_ids_for_source",
        fake_entity_ids_for_source,
    )

    result = await entity_service.list_entities(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType] - returns before database access.
        uuid.uuid4(),
        after_id=None,
        limit=50,
        source_id=source_id,
    )

    assert result.items == []
    assert result.total_count == 0
