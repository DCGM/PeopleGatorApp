from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionResponse,
)
from people_gator_api.services.crud_services import text_mention_service
from people_gator_api.weaviate_schema import (
    TEXT_MENTION_COLLECTION,
)


def _references(
    *,
    entity_id: uuid.UUID,
    source_id: uuid.UUID,
) -> dict[str, SimpleNamespace]:
    return {
        "entity": SimpleNamespace(objects=[SimpleNamespace(uuid=entity_id)]),
        "source": SimpleNamespace(objects=[SimpleNamespace(uuid=source_id)]),
    }


@pytest.mark.asyncio
async def test_create_text_mention_stores_properties_and_references() -> None:
    entity_id = uuid.uuid4()
    source_id = uuid.uuid4()
    inserted: dict[str, object] = {}

    class _Data:
        async def insert(self, **kwargs: object) -> None:
            inserted.update(kwargs)

    class _Collections:
        def get(self, name: str) -> SimpleNamespace:
            assert name == TEXT_MENTION_COLLECTION
            return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=_Collections())
    payload = TextMentionCreateRequest(
        name="Ada Lovelace",
        context="The notes were written by Ada Lovelace.",
        entity_id=entity_id,
        source_id=source_id,
    )

    result = await text_mention_service.create_text_mention(
        client,  # pyright: ignore[reportArgumentType]
        payload,
    )

    assert result.name == payload.name
    assert result.context == payload.context
    assert result.entity_id == entity_id
    assert result.source_id == source_id
    assert inserted == {
        "uuid": result.mention_id,
        "properties": {"name": payload.name, "context": payload.context},
        "references": {"entity": entity_id, "source": source_id},
    }


@pytest.mark.asyncio
async def test_create_text_mention_batch_streams_all_items_in_order() -> None:
    first = TextMentionCreateRequest(
        name="Ada",
        context=None,
        entity_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
    )
    second = TextMentionCreateRequest(
        name="Charles Babbage",
        context="with Charles Babbage",
        entity_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
    )
    added: list[dict[str, object]] = []

    class _Batch:
        async def __aenter__(self) -> "_Batch":
            return self

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _traceback: object,
        ) -> None:
            return None

        async def add_object(self, **kwargs: object) -> None:
            added.append(kwargs)

    class _BatchProvider:
        def stream(self) -> _Batch:
            return _Batch()

    class _Collections:
        def use(self, name: str) -> SimpleNamespace:
            assert name == TEXT_MENTION_COLLECTION
            return SimpleNamespace(batch=_BatchProvider())

    async def payloads():
        yield first
        yield second

    result = await text_mention_service.create_text_mention_batch(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        payloads(),
    )

    assert [item.name for item in result] == [first.name, second.name]
    assert [item.context for item in result] == [first.context, second.context]
    assert len(added) == 2
    assert added[0] == {
        "uuid": result[0].mention_id,
        "properties": {"name": first.name, "context": first.context},
        "references": {"entity": first.entity_id, "source": first.source_id},
    }
    assert added[1] == {
        "uuid": result[1].mention_id,
        "properties": {"name": second.name, "context": second.context},
        "references": {"entity": second.entity_id, "source": second.source_id},
    }


@pytest.mark.asyncio
async def test_get_text_mention_returns_record_with_references() -> None:
    mention_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    source_id = uuid.uuid4()

    class _Query:
        async def fetch_object_by_id(
            self,
            requested_id: uuid.UUID,
            **_kwargs: object,
        ) -> SimpleNamespace:
            assert requested_id == mention_id
            return SimpleNamespace(
                uuid=mention_id,
                properties={"name": "Ada", "context": "Context"},
                references=_references(
                    entity_id=entity_id,
                    source_id=source_id,
                ),
            )

    class _Collections:
        def get(self, name: str) -> SimpleNamespace:
            assert name == TEXT_MENTION_COLLECTION
            return SimpleNamespace(query=_Query())

    result = await text_mention_service.get_text_mention(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        mention_id,
    )

    assert result is not None
    assert result.mention_id == mention_id
    assert result.name == "Ada"
    assert result.context == "Context"
    assert result.entity_id == entity_id
    assert result.source_id == source_id


@pytest.mark.asyncio
async def test_get_text_mention_returns_none_when_missing() -> None:
    class _Query:
        async def fetch_object_by_id(
            self,
            _requested_id: uuid.UUID,
            **_kwargs: object,
        ) -> None:
            return None

    class _Collections:
        def get(self, _name: str) -> SimpleNamespace:
            return SimpleNamespace(query=_Query())

    result = await text_mention_service.get_text_mention(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        uuid.uuid4(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_text_mentions_filters_by_source_and_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mention_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    source_id = uuid.uuid4()
    captured: dict[str, object] = {}

    async def fake_fetch(
        _client: object,
        collection_name: str,
        **kwargs: object,
    ) -> tuple[list[SimpleNamespace], int]:
        captured["collection_name"] = collection_name
        captured.update(kwargs)
        return (
            [
                SimpleNamespace(
                    uuid=mention_id,
                    properties={"name": "Ada", "context": None},
                    references=_references(
                        entity_id=entity_id,
                        source_id=source_id,
                    ),
                )
            ],
            1,
        )

    monkeypatch.setattr(
        text_mention_service,
        "fetch_collection_page_with_total_count",
        fake_fetch,
    )

    result = await text_mention_service.list_text_mentions(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        source_id=source_id,
        entity_id=entity_id,
        after_id=None,
        limit=50,
    )

    assert captured["collection_name"] == TEXT_MENTION_COLLECTION
    assert captured["filters"] is not None
    assert result.total_count == 1
    assert result.items[0].mention_id == mention_id
    assert result.items[0].entity_id == entity_id
    assert result.items[0].source_id == source_id


@pytest.mark.asyncio
async def test_reassign_text_mention_replaces_entity_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mention_id = uuid.uuid4()
    previous_entity_id = uuid.uuid4()
    new_entity_id = uuid.uuid4()
    source_id = uuid.uuid4()
    replaced: dict[str, object] = {}

    async def fake_get(
        _client: object,
        requested_id: uuid.UUID,
    ) -> TextMentionResponse:
        assert requested_id == mention_id
        return TextMentionResponse(
            mention_id=mention_id,
            entity_id=previous_entity_id,
            source_id=source_id,
            name="Ada",
            context=None,
        )

    class _Data:
        async def reference_replace(self, **kwargs: object) -> None:
            replaced.update(kwargs)

    class _Collections:
        def get(self, _name: str) -> SimpleNamespace:
            return SimpleNamespace(data=_Data())

    client = SimpleNamespace(collections=_Collections())
    monkeypatch.setattr(text_mention_service, "get_text_mention", fake_get)

    result = await text_mention_service.reassign_text_mention_entity(
        client,  # pyright: ignore[reportArgumentType]
        mention_id,
        new_entity_id,
    )

    assert result is not None
    assert result.entity_id == new_entity_id
    assert replaced == {
        "from_uuid": mention_id,
        "from_property": "entity",
        "to": new_entity_id,
    }


@pytest.mark.asyncio
async def test_reassign_missing_text_mention_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(_client: object, _mention_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(text_mention_service, "get_text_mention", fake_get)

    result = await text_mention_service.reassign_text_mention_entity(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        uuid.uuid4(),
        uuid.uuid4(),
    )

    assert result is None
